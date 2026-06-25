"""QA report — stub (implemented in feat/qa-report)."""
from __future__ import annotations

from pathlib import Path

from timeline_extractor.confidence import ConfidenceResult


def render_qa_report(
    song_name: str,
    reconciled: list[dict],
    confidence: list[ConfidenceResult],
    out_dir: Path,
) -> Path:
    """Write <song>-qa-report.md to out_dir. Returns the report path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{song_name}-qa-report.md"

    lines = [f"# QA Report — {song_name}\n"]
    lines.append("| # | band | canonical | OCR | start | end | dur | score | op | flags |")
    lines.append("|---|------|-----------|-----|-------|-----|-----|-------|----|-------|")

    for r, c in zip(reconciled, confidence):
        li = r["line_idx"]
        start = f"{r['start']:.3f}" if r["start"] is not None else "—"
        end = f"{r['end']:.3f}" if r["end"] is not None else "—"
        dur = f"{r['end'] - r['start']:.2f}" if r["start"] is not None else "—"
        canon = r["en_text"].replace("\n", " / ")[:40]
        ocr = r["ocr_text"][:40]
        score = r.get("score", 0)
        op = r["match_status"]
        flags = ", ".join(c.flags) if c.flags else ""
        lines.append(f"| {li} | {c.band.value} | {canon} | {ocr} | {start} | {end} | {dur} | {score} | {op} | {flags} |")

    report_path.write_text("\n".join(lines) + "\n")
    return report_path
