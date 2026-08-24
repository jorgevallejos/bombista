"""The gate — `bombista validate`, and the tempo rule it shares.

Two strictness levels, and the difference between them is the difference
between two questions:

- **the default** asks *is this file sane*, and must tolerate work in
  progress. A song fresh from `bombista new` has no timeline yet and must
  still be savable, or the front door writes files the gate rejects.
- **`--for-performance`** asks *is this song finished*. It is the gate a
  song passes before it can be put in a setlist: a timeline must be
  present and consistent with the lyrics, and declared `media` must
  resolve. A **missing `tempo` is a warning here, not a failure** —
  pedal-driven mode works without one, and only the beat indicator, the
  count-in and clock-driven mode need it. A missing timeline or
  unresolvable media is a hard failure, because nothing can be displayed.

**Playability is checked here and not in Pregonero.** Every rule below
lives inside a single song file and needs no gig. If Pregonero
implemented its own there would be two understandings of SP JSON, and the
second would go stale the moment this one changed.

**Warnings are for what is correct but worth knowing**, and there are
three: an absent `tempo` (pedal-driven mode works without one), a
`linesHash` that no longer matches the lyrics (usually a corrected
translation, and only a human can say), and an absent `intro` (whatever
projects it simply stands dark). None of the three is a fault; all three
are things to learn before a gig rather than at one.

**Every problem is reported, never just the first** — a person fixing a
file wants all of it at once. That is why the module returns a list of
`Finding`s rather than raising: raising is a first-failure interface.

Pure and stdlib-only. Nothing here imports click, prints, or exits; the
CLI renders the findings and picks the exit code, and `serve` reuses
`validate_tempo` as the gate a typed-in tempo passes through.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .pipeline import is_lyric_item
from .provenance import compute_lines_hash
from .readers import _is_bracketed
from .serializer import validate_v2_envelope
from .writers import ENVELOPE_KEYS

__all__ = [
    "Finding",
    "REQUIRED_SONG_FIELDS",
    "TEMPO_KEYS",
    "errors",
    "warnings",
    "has_errors",
    "load_and_validate",
    "one_line",
    "render_findings",
    "resolve_media",
    "validate_song",
    "validate_tempo",
]

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    """One problem, and where in the file it is.

    `where` is a path into the song — `lyrics[7]`, `tempo.numerator`,
    `media.src` — because "the offending index" is the whole value of a
    validator over a positional format. `severity` is `"error"` (exit
    non-zero) or `"warning"` (say it, pass anyway).
    """

    severity: str
    where: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.where}: {self.message}"


REQUIRED_SONG_FIELDS: tuple[str, ...] = (
    "title",
    "artist",
    "notes",
    "title_translations",
    "lyrics",
)
"""The fields a song file must carry — the skeleton `bombista new` writes,
minus `intro`.

`intro` is offered by the skeleton but not required, because `serve`'s
from-scratch branch cannot supply one: a `.txt` has no source for it
(docs/bombista-serve-spec.md §10.2.1). Requiring it here would make
Bombista's own output fail Bombista's own gate."""

TEMPO_KEYS: tuple[str, ...] = ("bpm", "numerator", "denominator", "countInBars")
"""**`tempo` is written whole — or not written at all.** There is no valid
partial block (docs/bombista-serve-spec.md §11.5, checked against
Pregonero): `beatScheduler.ts` declares `numerator` and `denominator` as
required and `getBeatsPerBar` does `numerator % 3`, so a bpm-only block
yields NaN beats, bars and count-in — while `performedTempo.ts` degrades
perfectly. Correct scaling, broken pulse, no error anywhere.

Which is also why absence is safe and a partial block is not: Pregonero on
an absent block gives no pulse, no count-in, and scale pinned to 1."""

_POSITIVE_TEMPO_KEYS: tuple[str, ...] = ("bpm", "numerator", "denominator")


# ---------------------------------------------------------------------------
# selecting
# ---------------------------------------------------------------------------


def errors(findings: Iterable[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == ERROR]


def warnings(findings: Iterable[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == WARNING]


def has_errors(findings: Iterable[Finding]) -> bool:
    return any(f.severity == ERROR for f in findings)


# ---------------------------------------------------------------------------
# tempo — the one gate, shared by `validate` and `serve`'s review page
# ---------------------------------------------------------------------------


def _is_real_number(value: object) -> bool:
    """Numbers only. `True` is an `int` in Python and `True` is not a bpm."""
    return not isinstance(value, bool) and isinstance(value, (int, float))


def validate_tempo(tempo: object, *, where: str = "tempo") -> list[Finding]:
    """The whole-block rule, as findings.

    `bpm`, `numerator` and `denominator` must be present and positive.
    `countInBars` must be present and a whole number of bars — **zero is a
    real answer**, which is why it is the one field not required to be
    positive. Unknown keys are refused: a `tempo` carrying something
    Pregonero does not read is a value someone believes is doing work.

    Bombista never derives, measures or guesses any of these. The
    performer types them in, from the source that produced the audio,
    where they are exact (rules 4 and 5; B14 was dropped for this).
    """
    if not isinstance(tempo, dict):
        return [
            Finding(
                ERROR,
                where,
                "must be an object with bpm, numerator, denominator and "
                f"countInBars — got {type(tempo).__name__}",
            )
        ]

    found: list[Finding] = []
    for key in TEMPO_KEYS:
        if key not in tempo:
            found.append(
                Finding(
                    ERROR,
                    f"{where}.{key}",
                    "missing — a tempo block is written whole (bpm, numerator, "
                    "denominator, countInBars) or not at all",
                )
            )
            continue

        value = tempo[key]
        if key in _POSITIVE_TEMPO_KEYS:
            if not _is_real_number(value) or value <= 0:
                found.append(
                    Finding(ERROR, f"{where}.{key}", f"must be a positive number, got {value!r}")
                )
        elif not _is_real_number(value) or value < 0 or value != int(value):
            found.append(
                Finding(
                    ERROR,
                    f"{where}.{key}",
                    f"must be a whole number of bars, 0 or more, got {value!r}",
                )
            )

    for key in sorted(set(tempo) - set(TEMPO_KEYS)):
        found.append(
            Finding(
                ERROR,
                f"{where}.{key}",
                "unknown key — a tempo block carries exactly bpm, numerator, "
                "denominator and countInBars",
            )
        )
    return found


# ---------------------------------------------------------------------------
# media
# ---------------------------------------------------------------------------


def _media_search_path(song_path: Path | None, media_dirs: Sequence[Path]) -> list[Path]:
    """Where a relative `media.src` is looked for, in order: the
    directories given with `--media-dir`, then the song file's own.

    `media.src` is a **logical filename** — Pregonero resolves it through
    a per-machine map (`mediaPathStore.ts`), because the delivery video
    lives wherever that machine keeps it. There is no canonical location
    to hard-code, so the gate is told rather than guessing, and the
    failure names every directory it tried.

    **Which makes this check necessarily partial, and it must not be read
    as a guarantee.** *The media resolves* is a fact about the machine the
    gate ran on and the directories it was handed, not about the song
    file. It is worth having because the machine that runs the gate is the
    machine that runs the gig — but a pass here says the file was found
    *here*, and says nothing about anywhere else.
    """
    path = [Path(d) for d in media_dirs]
    if song_path is not None:
        path.append(Path(song_path).parent)
    return path or [Path(".")]


def resolve_media(
    src: str, *, song_path: Path | None = None, media_dirs: Sequence[Path] = ()
) -> Path | None:
    """The file `src` names, or None. An absolute `src` is used as given."""
    candidate = Path(src)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    for directory in _media_search_path(song_path, media_dirs):
        resolved = directory / candidate
        if resolved.exists():
            return resolved
    return None


def _validate_media(
    media: object, *, song_path: Path | None, media_dirs: Sequence[Path]
) -> list[Finding]:
    if not isinstance(media, dict):
        return [Finding(ERROR, "media", f"must be an object, got {type(media).__name__}")]

    src = media.get("src")
    if not isinstance(src, str) or not src.strip():
        return [
            Finding(ERROR, "media.src", f"must be a non-empty filename, got {src!r}")
        ]

    if resolve_media(src, song_path=song_path, media_dirs=media_dirs) is not None:
        return []

    looked = ", ".join(str(d) for d in _media_search_path(song_path, media_dirs))
    return [
        Finding(
            ERROR,
            "media.src",
            f"{src!r} does not resolve — looked in: {looked}. Pass --media-dir "
            "to say where the file lives.",
        )
    ]


# ---------------------------------------------------------------------------
# lyrics
# ---------------------------------------------------------------------------


def _validate_lyrics(items: object, lang: str) -> list[Finding]:
    if not isinstance(items, list):
        return [Finding(ERROR, "lyrics", f"must be a list, got {type(items).__name__}")]

    found: list[Finding] = []
    for i, item in enumerate(items):
        if not is_lyric_item(item, lang):
            found.append(
                Finding(
                    ERROR,
                    f"lyrics[{i}]",
                    f"not a lyric line — every entry must be an object carrying "
                    f"the {lang!r} key as a string",
                )
            )
            continue
        if _is_bracketed(item[lang]):
            found.append(
                Finding(
                    ERROR,
                    f"lyrics[{i}]",
                    f"section marker {item[lang].strip()!r} — a lyrics array "
                    "carries sung lines only, and one extra entry shifts every "
                    "timeline entry after it",
                )
            )
    return found


def _has_intro_text(intro: object) -> bool:
    """Whether *intro* carries any text at all, in any language.

    Any language, not the chosen one: a tagline in some language beats
    none, and which one gets projected is the consumer's decision, not the
    gate's. Anything that is not a string or a mapping of them carries no
    text by definition — this reports, it does not repair.
    """
    if isinstance(intro, str):
        return bool(intro.strip())
    if isinstance(intro, dict):
        return any(isinstance(v, str) and v.strip() for v in intro.values())
    return False


# ---------------------------------------------------------------------------
# the timing keys
# ---------------------------------------------------------------------------


def _validate_timeline(song: dict, *, lyric_count: int, for_performance: bool) -> list[Finding]:
    declared = "timelineVersion" in song
    has_timeline = "timeline" in song

    if not declared and not has_timeline:
        # The 11-song regression case named in the contract: a song with no
        # timeline and no version is a perfectly normal un-timed song.
        if for_performance:
            return [
                Finding(
                    ERROR,
                    "timeline",
                    "no timeline — a song without one cannot be displayed, and "
                    "cannot enter a setlist. Run `bombista align`, then "
                    "`bombista promote`.",
                )
            ]
        return []

    if not declared:
        return [
            Finding(
                ERROR,
                "timelineVersion",
                "missing, but the song carries a timeline — a timeline with no "
                "version is a v1 leftover or a half-written file. Never coerced; "
                "run `bombista migrate` to rebase it onto the v2 start cue.",
            )
        ]

    envelope = {key: song.get(key) for key in ENVELOPE_KEYS}
    version = envelope["timelineVersion"]
    if type(version) is not int or version != 2:
        return [
            Finding(
                ERROR,
                "timelineVersion",
                f"must be exactly 2 (never coerced) — got {version!r}",
            )
        ]

    try:
        validate_v2_envelope(envelope)
    except ValueError as exc:
        message = str(exc)
        where = "leadIn" if message.startswith("leadIn") else "timeline"
        return [Finding(ERROR, where, message)]

    entries = envelope["timeline"]
    if len(entries) != lyric_count:
        return [
            Finding(
                ERROR,
                "timeline",
                f"{len(entries)} entries for {lyric_count} lyric lines — the "
                "timeline is matched to lyrics by position, so a count that "
                "disagrees means every entry past the difference is wrong",
            )
        ]
    return []


def _validate_lines_hash(song: dict, *, lang: str) -> list[Finding]:
    """B4's guard, at the gate: does the stored hash still describe these
    lyrics?

    A **warning**, matching `promote`'s stance — the timeline may still be
    right, and only a human can say. What it cannot do is stay silent: the
    positional fragility this hash exists to expose is the failure class
    the whole tool is built against.
    """
    recorded = song.get("linesHash")
    if not isinstance(recorded, str):
        return []

    items = song.get("lyrics")
    if not isinstance(items, list) or not all(is_lyric_item(i, lang) for i in items):
        return []

    current = compute_lines_hash([item[lang] for item in items])
    if current == recorded:
        return []
    return [
        Finding(
            WARNING,
            "linesHash",
            "does not match the lyrics in this file — a line was likely "
            "inserted, deleted or reordered since the timeline was measured, "
            f"and every entry from there on may point at the wrong line "
            f"(recorded {recorded}, now {current})",
        )
    ]


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------


def validate_song(
    song: object,
    *,
    song_path: Path | None = None,
    lang: str = "es",
    for_performance: bool = False,
    media_dirs: Sequence[Path] = (),
) -> list[Finding]:
    """Every problem with *song*, in file order. Empty means it passes.

    See the module docstring for what each level asks. `song_path` is used
    only to resolve a relative `media.src` and to name where the gate
    looked; `media_dirs` adds directories ahead of it.
    """
    if not isinstance(song, dict):
        return [
            Finding(
                ERROR,
                "<file>",
                f"a song file must be a JSON object, got {type(song).__name__}",
            )
        ]

    found: list[Finding] = []

    for field in REQUIRED_SONG_FIELDS:
        if field not in song:
            found.append(
                Finding(
                    ERROR,
                    field,
                    "required field is missing — `bombista new` writes a "
                    "skeleton carrying every one of them",
                )
            )

    for field in ("title", "artist", "notes"):
        if field in song and not isinstance(song[field], str):
            found.append(
                Finding(ERROR, field, f"must be a string, got {type(song[field]).__name__}")
            )

    if "title_translations" in song and not isinstance(song["title_translations"], dict):
        found.append(
            Finding(
                ERROR,
                "title_translations",
                f"must be an object keyed by language, got "
                f"{type(song['title_translations']).__name__}",
            )
        )

    if "lyrics" in song:
        found.extend(_validate_lyrics(song["lyrics"], lang))

    if "tempo" in song:
        found.extend(validate_tempo(song["tempo"]))
    elif for_performance:
        found.append(
            Finding(
                WARNING,
                "tempo",
                "no tempo block — pedal-driven mode works without one, but the "
                "beat indicator, the count-in and clock-driven mode all need "
                "it. Type it in on `bombista serve`'s review page.",
            )
        )

    if for_performance and not _has_intro_text(song.get("intro")):
        found.append(
            Finding(
                WARNING,
                "intro",
                "no intro text — whatever projects the song's intro will stand "
                "dark. That is correct behaviour and not a fault, but it is "
                "better known before a gig than at one. `intro` is still not "
                "required: a song built from plain text has no source for one.",
            )
        )

    if "media" in song:
        found.extend(
            _validate_media(song["media"], song_path=song_path, media_dirs=media_dirs)
        )

    items = song.get("lyrics")
    found.extend(
        _validate_timeline(
            song,
            lyric_count=len(items) if isinstance(items, list) else 0,
            for_performance=for_performance,
        )
    )

    if for_performance:
        found.extend(_validate_lines_hash(song, lang=lang))

    return found


def load_and_validate(
    path: Path,
    *,
    lang: str = "es",
    for_performance: bool = False,
    media_dirs: Sequence[Path] = (),
) -> list[Finding]:
    """`validate_song` over a file — malformed JSON is a finding, not a
    traceback. The gate is a terminal, and a terminal answers."""
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [Finding(ERROR, "<file>", f"cannot be read ({exc.strerror})")]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [Finding(ERROR, "<file>", f"not valid JSON — {exc}")]

    return validate_song(
        parsed,
        song_path=path,
        lang=lang,
        for_performance=for_performance,
        media_dirs=media_dirs,
    )


def render_findings(path: Path | str, findings: Sequence[Finding]) -> list[str]:
    """The findings as lines for a terminal, headline first.

    Returns the lines rather than printing them — the same reason
    `songfile.timeline_diff` does: nothing in this module decides where its
    output goes, which is what lets a route reuse it.
    """
    problems = errors(findings)
    notes = warnings(findings)

    if problems:
        head = f"{path}: {len(problems)} problem{'' if len(problems) == 1 else 's'}"
    else:
        head = f"{path}: ok"
    if notes:
        head += f" ({len(notes)} warning{'' if len(notes) == 1 else 's'})"

    lines = [head]
    lines.extend(f"  {f.where}: {f.message}" for f in problems)
    lines.extend(f"  warning — {f.where}: {f.message}" for f in notes)
    return lines


def one_line(findings: Sequence[Finding]) -> str:
    """The findings as a single sentence, for somewhere a list cannot go —
    a 400 body, a status line under a control.

    **Identical messages are grouped**, and that is the whole point: three
    missing tempo keys are one rule broken three times, and a control that
    says the same twenty words three times is a control nobody reads to
    the end of.
    """
    grouped: dict[str, list[str]] = {}
    for finding in findings:
        grouped.setdefault(finding.message, []).append(finding.where)
    return "; ".join(
        f"{', '.join(where)}: {message}" for message, where in grouped.items()
    )
