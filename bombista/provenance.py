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
from typing import Sequence

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


TOOL_NAME = "bombista"


def tool_version() -> str:
    """`<tool name> <version>` — the name is part of the string because this
    block is embedded in other people's files (a song JSON's `_bombista`
    block), where a bare version number says nothing. The version comes from
    the installed distribution, falling back to parsing `pyproject.toml`
    directly (via `tomllib`) when the package isn't installed as one, so it
    is never hardcoded in two places.

    Public because `cli.py` answers `--version` with it. That is the point
    of the flag: the string a bug report quotes out of a song file and the
    string read off the terminal are then the same string, rather than two
    spellings of one fact that someone has to know how to reconcile. It also
    means `--version` inherits the fallback — a checkout that was never
    installed as a distribution still answers, instead of raising the
    RuntimeError `click.version_option(package_name=...)` would."""
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
        "toolVersion": tool_version(),
    }


WORDS_META_KEYS = ("extractedAt", "model", "device", "lang", "sha256")
"""What `asr-words.meta.json` carries out of a provenance block, beside
the absolute audio path. Everything a later run cannot re-establish about
the transcription that produced the stream."""

REUSED_KEYS = ("extractedAt", "model", "device", "lang")
"""What a `--words` run takes back from the sibling (B20 §11.10).

Exactly the four facts about *when and how the machine listened*, which a
run that skipped transcription did not establish. `sha256`, `durationSec`
and `audio` are NOT among them: that run did hash the file it was pointed
at, and those three are one coherent description of one file on disk —
which is the whole of what B1 exists to record. Overwriting a live
description with a recorded one would split it across two runs.
"""


def words_meta(provenance: dict, audio_path: Path, song_path: Path | None = None) -> dict:
    """The `asr-words.meta.json` sibling's content, from a run's provenance.

    The audio path is stored **absolute**, and this is the one place the
    two differ. `provenance["audio"]` is the path as `align` was given it,
    which is the honest record of the invocation but resolves only from
    the directory that run happened in — `staging/pimiento` holds
    `../../songs/audio/pimiento.m4a`. Copy the staging directory and the
    player has nothing (B20 §11.11). The sibling answers *where the take
    is*, so it says so in full.
    """
    meta = {key: provenance[key] for key in WORDS_META_KEYS if key in provenance}
    meta["audio"] = str(Path(audio_path).resolve())
    if song_path is not None:
        meta["song"] = str(Path(song_path).resolve())
    return meta


def provenance_for_reused_words(provenance: dict, meta: dict | None) -> dict:
    """A `--words` run's provenance: what this run established, plus what
    the run that actually transcribed recorded (B20 §11.10).

    `extractedAt` is a claim about **when the machine listened**, and on a
    `--words` run faster-whisper never runs — so stamping it fresh makes
    the report say the machine listened at the moment the report was
    written. §9.4 makes reusing the word stream *the* correction loop, so
    that is most runs, not an edge case.

    With no sibling (an older staging directory) the field is **omitted**
    and `wordsReused` says why. A wrong timestamp in an audit file is
    worse than an absent one, and absent is cheap. Never an mtime: it does
    not survive the directory being copied, which is the failure the
    sibling exists to avoid.
    """
    carried = dict(provenance)
    carried["wordsReused"] = True
    if meta is None:
        carried.pop("extractedAt", None)
        return carried
    for key in REUSED_KEYS:
        if key in meta:
            carried[key] = meta[key]
    return carried


def compute_lines_hash(lines: Sequence[str]) -> str:
    """`linesHash` — B4 (docs/bombista-product-backlog.md §1, §4).

    The timeline is matched to lyrics **by position**: insert or delete one
    line and every entry after it is silently wrong. This hashes the exact
    ordered line texts a timeline was built against (`pipeline.lyric_lines`'s
    output — the same `lines` list the aligner works from), so `promote` can
    detect that the target song's lyrics moved since extraction.

    Canonical form: the lines joined with `"\\n"`, UTF-8 encoded, sha256'd.
    Returned as `"sha256:<hex digest>"` (docs/bombista-product-backlog.md
    §3.6) — the prefix names the algorithm so the string is self-describing
    wherever it lands (rich JSON, `_bombista.linesHash`).
    """
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
