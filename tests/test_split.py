"""Unit tests for split.py — pure signal-processing functions."""
from __future__ import annotations

import numpy as np
import pytest
from timeline_extractor.split import frame_diff, frame_to_binarized
from PIL import Image


def test_frame_to_binarized_white_pixels():
    img = Image.fromarray(np.full((10, 10), 200, dtype=np.uint8))
    result = frame_to_binarized(img, threshold=30)
    assert result.shape == (10, 10)
    assert result.all()  # all above threshold → all 1s


def test_frame_to_binarized_black_pixels():
    img = Image.fromarray(np.zeros((10, 10), dtype=np.uint8))
    result = frame_to_binarized(img, threshold=30)
    assert not result.any()  # all 0s


def test_frame_diff_identical_frames():
    a = np.ones((10, 10), dtype=np.uint8)
    assert frame_diff(a, a) == pytest.approx(0.0)


def test_frame_diff_opposite_frames():
    a = np.zeros((10, 10), dtype=np.uint8)
    b = np.ones((10, 10), dtype=np.uint8)
    assert frame_diff(a, b) == pytest.approx(1.0)


def test_frame_diff_half_changed():
    a = np.zeros((10, 10), dtype=np.uint8)
    b = a.copy()
    b[:5, :] = 1
    diff = frame_diff(a, b)
    assert diff == pytest.approx(0.5)
