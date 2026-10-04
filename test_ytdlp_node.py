import yt_dlp
import time
import os

ydl_opts = {
    'format': 'bestaudio', 
    'outtmpl': 'scratch_media/%(id)s.%(ext)s',
    'noplaylist': True,
    'quiet': False,
    'extract_flat': False,
    'js_runtimes': {'nodejs': {}}
}

if not os.path.exists('scratch_media'):
    os.makedirs('scratch_media')

vid_url = 'https://www.youtube.com/watch?v=jS4aFq5-91M'

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    start_time = time.time()
    info = ydl.extract_info(vid_url, download=True)
    end_time = time.time()

print(f"Title: {info.get('title')}")
print(f"Duration: {info.get('duration')}s")
print(f"Time taken to download metadata and audio: {end_time - start_time:.2f}s")
