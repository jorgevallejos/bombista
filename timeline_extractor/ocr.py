"""OCR each card window via Tesseract."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from timeline_extractor.split import extract_frame_crop

OCR_SCALE = 3


def ocr_card(video: Path, start: float, end: float, crop: str, lang: str = "eng") -> str:
    """Extract mid-window frame, negate + scale, run tesseract PSM 6."""
    mid = (start + end) / 2
    raw = extract_frame_crop(video, mid, crop)
    negated = Image.fromarray(255 - np.array(raw.convert("L")))
    w, h = negated.size
    big = negated.resize((w * OCR_SCALE, h * OCR_SCALE), Image.LANCZOS)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img_path = Path(f.name)
    big.save(img_path)

    result = subprocess.run(
        ["tesseract", str(img_path), "stdout", "--psm", "6", "-l", lang],
        capture_output=True, text=True,
    )
    img_path.unlink()
    return result.stdout.strip().replace("\n", " ").replace("\r", " ")


def ocr_card_with_confidence(
    video: Path, start: float, end: float, crop: str, lang: str = "eng"
) -> tuple[str, float]:
    """Return (text, mean_word_confidence) using tesseract TSV output."""
    mid = (start + end) / 2
    raw = extract_frame_crop(video, mid, crop)
    negated = Image.fromarray(255 - np.array(raw.convert("L")))
    w, h = negated.size
    big = negated.resize((w * OCR_SCALE, h * OCR_SCALE), Image.LANCZOS)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img_path = Path(f.name)
    big.save(img_path)

    result = subprocess.run(
        ["tesseract", str(img_path), "stdout", "--psm", "6", "-l", lang, "tsv"],
        capture_output=True, text=True,
    )
    img_path.unlink()

    words = []
    confidences = []
    for line in result.stdout.splitlines()[1:]:  # skip header
        parts = line.split("\t")
        if len(parts) >= 12:
            conf_str = parts[10]
            text = parts[11].strip()
            if text and conf_str != "-1":
                try:
                    confidences.append(float(conf_str))
                    words.append(text)
                except ValueError:
                    pass

    text = " ".join(words)
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return text, mean_conf
