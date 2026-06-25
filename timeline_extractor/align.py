"""Alignment — global DP (§3.3) replacing the greedy spike reconcile."""
from __future__ import annotations

import unicodedata
from enum import Enum

from rapidfuzz import fuzz

# ── tuneable penalties (§3.4) ──────────────────────────────────────────────
SKIP_CARD_PENALTY = 0.40   # spurious card is common; cheaper to skip
SKIP_LINE_PENALTY = 0.60   # missing card is rare and alarming; more expensive
# SPLIT covers one card with two lines (rare). Adding a surcharge keeps SPLIT
# from winning via token subset credit when MISSING is the real answer.
SPLIT_SURCHARGE = 0.35
FUZZY_MATCH_THRESHOLD = 60  # kept for legacy reconcile compatibility


class AlignOp(str, Enum):
    MATCH = "MATCH"
    MERGE = "MERGE"
    SKIP_CARD = "SKIP_CARD"
    MISSING = "MISSING"
    SPLIT = "SPLIT"


def normalize(s: str) -> str:
    """Lowercase, strip diacritics, collapse embedded newlines, strip whitespace."""
    s = s.lower().replace("\n", " ").strip()
    # Strip diacritics (ñ→n, é→e) so OCR accents don't penalise match scores.
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _fuzzy(a: str, b: str) -> float:
    """Normalised token-sort ratio in [0, 1]."""
    return fuzz.token_sort_ratio(a, b) / 100.0


def _cost(card_text: str, line_text: str) -> float:
    return 1.0 - _fuzzy(normalize(card_text), normalize(line_text))


def _merge_cost(card_texts: list[str], line_text: str) -> float:
    merged = " ".join(normalize(t) for t in card_texts)
    return 1.0 - _fuzzy(merged, normalize(line_text))


INF = float("inf")


def dp_align(
    cards: list[tuple[float, float, str]],
    lines: list[str],
    skip_card_penalty: float = SKIP_CARD_PENALTY,
    skip_line_penalty: float = SKIP_LINE_PENALTY,
    split_surcharge: float = SPLIT_SURCHARGE,
) -> list[dict]:
    """
    Global monotonic alignment of cards against lyric lines (§3.3).

    Operations:
      MATCH  — 1 card  ↔ 1 line
      MERGE  — 2–3 cards ↔ 1 line
      SKIP_CARD — 1 card ↔ 0 lines  (extra/spurious card)
      MISSING   — 0 cards ↔ 1 line  (undisplayed or undetected line)
      SPLIT  — 1 card  ↔ 2 lines    (rare)

    Returns one dict per *line* with keys:
      line_idx, en_text, start, end, ocr_text, op (AlignOp), score
    """
    m, n = len(cards), len(lines)

    # D[i][j] = min cost to align first i cards with first j lines
    D = [[INF] * (n + 1) for _ in range(m + 1)]
    # back[i][j] = (prev_i, prev_j, op, card_slice)
    back: list[list[tuple | None]] = [[None] * (n + 1) for _ in range(m + 1)]

    D[0][0] = 0.0

    for i in range(m + 1):
        for j in range(n + 1):
            if D[i][j] == INF:
                continue
            cur = D[i][j]

            # MATCH: 1 card ↔ 1 line
            if i < m and j < n:
                c = _cost(cards[i][2], lines[j])
                if cur + c < D[i + 1][j + 1]:
                    D[i + 1][j + 1] = cur + c
                    back[i + 1][j + 1] = (i, j, AlignOp.MATCH, [i])

            # MERGE 2: 2 cards ↔ 1 line
            if i + 1 < m and j < n:
                c = _merge_cost([cards[i][2], cards[i + 1][2]], lines[j])
                if cur + c < D[i + 2][j + 1]:
                    D[i + 2][j + 1] = cur + c
                    back[i + 2][j + 1] = (i, j, AlignOp.MERGE, [i, i + 1])

            # MERGE 3: 3 cards ↔ 1 line
            if i + 2 < m and j < n:
                c = _merge_cost([cards[i][2], cards[i + 1][2], cards[i + 2][2]], lines[j])
                if cur + c < D[i + 3][j + 1]:
                    D[i + 3][j + 1] = cur + c
                    back[i + 3][j + 1] = (i, j, AlignOp.MERGE, [i, i + 1, i + 2])

            # SKIP_CARD: 1 card ↔ 0 lines
            if i < m:
                if cur + skip_card_penalty < D[i + 1][j]:
                    D[i + 1][j] = cur + skip_card_penalty
                    back[i + 1][j] = (i, j, AlignOp.SKIP_CARD, [i])

            # MISSING: 0 cards ↔ 1 line
            if j < n:
                if cur + skip_line_penalty < D[i][j + 1]:
                    D[i][j + 1] = cur + skip_line_penalty
                    back[i][j + 1] = (i, j, AlignOp.MISSING, [])

            # SPLIT: 1 card ↔ 2 lines (surcharge prevents token-subset false wins)
            if i < m and j + 1 < n:
                combined_line = normalize(lines[j]) + " " + normalize(lines[j + 1])
                c = split_surcharge + (1.0 - _fuzzy(normalize(cards[i][2]), combined_line))
                if cur + c < D[i + 1][j + 2]:
                    D[i + 1][j + 2] = cur + c
                    back[i + 1][j + 2] = (i, j, AlignOp.SPLIT, [i])

    # Traceback
    ops: list[tuple[AlignOp, list[int], int]] = []  # (op, card_indices, line_idx)
    i, j = m, n
    while i > 0 or j > 0:
        entry = back[i][j]
        if entry is None:
            break
        prev_i, prev_j, op, card_indices = entry
        if op == AlignOp.MATCH:
            ops.append((op, card_indices, prev_j))
        elif op == AlignOp.MERGE:
            ops.append((op, card_indices, prev_j))
        elif op == AlignOp.SPLIT:
            ops.append((AlignOp.SPLIT, card_indices, prev_j + 1))
            ops.append((AlignOp.SPLIT, card_indices, prev_j))
        elif op == AlignOp.SKIP_CARD:
            pass  # dropped card, no line entry
        elif op == AlignOp.MISSING:
            ops.append((op, [], prev_j))
        i, j = prev_i, prev_j

    ops.reverse()

    results = []
    line_idx = 0
    for op, card_indices, li in ops:
        line_text = lines[li] if li < len(lines) else ""
        if op == AlignOp.MISSING:
            results.append({
                "line_idx": li,
                "en_text": line_text,
                "start": None,
                "end": None,
                "ocr_text": "",
                "op": AlignOp.MISSING,
                "score": 0,
            })
        elif op in (AlignOp.MATCH, AlignOp.MERGE):
            first_card = cards[card_indices[0]]
            last_card = cards[card_indices[-1]]
            ocr_texts = [cards[ci][2] for ci in card_indices]
            score_val = _fuzzy(
                " ".join(normalize(t) for t in ocr_texts),
                normalize(line_text),
            )
            results.append({
                "line_idx": li,
                "en_text": line_text,
                "start": round(first_card[0], 3),
                "end": round(last_card[1], 3),
                "ocr_text": " | ".join(ocr_texts),
                "op": op,
                "score": round(score_val * 100, 1),
            })
        elif op == AlignOp.SPLIT:
            # One card spanning two lines — give each line the full card's window.
            c = cards[card_indices[0]]
            results.append({
                "line_idx": li,
                "en_text": line_text,
                "start": round(c[0], 3),
                "end": round(c[1], 3),
                "ocr_text": c[2],
                "op": AlignOp.SPLIT,
                "score": 0,
            })

    return results


# ── legacy greedy reconcile (kept for reference; not used in production) ───

def reconcile(
    cards: list[tuple[float, float, str]],
    lyric_lines: list[str],
) -> list[dict]:
    """Legacy greedy reconcile from spike — superseded by dp_align."""
    norm_lyrics = [normalize(ln) for ln in lyric_lines]

    def ctext(i: int) -> str:
        return normalize(cards[i][2]) if i < len(cards) else ""

    results = []
    ci = 0

    for li, lyric_norm in enumerate(norm_lyrics):
        if ci >= len(cards):
            results.append({
                "line_idx": li, "en_text": lyric_lines[li],
                "start": None, "end": None, "ocr_text": "",
                "match_status": "unmatched", "score": 0,
            })
            continue

        score_1 = fuzz.token_sort_ratio(lyric_norm, ctext(ci))
        score_2 = -1
        if ci + 1 < len(cards):
            merged = (ctext(ci) + " " + ctext(ci + 1)).strip()
            score_2 = fuzz.token_sort_ratio(lyric_norm, merged)

        if score_2 > score_1 and score_2 >= FUZZY_MATCH_THRESHOLD:
            start, end = cards[ci][0], cards[ci + 1][1]
            ocr = cards[ci][2] + " | " + cards[ci + 1][2]
            status, score, ci = "merge", score_2, ci + 2
        elif score_1 >= FUZZY_MATCH_THRESHOLD:
            start, end = cards[ci][0], cards[ci][1]
            ocr, status, score, ci = cards[ci][2], "1:1", score_1, ci + 1
        else:
            start, end = cards[ci][0], cards[ci][1]
            ocr, status, score, ci = cards[ci][2], f"low({score_1})", score_1, ci + 1

        results.append({
            "line_idx": li, "en_text": lyric_lines[li],
            "start": round(start, 3), "end": round(end, 3),
            "ocr_text": ocr, "match_status": status, "score": score,
        })

    return results
