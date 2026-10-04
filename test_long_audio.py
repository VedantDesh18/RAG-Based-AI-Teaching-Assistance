import os
import subprocess
import time
import tracemalloc
from faster_whisper import WhisperModel

# We will concatenate the first 4 audios to get roughly 40-50 minutes.
files = [
    "audios/01-how to install nodejs.mp3",
    "audios/02-variables in javascript.mp3",
    "audios/03-keywords var vs let vs const.mp3",
    "audios/04-datatypes in javascript.mp3"
]

out_file = "scratch_media/long_audio.mp3"

if not os.path.exists(out_file):
    with open("scratch_media/concat.txt", "w") as f:
        for audio in files:
            f.write(f"file '../{audio}'\n")
            
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "scratch_media/concat.txt", "-c", "copy", out_file], check=True)

# Calculate boundaries using ffprobe
boundaries = [0]
total_duration = 0
for audio in files:
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio], capture_output=True, text=True)
    duration = float(res.stdout.strip())
    total_duration += duration
    boundaries.append(total_duration)

print(f"Total duration: {total_duration/60:.2f} minutes")
print(f"Boundaries (seconds): {boundaries}")

print("Running small model on long audio...")
tracemalloc.start()
t0 = time.time()
model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe(out_file, language="hi", task="translate", vad_filter=True, condition_on_previous_text=False)

# Collect segments
results = []
for seg in segments:
    results.append({"start": seg.start, "end": seg.end, "text": seg.text})
    if len(results) % 50 == 0:
        print(f"Processed up to {seg.start:.2f}s...")

t1 = time.time()
peak_mem = tracemalloc.get_traced_memory()[1] / 1024 / 1024
tracemalloc.stop()

print(f"Time taken: {t1-t0:.2f}s (RTF: {(t1-t0)/total_duration:.2f})")
print(f"Peak RAM diff: {peak_mem:.2f} MB")

# Extrapolate to 4 hours
hours = 4
ratio = (hours * 3600) / total_duration
print(f"Extrapolated RAM for 4 hours: {peak_mem * ratio:.2f} MB")

print("Checking boundaries...")
for i, b in enumerate(boundaries[:-1]):
    print(f"Boundary {i}: ~{b:.2f}s")
    for seg in results:
        if seg["start"] >= b and seg["start"] < b + 30:
            print(f"  Start text near boundary: {seg['text']}")
            break

