import whisper
import json
import os

def transcribe_directory(input_dir: str = "audios", output_dir: str = "jsons") -> None:
    model = whisper.load_model("large-v2")
    os.makedirs(output_dir, exist_ok=True)
    audios = os.listdir(input_dir)
    for audio in audios:
        if "_" in audio:
            number = audio.split("_")[0]
            title = audio.split("_")[1][:-4]
            result = model.transcribe(
                audio=os.path.join(input_dir, audio),
                language="hi",
                task="translate",
                word_timestamps=False
            )
            chunks = []
            for segment in result["segments"]:
                chunks.append({"number": number, "title": title, "start": segment["start"], "end": segment["end"], "text": segment["text"]})
            chunks_with_metadata = {"chunks": chunks, "text": result["text"]}
            with open(os.path.join(output_dir, f"{audio}.json"), "w") as f:
                json.dump(chunks_with_metadata, f)
