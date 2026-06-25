"""Intra-text split — detect card changes within a brightness window."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

PIXEL_DIFF_THRESHOLD = 0.005


def extract_frame_crop(video: Path, t: float, crop: str) -> Image.Image:
    """Extract one frame at time t with crop filter, return PIL Image."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = Path(f.name)
    cmd = [
        "ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(video),
        "-frames:v", "1", "-vf", crop,
        str(tmp),
    ]
    subprocess.run(cmd, capture_output=True)
    img = Image.open(tmp).copy()
    tmp.unlink()
    return img


def frame_to_binarized(img: Image.Image, threshold: int = 30) -> np.ndarray:
    """Convert to grayscale and binarize — text pixels become 1, background 0."""
    gray = np.array(img.convert("L"), dtype=np.uint8)
    return (gray > threshold).astype(np.uint8)


def frame_diff(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute difference of binarized frames (0.0–1.0)."""
    return float(np.mean(np.abs(a.astype(int) - b.astype(int))))


def split_window_on_content_change(
    video: Path,
    start: float,
    end: float,
    crop: str,
    sample_every: float = 0.15,
    threshold: float = PIXEL_DIFF_THRESHOLD,
) -> list[tuple[float, float]]:
    """
    Sample binarized frames inside (start, end). When pixel-diff between
    consecutive samples exceeds threshold, insert a split at the midpoint.
    Only attempt on windows with enough samples (at least 3).
    """
    times = []
    t = start + 0.1
    while t < end - 0.1:
        times.append(t)
        t += sample_every

    if len(times) < 3:
        return [(start, end)]

    frames = [frame_to_binarized(extract_frame_crop(video, t, crop)) for t in times]
    diffs = [frame_diff(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]

    sub_windows = []
    seg_start = start
    for i, d in enumerate(diffs):
        if d >= threshold:
            split_t = (times[i] + times[i + 1]) / 2
            sub_windows.append((seg_start, split_t))
            seg_start = split_t

    sub_windows.append((seg_start, end))
    return sub_windows
