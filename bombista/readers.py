"""
Input normaliser — B5. Anti-corruption layer, not a rewrite: the second
`extract` argument may now be a CP song JSON *or* a plain lyrics text
file. Either shape is converted into a CP-shaped song dict here, at the
boundary, before `pipeline.py` / `anchoring.py` / `aligner.py` ever run —
those modules are unchanged and stay unaware this module exists (see
docs/bombista-product-backlog.md §2, "Architecture — normalise at the
boundary").

Structural conversion only. No network, no API keys, no LLM calls —
running fully offline is a product property (see provenance.py's sibling
docstring pattern: this module builds the `_bombista` metadata block that
B2 will later decide where to write; it does not write it into a song
file itself).

Detection:
- Parses as JSON *and* is an object -> the CP path. Passed through
  unchanged (never mutated with `_bombista` — see `NormalisedInput`,
  below). Must carry a `lyrics` list; a JSON object without one is a
  malformed song file, not a lyrics text file, and fails loudly rather
  than being silently reinterpreted as plain text.
- Anything else (fails to parse as JSON, or parses to something other
  than an object) -> the plain-text path: one line per lyric line. Blank
  lines and `[Bracketed]` lines are stripped and reported in
  `strippedLines` (never converted to markers — markers no longer exist,
  see B3). Each surviving line is wrapped as `{"<lang>": text}`, trailing
  whitespace stripped, nothing else altered. `title` is the filename
  stem, verbatim.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NormalisedInput:
    """Result of normalising one `extract` lyrics-input argument.

    `song` is a CP-shaped dict, ready for the existing pipeline
    (`pipeline.lyric_lines` etc.) exactly as if it had been
    `json.loads`-ed from a CP song file. `bombista` is the `_bombista`
    metadata block, kept as a *separate* object rather than stuffed into
    `song` — this is what keeps the CP pass-through byte-faithful (assert
    dict equality against the parsed input). Where the block eventually
    gets written into a song file is B2's decision, not this module's.
    """

    song: dict
    bombista: dict


MISSING_CP_FIELDS: tuple[str, ...] = (
    "artist",
    "tempo",
    "media",
    "title_translations",
    "intro",
    "translations",
)
"""CP song fields the plain-text path can never infer from bare lyric
text. Reported verbatim in `_bombista.missing` (docs/bombista-product-
backlog.md §2, "Partial CP song JSON is still CP song JSON") so a human —
or an LLM asked to finish the job — knows exactly what's absent."""


def _is_blank(line: str) -> bool:
    return line.strip() == ""


def _is_bracketed(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= 2 and stripped.startswith("[") and stripped.endswith("]")


def _normalise_plain_text(raw_text: str, *, lang: str, title: str) -> NormalisedInput:
    lyrics: list[dict] = []
    stripped_lines: list[dict] = []

    for i, line in enumerate(raw_text.splitlines(), start=1):
        if _is_blank(line):
            stripped_lines.append({"line": i, "text": "", "reason": "blank"})
            continue
        if _is_bracketed(line):
            stripped_lines.append(
                {"line": i, "text": line.strip(), "reason": "bracketed"}
            )
            continue
        lyrics.append({lang: line.rstrip()})

    song = {"title": title, "lyrics": lyrics}
    bombista = {
        "completeness": "partial",
        "filledLang": lang,
        "missing": list(MISSING_CP_FIELDS),
        "strippedLines": stripped_lines,
    }
    return NormalisedInput(song=song, bombista=bombista)


def _normalise_cp(song: dict, *, path: Path) -> NormalisedInput:
    lyrics = song.get("lyrics")
    if not isinstance(lyrics, list):
        raise ValueError(
            f'{path}: JSON object has no "lyrics" list — this looks like a '
            "malformed CP song file, not a lyrics text file "
            "(refusing to silently reinterpret it as plain text)"
        )
    return NormalisedInput(song=song, bombista={"completeness": "complete"})


def song_completeness(song: dict) -> str:
    """`"complete"` or `"partial"` — B2's `promote` refusal rule.

    A song is complete when either:
      - it already carries `_bombista.completeness == "complete"` (an
        emitted `--emit songjson` candidate whose input was CP JSON), or
      - it carries any of `MISSING_CP_FIELDS` (`artist`, `tempo`, `media`,
        ...) — fields the plain-text path can never fill in. This second
        clause is what makes the rule work on the real song files in
        `songs/`, which predate the `_bombista` block entirely and so
        never satisfy the first clause.

    Anything else — no `_bombista` block, none of `MISSING_CP_FIELDS`
    present — is `"partial"`: exactly what the plain-text path produces.
    """
    bombista = song.get("_bombista")
    if isinstance(bombista, dict) and bombista.get("completeness") == "complete":
        return "complete"
    if any(field in song for field in MISSING_CP_FIELDS):
        return "complete"
    return "partial"


def read_lyrics_input(path: Path, *, lang: str = "es") -> NormalisedInput:
    """Detect and normalise *path* — a CP song JSON or a plain lyrics text
    file — into a `NormalisedInput`. `lang` is only used on the plain-text
    path (the language key each surviving line is wrapped in, and the ASR
    language elsewhere in the CLI); a CP file's own language keys are
    untouched. Raises ValueError (naming the problem) if *path* parses as
    a JSON object but has no `lyrics` list.
    """
    raw_text = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return _normalise_plain_text(raw_text, lang=lang, title=path.stem)

    if isinstance(parsed, dict):
        return _normalise_cp(parsed, path=path)

    # Valid JSON that isn't an object (e.g. a bare array or number) is not
    # a CP song shape either -- fall back to treating the raw text as
    # plain lines rather than guessing at a JSON structure that was never
    # meant to be a song file.
    return _normalise_plain_text(raw_text, lang=lang, title=path.stem)
