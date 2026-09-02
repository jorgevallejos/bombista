"""
`bombista serve` — the local review process, and the JSON routes page 2
talks to (B20 §1, §3, §4).

An HTTP server on the loopback interface, in the same Python process the
CLI runs in. It serves the three-step flow — `1 Input · 2 Review · 3
Output` — and the JSON routes behind it:

    GET    /              -> step 1, or step 2 when a session was booted
    GET    /input         page 1 — the song, its media source, two defaults
    GET    /processing    page 1.5 — the run, as a state rather than a spinner
    GET    /output        page 3 — the SP JSON, read-only, and three downloads

    GET    /api/session   the lines, their machine anchors, bands, signals,
                          ASR context, leadIn and the run's provenance
    POST   /api/reanchor  {"overrides": {"<line>": <seconds>}} -> the full
                          per-line result, RE-ANCHORED against the audio
    POST   /api/emit      write a new SP JSON through the one merge path.
                          With no `out`, it writes `default_out_path` — which
                          is what page 3's `Save to the catalogue` presses
    POST   /api/tempo     {"tempo": {...}|null} -> the session, with the
                          typed-in block set or cleared. Whole, or refused.
    POST   /api/run       start a run; GET it for phases; DELETE to cancel
    GET    /api/lyrics    what a lyrics file declares, and the general
                          information page 1 prefills from it, before it is run
    GET    /api/browse    a directory listing, because the server needs a
                          real path and a browser File object has none (§9.6)
    GET    /api/download  the three downloads, as bytes — song, timeline, report
    GET    /review        page 2 — the list of lines, and the one control
    GET    /review/rows   that list again, as markup, after a re-anchor
    GET    /api/audio     the take, as bytes, so the page needs no relative src.
                          With `?path=`, the media file page 1 names instead —
                          the tap control needs the take audible at step 1,
                          where there is no session yet

**It re-anchors; it never shifts.** `anchoring.py` is forward-only: an
override advances the scan to the first word after the corrected time, so
every following line is re-derived *against the word stream*. A blanket
delta would displace lines that were measured correctly — the exact
HIGH-confidence rows the report exists to certify. There is no code here
that adds an offset to anything (§3, invariant 5).

**Nothing is imported from `cli.py`** (invariant 1). Both front ends call
the same extracted modules, so the routes and the command cannot drift
apart — that drift is the risk the whole item is shaped around (§6).

**Loopback only** (invariant 7). See `LOOPBACK_HOST`.

**Page 2 is the one page not here.** It is the next item, built against
the routes above and inheriting `pages.STYLESHEET` rather than being
retrofitted with it. `/review` answers 404 until then rather than serving
a stub that could be mistaken for the page; the step bar still links to
it, because the link is the navigation and the page is what fills it.
"""
from __future__ import annotations

import json
import mimetypes
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import pages
from .aligner import load_words, load_words_meta, save_words, transcribe_words
from .anchoring import SIGNAL_GLOSSES, anchor_lines, parse_anchor_overrides
from .models import Word
from .pipeline import build_timeline, lyric_lines, normalize_to_lead_in
from .provenance import build_provenance, compute_lines_hash, words_meta
from .readers import read_lyrics_input
from .skeleton import title_from_song_id
from .report import band_counts, render_qa_report
from .serializer import to_dict
from .validation import TEMPO_KEYS, one_line, validate_tempo, without_zero_count_in
from .writers import ENVELOPE_KEYS, merge_envelope

__all__ = [
    "LOOPBACK_HOST",
    "Session",
    "create_server",
    "load_session",
    "session_payload",
    "set_tempo",
    "build_sp_json",
    "default_out_path",
    "emit_sp_json",
    "lead_in_source",
]

LOOPBACK_HOST = "127.0.0.1"
"""The only address this server ever binds. Invariant 7, and the one way
this design could accidentally become the hosted service §1 rules out: a
dev server reachable on the LAN is holding someone else's audio on
someone else's machine. `create_server` takes a host argument — explicit
beats implicit for the thing that matters most here — and refuses every
value but this one."""

WORDS_FILENAME = "asr-words.jsonl"

_JSON = "application/json; charset=utf-8"


# ---------------------------------------------------------------------------
# the session — what a previous `align` left on disk
# ---------------------------------------------------------------------------


@dataclass
class Session:
    """One `serve` run's immutable inputs, plus the machine's own answer.

    `machine_starts` and `machine_bands` are what `anchor_lines` gives
    with no overrides at all. They are computed once, at load, and never
    recomputed: they are the "before" a hand-set line is recorded against
    — and the before/after §8.5 puts on the row — and re-deriving them
    from a run that already carries overrides would quietly turn the
    human's correction into the machine's value.
    """

    staging_dir: Path
    lyrics_path: Path
    song: dict
    lines: list[str]
    lang: str
    words: list[Word]
    lines_hash: str
    provenance: dict | None
    machine_starts: list[float | None]
    machine_bands: list[str]
    input_paths: frozenset[Path]
    audio_path: Path | None = None
    model_size: str = "medium"
    from_scratch: bool = False
    manual: bool = False
    """No recording, so no timeline, so nothing to review.

    **A song with words and no recording is a legitimate song** (Jorge,
    2026-09-02): it is performed by advancing the lines by hand, which is a
    normal night. The rule that a song could not leave step 1 without audio
    was written when a timeline was assumed.

    A manual session carries no words and no anchors, `/review` sends you
    to the output, and `build_sp_json` writes **none of the five timing
    keys** — not even `linesHash`, which guards a timeline that is not
    there, and not `timelineSignedOff`, which would claim a human reviewed
    one."""
    tempo: dict | None = None
    stripped_lines: list[dict] = field(default_factory=list)
    overrides: dict[int, float] = field(default_factory=dict)
    signed_off: str | None = None
    """The live state of the review, and the reason this is not frozen.

    `tempo` starts as whatever the song already carried and is what page 2
    has typed in since — `None` meaning the song has none, which is a real
    state and the honest one (§10.2.1, `songs@c5adf65`). It is never
    derived from anything: `set_tempo` is the only way it changes.

    `overrides` is what page 2 has set so far — page 3 serialises the
    timeline *as it stands*, and a download is a plain navigation that
    cannot carry a body, so the corrections live here rather than being
    posted with every request. `signed_off` is B19's clause made
    enforceable: it is stamped the first time a JSON download is taken and
    reused thereafter, because the sign-off is recorded once and is not a
    budget (§9.5)."""


def _input_paths(staging_dir: Path, lyrics_path: Path, stem: str) -> frozenset[Path]:
    """Every path this session's run reads or wrote. `/api/emit` refuses to
    write to any of them (invariant 6) — always a new file, which removes
    the file-changed-on-disk race and keeps the merge a pure function.

    Named by `align`'s own convention rather than listed from the
    directory, and computed once at load. A glob would do two wrong
    things: it would miss an artifact that is not on disk yet, and it
    would swallow `emit`'s own output, so a second emit to the same path
    would be refused for colliding with the first.

    Resolved, because `..` and a symlink reach the same file under a
    different spelling and a string comparison would miss both.
    """
    paths = {
        lyrics_path,
        staging_dir / WORDS_FILENAME,
        staging_dir / f"{stem}-timeline.json",
        staging_dir / f"{stem}-report.json",
        staging_dir / f"{stem}-song.json",
        staging_dir / f"{stem}-qa-report.md",
        staging_dir / f"{stem}-review.html",
    }
    paths.update(staging_dir.glob(f"{stem}-*.srt"))
    paths.update(staging_dir.glob(f"{stem}-*.lrc"))
    return frozenset(path.resolve() for path in paths)


def _from_scratch_song(song: dict, *, lang: str, info: dict | None) -> dict:
    """§10.2.1's from-scratch shape — a `.txt` came in, so the song file
    does not exist yet and Bombista writes one with only what a plain text
    plus step 1 can honestly supply.

    **There is no meter here, and that is the point** (§11.5, decided
    2026-08-16). An earlier pass wrote `{"bpm": <a number page 1 asked
    for>}`. Checked against Pregonero: `performedTempo.ts` degrades
    perfectly without a tempo block, but `beatScheduler.ts` declares
    `numerator` and `denominator` as required and does `numerator % 3`, so
    a bpm-only block returns NaN and the visual pulse and count-in break
    while the scaling keeps working. That is the same split brain
    `songs@c5adf65` deleted the placeholder blocks to avoid, one key
    deeper. So: **`tempo` is written whole or not at all**, Bombista
    cannot write it whole — it never measures a meter and will not invent
    `4/4` — and therefore it does not write it. The performer supplies
    these values and types them in by hand, where they are exact.
    """
    info = info or {}
    resolved_title = _text(info.get("title")) or song.get("title") or ""
    return {
        "title": resolved_title,
        "artist": _text(info.get("artist")),
        "notes": _text(info.get("notes")),
        # Not a translation collected from anyone — it is the title, in
        # the one language this file has, which is why it survives the
        # 2026-09-02 rule that no tool asks for a translation. Jorge's
        # sketch of 2026-08-15 fixes the shape.
        "title_translations": {lang: resolved_title},
        "lyrics": song.get("lyrics", []),
    }


# ---------------------------------------------------------------------------
# the song's general information — what a `.txt` cannot carry (step 6)
# ---------------------------------------------------------------------------

INFO_KEYS = ("title", "artist", "notes")
"""The keys page 1 collects, and the reason it collects them: a plain text
file carries words and nothing else, so without this the flow can only
ever make a song with no artist and no notes.

**`title_translations` was here and came off on 2026-09-02.** Translation
is not Bombista's concern — lyric translations are written outside the
suite in the file, and the title follows the same rule: *if it is a
translation, it was written elsewhere and the file already carries it*.
What a file carries still passes through untouched, because this list is
what page 1 may **replace**, and every key absent from it is left alone.

They are the song file's own key names on the wire too. A second
vocabulary between the page and the format would be a second thing to keep
true (§10.2)."""

CATALOGUE_ORDER = ("title", "artist", "notes", "title_translations", "tempo", "intro", "lyrics")
"""§10.2's key order, fixed against `songs/pimiento.json` — the order a key
Bombista adds is inserted in.

It decides **placement only**, never rewriting: a song that already
declares a key keeps the position it gave it, because the catalogue's real
files disagree with each other (`tempo` sits before `title_translations`
in libertad, after it in pimiento) and both are valid."""


def _text(value: object) -> str:
    """A typed-in string, trimmed. Anything else is not a string the
    performer typed, and reads as blank rather than as a `null` a consumer
    would have to step around."""
    return value.strip() if isinstance(value, str) else ""


def _place_key(song: dict, key: str, value: object) -> dict:
    """Return *song* with *key* set, in `CATALOGUE_ORDER`'s position when
    the song does not already have one.

    Appending at the end would be valid JSON and would still make every
    file Bombista touched look unlike every file it did not.
    """
    if key in song:
        return {name: (value if name == key else held) for name, held in song.items()}

    follows = CATALOGUE_ORDER[CATALOGUE_ORDER.index(key) + 1 :]
    placed: dict = {}
    for name, held in song.items():
        if name in follows and key not in placed:
            placed[key] = value
        placed[name] = held
    if key not in placed:
        placed[key] = value
    return placed


def _place_info(song: dict, info: dict | None) -> dict:
    """Apply page 1's general information to *song*.

    **`None` is not the same as an empty block.** A session booted straight
    into a review (`serve <staging> <song>`) was never asked these
    questions, and passes every key through byte for byte; page 1 always
    answers them, and an answer it gives is the answer.
    """
    if info is None:
        return song

    placed = song
    for key in INFO_KEYS:
        if key not in info:
            continue
        placed = _place_key(placed, key, _text(info[key]))
    return placed


def song_information(song: dict) -> dict:
    """What page 1 shows in the general-information block before anyone
    retypes it — read off the file, never assembled twice.

    `title_translations` is deliberately absent: the page has no field for
    it since 2026-09-02, and reporting a value nothing renders is an
    invitation to build the field back."""
    return {key: _text(song.get(key)) for key in INFO_KEYS}


def _find_provenance(staging_dir: Path, stem: str) -> dict | None:
    """The provenance of the run being reviewed, read back from whatever
    `align` was asked to write.

    Recorded, not recomputed. `build_provenance` streams the audio's
    sha256 and stamps `extractedAt` — running it here would describe *this*
    moment, not the run whose timings are on screen, and would make booting
    a session wait on a hash of a file the routes never otherwise touch.

    Three carriers, richest first: the report JSON, an `--emit songjson`
    output's `_bombista.source`, and — added with §11.10 — the
    `asr-words.meta.json` sibling. The sibling carries less (no duration,
    no tool version) but it is always there after a transcription, which
    the other two are not: the default `--emit timeline` writes a bare
    envelope, which by contract cannot carry provenance. It is also the
    only one a run started from page 1 leaves behind.

    Returns None when the directory holds none of the three. The caller
    says so rather than inventing one.
    """
    report_json = staging_dir / f"{stem}-report.json"
    if report_json.exists():
        data = json.loads(report_json.read_text(encoding="utf-8"))
        source = data.get("source")
        if isinstance(source, dict):
            return source

    song_json = staging_dir / f"{stem}-song.json"
    if song_json.exists():
        data = json.loads(song_json.read_text(encoding="utf-8"))
        bombista = data.get("_bombista")
        if isinstance(bombista, dict) and isinstance(bombista.get("source"), dict):
            return bombista["source"]

    return load_words_meta(staging_dir / WORDS_FILENAME)


def load_session(
    staging_dir: Path,
    lyrics_path: Path,
    *,
    lang: str = "es",
    audio_path: Path | None = None,
    model_size: str = "medium",
    info: dict | None = None,
    manual: bool = False,
) -> Session:
    """Boot a session from a staging directory and the lyrics it was
    aligned against.

    The staging directory supplies the word stream and the QA state; the
    lyrics file supplies the lines. It is a separate argument because
    `align` never copies its lyrics input into staging — a default staging
    directory holds `asr-words.jsonl`, the QA report and a bare timeline,
    and nothing that carries the lyric text.

    Raises ValueError naming what is missing. The caller renders it.
    """
    words_path = staging_dir / WORDS_FILENAME
    if not manual and not words_path.exists():
        raise ValueError(
            f"{staging_dir}: no {WORDS_FILENAME} — this is not an `align` "
            "staging directory, or the run did not finish"
        )

    normalised = read_lyrics_input(lyrics_path, lang=lang)
    from_scratch = normalised.bombista.get("completeness") == "partial"
    song = (
        _from_scratch_song(normalised.song, lang=lang, info=info)
        if from_scratch
        else _place_info(normalised.song, info)
    )
    items = song.get("lyrics")
    if not isinstance(items, list):
        raise ValueError(f'{lyrics_path}: song JSON has no "lyrics" list')

    lines = lyric_lines(items, lang)
    if not lines:
        raise ValueError(f"{lyrics_path}: no lyric lines carry the {lang!r} language key")

    # A manual session has nothing to transcribe and nothing to anchor. The
    # empty word list is not a degraded run — it is the honest state of a
    # song that was never given a recording, and everything downstream
    # branches on `manual` rather than on the emptiness.
    words = [] if manual else load_words(words_path)
    machine = [] if manual else anchor_lines(words, lines)

    # Read, not computed: whatever the song already declares. `align` has
    # no opinion about a tempo and neither does this, but a review that
    # showed an empty control over a song that has one would invite a
    # human to retype a value that was already right.
    declared = song.get("tempo")
    if isinstance(declared, dict):
        declared = without_zero_count_in(declared)

    return Session(
        audio_path=audio_path,
        model_size=model_size,
        from_scratch=from_scratch,
        manual=manual,
        tempo=declared if isinstance(declared, dict) else None,
        stripped_lines=normalised.bombista.get("strippedLines") or [],
        staging_dir=staging_dir,
        lyrics_path=lyrics_path,
        song=song,
        lines=lines,
        lang=lang,
        words=words,
        lines_hash=compute_lines_hash(lines),
        provenance=_find_provenance(staging_dir, lyrics_path.stem),
        machine_starts=[anchor.start for anchor in machine],
        machine_bands=[anchor.band for anchor in machine],
        input_paths=_input_paths(staging_dir, lyrics_path, lyrics_path.stem),
    )


# ---------------------------------------------------------------------------
# the one computation both mutating routes run
# ---------------------------------------------------------------------------


def _overrides_from_body(session: Session, body: dict) -> dict[int, float]:
    """`{"3": 36.32}` -> the mapping `anchor_lines` takes, via
    `anchoring.parse_anchor_overrides`.

    That function already exists for exactly this — its docstring names
    "a stepper's value posted by serve's review page" beside `--anchor` —
    and it owns the range check, so an out-of-range line is refused here
    in the same words the CLI refuses it in.
    """
    raw = body.get("overrides") or {}
    if not isinstance(raw, dict):
        raise ValueError('"overrides" must be an object of line -> seconds')

    # Line 0 goes through here like every other line (§8.6, settled
    # 2026-08-16). This function used to refuse it, on the argument that a
    # stepper on line 0 silently breaks the v2 contract. It does not:
    # `normalize_to_lead_in` runs on emit no matter how the value got
    # there, banks line 0's onset into `leadIn.durationSec` and writes
    # entry 0 as `0.00`. Invariant 3 is enforced by the normaliser, and
    # refusing the edit was defending it at the wrong layer.
    return parse_anchor_overrides(
        [f"{line}={seconds}" for line, seconds in raw.items()], len(session.lines)
    )


def _anchor(session: Session, overrides: dict[int, float]) -> dict[str, Any]:
    """Re-run the anchoring and rebuild the timeline. The extracted
    functions do all of it; nothing here computes a time."""
    anchors = anchor_lines(session.words, session.lines, overrides=overrides or None)
    entries = build_timeline(anchors, session.words, session.song["lyrics"], lang=session.lang)
    lead_in, normalized = normalize_to_lead_in(entries)
    return {
        "anchors": anchors,
        "entries": entries,
        "lead_in": lead_in,
        "normalized": normalized,
        "lead_in_source": lead_in_source(overrides),
    }


def lead_in_source(overrides: dict[int, float]) -> str:
    """`measured` | `manual` — the timeline v2 contract's own two words for
    where `leadIn.durationSec` came from.

    Line 0's onset *is* the lead-in (the normaliser banks it), and since
    §8.6 line 0 can be hand-set. So the lead-in is `manual` exactly when
    line 0 carries an override and `measured` otherwise. A correction
    anywhere else is not a claim about where the song starts.

    Note the word: the mockup and this repo's prose both say *hand-set*,
    and the interchange format does not carry it —
    `docs/timeline-v2-contract.md` takes `measured` | `manual` | `none`,
    is frozen, and Pregonero validates against exactly those three.
    """
    return "manual" if 0 in overrides else "measured"


def session_payload(session: Session, overrides: dict[int, float] | None = None) -> dict:
    """The shape both `/api/session` and `/api/reanchor` answer with.

    **Times are raw audio-clock seconds** — the clock the QA report and
    `--anchor` use, and the clock the audio element plays in. The
    cue-relative conversion happens on emit and is never shown: two clocks
    on one page is a real risk, and only one of them is ever visible (§8.3).
    """
    overrides = overrides or {}
    result = _anchor(session, overrides)
    anchors = result["anchors"]
    entries = result["entries"]

    lines = []
    for anchor in anchors:
        i = anchor.line_index
        entry = entries[i]
        line: dict[str, Any] = {
            "i": i,
            "text": session.lines[i],
            "start": entry.start,
            "end": entry.end,
            "band": anchor.band,
            "signals": list(anchor.signals),
            "signalGlosses": {
                signal: SIGNAL_GLOSSES[signal]
                for signal in anchor.signals
                if SIGNAL_GLOSSES.get(signal)
            },
            "machineStart": session.machine_starts[i],
            "machineBand": session.machine_bands[i],
            "handSet": i in overrides,
        }
        if anchor.asr_context:
            line["asrContext"] = anchor.asr_context
        lines.append(line)

    envelope = to_dict(
        result["lead_in"],
        result["normalized"],
        session.song,
        source=result["lead_in_source"],
    )
    counts = band_counts(anchors)

    return {
        "title": session.song.get("title", session.lyrics_path.stem),
        "lang": session.lang,
        "linesHash": session.lines_hash,
        "timelineSignedOff": session.signed_off,
        "leadIn": envelope["leadIn"],
        "provenance": session.provenance,
        "fromScratch": session.from_scratch,
        "tempo": session.tempo,
        "bands": {band: counts[band] for band in ("HIGH", "REVIEW", "FAIL")},
        "lines": lines,
    }


# ---------------------------------------------------------------------------
# emit — a new SP JSON, through the one merge path
# ---------------------------------------------------------------------------

OWNED_KEYS = ("linesHash", "timelineSignedOff")
"""The two keys Bombista owns that are not part of the timeline v2
envelope (§10.2). `linesHash` sits between `lyrics` and `timelineVersion`
— the boundary between what it guards and what it protects — and
`timelineSignedOff` sits beside it."""


def _place_owned_keys(song: dict, *, lines_hash: str, signed_off: str | None) -> dict:
    """Insert `linesHash` and `timelineSignedOff` immediately before
    `timelineVersion`, preserving every other key's order.

    Order is not decoration here: §10.2 fixes the real song-file key order
    against `songs/pimiento.json`, and Bombista's five keys travel in it.
    """
    placed: dict = {}
    for key, value in song.items():
        if key in OWNED_KEYS:
            continue
        if key == "timelineVersion":
            placed["linesHash"] = lines_hash
            placed["timelineSignedOff"] = signed_off
        placed[key] = value
    return placed


def set_tempo(session: Session, tempo: object) -> None:
    """Type a tempo in, or clear it. The only way `session.tempo` moves.

    **Whole, or refused.** `validation.validate_tempo` is the gate, and it
    is the same one `bombista validate` runs — there is one understanding
    of a valid tempo block in this repo, not one per front end. A partial
    block gives Pregonero correct scaling and a broken pulse with no error
    anywhere (docs/bombista-serve-spec.md §11.5), which is why a half-typed
    control must not be able to reach a file.

    **`None` — or an empty block, which is what four emptied fields post —
    clears the key**, and that is not the same as writing a null:
    absent is the honest state and Pregonero is already built for it — no
    pulse, no count-in, scale pinned to 1 (`songs@c5adf65`).

    **Nothing here derives anything.** The value arrives typed, from the
    source that produced the audio, where it is exact. Rules 4 and 5 stand
    and B14 stays dropped; what changed with this round is only *where* a
    performer may type it, not who supplies it.

    Raises ValueError listing every problem — the caller renders it, and
    the route turns it into a 400.
    """
    session.tempo = normalise_tempo(tempo)


def normalise_tempo(tempo: object) -> dict | None:
    """A typed-in block, checked and put in `TEMPO_KEYS` order — or `None`.

    Extracted when the control moved to page 1: the run route has to
    refuse a bad block **before** ninety seconds of transcription, and
    there is no session yet at that point. It is the same single gate
    either way — `validation.validate_tempo` — so a partial block cannot
    get in through one door and not the other.

    The block is rebuilt rather than stored as handed in: it is small
    enough that a browser's key order should not decide a song file's.
    """
    if tempo is None or tempo == {}:
        return None

    if isinstance(tempo, dict):
        tempo = without_zero_count_in(tempo)

    findings = validate_tempo(tempo)
    if findings:
        raise ValueError(one_line(findings))

    return {key: tempo[key] for key in TEMPO_KEYS if key in tempo}


def _place_tempo(song: dict, tempo: dict | None) -> dict:
    """Return *song* with the tempo block set, replaced or removed.

    A song that already declares one keeps **its own position** — files in
    the catalogue disagree about whether `tempo` comes before or after
    `title_translations`, both are valid, and normalising would rewrite
    files this tool is supposed to pass through. That rule is
    `_place_key`'s, shared with the general-information keys: one
    insertion rule, not one per key.
    """
    if tempo is None:
        return {key: value for key, value in song.items() if key != "tempo"}
    return _place_key(song, "tempo", tempo)


def sign_off(session: Session) -> str:
    """Stamp the review as read by a human, once (§9.5, B19's clause).

    It is recorded the first time a JSON download is taken and reused
    thereafter — wanting the timing block as well as the whole file is
    normal, and the sign-off is not a budget. Without it, §3's clause — a
    machine timeline and a reviewed one are indistinguishable — becomes
    unenforceable the moment the file leaves the folder its report is in.
    """
    if session.signed_off is None:
        session.signed_off = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return session.signed_off


def build_sp_json(
    session: Session, overrides: dict[int, float] | None = None
) -> tuple[dict, list[dict]]:
    """The Song Performance JSON as it stands, and the hand-set record.

    **There is no new schema** (§10.2): this IS the `songs/*.json` format.
    Bombista owns five keys — `linesHash`, `timelineSignedOff`,
    `timelineVersion`, `leadIn`, `timeline` — and passes everything else
    through untouched and in its original order, `lyrics` entries included,
    which are objects keyed by language and would lose every translation if
    they were ever flattened.

    `timelineSignedOff` is `None` until a JSON download is taken, and that
    is not a null scaffold: the key belongs in the file and its value is
    the fact being recorded, so a preview showing `null` is telling the
    truth — this run has not been signed off yet.

    Bands, signals and the per-line hand-set record are NOT in here. They
    belong to the report (§10.2): a song file is a song, and every consumer
    downstream would otherwise have to step around a QA blob.

    **A manual session returns early with none of the five.** A song with
    no recording has no timeline to describe, and writing an empty envelope
    would be a claim about timing that nothing measured.
    """
    if session.manual:
        # No recording, so no timeline, so **none of the five keys** — and
        # that includes `linesHash`, which guards a timeline that is not
        # there, and `timelineSignedOff`, which would claim a human read
        # one. The file is the song: the words, and whatever was typed.
        return _place_tempo(session.song, session.tempo), []

    overrides = session.overrides if overrides is None else overrides
    result = _anchor(session, overrides)
    envelope = to_dict(
        result["lead_in"],
        result["normalized"],
        session.song,
        source=result["lead_in_source"],
    )

    merged = merge_envelope(session.song, envelope)
    merged = _place_tempo(merged, session.tempo)
    merged = _place_owned_keys(
        merged, lines_hash=session.lines_hash, signed_off=session.signed_off
    )

    hand_set = [
        {
            "line": i,
            "machineStart": session.machine_starts[i],
            "start": overrides[i],
            "setAt": session.signed_off,
        }
        for i in sorted(overrides)
    ]
    return merged, hand_set


def timing_block(sp_json: dict) -> dict:
    """The `timeline only` download (§9.5) — the five timing keys, never a
    bare `timeline` array.

    Someone maintaining a song file by hand wants the block they can paste
    in. `timeline` without `linesHash` is the exact unguarded artifact B4
    exists to prevent, and without `timelineSignedOff` it cannot say a
    human ever read it. Handing over a bare array would make the convenient
    path the unsafe one.
    """
    return {key: sp_json[key] for key in OWNED_KEYS + ENVELOPE_KEYS}


def render_report(session: Session) -> str:
    """The `report` download — bands, signals, provenance and every
    hand-set line, as markdown.

    `report.render_qa_report` renders it, exactly as `align` does. A second
    renderer would be a second opinion about what a QA report says.
    """
    result = _anchor(session, session.overrides)
    _, hand_set = build_sp_json(session)
    return render_qa_report(
        anchors=result["anchors"],
        lines=session.lines,
        line_entries=result["entries"],
        lead_in=result["lead_in"],
        song_title=session.song.get("title", session.lyrics_path.stem),
        song_path=session.lyrics_path,
        audio_path=session.audio_path or Path(str((session.provenance or {}).get("audio", "—"))),
        model_size=session.model_size,
        lang=session.lang,
        staging_dir=session.staging_dir,
        provenance=_report_provenance(session),
        stripped_lines=session.stripped_lines,
        hand_set=hand_set,
    )


def _report_provenance(session: Session) -> dict:
    """The provenance the markdown report renders, complete by construction.

    The report reads every key; a session's provenance may carry only some
    of them. `asr-words.meta.json` is the case that made this necessary
    (§11.10): it is a real carrier and always present after a
    transcription — the only one a run started from page 1 leaves behind —
    but it records what the transcription established and no more, so it
    has no duration and no tool version.

    So the unknowns are laid down first and what the run actually recorded
    is laid over them. An audit document that says `unknown` is telling
    the truth; one that cannot render at all tells the user nothing, and
    one that guessed would be worse than both.
    """
    return {**_unknown_provenance(session), **(session.provenance or {})}


def _unknown_provenance(session: Session) -> dict:
    """A staging directory written by the default `--emit timeline` carries
    no provenance — the bare envelope cannot hold it by contract (§11.2).
    Say so, in the shape the report expects, rather than recomputing a
    sha256 that would describe now instead of the run on screen."""
    return {
        "audio": str(session.audio_path) if session.audio_path else "unknown",
        "sha256": "unknown",
        "durationSec": None,
        "model": session.model_size,
        "device": "unknown",
        "lang": session.lang,
        "extractedAt": "unknown",
        "toolVersion": "unknown",
    }


def default_out_path(session: Session) -> Path:
    """Where a write with no path of its own lands: `<stem>.json`, in the
    directory this run's working files are in.

    **It is a new file beside them, never one of them.** Invariant 6
    refuses every path the session read as an input, `align`'s
    `<stem>-song.json` included, so this is what is left — and it is what
    page 3's `Save to the catalogue` writes. One owner for the answer,
    because the page names the file before the press and the route writes
    it, and those two must not be able to disagree.
    """
    return session.staging_dir / f"{session.lyrics_path.stem}.json"


def emit_sp_json(session: Session, overrides: dict[int, float], out_path: Path) -> dict:
    """Write a NEW Song Performance JSON and return what was written plus
    the hand-set record.

    **Never writes to an input path** (invariant 6) — checked against
    resolved paths, before anything is opened.

    Writing a file is the programmatic equivalent of pressing a download,
    so it signs off: there is no path in this tool to an SP JSON that
    cannot say whether a human read it.
    """
    resolved = out_path.resolve()
    if resolved in session.input_paths:
        raise ValueError(
            f"{out_path}: refusing to write to a path this session read as an "
            "input — emit always writes a new file"
        )

    # Signing off records that a human read a timeline. A manual song has
    # none, so there is nothing to sign — and stamping one would be the
    # file claiming a review that never happened.
    if not session.manual:
        sign_off(session)
    merged, hand_set = build_sp_json(session, overrides)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return {
        "path": str(out_path),
        "manual": session.manual,
        "linesHash": merged.get("linesHash"),
        "timelineSignedOff": merged.get("timelineSignedOff"),
        "leadIn": merged.get("leadIn"),
        "timeline": merged.get("timeline"),
        "handSet": hand_set,
    }



# ---------------------------------------------------------------------------
# the run — page 1 -> page 1.5 (§9.4)
# ---------------------------------------------------------------------------

PHASES = ("transcribe", "anchor")
"""Two visible phases, and this is a state rather than a spinner (§9.4).
Transcription is the slow part; anchoring is instant and only has a row so
that the fast half is visible as a step rather than as a stall."""


class Run:
    """One `Process song →` press, on a worker thread.

    The anchoring, the reading and the merging are all the extracted
    modules' work — this owns the *sequencing* and nothing else, so there
    is no second implementation of anything here (invariant 1's spirit).

    **Cancel abandons; it does not kill the worker.** `faster_whisper`'s
    transcribe call is not interruptible without taking the process down
    with it, so cancelling marks the run, refuses to start the anchoring
    phase, and discards whatever the transcription eventually returns. The
    user is back on step 1 immediately, which is what Cancel promises.
    §9.6 lists killing the worker outright as still open; this is the
    honest half of it, and it is recorded as such rather than pretended.
    """

    def __init__(self, holder: "Holder", request: dict) -> None:
        self.holder = holder
        self.request = request
        self.state = "transcribing"
        self.error: str | None = None
        self.cancelled = False
        self.phases = {
            name: {"name": name, "state": "waiting", "started": None, "elapsed": None}
            for name in PHASES
        }

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        # `state` and phase 0 are ONE fact, so they get one writer, here,
        # before the worker exists (§12.3). `__init__` setting
        # `state = "transcribing"` while `_work` turned the phase running
        # on the other thread left a window — a few milliseconds wide on
        # this Mac, wide enough on a loaded CI runner — where the payload
        # claimed transcription with every phase `waiting`. That is §9.4's
        # state degraded into a spinner with extra rows, and the page
        # renders it. The staging `mkdir` now counts inside this phase's
        # elapsed time, which is honest: it is work the phase is doing.
        self._begin("transcribe")
        thread = threading.Thread(target=self._work, daemon=True)
        thread.start()

    def cancel(self) -> None:
        self.cancelled = True
        self.state = "cancelled"

    def payload(self) -> dict:
        phases = []
        for name in PHASES:
            phase = self.phases[name]
            elapsed = phase["elapsed"]
            if elapsed is None and phase["started"] is not None:
                elapsed = time.monotonic() - phase["started"]
            phases.append(
                {
                    "name": name,
                    "state": phase["state"],
                    "elapsedSec": None if elapsed is None else round(elapsed, 1),
                }
            )
        return {"state": self.state, "phases": phases, "error": self.error}

    # -- the work ----------------------------------------------------------

    def _begin(self, name: str) -> None:
        self.phases[name].update(state="running", started=time.monotonic())

    def _finish(self, name: str, state: str = "done") -> None:
        phase = self.phases[name]
        started = phase["started"]
        phase.update(
            state=state,
            elapsed=0.0 if started is None else time.monotonic() - started,
        )

    def _work(self) -> None:
        try:
            staging = Path(self.request["staging"])
            staging.mkdir(parents=True, exist_ok=True)
            words_path = staging / WORDS_FILENAME
            manual = not self.request["media"]
            media = Path(self.request["media"]) if not manual else None

            if manual:
                # Nothing to transcribe and nothing to anchor. Both phases
                # are marked skipped rather than done, because a run that
                # reported *done* on work it never did would be page 1.5
                # lying about the only thing it exists to show.
                self._finish("transcribe", "skipped")
                self._begin("anchor")
                self._finish("anchor", "skipped")
                self.holder.session = load_session(
                    staging,
                    Path(self.request["lyrics"]),
                    lang=self.request["lang"],
                    info=self.request.get("info"),
                    manual=True,
                )
                if "tempo" in self.request:
                    self.holder.session.tempo = self.request["tempo"]
                self.state = "done"
                return

            # **Cached only when it is a transcription of THIS take.** The
            # words file is a transcription of one recording, and a staging
            # directory may be reused for another — `serve --staging` takes
            # one directory and a caller may open every song in it. Reusing
            # it regardless is the same wrong-take failure §11.11 forbids
            # for the player, arriving through the cache instead: the
            # machine reports it listened and it listened to something
            # else.
            filed = (load_words_meta(words_path) or {}).get("audio")
            same_take = (
                words_path.exists()
                and isinstance(filed, str)
                and Path(filed) == media.resolve()
            )

            if same_take:
                # §9.4's one line of copy, and the whole ergonomics of the
                # correction loop: the slow part is cached, so coming back
                # is a second rather than ninety.
                self._finish("transcribe", "cached")
            else:
                words = transcribe_words(
                    media,
                    model_size=self.request["model"],
                    language=self.request["lang"],
                )
                if self.cancelled:
                    return
                # The sibling is filed here and nowhere else on this path:
                # a run started from page 1 writes no report JSON, so
                # without it the staging directory could say neither when
                # the machine listened nor where the take is (§11.10,
                # §11.11). `build_provenance` streams the audio's sha256,
                # which is the same work `align` does once per run.
                save_words(
                    words,
                    words_path,
                    meta=words_meta(
                        build_provenance(
                            media,
                            model_size=self.request["model"],
                            lang=self.request["lang"],
                        ),
                        media,
                        Path(self.request["lyrics"]),
                    ),
                )
                self._finish("transcribe")

            if self.cancelled:
                return

            self.state = "anchoring"
            self._begin("anchor")
            session = load_session(
                staging,
                Path(self.request["lyrics"]),
                lang=self.request["lang"],
                audio_path=media,
                model_size=self.request["model"],
                info=self.request.get("info"),
            )
            # Checked at the door and stored normalised, so this is an
            # assignment rather than a second judgement of the same block.
            if "tempo" in self.request:
                session.tempo = self.request["tempo"]
            if self.cancelled:
                return
            self._finish("anchor")
            self.holder.session = session
            self.state = "done"
        except Exception as exc:  # the page has to be able to say why
            if not self.cancelled:
                self.error = str(exc)
                self.state = "failed"


class Holder:
    """The one mutable thing the handler class closes over: the session
    being reviewed, and the run producing it."""

    def __init__(
        self,
        session: Session | None = None,
        staging: Path | None = None,
        *,
        browse_from: Path | None = None,
        song: Path | None = None,
        header: bool = True,
    ) -> None:
        self.session = session
        self.run: Run | None = None
        self.browse_from = str(browse_from or Path.home())
        """Where the file pickers open. The home folder is the standalone
        answer and a poor one on a screen whose whole job is to find a
        lyrics file and a recording that live in the same folder as each
        other (walked 2026-09-02). A caller that knows where the songs are
        says so; Bombista learns a directory and nothing else."""

        self.song = str(song) if song else ""
        """A song file page 1 starts prefilled from, which is what makes an
        edit an edit rather than a second new song. The page reaches it
        through exactly the route a pick takes, so there is one answer to
        *what does this file say*."""

        self.header = header
        """Whether to draw the product header — name, tagline, version,
        *a Tramoya tool by Chango Pepper*. Off, the version still shows:
        two builds calling themselves the same number is the trap that has
        cost this project a day."""
        self.staging = staging
        """Where a run started from page 1 stages its working files, when
        the caller named a directory (`serve --staging`).

        **It exists because the caller may need to promote from it.** The
        default below is a cache under `~/.cache/bombista`, which is the
        right answer for somebody running Bombista on its own and the
        wrong one for a caller that intends to read the emitted
        `<stem>.json` back out — it would have to know this module's cache
        layout to find it. A path in, a path out: the caller says where
        the run works, and the page prints the file it will write there.

        Bombista learns nothing about who is calling. This is a directory
        and nothing else."""


DEFAULT_STAGING_ROOT = Path.home() / ".cache" / "bombista"
"""Where a run started from page 1 stages `asr-words.jsonl` and the rest.

A cache directory, not an output directory: page 3 offers downloads and
the app does not choose where those land (§9.3, decision 3). It has to be
stable rather than temporary, because a stable location is what makes the
second run of a song skip transcription — the difference between a
90-second wait and a sub-second one. It sits beside the faster-whisper
model cache, which is already under `~/.cache`.
"""

LYRICS_SUFFIXES = (".json", ".txt")
MEDIA_SUFFIXES = (".mp3", ".m4a", ".wav", ".flac", ".mp4", ".mov", ".aac", ".ogg")


def start_run(holder: Holder, body: dict) -> dict:
    """Validate `Process song →` and put it on a worker thread."""
    if holder.run is not None and holder.run.state in ("transcribing", "anchoring"):
        raise Busy("a run is already going — cancel it before starting another")

    lyrics = _existing_file(body.get("lyrics"), "lyrics")
    # **A recording is optional** (Jorge, 2026-09-02). Words and no
    # recording is a legitimate song, advanced by hand during the
    # performance; there is nothing to align, so there is nothing to
    # require. The old rule assumed a timeline.
    media = _existing_file(body["media"], "media source") if body.get("media") else None
    lang = body.get("lang") or "es"
    model = body.get("model") or "medium"

    # The language constraint is ENFORCED here, not merely rendered (§9.3):
    # a language the file does not carry has no lines to anchor, and a
    # dropdown that only disables the option is a guard a reload removes.
    declared = declared_languages(lyrics)
    if declared and lang not in declared:
        raise ValueError(
            f"{lyrics.name} carries no {lang!r} lyrics — it declares "
            f"{', '.join(declared)}"
        )

    # The body wins, then the directory the caller named on the command line, then
    # the cache. The last is the standalone default and stays exactly as it was.
    if body.get("staging"):
        staging = Path(body["staging"])
    elif holder.staging is not None:
        staging = holder.staging
    else:
        staging = DEFAULT_STAGING_ROOT / lyrics.stem
    request = {
        "lyrics": str(lyrics),
        "media": str(media) if media else "",
        "lang": lang,
        "model": model,
        "staging": str(staging),
        "info": body.get("info"),
    }
    # The tempo is checked HERE, at the door, and not after ninety seconds
    # of transcription — through the one shared gate, so a partial block is
    # refused in the same words `bombista validate` refuses it in.
    #
    # It is carried only when the body said something. **Said nothing and
    # said nothing is there are different answers**: a session booted into
    # a review keeps whatever the song declares, while four emptied fields
    # on page 1 clear the key.
    if "tempo" in body:
        request["tempo"] = normalise_tempo(body["tempo"])

    holder.session = None
    holder.run = Run(holder, request)
    holder.run.start()
    return holder.run.payload()


class Busy(Exception):
    """A second run was asked for while one was going. 409, not 400."""


def _existing_file(value: object, what: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"no {what} file was chosen")
    path = Path(value)
    if not path.is_file():
        raise ValueError(f"{path}: no such file")
    return path


def declared_languages(lyrics_path: Path) -> list[str]:
    """The languages an SP JSON declares, in order of first appearance.

    A `.txt` declares nothing and returns `[]` — every language is open to
    it, because the one language it has is the one the user picks.
    """
    return _declared(read_lyrics_input(lyrics_path))


def _declared(normalised) -> list[str]:
    if normalised.bombista.get("completeness") != "complete":
        return []
    seen: dict[str, None] = {}
    for item in normalised.song.get("lyrics", []):
        if isinstance(item, dict):
            for key, value in item.items():
                if isinstance(value, str):
                    seen.setdefault(key, None)
    return list(seen)


def previous_take(
    lyrics_path: Path, *, staging: Path | None, browse_from: Path | None
) -> dict | None:
    """The recording **this song** was last aligned against, if it can be
    found — `{"path": ..., "name": ...}` or None.

    **Being asked is not the problem; being asked silently is** (Jorge,
    2026-09-02). On an edit the lyrics field prefilled and this one did
    not, so nothing said whether the app had forgotten the take or was
    waiting to be told. It stays changeable: re-aligning against a
    different take is the normal reason to edit a song.

    **The question is per SONG, and the first version of this answered a
    per-DIRECTORY one** — it read the take out of `asr-words.meta.json`
    with no reference to which song was being described, so a staging
    directory shared between songs handed every one of them the last
    song's recording. Walked 2026-09-02: a `.txt` that had never been
    aligned against anything arrived with a 2:40 take attached, the
    consent popup never appeared because a media source was set, and the
    review came back with every line `no-anchor`. Two sources now, both of
    them about this song:

    1. **The song's own `media.src`**, which is the file's own statement
       about its take. It is a logical filename rather than a path, so it
       is looked for beside the song file and in the directory the pickers
       open in — and nowhere else, because guessing more widely is how a
       player ends up on the wrong take.
    2. **`asr-words.meta.json`, but only when it names this song.** The
       meta records which lyrics file the transcription was made for, so
       it can be asked a question about a song rather than about a folder.

    **A plain text file gets nothing, ever.** A `.txt` carries no record of
    any recording, so there is no honest source for one — and it is the
    case the walk broke on.

    **Never another file.** The same rule `audio_path_for` follows: a
    prefill that quietly named a different recording would make every
    judgement about it wrong, and the person would not know.
    """
    if lyrics_path.suffix.lower() != ".json":
        return None

    found = _declared_media(lyrics_path, browse_from=browse_from)
    if found is not None:
        return found

    if staging is None:
        return None
    meta = load_words_meta(staging / WORDS_FILENAME) or {}
    if not _meta_is_for(meta, lyrics_path):
        return None
    filed = meta.get("audio")
    if isinstance(filed, str) and filed and Path(filed).is_file():
        return {"path": str(Path(filed).resolve()), "name": Path(filed).name}
    return None


def _meta_is_for(meta: dict, lyrics_path: Path) -> bool:
    """Whether a staging directory's transcription was made for *this*
    song's words.

    A staging directory is not necessarily one song's: `serve --staging`
    takes one directory and a caller may reuse it for every song it opens.
    So the meta has to say which song it belongs to, and a meta written
    before it recorded that says nothing rather than yes — **an unknown
    provenance is not a match.**
    """
    named = meta.get("song")
    if not isinstance(named, str) or not named:
        return False
    try:
        return Path(named).resolve() == lyrics_path.resolve()
    except OSError:
        return False


def _declared_media(lyrics_path: Path, *, browse_from: Path | None) -> dict | None:
    """The song file's own `media.src`, resolved beside the file and in the
    directory the pickers open in."""
    try:
        declared = json.loads(lyrics_path.read_text(encoding="utf-8")).get("media")
    except (OSError, ValueError):
        return None
    src = (declared or {}).get("src") if isinstance(declared, dict) else None
    if not isinstance(src, str) or not src:
        return None

    for root in (lyrics_path.parent, browse_from):
        if root is None:
            continue
        candidate = Path(root) / src
        if candidate.is_file():
            return {"path": str(candidate.resolve()), "name": candidate.name}
    return None


def describe_lyrics(
    lyrics_path: Path,
    *,
    lang: str = "es",
    staging: Path | None = None,
    browse_from: Path | None = None,
) -> dict:
    """What page 1 needs to know about a lyrics file the moment it is
    chosen: which branch it takes, what it declares, what the normaliser
    will strip out of it — before the run, never after (§3, §9.3) — and,
    since step 6, the general information and tempo to prefill.

    The stripped lines come from `readers.py`'s own `strippedLines`, never
    recounted here: two implementations of "what counts as a lyric line" is
    exactly the drift B5's boundary exists to prevent.
    """
    normalised = read_lyrics_input(lyrics_path, lang=lang)
    complete = normalised.bombista.get("completeness") == "complete"
    declared_tempo = normalised.song.get("tempo") if complete else None
    return {
        "path": str(lyrics_path),
        "name": lyrics_path.name,
        "slug": lyrics_path.stem,
        "branch": "sp" if complete else "txt",
        "declaredLanguages": _declared(normalised),
        "strippedLines": normalised.bombista.get("strippedLines") or [],
        "lineCount": len(normalised.song.get("lyrics", [])),
        # Step 6: page 1 collects the song's general information, so it
        # shows what the file already says before anyone retypes it. A
        # `.txt` says none of it, and gets the same title seed
        # `bombista new` writes — two doors into one tool should not
        # disagree about the first thing they put in a file.
        "info": (
            song_information(normalised.song)
            if complete
            else {"title": title_from_song_id(lyrics_path.stem), "artist": "", "notes": ""}
        ),
        "tempo": declared_tempo if isinstance(declared_tempo, dict) else None,
        "media": previous_take(lyrics_path, staging=staging, browse_from=browse_from),
    }


def audio_path_for(session: Session) -> Path:
    """The take this session's timings were measured against (§8.9).

    `serve` knows the path — from step 1, or from the run's own provenance
    when the session was booted straight into a review — so the bytes come
    off a loopback route rather than a relative `src`. B16's page needs a
    relative path because it is a loose file that must still work from a
    USB stick; a running process does not, and a relative `src` would be a
    second answer to where the audio is.

    **The audio-clock rule is why this is fussy** (CLAUDE.md): a timeline
    is only meaningful against the take it was measured from, so the wrong
    file is worse than no file.

    **Four steps, in this order, each reached only when the one above it
    yields nothing** (§11.11, fixed 2026-08-16):

    1. what the user named — `serve --audio`, or page 1's media picker;
    2. the absolute path in `asr-words.meta.json`, which is what makes a
       staging directory that has been moved or copied still findable;
    3. the run's own recorded path, which `align` stores **as it was
       given** — `staging/pimiento` holds `../../songs/audio/pimiento.m4a`
       — so it is tried against the roots that spelling could have been
       relative to, the directory the run happened in included;
    4. fail loudly.

    **Never substitute another file.** An audio route that silently plays
    the wrong take makes every judgement the user made against it wrong,
    and they will not know. A player that says it cannot find the take is
    strictly better than one that finds the wrong one — so there is no
    "the only audio file nearby" step, and there must not be.
    """
    if session.audio_path and session.audio_path.is_file():
        return session.audio_path

    filed = (load_words_meta(session.staging_dir / WORDS_FILENAME) or {}).get("audio")
    if isinstance(filed, str) and filed:
        candidate = Path(filed)
        if candidate.is_file():
            return candidate.resolve()

    recorded = (session.provenance or {}).get("audio")
    if isinstance(recorded, str) and recorded:
        for root in (Path.cwd(), session.staging_dir, session.staging_dir.parent):
            candidate = (root / recorded).resolve()
            if candidate.is_file():
                return candidate

    named = filed or recorded or "unrecorded"
    raise ValueError(
        "no audio for this run — the take is not where the run recorded it "
        f"({named}). Pass `--audio <file>`, or start again at step 1 and "
        "choose it. The player will not play a different take."
    )


def media_path(path: Path) -> Path:
    """A media file page 1 may play, or a refusal naming why.

    The tap control needs the take audible before there is a session to
    ask for it, so the page names a path. It is the same latitude
    `/api/lyrics` has and it is constrained the same way `browse` is: a
    file that exists, with a suffix this tool can open. Nothing here
    widens what the process is willing to read — `browse` already lists
    these files, and this server answers on loopback only.
    """
    if not path.is_file():
        raise ValueError(f"{path}: no such file")
    if path.suffix.lower() not in MEDIA_SUFFIXES:
        raise ValueError(f"{path.name}: not a media file this tool can play")
    return path


def browse(path: Path) -> dict:
    """§9.6, resolved: a loopback listing rather than `<input type="file">`.

    The server needs a real path — to read the lyrics, to hash the audio
    for provenance, and to write the re-run command into the report. A
    browser `File` object has no path, so the alternative (accept the
    upload and stage it) would copy a 50 MB m4a in order to recover
    something the file already had two directories away, and every path the
    tool then recorded would name the copy rather than the take the
    timeline is only meaningful against.

    Only directories and files this tool can actually open are listed —
    offering a `.docx` in a lyrics picker is offering a refusal.
    """
    if not path.is_dir():
        raise ValueError(f"{path}: not a directory")

    entries = []
    for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.name.startswith("."):
            continue
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        if not is_dir and child.suffix.lower() not in LYRICS_SUFFIXES + MEDIA_SUFFIXES:
            continue
        entries.append({"name": child.name, "path": str(child), "dir": is_dir})

    return {"path": str(path), "parent": str(path.parent), "entries": entries}


# ---------------------------------------------------------------------------
# the process
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    """The routes. Every refusal from the extracted modules arrives here as
    a ValueError carrying its message verbatim — only the rendering differs
    between a terminal and an HTTP response, never the reason."""

    server_version = "bombista"
    holder: Holder

    # -- pages -------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's name
        route, params = self._split()
        try:
            if route == "/":
                # Booted with a staging directory, the user is here to
                # review; booted bare, they are here to start. `/` answers
                # which rather than guessing at a landing page.
                self._redirect("/review" if self.holder.session else "/input")
            elif route == "/input":
                self._html(
                    pages.render_input(
                        browse_from=self.holder.browse_from,
                        song=self.holder.song,
                        header=self.holder.header,
                    )
                )
            elif route == "/processing":
                self._html(
                    pages.render_processing(**self._run_lede(), header=self.holder.header)
                )
            elif route == "/output":
                self._output_page()
            elif route == "/review":
                self._review_page()
            elif route == "/review/rows":
                self._review_rows()
            elif route == "/api/audio":
                self._audio(params)
            elif route == "/api/session":
                self._respond(200, session_payload(self._session()))
            elif route == "/api/run":
                self._respond(200, self._run_payload())
            elif route == "/api/browse":
                self._respond(
                    200, browse(Path(params.get("path", [self.holder.browse_from])[0]))
                )
            elif route == "/api/lyrics":
                self._respond(
                    200,
                    describe_lyrics(
                        Path(params["path"][0]),
                        lang=params.get("lang", ["es"])[0],
                        staging=self.holder.staging,
                        browse_from=Path(self.holder.browse_from),
                    ),
                )
            elif route == "/api/download":
                self._download(params.get("kind", ["song"])[0])
            else:
                self._error(404, f"no route {route}")
        except ValueError as exc:
            self._error(400, str(exc))
        except KeyError as exc:
            self._error(400, f"missing parameter {exc}")

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's name
        route, _ = self._split()
        routes = {
            "/api/reanchor": self._reanchor,
            "/api/emit": self._emit,
            "/api/tempo": self._set_tempo,
            "/api/run": self._start_run,
        }
        handler = routes.get(route)
        if handler is None:
            self._error(404, f"no route {route}")
            return
        try:
            self._respond(200, handler(self._body()))
        except Busy as exc:
            self._error(409, str(exc))
        except ValueError as exc:
            self._error(400, str(exc))

    def do_DELETE(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's name
        route, _ = self._split()
        if route != "/api/run":
            self._error(404, f"no route {route}")
            return
        if self.holder.run is None:
            self._error(404, "nothing is running")
            return
        self.holder.run.cancel()
        self._respond(200, self.holder.run.payload())

    # -- the routes' bodies ------------------------------------------------

    def _reanchor(self, body: dict) -> dict:
        session = self._session()
        overrides = _overrides_from_body(session, body)
        # Recorded on the session: page 3 serialises the timeline as it
        # stands, and a download is a navigation that cannot carry a body.
        session.overrides = overrides
        return session_payload(session, overrides)

    def _set_tempo(self, body: dict) -> dict:
        session = self._session()
        if "tempo" not in body:
            raise ValueError(
                'POST /api/tempo needs a "tempo" key — an object with all four '
                "values, or null to clear it"
            )
        set_tempo(session, body["tempo"])
        return session_payload(session, session.overrides)

    def _emit(self, body: dict) -> dict:
        session = self._session()
        overrides = (
            _overrides_from_body(session, body)
            if "overrides" in body
            else session.overrides
        )
        out = body.get("out")
        out_path = Path(out) if out else default_out_path(session)
        return emit_sp_json(session, overrides, out_path)

    def _start_run(self, body: dict) -> dict:
        return start_run(self.holder, body)

    def _run_payload(self) -> dict:
        if self.holder.run is None:
            return {"state": "idle", "phases": [], "error": None}
        return self.holder.run.payload()

    def _run_lede(self) -> dict:
        run = self.holder.run
        if run is None:
            return {}
        return {
            "media_name": Path(run.request["media"]).name,
            "model": run.request["model"],
            "lang": run.request["lang"],
        }

    def _review_page(self) -> None:
        """Page 2, and the reason `/review` used to 404: it was the one page
        not built, and a stub could have been mistaken for it."""
        session = self.holder.session
        if session is None:
            self._redirect("/input")
            return
        if session.manual:
            # There is no timeline to review. Sending the person to a page
            # of empty rows would be the flow pretending a step happened.
            self._redirect("/output")
            return
        self._html(
            pages.render_review(
                session_payload(session, session.overrides), header=self.holder.header
            )
        )

    def _review_rows(self) -> None:
        """The list of lines, as markup, for the page to swap in after a
        re-anchor.

        The rows are rendered by `pages.render_rows` rather than by the
        page's JavaScript so there is ONE template rather than two that can
        disagree about what a row says — the same reason `serve` imports
        the CLI's modules instead of copying them (invariant 1's spirit).
        It answers off `session.overrides`, which `/api/reanchor` has just
        set, so the markup and the JSON describe the same state.
        """
        session = self._session()
        payload = session_payload(session, session.overrides)
        self._send(200, pages.render_rows(payload).encode("utf-8"), "text/html; charset=utf-8")

    def _audio(self, params: dict) -> None:
        """The take, as bytes, over loopback (§8.9).

        Ranges are honoured because the transport seeks: a player that can
        only start from zero cannot be used to judge a line by ear, and
        judging by ear is the whole of §6's acceptance case.

        **With a `path`, it serves that file instead of the session's**,
        which is what lets page 1 play the recording the person just chose:
        there is no session yet at step 1, and tapping a tempo along with a
        take you cannot hear is tapping along with nothing. The path is
        constrained the same way `browse` constrains what it lists — a
        real file with a media suffix — and this process answers on
        loopback only. It is the same latitude `/api/lyrics` already has:
        the page names a file the person picked out of this server's own
        listing, and the server reads it.
        """
        named = params.get("path", [None])[0]
        if named:
            try:
                path = media_path(Path(named))
            except ValueError as exc:
                self._error(404, str(exc))
                return
        else:
            try:
                path = audio_path_for(self._session())
            except ValueError as exc:
                self._error(404, str(exc))
                return
        size = path.stat().st_size
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start, end = _range_header(self.headers.get("Range"), size)

        with path.open("rb") as handle:
            handle.seek(start)
            payload = handle.read(end - start + 1)

        partial = (start, end) != (0, size - 1)
        self._send(
            206 if partial else 200,
            payload,
            content_type,
            extra={
                "Accept-Ranges": "bytes",
                **({"Content-Range": f"bytes {start}-{end}/{size}"} if partial else {}),
            },
        )

    def _output_page(self) -> None:
        session = self.holder.session
        if session is None:
            self._redirect("/input")
            return
        sp_json, _ = build_sp_json(session)
        self._html(
            pages.render_output(
                sp_json,
                filename=f"{session.lyrics_path.stem}.json",
                save_path=str(default_out_path(session)),
                from_scratch=session.from_scratch,
                manual=session.manual,
                header=self.holder.header,
            )
        )

    def _download(self, kind: str) -> None:
        """The three downloads (§9.5). Bytes, never a file written to a
        path — which is also why invariant 6 cannot be violated here: page
        3 chooses no path, so it can overwrite none.

        Pressing either JSON download records the sign-off. The report does
        not: it certifies nothing, and taking it is not a decision.
        """
        session = self._session()
        stem = session.lyrics_path.stem

        if session.manual and kind != "song":
            raise ValueError(
                f"this song has no recording, so there is no {kind} to take — "
                "the whole file is the only download, and it carries the words"
            )

        if kind == "report":
            self._attachment(
                render_report(session).encode("utf-8"),
                f"{stem}-qa-report.md",
                "text/markdown; charset=utf-8",
            )
            return

        if kind not in ("song", "timeline"):
            raise ValueError(f"unknown download {kind!r}")

        sign_off(session)
        sp_json, _ = build_sp_json(session)
        payload = sp_json if kind == "song" else timing_block(sp_json)
        name = f"{stem}.json" if kind == "song" else f"{stem}-timeline.json"
        self._attachment(
            (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
            name,
            _JSON,
        )

    # -- plumbing ----------------------------------------------------------

    def _session(self) -> Session:
        if self.holder.session is None:
            raise _NoSession()
        return self.holder.session

    def _split(self) -> tuple[str, dict]:
        parsed = urlparse(self.path)
        return parsed.path, parse_qs(parsed.query)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"request body is not valid JSON ({exc})")
        if not isinstance(body, dict):
            raise ValueError("request body must be a JSON object")
        return body

    def _respond(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), _JSON)

    def _error(self, status: int, message: str) -> None:
        self._respond(status, {"error": message})

    def _html(self, markup: str) -> None:
        self._send(200, markup.encode("utf-8"), "text/html; charset=utf-8")

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _attachment(self, payload: bytes, filename: str, content_type: str) -> None:
        self._send(
            200,
            payload,
            content_type,
            extra={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def _send(self, status: int, payload: bytes, content_type: str, extra=None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except _NoSession:
            self._error(404, "no song is loaded — start at step 1")

    def log_message(self, format: str, *args: Any) -> None:
        """Silence the default stderr access log — one user, one page, one
        socket. The CLI prints the URL and nothing else."""


def _range_header(value: str | None, size: int) -> tuple[int, int]:
    """`bytes=START-END` -> the closed interval to send, clamped to the
    file. Anything this does not understand is answered whole rather than
    refused: a player that cannot seek is a degradation, and a 416 is a
    player that cannot play."""
    if not value or not value.startswith("bytes=") or "," in value:
        return 0, size - 1
    first, _, last = value[len("bytes="):].partition("-")
    try:
        start = int(first) if first else 0
        end = int(last) if last else size - 1
    except ValueError:
        return 0, size - 1
    start = max(0, min(start, size - 1))
    end = max(start, min(end, size - 1))
    return start, end


class _NoSession(Exception):
    """Raised by a route that needs a loaded song when there is none."""


def create_server(
    session: Session | None = None,
    *,
    port: int = 0,
    host: str = LOOPBACK_HOST,
    staging: Path | None = None,
    browse_from: Path | None = None,
    song: Path | None = None,
    header: bool = True,
) -> ThreadingHTTPServer:
    """A threading HTTP server bound to the loopback interface.

    *session* is optional: `serve` with a staging directory boots straight
    into a review (PR 2's development seam), and `serve` with nothing at
    all starts the user at step 1, where page 1 makes the session.

    *staging* is where a run started from page 1 does its work. See
    `Holder.staging`: it is for a caller that means to read the emitted
    `<stem>.json` back out, and the default cache is unchanged without it.

    *browse_from*, *song* and *header* are the three answers a caller may
    give about the page itself — where the pickers open, a song file page 1
    starts prefilled from, and whether the product header is drawn. See
    `Holder` for each. **None of them tells this process who is calling**,
    and none of them changes what Bombista writes.

    *host* is explicit and takes exactly one value (invariant 7): the
    argument exists so the bind address is visible at every call site, not
    so it can be changed. *port* defaults to 0 — the OS picks a free one
    and the caller reads it back off `server_address`.

    Threading because the page polls a run while it works, and streams
    audio from the same process while re-anchoring; a single-threaded
    server would stall the player on every correction.
    """
    if host != LOOPBACK_HOST:
        raise ValueError(
            f"refusing to bind {host!r} — bombista serve binds {LOOPBACK_HOST} "
            "and nothing else (the audio never leaves this machine)"
        )

    holder = Holder(session, staging, browse_from=browse_from, song=song, header=header)
    handler = type("_SessionHandler", (_Handler,), {"holder": holder})
    return ThreadingHTTPServer((host, port), handler)
