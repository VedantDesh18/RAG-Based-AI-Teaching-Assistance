import os
import subprocess

def extract_audio(input_path: str, output_path: str) -> None:
    """
    Extracts audio from a video file and saves it as an MP3.
    """
    subprocess.run(["ffmpeg", "-y", "-i", input_path, output_path], check=True)

def process_videos_directory(input_dir: str = 'videos', output_dir: str = 'audios') -> None:
    """
    Processes all videos in the given directory.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    for file in os.listdir(input_dir):
        file_name = os.path.splitext(file)[0]
        input_path = os.path.join(input_dir, file)
        output_path = os.path.join(output_dir, f"{file_name}.mp3")
        extract_audio(input_path, output_path)

if __name__ == "__main__":
    process_videos_directory()
