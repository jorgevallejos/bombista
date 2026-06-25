"""Unit tests for the DP alignment in align.py (§3.3)."""
from __future__ import annotations

import pytest
from timeline_extractor.align import dp_align, AlignOp


def card(start, end, text):
    return (start, end, text)


# ── clean 1:1 ──────────────────────────────────────────────────────────────

def test_dp_clean_1to1():
    cards = [
        card(0.0, 2.0, "of shining silver"),
        card(3.0, 5.0, "beneath the morning sun"),
    ]
    lines = ["of shining silver", "beneath the morning sun"]
    results = dp_align(cards, lines)
    assert len(results) == 2
    for r in results:
        assert r["op"] == AlignOp.MATCH
    assert results[0]["start"] == pytest.approx(0.0)
    assert results[0]["end"] == pytest.approx(2.0)
    assert results[1]["start"] == pytest.approx(3.0)
    assert results[1]["end"] == pytest.approx(5.0)


# ── two-card merge ─────────────────────────────────────────────────────────

def test_dp_two_card_merge():
    """One lyric line with embedded newline: two cards → one merged entry."""
    cards = [
        card(0.0, 1.5, "you will be exquisite he sighs"),
        card(1.5, 3.0, "while i dream of my muddy childhood pond"),
    ]
    lines = ['You will be exquisite, he sighs,\nwhile I dream of my muddy childhood pond.']
    results = dp_align(cards, lines)
    assert len(results) == 1
    r = results[0]
    assert r["op"] == AlignOp.MERGE
    assert r["start"] == pytest.approx(0.0)
    assert r["end"] == pytest.approx(3.0)


# ── spurious card (SKIP_CARD) ──────────────────────────────────────────────

def test_dp_spurious_card_skipped():
    """An extra garbage card is absorbed as SKIP_CARD without shifting later lines."""
    cards = [
        card(0.0, 0.3, "NOISE LOGO xyz"),   # spurious — below min-duration or garbage
        card(1.0, 3.0, "alpha beta gamma"),
        card(4.0, 6.0, "delta epsilon"),
    ]
    lines = ["alpha beta gamma", "delta epsilon"]
    results = dp_align(cards, lines)
    assert len(results) == 2
    ops = [r["op"] for r in results]
    assert AlignOp.MATCH in ops or AlignOp.MERGE in ops
    # No MISSING — both lines should be matched
    assert all(r["op"] != AlignOp.MISSING for r in results)
    # Monotonic
    assert results[0]["end"] <= results[1]["start"] + 1e-6


# ── missing card (SKIP_LINE) ───────────────────────────────────────────────

def test_dp_missing_card():
    """A lyric line with no matching card gets a MISSING entry.

    Cards cover lines 0 and 2; the middle line (1) has no card.
    Its text is completely unlike lines 0 and 2, so SPLIT is expensive
    and MISSING (penalty=0.60) is cheaper.
    """
    cards = [
        card(0.0, 2.0, "of shining silver moonlight"),
        # card for line 1 is absent
        card(5.0, 7.0, "the deep dark forest echoes"),
    ]
    lines = [
        "of shining silver moonlight",
        "zxqw pppp rrrrr sssss",   # nonsense; SPLIT would score near 0
        "the deep dark forest echoes",
    ]
    results = dp_align(cards, lines)
    assert len(results) == 3
    ops = [r["op"] for r in results]
    assert AlignOp.MISSING in ops, f"Expected MISSING in ops, got {ops}"
    missing = [r for r in results if r["op"] == AlignOp.MISSING]
    assert len(missing) == 1
    assert missing[0]["start"] is None or missing[0]["start"] == 0.0


# ── three-card merge (edge of cap) ─────────────────────────────────────────

def test_dp_three_card_merge():
    cards = [
        card(0.0, 1.0, "part one"),
        card(1.0, 2.0, "part two"),
        card(2.0, 3.0, "part three"),
    ]
    lines = ["part one part two part three"]
    results = dp_align(cards, lines)
    assert len(results) == 1
    assert results[0]["op"] == AlignOp.MERGE
    assert results[0]["start"] == pytest.approx(0.0)
    assert results[0]["end"] == pytest.approx(3.0)


# ── monotonicity invariant ─────────────────────────────────────────────────

def test_dp_result_is_monotonic():
    cards = [
        card(0.0, 2.0, "line one text here"),
        card(2.5, 4.0, "line two text here"),
        card(5.0, 6.5, "line three text here"),
        card(7.0, 8.0, "line four text here"),
    ]
    lines = ["line one text here", "line two text here", "line three text here", "line four text here"]
    results = dp_align(cards, lines)
    prev_end = -1.0
    for r in results:
        if r["start"] is not None:
            assert r["start"] >= prev_end - 1e-6, f"Monotonicity violated: {results}"
            prev_end = r["end"]
