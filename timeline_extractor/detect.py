"""Brightness-edge detection via ffmpeg signalstats."""
from __future__ import annotations

import subprocess
from pathlib import Path

YAVG_BLANK_THRESHOLD = 17.0
MIN_CARD_DURATION = 0.5


def get_yavg_per_frame(video: Path, crop: str) -> list[float]:
    """Run ffmpeg signalstats on the cropped subtitle band, return YAVG per frame."""
    cmd = [
        "ffmpeg", "-i", str(video),
        "-vf", f"{crop},signalstats,metadata=print:file=-",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    frames = []
    for line in result.stdout.splitlines():
        if "lavfi.signalstats.YAVG=" in line:
            try:
                frames.append(float(line.split("=")[1]))
            except (IndexError, ValueError):
                pass
    return frames


def yavg_to_windows(
    yavg: list[float],
    fps: int = 25,
    blank_threshold: float = YAVG_BLANK_THRESHOLD,
    min_duration: float = MIN_CARD_DURATION,
) -> list[tuple[float, float]]:
    """Convert per-frame YAVG into (start, end) text windows."""
    in_text = False
    windows = []
    start_frame = 0

    for i, v in enumerate(yavg):
        is_text = v > blank_threshold
        if not in_text and is_text:
            in_text = True
            start_frame = i
        elif in_text and not is_text:
            in_text = False
            start = start_frame / fps
            end = i / fps
            if end - start >= min_duration:
                windows.append((start, end))

    if in_text:
        start = start_frame / fps
        end = len(yavg) / fps
        if end - start >= min_duration:
            windows.append((start, end))

    return windows
