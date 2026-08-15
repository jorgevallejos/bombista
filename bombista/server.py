"""
`bombista serve` — the local review process, and the JSON routes page 2
talks to (B20 §1, §3, §4).

An HTTP server on the loopback interface, in the same Python process the
CLI runs in. It holds one session — the lines, the word stream and the QA
state of a previous `align` — and answers three routes with JSON:

    GET  /api/session   the lines, their machine anchors, bands, signals,
                        ASR context, leadIn and the run's provenance
    POST /api/reanchor  {"overrides": {"<line>": <seconds>}} -> the full
                        per-line result, RE-ANCHORED against the audio
    POST /api/emit      write a new SP JSON through the one merge path

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

Page 2's HTML is not here — it is built against these routes in the next
item, and `/` is a 404 until then rather than a stub that could be
mistaken for the page.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .aligner import load_words
from .anchoring import SIGNAL_GLOSSES, anchor_lines, parse_anchor_overrides
from .models import Word
from .pipeline import build_timeline, lyric_lines, normalize_to_lead_in
from .provenance import compute_lines_hash
from .readers import read_lyrics_input
from .report import band_counts
from .serializer import to_dict
from .writers import merge_envelope

__all__ = [
    "LOOPBACK_HOST",
    "Session",
    "create_server",
    "load_session",
    "session_payload",
    "emit_sp_json",
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


@dataclass(frozen=True)
class Session:
    """One `serve` run's immutable inputs, plus the machine's own answer.

    `machine_starts` is what `anchor_lines` gives with no overrides at
    all. It is computed once, at load, and never recomputed: it is the
    "before" a hand-set line is recorded against, and re-deriving it from
    a run that already carries overrides would quietly turn the human's
    correction into the machine's value.
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
    input_paths: frozenset[Path]


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


def _find_provenance(staging_dir: Path, stem: str) -> dict | None:
    """The provenance of the run being reviewed, read back from whatever
    `align` was asked to write.

    Recorded, not recomputed. `build_provenance` streams the audio's
    sha256 and stamps `extractedAt` — running it here would describe *this*
    moment, not the run whose timings are on screen, and would make booting
    a session wait on a hash of a file the routes never otherwise touch.

    Returns None when the staging directory holds neither carrier (the
    default `--emit timeline` writes a bare envelope, which by contract
    cannot carry provenance). The caller says so rather than inventing one.
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

    return None


def load_session(staging_dir: Path, lyrics_path: Path, *, lang: str = "es") -> Session:
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
    if not words_path.exists():
        raise ValueError(
            f"{staging_dir}: no {WORDS_FILENAME} — this is not an `align` "
            "staging directory, or the run did not finish"
        )

    normalised = read_lyrics_input(lyrics_path, lang=lang)
    song = normalised.song
    items = song.get("lyrics")
    if not isinstance(items, list):
        raise ValueError(f'{lyrics_path}: song JSON has no "lyrics" list')

    lines = lyric_lines(items, lang)
    if not lines:
        raise ValueError(f"{lyrics_path}: no lyric lines carry the {lang!r} language key")

    words = load_words(words_path)
    machine = anchor_lines(words, lines)

    return Session(
        staging_dir=staging_dir,
        lyrics_path=lyrics_path,
        song=song,
        lines=lines,
        lang=lang,
        words=words,
        lines_hash=compute_lines_hash(lines),
        provenance=_find_provenance(staging_dir, lyrics_path.stem),
        machine_starts=[anchor.start for anchor in machine],
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

    overrides = parse_anchor_overrides(
        [f"{line}={seconds}" for line, seconds in raw.items()], len(session.lines)
    )

    if 0 in overrides:
        # Invariant 3: line 0 is always 0.00 in a v2 timeline and its
        # offset lives in `leadIn`. A stepper on line 0 would silently
        # break the contract — local error and global drift are different
        # problems and get different controls (§3).
        raise ValueError(
            "line 0 cannot be moved — it is the start cue. Timeline v2 "
            "normalises it to 0.00 and banks the offset in leadIn"
        )
    return overrides


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
    }


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
            "handSet": i in overrides,
        }
        if anchor.asr_context:
            line["asrContext"] = anchor.asr_context
        lines.append(line)

    envelope = to_dict(result["lead_in"], result["normalized"], session.song)
    counts = band_counts(anchors)

    return {
        "title": session.song.get("title", session.lyrics_path.stem),
        "lang": session.lang,
        "linesHash": session.lines_hash,
        "leadIn": envelope["leadIn"],
        "provenance": session.provenance,
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


def _place_owned_keys(song: dict, *, lines_hash: str, signed_off: str) -> dict:
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


def emit_sp_json(session: Session, overrides: dict[int, float], out_path: Path) -> dict:
    """Write a NEW Song Performance JSON and return what was written plus
    the hand-set record.

    **Never writes to an input path** (invariant 6) — checked against
    resolved paths, before anything is opened.

    **The song file carries five keys and no QA blob** (§10.2): `linesHash`,
    `timelineSignedOff`, `timelineVersion`, `leadIn`, `timeline`. Bands,
    signals and the per-line hand-set record belong to the report, so the
    record travels on this function's return value rather than in the
    file. A song file is a song.
    """
    resolved = out_path.resolve()
    if resolved in session.input_paths:
        raise ValueError(
            f"{out_path}: refusing to write to a path this session read as an "
            "input — emit always writes a new file"
        )

    result = _anchor(session, overrides)
    envelope = to_dict(result["lead_in"], result["normalized"], session.song)
    signed_off = datetime.now(timezone.utc).isoformat(timespec="seconds")

    merged = merge_envelope(session.song, envelope)
    merged = _place_owned_keys(merged, lines_hash=session.lines_hash, signed_off=signed_off)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    hand_set = [
        {
            "line": i,
            "machineStart": session.machine_starts[i],
            "start": overrides[i],
            "setAt": signed_off,
        }
        for i in sorted(overrides)
    ]

    return {
        "path": str(out_path),
        "linesHash": session.lines_hash,
        "timelineSignedOff": signed_off,
        "leadIn": envelope["leadIn"],
        "timeline": envelope["timeline"],
        "handSet": hand_set,
    }


# ---------------------------------------------------------------------------
# the process
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    """The routes. Every refusal from the extracted modules arrives here as
    a ValueError carrying its message verbatim — only the rendering differs
    between a terminal and an HTTP response, never the reason."""

    server_version = "bombista"
    session: Session

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's name
        if self.path == "/api/session":
            self._respond(200, session_payload(self.session))
            return
        self._respond(
            404,
            {
                "error": (
                    "no page here — the review page is built against these "
                    "routes: GET /api/session, POST /api/reanchor, POST /api/emit"
                )
            },
        )

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's name
        routes = {"/api/reanchor": self._reanchor, "/api/emit": self._emit}
        route = routes.get(self.path)
        if route is None:
            self._respond(404, {"error": f"no route {self.path}"})
            return

        try:
            body = self._body()
            self._respond(200, route(body))
        except ValueError as exc:
            self._respond(400, {"error": str(exc)})

    def _reanchor(self, body: dict) -> dict:
        return session_payload(self.session, _overrides_from_body(self.session, body))

    def _emit(self, body: dict) -> dict:
        overrides = _overrides_from_body(self.session, body)
        out = body.get("out")
        out_path = (
            Path(out)
            if out
            else self.session.staging_dir / f"{self.session.lyrics_path.stem}.sp.json"
        )
        return emit_sp_json(self.session, overrides, out_path)

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
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", _JSON)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        """Silence the default stderr access log — one user, one page, one
        socket. The CLI prints the URL and nothing else."""


def create_server(
    session: Session, *, port: int = 0, host: str = LOOPBACK_HOST
) -> ThreadingHTTPServer:
    """A threading HTTP server bound to the loopback interface.

    *host* is explicit and takes exactly one value (invariant 7): the
    argument exists so the bind address is visible at every call site, not
    so it can be changed. *port* defaults to 0 — the OS picks a free one
    and the caller reads it back off `server_address`.

    Threading because the page fires a re-anchor while the audio is still
    streaming from the same process; a single-threaded server would stall
    the player on every correction.
    """
    if host != LOOPBACK_HOST:
        raise ValueError(
            f"refusing to bind {host!r} — bombista serve binds {LOOPBACK_HOST} "
            "and nothing else (the audio never leaves this machine)"
        )

    handler = type("_SessionHandler", (_Handler,), {"session": session})
    return ThreadingHTTPServer((host, port), handler)
