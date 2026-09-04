"""
Serializes a normalised timeline (lead-in + entries) to the timeline v2
interchange envelope consumed by the translator's timeline-import button.

Format:
    {
      "timelineVersion": 2,
      "leadIn": {"durationSec": 7.26, "source": "measured", "confidence": "low"},
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
_LEAD_IN_KEYS = {"durationSec", "source", "confidence"}
_LEAD_IN_LEGACY_KEYS = {"apply"}
"""Keys a file written before 2026-09-04 may still carry, accepted and ignored.

**`apply` was this tool's and stopped being it.** It was derived from
`media.type == "video"`; under *the song holds no media* nothing declares media,
and **the decision to apply the lead-in moved to Pregonero**, which is the only
party that knows a video is assigned for a gig.

**Accepted rather than refused, because nothing is migrated.** Files already on
disk carry the key; refusing them would make walk state unvalidatable for no
gain, and Pregonero's own parser drops it the same way. **Nothing writes it.**
"""
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


def to_dict(
    lead_in: float,
    entries: Sequence[TimelineEntry],
    *,
    source: str = "measured",
) -> dict:
    """Build the timeline v2 envelope from an already-normalised timeline.

    `entries` must already be relative to the start cue (see
    `pipeline.normalize_to_lead_in`) — entry 0 is expected to start at
    `0.0`. Raises ValueError if the resulting envelope fails
    `validate_v2_envelope`.

    **THE SONG IS NOT AN ARGUMENT ANY MORE** (Jorge, 2026-09-04). It was here
    for one reason: `leadIn.apply`, derived from `media.type == "video"`. Under
    *the song holds no media* nothing declares media, so that default would
    have silently flipped to False and **every video song would have lost its
    lead-in correction with nothing reporting it.**

    **`leadIn` splits the way the media did.** Its measured VALUE stays here —
    it is a real measurement of the words, which is Bombista's output. The
    DECISION to apply it is Pregonero's, taken from whether a video is assigned
    to the song for a gig in `visuals.json`; after the split Pregonero is the
    only party that could know. So this writes the number and says nothing
    about what to do with it.

    *source* is the contract's `leadIn.source`: `measured` when Bombista
    computed the value, `manual` when a human overrode it. It defaults to
    `measured` because that is what every caller but `serve` does — the
    CLI derives line 0's onset from the word stream and nothing else.
    `serve` passes `manual` when line 0 was hand-set, which it may be
    since §8.6: the normaliser banks whatever line 0's onset is, so a
    lead-in can now come from either place and a file that cannot say
    which one claims a machine measured a number a person typed.
    """
    envelope = {
        "timelineVersion": TIMELINE_VERSION,
        "leadIn": {
            "durationSec": round(lead_in, 2),
            "source": source,
            "confidence": "low",
        },
        "timeline": [{"start": e.start, "end": e.end} for e in entries],
    }
    validate_v2_envelope(envelope)
    return envelope


def write_timeline(lead_in: float, entries: Sequence[TimelineEntry], path: Path) -> None:
    """Write the timeline v2 interchange JSON to *path*."""
    data = to_dict(lead_in, entries)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def validate_v2_envelope(envelope: dict) -> None:
    """Raises ValueError naming the problem if *envelope* is not a valid
    timeline v2 envelope (docs/timeline-v2-contract.md):

    - exactly the three top-level keys, `timelineVersion` exactly `2`
      (never coerced);
    - `leadIn` has exactly its three fields, each within its value domain;
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
    extra = sorted(set(lead_in.keys()) - _LEAD_IN_KEYS - _LEAD_IN_LEGACY_KEYS)
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

    if not entries:
        # Contract amendment 2026-08-13: a file claiming to be a timeline
        # while carrying no timeline is malformed (truncated or half-written),
        # not an untimed song. Loading it silently would make the song look
        # like it simply has no timings — the exact silent failure this
        # format exists to eliminate.
        raise ValueError(
            "this timeline file is incomplete — it declares version "
            f"{TIMELINE_VERSION} but contains no timeline"
        )

    if entries[0].start != 0.0:
        raise ValueError(
            "timeline[0].start must be exactly 0.0 (entries are relative to "
            f"the start cue) — got {entries[0].start}"
        )

    validate_timeline(entries)
