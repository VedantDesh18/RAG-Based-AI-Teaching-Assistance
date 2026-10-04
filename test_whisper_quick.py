import time
import tracemalloc
from faster_whisper import WhisperModel
import subprocess
import os

# Create 2 sec audio
if not os.path.exists("scratch_media/test_short.mp3"):
    subprocess.run(["ffmpeg", "-y", "-i", "audios/01-how to install nodejs.mp3", "-t", "2", "scratch_media/test_short.mp3"], check=True)

for m in ["small"]:
    print(f"--- Model: {m} ---")
    tracemalloc.start()
    t0 = time.time()
    try:
        model = WhisperModel(m, device="cpu", compute_type="int8")
        t_load = time.time() - t0
        segments, info = model.transcribe("scratch_media/test_short.mp3")
        res = list(segments)
        t_transcribe = time.time() - t0 - t_load
        peak_mem = tracemalloc.get_traced_memory()[1] / 1024 / 1024
        print(f"Load time: {t_load:.2f}s, Transcribe time (2s audio): {t_transcribe:.2f}s")
        print(f"Peak RAM: {peak_mem:.2f} MB")
    except Exception as e:
        print(f"Error: {e}")
    tracemalloc.stop()
