"""Confidence model — stub (implemented in feat/confidence-model)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Band(str, Enum):
    HIGH = "HIGH"
    REVIEW = "REVIEW"
    FAIL = "FAIL"


@dataclass
class ConfidenceResult:
    band: Band
    fuzzy_score: float
    ocr_confidence: float
    alignment_op: str
    flags: list[str]


def compute_band(
    fuzzy_score: float,
    ocr_confidence: float,
    alignment_op: str,
    t_fuzzy: float = 80.0,
    t_ocr: float = 60.0,
) -> ConfidenceResult:
    """Derive a HIGH/REVIEW/FAIL band from per-line signals."""
    flags = []

    if alignment_op in ("unmatched", "MISSING"):
        flags.append("missing-card")
        return ConfidenceResult(Band.FAIL, fuzzy_score, ocr_confidence, alignment_op, flags)

    if fuzzy_score < 40.0:
        flags.append("very-low-fuzzy")
        return ConfidenceResult(Band.FAIL, fuzzy_score, ocr_confidence, alignment_op, flags)

    if fuzzy_score < t_fuzzy:
        flags.append("low-fuzzy")
    if ocr_confidence < t_ocr:
        flags.append("low-ocr-confidence")

    if flags:
        return ConfidenceResult(Band.REVIEW, fuzzy_score, ocr_confidence, alignment_op, flags)

    return ConfidenceResult(Band.HIGH, fuzzy_score, ocr_confidence, alignment_op, [])
