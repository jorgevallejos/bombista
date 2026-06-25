"""Unit tests for align.py — greedy reconcile (identical to spike behaviour)."""
from __future__ import annotations

import pytest
from timeline_extractor.align import normalize, reconcile


def card(start, end, text):
    return (start, end, text)


def test_normalize_strips_and_lowercases():
    assert normalize("  Hello World\n") == "hello world"


def test_normalize_collapses_newline():
    assert normalize("line one\nline two") == "line one line two"


def test_reconcile_clean_1to1():
    cards = [card(0.0, 2.0, "hello world")]
    lines = ["hello world"]
    results = reconcile(cards, lines)
    assert len(results) == 1
    r = results[0]
    assert r["match_status"] == "1:1"
    assert r["start"] == pytest.approx(0.0)
    assert r["end"] == pytest.approx(2.0)


def test_reconcile_merge_two_cards():
    cards = [
        card(0.0, 1.5, "first part of"),
        card(1.5, 3.0, "the lyric line"),
    ]
    lines = ["first part of the lyric line"]
    results = reconcile(cards, lines)
    assert len(results) == 1
    r = results[0]
    assert r["match_status"] == "merge"
    assert r["start"] == pytest.approx(0.0)
    assert r["end"] == pytest.approx(3.0)


def test_reconcile_multiple_lines_monotonic():
    cards = [
        card(0.0, 2.0, "alpha beta"),
        card(2.5, 4.0, "gamma delta"),
        card(4.5, 6.0, "epsilon zeta"),
    ]
    lines = ["alpha beta", "gamma delta", "epsilon zeta"]
    results = reconcile(cards, lines)
    assert len(results) == 3
    ends = [r["end"] for r in results]
    assert ends == sorted(ends), "results must be monotonic"


def test_reconcile_fewer_cards_than_lines_produces_unmatched():
    cards = [card(0.0, 2.0, "alpha beta")]
    lines = ["alpha beta", "gamma delta"]
    results = reconcile(cards, lines)
    assert len(results) == 2
    assert results[0]["match_status"] == "1:1"
    assert results[1]["start"] is None
