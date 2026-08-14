from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    """
    One recognized word with its timestamps, in seconds of the source
    audio's clock. Produced by the aligner (faster-whisper word
    timestamps), consumed by the anchoring stage.
    """
    text: str
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < 0:
            raise ValueError(f"Word times must be non-negative: {self}")


@dataclass(frozen=True)
class TimelineEntry:
    """
    One cue window. Matches TimelineEntry in songState.ts.
    Window is half-open [start, end).
    """
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < 0:
            raise ValueError(f"TimelineEntry times must be non-negative: {self}")
