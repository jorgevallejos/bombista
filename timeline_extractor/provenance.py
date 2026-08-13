"""
Provenance block builder — B1.

The shipped Tragedia timeline was ~17 s wrong for weeks because nothing
recorded *which audio file* it was derived from (see
docs/bombista-product-backlog.md, B1). `build_provenance` is called once
per `extract` run and records the audio's identity (path + sha256),
duration, the model/device/language used, when the run happened, and the
tool's version.

Today this dict feeds only the QA report header (`report.py`) — the
surface a human actually reads. B2 will drop this same dict, unmodified,
into the rich JSON output and a song JSON's `_bombista` block; this module
does not write either of those yet, it only builds and exports the dict
for B2 to reuse. Do not duplicate this logic there.

Never in the native timeline v2 envelope (`serializer.py::to_dict`) — the
translator parses that envelope strictly (docs/timeline-v2-contract.md).
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from .aligner import DEVICE_STRING

_HASH_CHUNK_SIZE = 1024 * 1024  # 1 MiB — audio files run to tens of MB


def _sha256_file(path: Path) -> str:
    """Hex sha256 digest of *path*'s bytes, streamed in chunks so a large
    audio file is never read whole into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _duration_sec(path: Path) -> float | None:
    """Container duration in seconds via PyAV (already a transitive
    faster-whisper dependency — no new dependency, no ffprobe shell-out).
    Returns None if it cannot be determined for any reason: provenance
    must never crash an extract run over a duration read failure."""
    try:
        import av

        with av.open(str(path)) as container:
            duration = container.duration  # microseconds, or None
            if duration is None:
                return None
            return round(duration / 1_000_000, 3)
    except Exception:
        return None


TOOL_NAME = "timeline-extractor"


def _tool_version() -> str:
    """`<tool name> <version>` — the name is part of the string because this
    block is embedded in other people's files (a song JSON's `_bombista`
    block), where a bare version number says nothing. The version comes from
    the installed distribution, falling back to parsing `pyproject.toml`
    directly (via `tomllib`) when the package isn't installed as one, so it
    is never hardcoded in two places."""
    try:
        from importlib.metadata import version

        return f"{TOOL_NAME} {version(TOOL_NAME)}"
    except Exception:
        try:
            import tomllib

            pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            return f"{TOOL_NAME} {data['project']['version']}"
        except Exception:
            return f"{TOOL_NAME} unknown"


def build_provenance(
    audio_path: Path,
    *,
    model_size: str,
    lang: str,
    now: datetime | None = None,
) -> dict:
    """Build the provenance block for one `extract` run.

    `now` is injectable so tests are deterministic; when omitted, it
    defaults to `datetime.now().astimezone()` (local time, ISO 8601 with
    UTC offset). sha256 is computed even when `--words` skips
    transcription — that's exactly when it earns its keep, since nothing
    else in that run touches the audio file.
    """
    now = now or datetime.now().astimezone()
    return {
        "audio": str(audio_path),
        "sha256": _sha256_file(audio_path),
        "durationSec": _duration_sec(audio_path),
        "model": f"faster-whisper:{model_size}",
        "device": DEVICE_STRING,
        "lang": lang,
        "extractedAt": now.isoformat(timespec="seconds"),
        "toolVersion": _tool_version(),
    }
