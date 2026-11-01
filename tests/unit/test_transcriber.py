from videoqa.core import transcriber


def test_pyav_compatibility_wrapper_drops_removed_metadata_errors(monkeypatch):
    """PyAV 19 must not reject faster-whisper's legacy keyword argument."""
    received: dict[str, object] = {}

    def fake_open(*args, **kwargs):
        received["args"] = args
        received["kwargs"] = kwargs
        return "opened"

    monkeypatch.setattr(transcriber, "_orig_av_open", fake_open)

    assert transcriber._compat_av_open("recording.mp4", mode="r", metadata_errors="ignore") == "opened"
    assert received == {"args": ("recording.mp4",), "kwargs": {"mode": "r"}}


def test_bounded_env_int_uses_a_safe_value(monkeypatch):
    monkeypatch.setenv("WHISPER_BEAM_SIZE", "invalid")
    assert transcriber._bounded_env_int("WHISPER_BEAM_SIZE", 1, 1, 5) == 1

    monkeypatch.setenv("WHISPER_BEAM_SIZE", "99")
    assert transcriber._bounded_env_int("WHISPER_BEAM_SIZE", 1, 1, 5) == 5


def test_transcribe_audio_explicit_hindi(monkeypatch):
    """Explicit Hindi transcription passes language='hi' and task='transcribe'."""
    call_kwargs = {}

    class FakeSegment:
        start = 0.0
        end = 5.0
        text = "यह एक हिंदी व्याख्यान है।"

    class FakeInfo:
        language = "hi"

    class FakeModel:
        def transcribe(self, audio_path, **kwargs):
            call_kwargs.update(kwargs)
            return iter([FakeSegment()]), FakeInfo()

    monkeypatch.setattr(transcriber, "_get_whisper_model", lambda *args, **kwargs: FakeModel())

    result = transcriber.transcribe_audio("fake_audio.mp3", "vid-123", language="hi")

    assert call_kwargs.get("language") == "hi"
    assert call_kwargs.get("task") == "transcribe"
    assert result["language"] == "hi"
    assert len(result["segments"]) == 1
    assert result["segments"][0]["text_original"] == "यह एक हिंदी व्याख्यान है।"
    assert result["segments"][0]["language"] == "hi"


def test_transcribe_audio_auto_language_preserved(monkeypatch):
    """When no language is specified, language kwarg is omitted to preserve auto-detection."""
    call_kwargs = {}

    class FakeSegment:
        start = 1.0
        end = 4.0
        text = "English speech detected automatically."

    class FakeInfo:
        language = "en"

    class FakeModel:
        def transcribe(self, audio_path, **kwargs):
            call_kwargs.update(kwargs)
            return iter([FakeSegment()]), FakeInfo()

    monkeypatch.setattr(transcriber, "_get_whisper_model", lambda *args, **kwargs: FakeModel())

    result = transcriber.transcribe_audio("fake_audio.mp3", "vid-456", language=None)

    assert "language" not in call_kwargs
    assert call_kwargs.get("task") == "transcribe"
    assert result["language"] == "en"
    assert result["segments"][0]["text_original"] == "English speech detected automatically."


def test_transcribe_audio_preserves_timestamps_and_offsets(monkeypatch):
    """Segment offsets and timing math are preserved correctly."""
    class FakeSegment:
        start = 2.5
        end = 7.5
        text = "Timing test"

    class FakeInfo:
        language = "en"

    class FakeModel:
        def transcribe(self, audio_path, **kwargs):
            return iter([FakeSegment()]), FakeInfo()

    monkeypatch.setattr(transcriber, "_get_whisper_model", lambda *args, **kwargs: FakeModel())

    result = transcriber.transcribe_audio("fake_audio.mp3", "vid-789", offset=100.0)

    assert result["segments"][0]["start_seconds"] == 102.5
    assert result["segments"][0]["end_seconds"] == 107.5

