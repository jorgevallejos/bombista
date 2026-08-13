"""
Serializes a normalised timeline (lead-in + entries) to the timeline v2
interchange envelope consumed by the translator's timeline-import button.

Format:
    {
      "timelineVersion": 2,
      "leadIn": {"durationSec": 7.26, "source": "measured", "confidence": "low", "apply": false},
      "timeline": [{"start": 0.0, "end": 5.84}, ...]
    }

See docs/timeline-v2-contract.md for the full spec (frozen — do not modify
unilaterally). `entries` passed in here are already normalised to the start
cue (see `pipeline.normalize_to_lead_in`) — this module does not subtract
the lead-in itself, it only builds and validates the envelope around it.
"""
import json
from pathlib import Path
from typing import Sequence

from .models import TimelineEntry

TIMELINE_VERSION = 2

_ENVELOPE_KEYS = {"timelineVersion", "leadIn", "timeline"}
_LEAD_IN_KEYS = {"durationSec", "source", "confidence", "apply"}
_LEAD_IN_SOURCES = {"measured", "manual", "none"}
_LEAD_IN_CONFIDENCES = {"low", "high"}


def validate_timeline(entries: Sequence[TimelineEntry]) -> None:
    """Raises ValueError if the sequence violates the translator's invariants:
    every entry's start must be >= the previous entry's end (non-decreasing,
    non-overlapping), one entry per song item, in item order.
    """
    previous_end = float("-inf")
    for i, entry in enumerate(entries):
        if entry.start < previous_end:
            raise ValueError(
                f"timeline[{i}]: times must be monotonic (start={entry.start} < previous end={previous_end})"
            )
        previous_end = entry.end


def _lead_in_apply_default(song: dict) -> bool:
    """`leadIn.apply` defaults to True when the song is Video-mode
    (`media.type == "video"`), else False — including when `media` is
    absent entirely."""
    media = song.get("media")
    return isinstance(media, dict) and media.get("type") == "video"


def to_dict(lead_in: float, entries: Sequence[TimelineEntry], song: dict) -> dict:
    """Build the timeline v2 envelope from an already-normalised timeline.

    `entries` must already be relative to the start cue (see
    `pipeline.normalize_to_lead_in`) — entry 0 is expected to start at
    `0.0`. `song` supplies `media.type` for the `leadIn.apply` default.
    Raises ValueError if the resulting envelope fails `validate_v2_envelope`.
    """
    envelope = {
        "timelineVersion": TIMELINE_VERSION,
        "leadIn": {
            "durationSec": round(lead_in, 2),
            "source": "measured",
            "confidence": "low",
            "apply": _lead_in_apply_default(song),
        },
        "timeline": [{"start": e.start, "end": e.end} for e in entries],
    }
    validate_v2_envelope(envelope)
    return envelope


def write_timeline(
    lead_in: float, entries: Sequence[TimelineEntry], song: dict, path: Path
) -> None:
    """Write the timeline v2 interchange JSON to *path*."""
    data = to_dict(lead_in, entries, song)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def validate_v2_envelope(envelope: dict) -> None:
    """Raises ValueError naming the problem if *envelope* is not a valid
    timeline v2 envelope (docs/timeline-v2-contract.md):

    - exactly the three top-level keys, `timelineVersion` exactly `2`
      (never coerced);
    - `leadIn` has exactly its four fields, each within its value domain;
    - `timeline` entries have numeric `start`/`end`, `timeline[0].start`
      is exactly `0.0`, and the existing monotonic chain holds.

    Accepts either freshly built envelopes (whose `timeline` entries are
    plain `{start, end}` dicts of floats) or envelopes just parsed from
    disk (e.g. a `promote` candidate) — the same rules apply to both.
    """
    if not isinstance(envelope, dict):
        raise ValueError("timeline v2 envelope must be a JSON object")

    extra = sorted(set(envelope.keys()) - _ENVELOPE_KEYS)
    missing = sorted(_ENVELOPE_KEYS - set(envelope.keys()))
    if extra or missing:
        raise ValueError(
            "timeline v2 envelope must have exactly the keys "
            f"{sorted(_ENVELOPE_KEYS)} — missing {missing}, extra {extra}"
        )

    version = envelope["timelineVersion"]
    if type(version) is not int or version != TIMELINE_VERSION:
        raise ValueError(
            f"timelineVersion must be exactly {TIMELINE_VERSION} (absent or "
            f"any other value is rejected, never coerced) — got {version!r}"
        )

    lead_in = envelope["leadIn"]
    if not isinstance(lead_in, dict):
        raise ValueError("leadIn must be an object")
    extra = sorted(set(lead_in.keys()) - _LEAD_IN_KEYS)
    missing = sorted(_LEAD_IN_KEYS - set(lead_in.keys()))
    if extra or missing:
        raise ValueError(
            f"leadIn must have exactly the keys {sorted(_LEAD_IN_KEYS)} — "
            f"missing {missing}, extra {extra}"
        )

    duration = lead_in["durationSec"]
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
        raise ValueError(f"leadIn.durationSec must be a number >= 0, got {duration!r}")
    if lead_in["source"] not in _LEAD_IN_SOURCES:
        raise ValueError(
            f"leadIn.source must be one of {sorted(_LEAD_IN_SOURCES)}, got {lead_in['source']!r}"
        )
    if lead_in["confidence"] not in _LEAD_IN_CONFIDENCES:
        raise ValueError(
            f"leadIn.confidence must be one of {sorted(_LEAD_IN_CONFIDENCES)}, "
            f"got {lead_in['confidence']!r}"
        )
    if not isinstance(lead_in["apply"], bool):
        raise ValueError(f"leadIn.apply must be a bool, got {lead_in['apply']!r}")

    timeline = envelope["timeline"]
    if not isinstance(timeline, list):
        raise ValueError('"timeline" must be an array')

    entries: list[TimelineEntry] = []
    for i, item in enumerate(timeline):
        if not isinstance(item, dict):
            raise ValueError(f"timeline[{i}]: must be an object")
        start, end = item.get("start"), item.get("end")
        for name, value in (("start", start), ("end", end)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"timeline[{i}]: {name} must be a number, got {value!r}")
        entries.append(TimelineEntry(start=float(start), end=float(end)))

    if entries and entries[0].start != 0.0:
        raise ValueError(
            "timeline[0].start must be exactly 0.0 (entries are relative to "
            f"the start cue) — got {entries[0].start}"
        )

    validate_timeline(entries)
