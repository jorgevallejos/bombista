"""
Pure timeline-building: anchors + word stream + song items -> TimelineEntry list.

One entry per song item, in item order (the contract's parallel-array rule).
Every item must be a lyric line (a dict carrying the chosen language key) —
section markers and meta entries are no longer supported; encountering one
raises ValueError naming the offending index.

- Lyric line i runs from its anchor's start to the NEXT lyric line's anchor
  start.
- The last lyric line ends at the last transcribed word's end + LAST_LINE_PAD.
- A FAIL anchor (start is None) gets a start linearly interpolated between
  the nearest anchored neighbors (with the song edges as virtual endpoints:
  0.0 before the first line, the last word's end after the last), so the
  candidate timeline is still emittable; the QA report tells the human to
  fix it with `--anchor`. Interpolation between monotone knots can never
  break monotonicity.
"""
from __future__ import annotations

from typing import Sequence

from .anchoring import LineAnchor
from .models import TimelineEntry, Word
from .serializer import validate_timeline

LAST_LINE_PAD = 1.0
"""Seconds the last lyric line stays on screen past its last recognized word."""


def is_lyric_item(item: object, lang: str) -> bool:
    """A lyric item is a dict carrying the chosen language key as a string."""
    return isinstance(item, dict) and isinstance(item.get(lang), str)


def _require_lyric_items(items: Sequence[object], lang: str) -> None:
    """Raises ValueError naming the index of the first item that is not a
    lyric line. Section markers and meta entries are no longer supported —
    every entry in a song's `lyrics` array must carry the chosen language
    key."""
    for i, item in enumerate(items):
        if not is_lyric_item(item, lang):
            raise ValueError(
                f"lyrics[{i}]: not a lyric line — every entry must be an "
                f"object carrying the {lang!r} key (section markers and "
                f"meta entries are no longer supported)"
            )


def lyric_lines(items: Sequence[object], lang: str) -> list[str]:
    """The ordered canonical lyric texts. A text may contain embedded
    newlines — it is still one line, one timeline entry. Raises ValueError
    (see `_require_lyric_items`) if any item is not a lyric line."""
    _require_lyric_items(items, lang)
    return [item[lang] for item in items]


def _fill_missing_starts(
    starts: Sequence[float | None], last_word_end: float
) -> list[float]:
    """Linear interpolation of None starts between the nearest known knots.

    Virtual knots bound the song: index -1 at 0.0 and index n at the last
    word's end (clamped up to the last known anchor so a stray override past
    the audio can't fold the tail backwards).
    """
    n = len(starts)
    knots: list[tuple[int, float]] = [(-1, 0.0)]
    for i, s in enumerate(starts):
        if s is not None:
            # clamp defensively so interpolation knots are non-decreasing
            knots.append((i, max(s, knots[-1][1])))
    knots.append((n, max(last_word_end, knots[-1][1])))

    filled = list(starts)
    for (i0, s0), (i1, s1) in zip(knots, knots[1:]):
        for i in range(i0 + 1, i1):
            filled[i] = s0 + (s1 - s0) * (i - i0) / (i1 - i0)
    return [s for s in filled]  # type: ignore[misc]


def build_timeline(
    anchors: Sequence[LineAnchor],
    words: Sequence[Word],
    items: Sequence[object],
    *,
    lang: str = "es",
) -> list[TimelineEntry]:
    """Build the contract-shaped timeline: one entry per item, 1:1 in order.

    `items` must all be lyric lines (see `_require_lyric_items`); `anchors`
    is parallel to them, as produced by `anchoring.anchor_lines`. Raises
    ValueError if any item is not a lyric line, if the counts disagree, or
    if the result violates the output contract.
    """
    _require_lyric_items(items, lang)
    if len(anchors) != len(items):
        raise ValueError(
            f"anchor count ({len(anchors)}) must match lyric-line count "
            f"({len(items)}) of the song's items"
        )

    ordered = sorted(anchors, key=lambda a: a.line_index)
    last_word_end = max((w.end for w in words), default=0.0)
    starts = _fill_missing_starts([a.start for a in ordered], last_word_end)
    starts = [round(s, 2) for s in starts]

    entries: list[TimelineEntry] = []
    for k in range(len(items)):
        start = starts[k]
        if k + 1 < len(starts):
            end = starts[k + 1]
        else:
            end = round(max(start, last_word_end + LAST_LINE_PAD), 2)
        entries.append(TimelineEntry(start, end))

    validate_timeline(entries)
    return entries


def normalize_to_lead_in(
    entries: Sequence[TimelineEntry],
) -> tuple[float, list[TimelineEntry]]:
    """Rebase a raw (audio-clock) timeline onto a start cue (timeline v2,
    docs/timeline-v2-contract.md).

    `lead_in` is `entries[0].start` (the measured onset of line 0), rounded
    to 2 decimals. Every returned entry is `round(raw_value - lead_in, 2)`,
    so entry 0 always starts at exactly `0.0`. Pure, stdlib only — does not
    touch the song dict or decide whether the lead-in should be applied at
    playback (that's `leadIn.apply`, decided in the serializer from
    `media.type`).

    An empty *entries* returns `(0.0, [])`.
    """
    if not entries:
        return 0.0, []

    lead_in = round(entries[0].start, 2)
    normalized = [
        TimelineEntry(round(e.start - lead_in, 2), round(e.end - lead_in, 2))
        for e in entries
    ]
    return lead_in, normalized
