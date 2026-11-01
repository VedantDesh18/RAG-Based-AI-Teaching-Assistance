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
