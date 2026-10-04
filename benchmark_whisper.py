import time
import psutil
import os
import sys
import json
import difflib
from faster_whisper import WhisperModel
import subprocess

# 1. Prepare clip (3 minutes = 180 seconds)
if not os.path.exists("scratch_media/test_clip.mp3"):
    os.makedirs("scratch_media", exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-i", "audios/01-how to install nodejs.mp3", "-t", "180", "scratch_media/test_clip.mp3"], check=True)

# 2. Get baseline json for first 180s
with open("jsons/01-how to install nodejs.mp3.json", "r") as f:
    orig_data = json.load(f)

baseline_text = []
for seg in orig_data["chunks"]:
    if float(seg['start']) < 180:
        baseline_text.append(seg['text'])
baseline_words = " ".join(baseline_text).split()

import tracemalloc

def get_memory():
    return tracemalloc.get_traced_memory()[0] / 1024 / 1024

def run_benchmark(model_size, language, task):
    print(f"--- Model: {model_size}, Lang: {language}, Task: {task} ---")
    
    tracemalloc.start()
    
    t0 = time.time()
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    load_time = time.time() - t0
    peak_mem = tracemalloc.get_traced_memory()[1] / 1024 / 1024
    
    t1 = time.time()
    segments, info = model.transcribe("scratch_media/test_clip.mp3", language=language, task=task)
    
    out_words = []
    for seg in segments:
        out_words.extend(seg.text.split())
    
    process_time = time.time() - t1
    peak_mem_total = tracemalloc.get_traced_memory()[1] / 1024 / 1024
    tracemalloc.stop()
    
    # Calculate similarity
    sim = difflib.SequenceMatcher(None, baseline_words, out_words).ratio()
    
    print(f"Load Time: {load_time:.2f}s, Process Time: {process_time:.2f}s (RTF: {process_time/180:.2f})")
    print(f"Peak RAM diff: {peak_mem:.2f} MB")
    print(f"Word Similarity vs Baseline: {sim:.3f}")
    if out_words:
        print(f"Preview: {' '.join(out_words[:15])}...")
    else:
        print("Preview: [No output]")
    print()
    del model

print("= English Models =")
for m in ["small", "turbo", "distil-small.en"]:
    run_benchmark(m, "en", "transcribe")

print("= Hindi Translate Models =")
for m in ["turbo", "small", "medium", "large-v2"]:
    run_benchmark(m, "hi", "translate")

