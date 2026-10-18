"""Configured, portable media storage references and safe path resolution."""

from pathlib import Path

import videoqa.config as config_module


def _configured_root(key: str, default: str) -> Path:
    value = config_module.config.get("paths", {}).get(key, default)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def media_root() -> Path:
    return _configured_root("media", "data/media")


def legacy_media_root() -> Path:
    return _configured_root("legacy_media", "videos")


def allowed_media_roots() -> dict[str, Path]:
    """Map stable DB reference prefixes to their configured storage roots."""
    roots = {"media": media_root(), "legacy": legacy_media_root()}
    return {name: path for name, path in roots.items() if path}


def _within(path: Path, root: Path) -> bool:
    try:
        return path.is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def media_reference(path: str | Path, root_name: str = "media") -> str:
    """Return a portable root-tagged reference such as ``media/clip.mp4``."""
    roots = allowed_media_roots()
    root = roots.get(root_name)
    if root is None:
        raise ValueError(f"Unknown media storage root: {root_name}")
    resolved = Path(path).expanduser().resolve()
    if not _within(resolved, root):
        raise ValueError("Media file is outside its configured storage root")
    relative = resolved.relative_to(root)
    if not relative.parts or any(part in {".", ".."} for part in relative.parts):
        raise ValueError("Invalid media path")
    return f"{root_name}/{relative.as_posix()}"


def resolve_media_path(reference: str | Path) -> Path | None:
    """Resolve a stored media reference without allowing access outside roots.

    Root-tagged references are the canonical format. Absolute paths and older
    project-relative paths remain supported so existing databases keep working.
    """
    raw = Path(reference).expanduser()
    roots = allowed_media_roots()

    if raw.is_absolute():
        candidate = raw.resolve()
        return candidate if any(_within(candidate, root) for root in roots.values()) else None

    parts = raw.parts
    if len(parts) >= 2 and parts[0] in roots:
        root = roots[parts[0]]
        candidate = (root.joinpath(*parts[1:])).resolve()
        return candidate if _within(candidate, root) else None

    # Backward compatibility for the project's former CWD-relative references.
    candidate = (Path.cwd() / raw).resolve()
    if any(_within(candidate, root) for root in roots.values()):
        return candidate

    # Some early records stored only the filename relative to the media root.
    for root in roots.values():
        candidate = (root / raw).resolve()
        if _within(candidate, root):
            return candidate
    return None


def media_file_is_readable(path: Path) -> bool:
    try:
        if not path.is_file():
            return False
        with path.open("rb") as source:
            return bool(source.read(1))
    except OSError:
        return False
