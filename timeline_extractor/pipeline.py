"""
Pure timeline-building: anchors + word stream + song items -> TimelineEntry list.

One entry per song item, in item order (the contract's parallel-array rule):

- Section markers (any item that is not a dict carrying the chosen language
  key) get the `{start: 0, end: 0}` placeholder and are skipped in alignment.
- Lyric line i runs from its anchor's start to the NEXT lyric line's anchor
  start (display-card continuity — markers between lyric lines don't break
  the chain).
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
    """A lyric item is a dict carrying the chosen language key; anything else
    (bare strings, `{"type": "section", ...}` dicts, dicts in other languages
    only) is a section marker."""
    return isinstance(item, dict) and isinstance(item.get(lang), str)


def lyric_lines(items: Sequence[object], lang: str) -> list[str]:
    """The ordered canonical lyric texts (markers skipped). A text may contain
    embedded newlines — it is still one line, one timeline entry."""
    return [item[lang] for item in items if is_lyric_item(item, lang)]


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
    """Build the contract-shaped timeline: one entry per item, markers {0,0}.

    `anchors` is parallel to the lyric lines of `items` (markers excluded),
    as produced by `anchoring.anchor_lines`. Raises ValueError if the counts
    disagree or the result violates the output contract.
    """
    lyric_positions = [i for i, item in enumerate(items) if is_lyric_item(item, lang)]
    if len(anchors) != len(lyric_positions):
        raise ValueError(
            f"anchor count ({len(anchors)}) must match lyric-line count "
            f"({len(lyric_positions)}) of the song's items"
        )

    ordered = sorted(anchors, key=lambda a: a.line_index)
    last_word_end = max((w.end for w in words), default=0.0)
    starts = _fill_missing_starts([a.start for a in ordered], last_word_end)
    starts = [round(s, 2) for s in starts]

    entries: list[TimelineEntry] = [TimelineEntry(0.0, 0.0) for _ in items]
    for k, item_index in enumerate(lyric_positions):
        start = starts[k]
        if k + 1 < len(starts):
            end = starts[k + 1]
        else:
            end = round(max(start, last_word_end + LAST_LINE_PAD), 2)
        entries[item_index] = TimelineEntry(start, end)

    validate_timeline(entries)
    return entries
