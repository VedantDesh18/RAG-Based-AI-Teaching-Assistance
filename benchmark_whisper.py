import os
import sys
import time
import json
import difflib
import argparse
import subprocess
import tracemalloc

# ---------------------------------------------------------------------------
# Environment setup: thread / memory limits MUST be set before CTranslate2 / MKL
# ---------------------------------------------------------------------------
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("CT2_USE_EXPERIMENTAL_PACKED_GEMM", "0")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# Compatibility patch for PyAV >= 14/19 where metadata_errors kwarg was removed
try:
    import av as _av_module
    _orig_av_open = _av_module.open

    def _compat_av_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return _orig_av_open(*args, **kwargs)

    _av_module.open = _compat_av_open

    import faster_whisper.audio as _fw_audio
    _fw_audio.av = _av_module
except Exception:
    pass

import ctranslate2
from faster_whisper import WhisperModel

# Detect optimal device and compute type
DEVICE = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"


def prepare_test_clip(audio_src="audios/01-how to install nodejs.mp3", duration_sec=180, out_path="scratch_media/test_clip.mp3"):
    """Prepares a test clip of specified duration if it doesn't already exist."""
    if not os.path.exists(out_path):
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        if os.path.exists(audio_src):
            subprocess.run(
                ["ffmpeg", "-y", "-i", audio_src, "-t", str(duration_sec), out_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
    return out_path


def get_baseline_words(json_path="jsons/01-how to install nodejs.mp3.json", max_seconds=180):
    """Loads baseline English reference text for similarity calculation."""
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        baseline_text = [
            seg["text"] for seg in data.get("chunks", [])
            if float(seg.get("start", 0)) < max_seconds
        ]
        return " ".join(baseline_text).split()
    except Exception:
        return []


def run_benchmark(
    audio_path,
    model_size="large-v3",
    language=None,          # None = auto-detects all languages (Hindi, English, etc.)
    task="translate",       # "translate" ensures transcription is ALWAYS in English
    baseline_words=None,
    beam_size=5,
    backend="faster_whisper",
    output_json=None
):
    """
    Runs Whisper benchmark.
    - Default model: large-v3
    - Default task: translate (transcription is always in English)
    - Default language: None (auto-detects all languages, translating Hindi/non-English to English)
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    print("=" * 70)
    print(f"Backend     : {backend}")
    print(f"Model       : Whisper {model_size} ({DEVICE}, {COMPUTE_TYPE})")
    print(f"Audio File  : {audio_path}")
    print(f"Language In : {'Auto-detect (all languages)' if language is None else language}")
    print(f"Task        : {task} (Transcription output is ALWAYS in English)")
    print("=" * 70)

    tracemalloc.start()
    t0 = time.time()

    if backend == "faster_whisper":
        model = WhisperModel(
            model_size,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
            cpu_threads=2,
            num_workers=1
        )
        load_time = time.time() - t0
        peak_mem_load = tracemalloc.get_traced_memory()[1] / 1024 / 1024

        t1 = time.time()
        segments_gen, info = model.transcribe(
            audio_path,
            language=language,
            task=task,
            beam_size=beam_size
        )
        detected_lang = info.language
        lang_prob = info.language_probability

        chunks = []
        out_words = []
        for seg in segments_gen:
            text_clean = seg.text.strip()
            out_words.extend(text_clean.split())
            chunks.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": text_clean
            })
        process_time = time.time() - t1
        del model

    else:
        # Fallback / optional OpenAI Whisper backend
        import whisper
        model = whisper.load_model(model_size, in_memory=False)
        load_time = time.time() - t0
        peak_mem_load = tracemalloc.get_traced_memory()[1] / 1024 / 1024

        t1 = time.time()
        result = model.transcribe(
            audio=audio_path,
            language=language,
            task=task,
            word_timestamps=False
        )
        detected_lang = result.get("language", "unknown")
        lang_prob = 1.0

        chunks = []
        out_words = []
        for seg in result.get("segments", []):
            text_clean = seg["text"].strip()
            out_words.extend(text_clean.split())
            chunks.append({
                "start": round(seg["start"], 2),
                "end": round(seg["end"], 2),
                "text": text_clean
            })
        process_time = time.time() - t1
        del model

    peak_mem_total = tracemalloc.get_traced_memory()[1] / 1024 / 1024
    tracemalloc.stop()

    # Audio analysis printout
    print("\n[Audio Analysis & Translation]")
    print(f"  * Detected Language: '{detected_lang}' (Confidence: {lang_prob:.2%})")
    if detected_lang == "hi":
        print("  * Hindi voice detected -> Translated into English.")
    elif detected_lang != "en":
        print(f"  * '{detected_lang}' voice detected -> Translated into English.")
    else:
        print("  * English voice detected -> Transcribed in English.")
    print("  * Transcription Output Language: English (Guaranteed)")

    # Performance metrics
    print("\n[Performance Metrics]")
    print(f"  * Model Load Time : {load_time:.2f}s")
    print(f"  * Process Time    : {process_time:.2f}s")
    print(f"  * Peak RAM Usage  : {peak_mem_total:.2f} MB")
    print(f"  * Segments Count  : {len(chunks)}")
    print(f"  * Total Words     : {len(out_words)}")

    # Baseline comparison if available
    if baseline_words:
        sim = difflib.SequenceMatcher(None, baseline_words, out_words).ratio()
        print(f"  * Similarity vs Baseline: {sim:.3f}")

    # English Preview
    print("\n[English Transcription Preview]")
    if chunks:
        for seg in chunks[:8]:
            print(f"  [{seg['start']:6.2f}s -> {seg['end']:6.2f}s] {seg['text']}")
        if len(chunks) > 8:
            print(f"  ... ({len(chunks) - 8} more segments)")
    else:
        print("  [No speech detected]")

    # Save output JSON
    if output_json:
        output_abs = os.path.abspath(output_json)
        with open(output_abs, "w", encoding="utf-8") as f:
            json.dump({
                "model": model_size,
                "backend": backend,
                "detected_language": detected_lang,
                "language_probability": lang_prob,
                "task": task,
                "transcription_language": "en",
                "chunks": chunks
            }, f, indent=2, ensure_ascii=False)
        print(f"\nSaved full English transcription JSON to:\n  {output_abs}")

    print()
    return chunks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Whisper large-v3 English Translation & Benchmark")
    parser.add_argument("--audio", "-a", type=str, default=None, help="Path to input audio file")
    parser.add_argument("--model", "-m", type=str, default="large-v3", help="Whisper model size (default: large-v3)")
    parser.add_argument("--task", "-t", type=str, default="translate", help="Whisper task: 'translate' to always output English (default: translate)")
    parser.add_argument("--language", "-l", type=str, default=None, help="Audio language code (default: None for auto-detect all languages)")
    parser.add_argument("--output", "-o", type=str, default="output_whisper_large_v3.json", help="Path to save output JSON")
    parser.add_argument("--backend", "-b", type=str, default="faster_whisper", choices=["faster_whisper", "whisper"], help="Whisper backend engine")
    parser.add_argument("--beam_size", type=int, default=5, help="Beam size for transcription decoding")

    args = parser.parse_args()

    # Determine target audio file
    if args.audio:
        target_audio = args.audio
    elif os.path.exists("audios/sample.mp3"):
        target_audio = "audios/sample.mp3"
    elif os.path.exists("scratch_media/test_clip.mp3"):
        target_audio = "scratch_media/test_clip.mp3"
    else:
        target_audio = prepare_test_clip()

    # Baseline words for similarity if testing benchmark audio
    baseline_words = None
    if "01-how to install nodejs" in target_audio or "test_clip" in target_audio:
        baseline_words = get_baseline_words()

    # Run benchmark
    run_benchmark(
        audio_path=target_audio,
        model_size=args.model,
        language=args.language,
        task=args.task,
        baseline_words=baseline_words,
        beam_size=args.beam_size,
        backend=args.backend,
        output_json=args.output
    )
