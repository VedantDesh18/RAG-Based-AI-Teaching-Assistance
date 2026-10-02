# converts video to mp3
import os
import subprocess

files = os.listdir('videos')
for file in files:
    file_name = os.path.splitext(file)[0]
    subprocess.run(["ffmpeg", "-y", "-i", f"videos/{file}", f"audios/{file_name}.mp3"])

