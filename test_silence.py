import os
import subprocess
import time
from faster_whisper import WhisperModel

# 1. Generate 60 seconds of silence
subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "60", "scratch_media/silence.mp3"], check=True)

# 2. Extract 5 seconds of speech from lecture
subprocess.run(["ffmpeg", "-y", "-i", "audios/01-how to install nodejs.mp3", "-t", "5", "scratch_media/speech.mp3"], check=True)

# 3. Concat silence + speech
with open("scratch_media/concat_silence.txt", "w") as f:
    f.write("file 'silence.mp3'\n")
    f.write("file 'speech.mp3'\n")
subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "scratch_media/concat_silence.txt", "-c", "copy", "scratch_media/silenced_speech.mp3"], check=True)

print("Running silence test VAD OFF...")
model = WhisperModel("small", device="cpu", compute_type="int8")

t0 = time.time()
segments, info = model.transcribe("scratch_media/silenced_speech.mp3", language="en", vad_filter=False)
res_off = list(segments)
t1 = time.time()

print("Segments VAD OFF:")
for s in res_off:
    print(f"[{s.start:.1f} - {s.end:.1f}]: {s.text}")

print("---")
print("Running silence test VAD ON...")
t0 = time.time()
segments, info = model.transcribe("scratch_media/silenced_speech.mp3", language="en", vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500))
res_on = list(segments)
t1 = time.time()

print("Segments VAD ON:")
for s in res_on:
    print(f"[{s.start:.1f} - {s.end:.1f}]: {s.text}")

