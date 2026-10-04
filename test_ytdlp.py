import yt_dlp
import time
import os
import shutil

ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': 'scratch_media/%(id)s.%(ext)s',
    'noplaylist': True,
    'quiet': False,
    'extract_flat': False, # get full metadata
}

if not os.path.exists('scratch_media'):
    os.makedirs('scratch_media')

# Short video for test (3-5 min) - "What is forEach" or similar.
# Let's use a known youtube ID. e.g. a random 3 min youtube video. 
# We'll use "jS4aFq5-91M" (JavaScript Array forEach() - 3 min)
vid_url = 'https://www.youtube.com/watch?v=jS4aFq5-91M'

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    start_time = time.time()
    info = ydl.extract_info(vid_url, download=True)
    end_time = time.time()

print(f"Title: {info.get('title')}")
print(f"Duration: {info.get('duration')}s")
print(f"Time taken to download metadata and audio: {end_time - start_time:.2f}s")
