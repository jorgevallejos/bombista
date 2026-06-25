"""Greedy reconcile — lifted from spike (will be replaced by DP in feat/dp-alignment)."""
from __future__ import annotations

from rapidfuzz import fuzz

FUZZY_MATCH_THRESHOLD = 60


def normalize(s: str) -> str:
    """Lowercase, collapse embedded newlines to space, strip whitespace."""
    return s.lower().replace("\n", " ").strip()


def reconcile(
    cards: list[tuple[float, float, str]],
    lyric_lines: list[str],
) -> list[dict]:
    """
    Sequential greedy assignment: process lyric lines in order, consuming cards
    in order. Each line consumes either 1 or 2 consecutive cards — whichever
    gives a higher fuzzy score. Guarantees monotonicity.
    """
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
            start = cards[ci][0]
            end = cards[ci + 1][1]
            ocr = cards[ci][2] + " | " + cards[ci + 1][2]
            status = "merge"
            score = score_2
            ci += 2
        elif score_1 >= FUZZY_MATCH_THRESHOLD:
            start = cards[ci][0]
            end = cards[ci][1]
            ocr = cards[ci][2]
            status = "1:1"
            score = score_1
            ci += 1
        else:
            start = cards[ci][0]
            end = cards[ci][1]
            ocr = cards[ci][2]
            status = f"low({score_1})"
            score = score_1
            ci += 1

        results.append({
            "line_idx": li,
            "en_text": lyric_lines[li],
            "start": round(start, 3),
            "end": round(end, 3),
            "ocr_text": ocr,
            "match_status": status,
            "score": score,
        })

    return results
