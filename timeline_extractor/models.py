from dataclasses import dataclass


@dataclass(frozen=True)
class TimelineEntry:
    """
    One cue window. Matches TimelineEntry in songState.ts.
    Window is half-open [start, end). Zero-length entries (start == end)
    are never matched by the cue lookup — used as section-marker placeholders.
    """
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < 0:
            raise ValueError(f"TimelineEntry times must be non-negative: {self}")
