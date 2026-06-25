"""Unit tests for detect.py — brightness-edge detection (pure functions only)."""
from __future__ import annotations

import pytest
from timeline_extractor.detect import yavg_to_windows


def make_yavg(blank_val: float, text_val: float, pattern: list) -> list[float]:
    """Build a YAVG series from a pattern of (value, n_frames) pairs."""
    out = []
    for val, n in pattern:
        out.extend([val] * n)
    return out


def test_single_text_window():
    # 25 blank, 50 text, 25 blank  @25fps → window [1.0, 3.0)
    yavg = make_yavg(5.0, 30.0, [(5.0, 25), (30.0, 50), (5.0, 25)])
    windows = yavg_to_windows(yavg, fps=25)
    assert len(windows) == 1
    start, end = windows[0]
    assert start == pytest.approx(1.0)
    assert end == pytest.approx(3.0)


def test_two_separate_windows():
    yavg = make_yavg(5.0, 30.0, [
        (5.0, 10), (30.0, 25), (5.0, 10), (30.0, 25), (5.0, 10)
    ])
    windows = yavg_to_windows(yavg, fps=25)
    assert len(windows) == 2


def test_short_flicker_filtered():
    # A 5-frame (0.2s) text burst is below MIN_CARD_DURATION and must be dropped.
    yavg = [5.0] * 50 + [30.0] * 5 + [5.0] * 50
    windows = yavg_to_windows(yavg, fps=25)
    assert len(windows) == 0


def test_text_at_end_of_stream():
    # Card that runs to the end of the stream (no trailing blank).
    yavg = [5.0] * 25 + [30.0] * 50
    windows = yavg_to_windows(yavg, fps=25)
    assert len(windows) == 1


def test_all_blank_returns_empty():
    yavg = [5.0] * 100
    assert yavg_to_windows(yavg, fps=25) == []
