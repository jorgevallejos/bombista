"""
Serializes a list of TimelineEntry to the interchange JSON format consumed by
the translator's A+ timeline-import button (Prompt 16).

Format: { "timeline": [{ "start": 0.0, "end": 4.2 }, ...] }
See docs/output-contract.md for the full spec.
"""
import json
from pathlib import Path
from typing import Sequence

from .models import TimelineEntry


def validate_timeline(entries: Sequence[TimelineEntry]) -> None:
    """Raises ValueError if the sequence violates the translator's invariants."""
    previous_end = float("-inf")
    for i, entry in enumerate(entries):
        if entry.start < previous_end:
            raise ValueError(
                f"timeline[{i}]: times must be monotonic (start={entry.start} < previous end={previous_end})"
            )
        previous_end = entry.end


def to_dict(entries: Sequence[TimelineEntry]) -> dict:
    """Convert entries to the interchange dict (not yet written to disk)."""
    raise NotImplementedError("serializer not implemented yet — write the test first (TDD red)")


def write_timeline(entries: Sequence[TimelineEntry], path: Path) -> None:
    """Write the interchange JSON to *path*."""
    data = to_dict(entries)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
