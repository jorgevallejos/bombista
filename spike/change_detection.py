"""
Spike: ffmpeg change-detection on tragedia "lyrics-only" video.

Pipeline:
  1. Brightness-edge detection  → raw cue windows (YAVG threshold on subtitle band)
  2. Intra-text split            → detect card changes with no dark gap (avg-hash diff)
  3. OCR                         → text per card (tesseract, psm 7 on negated crop)
  4. Reconcile                   → 29 lyric lines via fuzzy-match of .en entries
  5. Emit                        → serializer.write_timeline → docs/spike-candidate-timeline.json
  6. QA table                    → line | start | end | OCR text | match status

Run from repo root (with venv active):
  python spike/change_detection.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

import numpy as np
from PIL import Image
from rapidfuzz import fuzz, process

# ── paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
VIDEO = Path("/Users/jorgevallejos/Chango Pepper/animations/tragedia-de-cerdo-asado/Master Sequence only subtitles.mp4")
SONG_JSON = Path("/Users/jorgevallejos/Chango Pepper/songs/tragedia-de-cerdo-asado.json")
OUT_PATH = REPO_ROOT / "docs" / "spike-candidate-timeline.json"

# Add package to path so we can import serializer
sys.path.insert(0, str(REPO_ROOT))
from bombista.models import TimelineEntry
from bombista.serializer import write_timeline

# ── tuning knobs ──────────────────────────────────────────────────────────────
CROP = "crop=1620:320:0:760"       # subtitle band (bottom 320 rows)
FPS = 25
YAVG_BLANK_THRESHOLD = 17.0        # YAVG below → blank frame
YAVG_HYSTERESIS = 0.3              # must stay above/below for edge confirmation
HASH_CHANGE_THRESHOLD = 6          # avg-hash bits differ → new card (0–64 scale)
MIN_CARD_DURATION = 0.5            # seconds — ignore sub-half-second flickers
OCR_SCALE = 3                      # upsample factor before tesseract
FUZZY_MATCH_THRESHOLD = 60         # rapidfuzz score (0–100) to accept a match


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: brightness-edge detection via ffmpeg signalstats
# ══════════════════════════════════════════════════════════════════════════════

def get_yavg_per_frame(video: Path) -> list[float]:
    """Run ffmpeg signalstats on the cropped subtitle band, return YAVG per frame."""
    print("  [ffmpeg] extracting YAVG per frame …", flush=True)
    cmd = [
        "ffmpeg", "-i", str(video),
        "-vf", f"{CROP},signalstats,metadata=print:file=-",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # metadata=print:file=- writes to stdout: "lavfi.signalstats.YAVG=18.3"
    frames = []
    for line in result.stdout.splitlines():
        if "lavfi.signalstats.YAVG=" in line:
            try:
                val = float(line.split("=")[1])
                frames.append(val)
            except (IndexError, ValueError):
                pass
    print(f"  [ffmpeg] {len(frames)} frames extracted", flush=True)
    return frames


def yavg_to_windows(yavg: list[float], fps: int = FPS) -> list[tuple[float, float]]:
    """Convert per-frame YAVG into (start, end) text windows using threshold + hysteresis."""
    in_text = False
    windows = []
    start_frame = 0

    for i, v in enumerate(yavg):
        is_text = v > YAVG_BLANK_THRESHOLD
        if not in_text and is_text:
            in_text = True
            start_frame = i
        elif in_text and not is_text:
            in_text = False
            start = start_frame / fps
            end = i / fps
            if end - start >= MIN_CARD_DURATION:
                windows.append((start, end))

    if in_text:
        start = start_frame / fps
        end = len(yavg) / fps
        if end - start >= MIN_CARD_DURATION:
            windows.append((start, end))

    return windows


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: intra-text split — detect card changes within a text window
# ══════════════════════════════════════════════════════════════════════════════

def extract_frame_crop(video: Path, t: float, crop: str) -> Image.Image:
    """Extract one frame at time t, apply crop filter, return PIL Image."""
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


PIXEL_DIFF_THRESHOLD = 0.005  # ~0.5% of pixels changed → new card


def split_window_on_content_change(
    video: Path,
    start: float,
    end: float,
    sample_every: float = 0.15,
) -> list[tuple[float, float]]:
    """
    Sample binarized frames inside (start, end). When pixel-diff between
    consecutive samples exceeds threshold, insert a split at the midpoint.
    """
    times = []
    t = start + 0.1
    while t < end - 0.1:
        times.append(t)
        t += sample_every

    if len(times) < 3:
        return [(start, end)]

    frames = [frame_to_binarized(extract_frame_crop(video, t, CROP)) for t in times]
    diffs = [frame_diff(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]

    # Find local maxima above threshold — these are card-change points
    sub_windows = []
    seg_start = start
    for i, d in enumerate(diffs):
        if d >= PIXEL_DIFF_THRESHOLD:
            split_t = (times[i] + times[i + 1]) / 2
            sub_windows.append((seg_start, split_t))
            seg_start = split_t

    sub_windows.append((seg_start, end))
    return sub_windows


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: OCR each card window
# ══════════════════════════════════════════════════════════════════════════════

def ocr_card(video: Path, start: float, end: float) -> str:
    """Extract mid-window frame, negate + scale, run tesseract PSM 6."""
    mid = (start + end) / 2
    raw = extract_frame_crop(video, mid, CROP)
    # negate (white text → black on white for tesseract), then upscale
    negated = Image.fromarray(255 - np.array(raw.convert("L")))
    w, h = negated.size
    big = negated.resize((w * OCR_SCALE, h * OCR_SCALE), Image.LANCZOS)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img_path = Path(f.name)
    big.save(img_path)

    result = subprocess.run(
        ["tesseract", str(img_path), "stdout", "--psm", "6", "-l", "eng"],
        capture_output=True, text=True,
    )
    img_path.unlink()
    return result.stdout.strip().replace("\n", " ").replace("\r", " ")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: reconcile detected cards → 29 lyric lines
# ══════════════════════════════════════════════════════════════════════════════

def load_en_lyrics(song_json: Path) -> list[str]:
    data = json.loads(song_json.read_text())
    return [entry["en"] for entry in data["lyrics"]]


def normalize(s: str) -> str:
    return s.lower().replace("\n", " ").strip()


def reconcile(
    cards: list[tuple[float, float, str]],  # (start, end, ocr_text)
    lyric_lines: list[str],
) -> list[dict]:
    """
    Sequential greedy assignment: process lyric lines in order, consuming cards
    in order. Each line consumes either 1 or 2 consecutive cards — whichever
    gives a higher fuzzy score. This guarantees monotonicity.
    """
    norm_lyrics = [normalize(ln) for ln in lyric_lines]

    def ctext(i: int) -> str:
        return normalize(cards[i][2]) if i < len(cards) else ""

    results = []
    ci = 0  # next unused card index

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
            # Low confidence — consume one card to stay aligned, flag it
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

    if ci < len(cards):
        print(f"  !! {len(cards) - ci} unassigned cards after reconcile (ci={ci})")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=== Tragedia change-detection spike ===\n")

    # 1. Brightness edges
    print("STEP 1: brightness-edge detection")
    yavg = get_yavg_per_frame(VIDEO)
    raw_windows = yavg_to_windows(yavg)
    print(f"  → {len(raw_windows)} raw windows from brightness edges\n")

    # 2. Intra-text split — only attempt on windows longer than 5 s to avoid
    #    false splits on stable single-card frames
    print("STEP 2: intra-text split (avg-hash, windows > 5 s only)")
    cards_raw: list[tuple[float, float]] = []
    splits_applied = 0
    for i, (s, e) in enumerate(raw_windows):
        if e - s > 5.0:
            sub = split_window_on_content_change(VIDEO, s, e)
        else:
            sub = [(s, e)]
        if len(sub) > 1:
            splits_applied += 1
            print(f"  window {i} [{s:.2f}–{e:.2f}s]: split into {len(sub)} cards")
        cards_raw.extend(sub)
    print(f"  → {len(cards_raw)} cards after splitting ({splits_applied} windows split)\n")

    # 3. OCR
    print("STEP 3: OCR (tesseract PSM 6)")
    cards: list[tuple[float, float, str]] = []
    for j, (s, e) in enumerate(cards_raw):
        text = ocr_card(VIDEO, s, e)
        cards.append((s, e, text))
        print(f"  card {j:02d} [{s:.2f}–{e:.2f}s]: {text[:60]!r}")
    print()

    # 4. Reconcile
    print("STEP 4: reconcile cards → 29 lyric lines")
    lyric_lines = load_en_lyrics(SONG_JSON)
    reconciled = reconcile(cards, lyric_lines)
    print()

    # 5. Emit via serializer
    print("STEP 5: emit via serializer.write_timeline")
    entries = []
    for r in reconciled:
        if r["start"] is None:
            # Placeholder for unmatched lines — use 0,0 sentinel
            entries.append(TimelineEntry(start=0.0, end=0.0))
        else:
            entries.append(TimelineEntry(start=r["start"], end=r["end"]))

    write_timeline(entries, OUT_PATH)
    print(f"  → written to {OUT_PATH}\n")

    # 6. QA table
    print("=" * 100)
    print(f"{'#':>3}  {'START':>7}  {'END':>7}  {'STATUS':>9}  {'SCORE':>5}  {'EN LYRIC':<45}  OCR TEXT")
    print("-" * 100)
    matched_1_1 = 0
    merged = 0
    unmatched = 0
    for r in reconciled:
        li = r["line_idx"]
        s = f"{r['start']:.3f}" if r["start"] is not None else "  —  "
        e = f"{r['end']:.3f}" if r["end"] is not None else "  —  "
        lyric_short = r["en_text"].replace("\n", " / ")[:44]
        ocr_short = r["ocr_text"][:50]
        status = r["match_status"]
        score = r.get("score", 0)
        print(f"{li:>3}  {s:>7}  {e:>7}  {status:>9}  {score:>5}  {lyric_short:<45}  {ocr_short}")
        if status == "1:1":
            matched_1_1 += 1
        elif status == "merge":
            merged += 1
        else:
            unmatched += 1

    print("=" * 100)
    print(f"\nSummary: {matched_1_1} matched 1:1 | {merged} merged (two-card) | {unmatched} unmatched")
    print(f"Total cards detected: {len(cards)} | Total lyric lines: {len(lyric_lines)}")

    # Check monotonicity
    mono_ok = True
    prev_end = -1.0
    for r in reconciled:
        if r["start"] is not None and r["start"] < prev_end:
            print(f"  !! monotonicity violation at line {r['line_idx']}: start={r['start']} < prev_end={prev_end}")
            mono_ok = False
        if r["end"] is not None:
            prev_end = r["end"]
    if mono_ok:
        print("Monotonicity: OK")


if __name__ == "__main__":
    main()
