"""
The session event log — a spike, and off unless you switch it on.

`projects/tramoya-integration/agent-design.md` (2026-09-07) fixes what
this exists for and what it must never become. One real work session —
Jorge rebuilding the song catalogue from nothing — is observed, so that an
agent's read of the log can be compared against his own memory of the same
afternoon. **If the agent's list contains nothing he missed, the idea
dies.** Nothing here analyses anything, nothing is proposed, nothing is
cross-app: this module writes a file and that is the whole of it.

**The constraint is the design.** The session being observed is the first
careful catalogue rebuild, and a spike that disturbs it has already cost
more than it could ever return. So:

- **Off by default.** One switch, `BOMBISTA_SESSION_LOG=<path>`, and there
  is no flag, no config file and no default destination. A session cannot
  be observed by accident.
- **Never inside `songs/`.** A binding rule of the vault this tool serves,
  enforced on the *resolved* path rather than on how it was spelled.
- **Write-only and silent.** Nothing is read back, nothing is printed,
  nothing is asked. Every failure — a full disk, a bad path, a value that
  will not serialise — is swallowed, and the caller carries on as though
  the log were off.
- **Immediate.** One `os.write` per event, on a file opened `O_APPEND`. No
  userspace buffer, so a process that dies mid-session still leaves every
  event it had written. There is deliberately no `fsync`: a sync per event
  would be the one thing here slow enough to be felt, and the failure it
  guards against is a machine crash rather than a program crash.

**Errors and abandoned flows are first-class.** They are the events with
the most signal — a session's own memory loses them first — so they are
recorded in the same shape and at the same weight as a success.

**No lyrics, no song text, no file contents.** Slugs and structure only.
The call sites are ours and pass what they mean to pass; `_scrub` is the
guard behind them, so a field added a year from now cannot quietly start
writing the words down. A denied value survives only as its length, which
says *this was filled in* without saying what with.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "ENV_VAR",
    "client_event",
    "destination",
    "enabled",
    "log",
    "refused",
    "reset",
]

ENV_VAR = "BOMBISTA_SESSION_LOG"
"""The only switch. Set it to the file the events should be appended to."""

FORBIDDEN_PARENT = "songs"
"""**Never write inside `songs/`.** The catalogue is the thing this spike
exists to watch being rebuilt, and it is the one directory a write from an
observer could damage in a way no later step repairs. Matched as a whole
path component, casefolded — macOS is case-insensitive, so `Songs` and
`songs` are one directory — and never as a substring, so `songs-log`
beside it is a perfectly good destination."""

MAX_STRING = 200
"""Long strings are truncated. Nothing this log records is prose; a value
longer than this is either a mistake or something that should not be
here."""

MAX_ITEMS = 200
"""A list is kept whole up to this length — long enough for the longest
tap burst a hand produces, short enough that a runaway value cannot fill
the disk it is being written to."""

MAX_DEPTH = 4
"""How far into a nested structure the scrub goes before it stops
describing and starts summarising."""

DENIED_KEYS = frozenset(
    {
        "artist",
        "body",
        "content",
        "line_text",
        "linetext",
        "lyric",
        "lyrics",
        "lines",
        "notes",
        "text",
        "title",
        "title_translations",
        "titletranslations",
        "transcript",
        "words",
    }
)
"""Keys whose value is a human's own words, or a file's contents, and is
therefore never written. `line` is NOT here and must not be: a line
*index* is exactly the structure the log is for. Count and size fields
(`lineCount`, `notesLen`) carry what is worth knowing about the rest."""

RESERVED = ("command", "screen", "action", "outcome")
"""The four fields every event may carry, in the order they are written —
which command or which screen, what was done, and how it ended."""

NEVER_A_PATH = frozenset({"screen", "action", "kind", "outcome", "command"})
"""Keys whose value leads with a `/` and is not a file. A route is the
screen's whole name — shortening `/api/session-log` to `session-log` would
be this module editing the one field the log is mostly made of. Every
other string that starts like an absolute path is treated as one."""


class _Writer:
    """One open file, one sequence, one lock.

    `serve` is a `ThreadingHTTPServer` — the page polls a run while it
    streams audio and re-anchors — so several threads reach `log` at once.
    The lock covers the numbering and the clocks; the write itself is a
    single `os.write` to an `O_APPEND` descriptor, which is what keeps a
    line whole even when two processes share the file.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        self._lock = threading.Lock()
        self._seq = 0
        self._start = time.monotonic()
        self._last = self._start

    def write(self, kind: str, fields: dict) -> None:
        with self._lock:
            now = time.monotonic()
            self._seq += 1
            event = {
                "seq": self._seq,
                "mono": round(now - self._start, 3),
                "wall": datetime.now(timezone.utc).astimezone().isoformat(
                    timespec="milliseconds"
                ),
                "sinceSec": round(now - self._last, 3),
                "kind": kind,
            }
            self._last = now
            for key in RESERVED:
                if key in fields:
                    event[key] = _scrub(fields[key], key)
            for key, value in fields.items():
                if key in RESERVED or key in ("seq", "mono", "wall", "sinceSec", "kind"):
                    continue
                _place(event, key, value)
            line = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
            os.write(self._fd, line)

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass


_OFF = object()
"""The resolved-and-refused state, so a refusal is decided once rather
than re-litigated on every event."""

_writer: _Writer | None | object = _OFF
_refused: str | None = None
_resolve_lock = threading.Lock()


def reset() -> None:
    """Forget the resolved destination and close the file.

    For tests, and for nothing else in the product: the destination is
    read from the environment exactly once per process, so it cannot
    change under a running session and there is no `getenv` in the hot
    path.
    """
    global _writer, _refused
    with _resolve_lock:
        if isinstance(_writer, _Writer):
            _writer.close()
        _writer = _OFF
        _refused = None


def enabled() -> bool:
    """Whether events are being written. Resolves the destination on the
    first call, and never asks again."""
    return _resolved() is not None


def destination() -> Path | None:
    """The file being appended to, or `None`."""
    writer = _resolved()
    return None if writer is None else writer.path


def refused() -> str | None:
    """Why the destination was turned down, if it was.

    Nothing in Bombista prints this — the log is silent, and a spike that
    interrupted the session to complain about its own configuration would
    be the failure it was designed around. It is here so a test, or
    somebody checking their own setup from a REPL, can ask.
    """
    _resolved()
    return _refused


def log(kind: str, **fields: object) -> None:
    """Append one event. Never raises, never prints, never blocks on I/O
    beyond the single append.

    `kind` says what sort of thing happened — `screen`, `run`, `line`,
    `song`, `tap`, `command`. The four reserved fields say which command
    or screen it belongs to, what was done and how it ended; everything
    else travels beside them.
    """
    try:
        writer = _resolved()
        if writer is None:
            return
        writer.write(kind, fields)
    except Exception:
        # The session it observes must not be affected by it, at all.
        # There is nowhere for this to go: a message on stderr is screen
        # output, and a second log would have the same problem as the
        # first.
        pass


# ---------------------------------------------------------------------------
# resolving the destination — once, and with two refusals
# ---------------------------------------------------------------------------


def _resolved() -> _Writer | None:
    global _writer, _refused
    if _writer is not _OFF:
        return _writer  # type: ignore[return-value]
    with _resolve_lock:
        if _writer is not _OFF:
            return _writer  # type: ignore[return-value]
        writer, why = _open()
        _writer = writer
        _refused = why
        return writer


def _open() -> tuple[_Writer | None, str | None]:
    raw = (os.environ.get(ENV_VAR) or "").strip()
    if not raw:
        return None, None
    try:
        path = Path(raw).expanduser().resolve()
    except Exception as exc:  # a path the OS will not even normalise
        return None, f"{raw!r} is not a usable path ({exc})"

    if any(part.casefold() == FORBIDDEN_PARENT for part in path.parts[:-1]):
        return None, (
            f"refusing {path} — the session log is never written inside "
            f"a {FORBIDDEN_PARENT}/ directory"
        )
    if path.is_dir():
        return None, f"refusing {path} — it is a directory, not a file"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return _Writer(path), None
    except Exception as exc:
        return None, f"refusing {path} — it could not be opened ({exc})"


# ---------------------------------------------------------------------------
# the scrub — slugs and structure only
# ---------------------------------------------------------------------------


def _place(event: dict, key: str, value: object) -> None:
    """Put one caller-supplied field on the event, or its size instead."""
    if key.casefold() in DENIED_KEYS:
        size = _sizeof(value)
        if size is not None:
            event[f"{key}Len"] = size
        return
    event[key] = _scrub(value, key)


def _sizeof(value: object) -> int | None:
    try:
        return len(value)  # type: ignore[arg-type]
    except TypeError:
        return None


def _scrub(value: object, key: str = "", depth: int = 0) -> object:
    """Everything written passes through here.

    Numbers and booleans go as they are. A string that is a path is
    reduced to its own name, because the log records *which song*, never
    where somebody's home directory is; any string is truncated. Anything
    the JSON encoder would choke on becomes its type name rather than
    costing the event.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Path):
        return value.name
    if isinstance(value, str):
        return _string(value, key)
    if depth >= MAX_DEPTH:
        return f"<{type(value).__name__}>"
    if isinstance(value, (list, tuple)):
        return [_scrub(item, key, depth + 1) for item in list(value)[:MAX_ITEMS]]
    if isinstance(value, dict):
        out: dict = {}
        for name, item in value.items():
            name = str(name)
            if name.casefold() in DENIED_KEYS:
                size = _sizeof(item)
                if size is not None:
                    out[f"{name}Len"] = size
                continue
            out[name] = _scrub(item, name, depth + 1)
        return out
    return f"<{type(value).__name__}>"


def _string(value: str, key: str = "") -> str:
    """A path becomes its own last component; everything is truncated.

    Only a string that *starts* like a path is treated as one — a time
    signature is `4/4` and reducing it to `4` would be this module
    corrupting the very thing it was asked to record — and never under a
    key that holds a route (`NEVER_A_PATH`).
    """
    if key.casefold() not in NEVER_A_PATH and (
        value.startswith("/") or value.startswith("~/")
    ):
        value = value.rsplit("/", 1)[-1] or value
    if len(value) > MAX_STRING:
        return value[:MAX_STRING] + "…"
    return value


# ---------------------------------------------------------------------------
# the browser's half — one kind, one fixed set of fields
# ---------------------------------------------------------------------------

CLIENT_KINDS = frozenset({"tap"})
"""What a page is allowed to file. One kind, because there is one thing
the browser knows and the process does not: the tap.

**The raw gaps between presses exist nowhere else.** They are in the tab
and they are gone when it closes — and tapping is the interaction the
spike was designed around, so it is the one thing worth a route."""

CLIENT_FIELDS = (
    "action",
    "outcome",
    "attempt",
    "taps",
    "intervalsMs",
    "beats",
    "accepted",
    "typed",
    "signature",
    "bars",
    "reason",
)
"""Every field a tap event may carry, and nothing else passes.

`intervalsMs` is the raw gaps, `attempt` which try this was, `taps` how
many presses it took, `beats` what the page settled on, and `accepted`
whether that value was kept or tapped again. A field not named here is
dropped without comment: this is a fixed shape with a fixed vocabulary,
not a write endpoint.
"""

CLIENT_SCREEN = "/input"
"""Stamped rather than taken from the body — the tap control lives on page
1 and nowhere else, so the page does not get to name its own screen."""


def client_event(body: object) -> None:
    """File one event sent by a page. Never raises, and answers nothing.

    Everything the browser sends is treated as a claim about ITS OWN
    interaction and nothing else: the kind must be one this module knows,
    the fields are taken from `CLIENT_FIELDS` by name, and the screen is
    stamped here. `log` scrubs what survives that, so a page cannot write
    song text into the file even by mistake.
    """
    try:
        if not isinstance(body, dict) or body.get("kind") not in CLIENT_KINDS:
            return
        fields = {name: body[name] for name in CLIENT_FIELDS if name in body}
        log(body["kind"], command="serve", screen=CLIENT_SCREEN, **fields)
    except Exception:
        pass
