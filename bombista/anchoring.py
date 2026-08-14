"""Anchor lyric line onsets against a word-timestamp stream.

Forward-only sequential anchoring: a line's onset is the time of the
earliest word (from the previous anchor onward) that matches the line's
first token, corroborated by a match of another of the line's first few
tokens within the following few words. Falls back to the line's second
token as lead if the first word was apparently mis-heard; otherwise the
line gets no anchor. The scan position only ever advances.

Ported (verbatim matching logic; adapted names/types) from the
ASR-following spike in live-lyric-translator-dev:
  - spike/matcher/follower.py            (normalize_token, tokenize_line,
                                           levenshtein, fuzzy_match)
  - spike/harness/derive_ground_truth.py (the sequential anchoring algorithm)

Extended here with a named-signal confidence band per line, adapted from
the QA design's OCR confidence model to ASR word streams.
"""
from __future__ import annotations

import statistics
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from .models import Word

__all__ = [
    "LineAnchor",
    "anchor_lines",
    "parse_anchor_overrides",
    "normalize_token",
    "tokenize_line",
    "levenshtein",
    "fuzzy_match",
]

# --- ported verbatim from the spike's follower.py -------------------------


def normalize_token(word: str) -> str:
    """Lowercase, strip accents/diacritics, keep only alphanumerics.

    '¡QUÉ' -> 'que', "pa'" -> 'pa', 'años' -> 'anos'.
    """
    decomposed = unicodedata.normalize("NFKD", word.lower())
    return "".join(
        ch for ch in decomposed if not unicodedata.combining(ch) and ch.isalnum()
    )


def tokenize_line(line: str) -> list[str]:
    """Whitespace-split (newlines included) and normalize; drop empties."""
    tokens = []
    for raw in line.split():
        tok = normalize_token(raw)
        if tok:
            tokens.append(tok)
    return tokens


def levenshtein(a: str, b: str) -> int:
    """Plain DP edit distance. Words are short; O(len*len) is fine."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def fuzzy_match(word: str, target: str) -> bool:
    """Is normalized `word` a plausible recognition of normalized `target`?

    - Exact match always counts.
    - Short targets (<= 3 chars: de, la, y, sal...) must match exactly.
    - Prefix match (either direction, both sides >= 4 chars) absorbs
      truncated/extended ASR emissions ('brillan' vs 'brillante').
    - Edit distance 1 for targets >= 4 chars, 2 for targets >= 7 chars.
    """
    if word == target:
        return True
    if len(target) <= 3 or len(word) <= 3:
        return False
    if len(word) >= 4 and len(target) >= 4 and (
        word.startswith(target) or target.startswith(word)
    ):
        return True
    max_dist = 2 if len(target) >= 7 else 1
    return levenshtein(word, target) <= max_dist


# --- confidence-band tuning: every threshold named and independently tested ---

LEAD_WINDOW_TOKENS = 4
"""Opening tokens of a line considered for anchoring/corroboration."""

CORROBORATION_WINDOW = 8
"""Words after a lead match searched for a corroborating token match."""

AMBIGUITY_HORIZON = 12
"""Words after a chosen anchor searched for a repeat of its lead token
(repeated-chorus risk). Wide enough to span a back-to-back chorus repeat
without reaching into the next line's own legitimate occurrence."""

GAP_OUTLIER_RATIO = 3.0
"""How far (multiplicatively, either direction) the gap since the previous
anchor may stray from the median of prior gaps before it's suspicious."""

GAP_OUTLIER_MIN_SAMPLES = 2
"""Prior gaps required before the gap-outlier check applies (avoids noisy
flags on the first couple of anchors, when there's no established rhythm
to compare against)."""


@dataclass(frozen=True)
class LineAnchor:
    """Result of anchoring one lyric line onto the word-timestamp stream."""

    line_index: int
    start: float | None
    band: str  # "HIGH" | "REVIEW" | "FAIL"
    signals: tuple[str, ...]
    asr_context: str
    lead_token: int | None  # 0 = token[0], 1 = fallback, None = not found/override


def _lead_match(
    toks: list[tuple[str, float, str]],
    start_idx: int,
    end_idx: int,
    window: list[str],
    lead: int,
) -> tuple[int | None, bool]:
    """Earliest index in [start_idx, end_idx) matching window[lead], plus
    whether that match is corroborated by another window token within the
    following CORROBORATION_WINDOW words. A single-token window (no other
    tokens to corroborate with) is accepted uncorroborated."""
    rest = [tok for tok in window if tok != window[lead]]
    for i in range(start_idx, end_idx):
        if fuzzy_match(toks[i][0], window[lead]):
            corroborated = any(
                fuzzy_match(toks[j][0], r)
                for j in range(i + 1, min(i + 1 + CORROBORATION_WINDOW, len(toks)))
                for r in rest
            )
            if corroborated or not rest:
                return i, corroborated
    return None, False


def _find_anchor(
    toks: list[tuple[str, float, str]],
    start_idx: int,
    end_idx: int,
    window: list[str],
) -> tuple[int | None, int | None, bool]:
    """Try lead token[0], then token[1] as a fallback lead (first word
    mis-heard). Returns (index, lead_used, corroborated) or (None, None, False)."""
    for lead in range(min(2, len(window))):
        found, corroborated = _lead_match(toks, start_idx, end_idx, window, lead)
        if found is not None:
            return found, lead, corroborated
    return None, None, False


def _resync(toks: list[tuple[str, float, str]], at_or_after: float) -> int:
    """First word index at/after `at_or_after`, or len(toks) if none."""
    for i, tok in enumerate(toks):
        if tok[1] >= at_or_after:
            return i
    return len(toks)


def _asr_context(toks: list[tuple[str, float, str]], index: int) -> str:
    end = min(index + CORROBORATION_WINDOW, len(toks))
    return " ".join(tok[2] for tok in toks[index:end])


def parse_anchor_overrides(values: Iterable[str], line_count: int) -> dict[int, float]:
    """Parse `LINE=SECONDS` strings into the `overrides` mapping
    `anchor_lines` takes, rejecting anything it cannot honour.

    It lives beside `anchor_lines` rather than in the CLI because an
    override is an anchoring concept, and every front end has to reach the
    same mapping from the same text: `--anchor 7=93.4` on the command
    line, a stepper's value posted by `serve`'s review page (B20). Raises
    ValueError naming the offending value; the caller renders it.

    `line_count` is checked here, not later, because an out-of-range index
    would otherwise be silently ignored — the correction would look
    applied and would not be.
    """
    overrides: dict[int, float] = {}
    for raw in values:
        line_part, sep, seconds_part = raw.partition("=")
        try:
            if not sep:
                raise ValueError
            line = int(line_part)
            seconds = float(seconds_part)
            if line < 0 or seconds < 0:
                raise ValueError
        except ValueError:
            raise ValueError(f"--anchor must be LINE=SECONDS (non-negative), got {raw!r}")
        if line >= line_count:
            raise ValueError(
                f"--anchor line {line} out of range: song has {line_count} "
                f"lyric lines (0..{line_count - 1})"
            )
        overrides[line] = seconds
    return overrides


def anchor_lines(
    words: list[Word],
    lines: list[str],
    *,
    overrides: dict[int, float] | None = None,
) -> list[LineAnchor]:
    """Anchor each lyric line's onset, forward-only, with a confidence band.

    `lines` are ordered lyric-line strings (may contain embedded newlines;
    one line is still one anchor). `overrides` maps line index to a
    hand-set onset (seconds): that line gets that start verbatim, band
    HIGH, signal "override", and the scan resyncs to the first word at or
    after that time before anchoring the next line.
    """
    overrides = overrides or {}
    toks: list[tuple[str, float, str]] = [
        (normalize_token(w.text), w.start, w.text)
        for w in words
        if normalize_token(w.text)
    ]
    n = len(toks)

    results: list[LineAnchor] = []
    pos = 0
    anchor_times: list[float] = []

    for idx, line in enumerate(lines):
        if idx in overrides:
            start = overrides[idx]
            results.append(LineAnchor(idx, start, "HIGH", ("override",), "", None))
            pos = _resync(toks, start)
            anchor_times.append(start)
            continue

        window = tokenize_line(line)[:LEAD_WINDOW_TOKENS]
        found, lead_used, corroborated = _find_anchor(toks, pos, n, window)

        if found is None:
            results.append(LineAnchor(idx, None, "FAIL", ("no-anchor",), "", None))
            continue

        start = toks[found][1]
        signals: list[str] = []
        if lead_used == 1:
            signals.append("lead-fallback")
        if not corroborated:
            signals.append("uncorroborated")

        repeat_idx, _ = _lead_match(
            toks, found + 1, min(found + 1 + AMBIGUITY_HORIZON, n), window, lead_used
        )
        if repeat_idx is not None:
            signals.append("ambiguous")

        prior_gaps = [
            anchor_times[i + 1] - anchor_times[i]
            for i in range(len(anchor_times) - 1)
        ]
        if len(prior_gaps) >= GAP_OUTLIER_MIN_SAMPLES and anchor_times:
            median_gap = statistics.median(prior_gaps)
            gap = start - anchor_times[-1]
            if median_gap > 0 and (
                gap > median_gap * GAP_OUTLIER_RATIO
                or gap < median_gap / GAP_OUTLIER_RATIO
            ):
                signals.append("gap-outlier")

        band = "HIGH" if not signals else "REVIEW"
        display_signals = tuple(signals) if signals else ("clean-anchor",)

        results.append(
            LineAnchor(
                idx,
                start,
                band,
                display_signals,
                _asr_context(toks, found),
                lead_used,
            )
        )
        pos = found + 1
        anchor_times.append(start)

    return results
