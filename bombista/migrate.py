"""
B13 — migrate a shipped **v1** song onto the timeline v2 start cue.

A v1 song carries raw audio-clock times in `timeline` and no version
stamp. Migration is exactly what B12 does to a fresh run, applied to
stored data: subtract `raw[0].start` from every entry, bank it in
`leadIn`, stamp `timelineVersion: 2`.

**This module adds no rules of its own.** The subtraction and rounding
are `pipeline.normalize_to_lead_in`; the `leadIn.apply` default
(`media.type == "video"`), the envelope shape and its invariants —
entry 0 at exactly `0.0`, monotonic, exactly three keys — are
`serializer.to_dict`; the key-order-preserving merge is
`writers.merge_envelope`, the one merge path. What lives here is the
refusal set that stops a *wrong* migration: everything below is a
reason to stop, loudly, before anything is written.

Not idempotent by design — **idempotent by refusal.** A second run on an
already-migrated song would subtract the lead-in twice and shift the
whole song earlier; a silent no-op would be almost as bad, because it
looks like success. So an already-v2 song raises.
"""
from __future__ import annotations

from .models import TimelineEntry
from .pipeline import normalize_to_lead_in
from .serializer import to_dict, validate_timeline
from .writers import ENVELOPE_KEYS, merge_envelope

__all__ = ["migrate_song_to_v2", "ENVELOPE_KEYS"]


def _raw_entries(timeline: list) -> list[TimelineEntry]:
    entries: list[TimelineEntry] = []
    for i, item in enumerate(timeline):
        if not isinstance(item, dict):
            raise ValueError(f"timeline[{i}]: must be an object, got {item!r}")
        start, end = item.get("start"), item.get("end")
        for name, value in (("start", start), ("end", end)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"timeline[{i}]: {name} must be a number, got {value!r}")
        entries.append(TimelineEntry(start=float(start), end=float(end)))
    return entries


def migrate_song_to_v2(song: dict) -> dict:
    """Return a copy of the v1 *song* rebased onto the start cue.

    Every key other than `timelineVersion`, `leadIn` and `timeline` is
    preserved untouched and in order; the three envelope keys land where
    the v1 `timeline` was. *song* itself is not modified.

    Raises ValueError, naming the problem, if the song is not a v1 song
    that can be migrated safely:

    - it is already v2 (a version stamp, or a `leadIn` without one —
      a half-stamped song is corrupt, not v1);
    - it has no `lyrics` list, or no non-empty `timeline` list;
    - the entry count differs from the lyric count (the timeline is
      positional — a mismatch means it belongs to different lyrics);
    - an entry's `start`/`end` is not a number, or the stored timeline
      is not monotonic.
    """
    if "timelineVersion" in song:
        raise ValueError(
            "this song is already timeline v2 "
            f"(timelineVersion={song['timelineVersion']!r}) — refusing to "
            "migrate it again, which would subtract the lead-in twice and "
            "shift every line earlier"
        )
    if "leadIn" in song:
        raise ValueError(
            "this song carries a leadIn but no timelineVersion stamp — that "
            "is a half-migrated song, not a v1 one. Refusing to migrate: "
            "subtracting again would be silently wrong. Fix it by hand"
        )

    items = song.get("lyrics")
    if not isinstance(items, list) or not items:
        raise ValueError('song has no "lyrics" list — nothing to migrate against')

    timeline = song.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        raise ValueError(
            'song has no non-empty "timeline" to migrate — an untimed song '
            "is left alone, never stamped"
        )

    if len(timeline) != len(items):
        raise ValueError(
            f"timeline length ({len(timeline)}) must match the song's lyric "
            f"line count ({len(items)}) — the timeline is positional, so a "
            "mismatch means it does not belong to these lyrics. Refusing"
        )

    entries = _raw_entries(timeline)
    validate_timeline(entries)  # the stored v1 times must already be sane

    lead_in, normalized = normalize_to_lead_in(entries)
    envelope = to_dict(lead_in, normalized, song)
    return merge_envelope(song, envelope)
