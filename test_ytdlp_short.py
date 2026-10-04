import yt_dlp
import time
import os

ydl_opts = {
    'format': 'bestaudio', # strictly audio
    'outtmpl': 'scratch_media/%(id)s.%(ext)s',
    'noplaylist': True,
    'quiet': False,
    'extract_flat': False,
    # Pass node as JS player client (yt-dlp auto-detects, but this enforces it implicitly if we want, or we just rely on auto)
}

if not os.path.exists('scratch_media'):
    os.makedirs('scratch_media')

vid_url = 'https://www.youtube.com/watch?v=BaW_sgmCZ8U' # 10 second timer video

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    start_time = time.time()
    info = ydl.extract_info(vid_url, download=True)
    end_time = time.time()

print(f"Title: {info.get('title')}")
print(f"Duration: {info.get('duration')}s")
print(f"Time taken to download metadata and audio: {end_time - start_time:.2f}s")
