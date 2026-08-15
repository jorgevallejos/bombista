"""
Shared fixtures for the `serve` tests (B20).

Synthetic `Word` lists throughout — no whisper model, no audio decoding
(CLAUDE.md, Development Protocol). `words_for` builds a stream that
anchors every line cleanly, which is what most of these tests want: they
are about the pages and the flow, not about the anchoring, which
tests/test_anchoring.py and tests/test_server.py already pin.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from bombista.aligner import save_words
from bombista.anchoring import tokenize_line
from bombista.models import Word

FIXTURES = Path(__file__).parent / "fixtures"
LIBERTAD_SONG = FIXTURES / "libertad-song.json"

SYNTHETIC_SONG = FIXTURES / "synthetic-19-song.json"
SYNTHETIC_WORDS = FIXTURES / "synthetic-19-words.jsonl"

# --- the synthetic 19-line fixture, and the facts the tests assume of it ---
#
# §11.3, settled 2026-08-16: two tiers. This one is committed and runs in
# CI; the pimiento canary is opt-in and points at the private vault. **No
# song lyrics, no real asr-words.jsonl and no audio enter this
# repository** — the words below are invented, built by hand rather than
# trimmed from the real stream, because a trimmed ASR stream still
# contains the sung words.
#
# What it *is* built to share with the canary is the arithmetic: the same
# nineteen onsets, the same one-word misdetection, so §6's and §8.8's
# measured numbers are reproduced by a fixture that publishes nothing.
# Those onsets are already printed in docs/bombista-serve-spec.md; the
# lyrics are not, and are not here.
LINE_COUNT = 19
LEAD_IN = 8.92
MOVED_LEAD_IN = 9.32
"""Line 0, forward by 0.40 s — the mockup's demonstration of §8.6."""

FLAGGED_LINE = 3
MACHINE_START = 37.54
"""Where the machine puts the flagged line: its first word was misheard,
so it anchored on the second one."""

TRUE_ONSET = 36.32
"""Where the line actually starts. The error is exactly one word — 1.22 s,
which is 24 separate presses and the reason §8.4's press-and-hold exists."""

LATE_ONSET = 40.00
"""Inside the bounds, and far enough that the NEXT line's gap falls below
a third of the song's median — the band recompute §8.8 exists to show."""


def words_for(lines, *, first_start: float = 10.0, gap: float = 5.0) -> list[Word]:
    """A word stream that anchors `lines` cleanly, one line every `gap`
    seconds starting at `first_start`."""
    words: list[Word] = []
    for i, line in enumerate(lines):
        t = first_start + i * gap
        for k, token in enumerate(tokenize_line(line)):
            start = round(t + k * 0.4, 3)
            words.append(Word(token, start, round(start + 0.3, 3)))
    return words


@pytest.fixture(autouse=True)
def staging_root(tmp_path, monkeypatch):
    """A run started from page 1 stages into `~/.cache/bombista/<slug>` so
    that a second run of the same song skips transcription. Tests must
    never write there — a cache the suite populates is a cache that makes
    the next test lie about whether it transcribed."""
    from bombista import server

    root = tmp_path / "cache"
    monkeypatch.setattr(server, "DEFAULT_STAGING_ROOT", root)
    return root


@pytest.fixture
def libertad(tmp_path: Path) -> dict:
    """A staging directory and the real committed song fixture beside it —
    four languages on every lyric entry, a real tempo block, an intro."""
    song = json.loads(LIBERTAD_SONG.read_text(encoding="utf-8"))
    lines = [item["es"] for item in song["lyrics"]]

    staging = tmp_path / "staging"
    staging.mkdir()
    save_words(words_for(lines), staging / "asr-words.jsonl")
    song_path = tmp_path / "libertad.json"
    song_path.write_text(json.dumps(song, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "staging": staging,
        "song_path": song_path,
        "song": song,
        "lines": lines,
        "words": words_for(lines),
        "audio": _touch(tmp_path / "libertad.m4a"),
    }


@pytest.fixture
def synthetic(tmp_path: Path) -> dict:
    """The committed 19-line fixture, staged the way `align` leaves a run.

    Copied into `tmp_path` rather than read in place, because a session
    computes its input paths from where the files are and `/api/emit`
    refuses to write to any of them — a test that emitted next to the
    committed fixture would be writing into the repository.
    """
    staging = tmp_path / "synthetic-staging"
    staging.mkdir()
    (staging / "asr-words.jsonl").write_text(
        SYNTHETIC_WORDS.read_text(encoding="utf-8"), encoding="utf-8"
    )
    song_path = tmp_path / "synthetic.json"
    song_path.write_text(SYNTHETIC_SONG.read_text(encoding="utf-8"), encoding="utf-8")

    return {"staging": staging, "song_path": song_path, "audio": _touch(tmp_path / "s.m4a")}


@pytest.fixture
def synthetic_session(synthetic: dict):
    from bombista import server

    return server.load_session(
        synthetic["staging"], synthetic["song_path"], lang="es", audio_path=synthetic["audio"]
    )


def _touch(path: Path) -> Path:
    path.write_bytes(b"\x00" * 32)
    return path


class Client:
    """A tiny JSON/HTML client over the real loopback socket."""

    def __init__(self, base: str) -> None:
        self.base = base

    def request(self, method, path, body=None, *, raw=False, binary=False, headers=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        sent = {"Content-Type": "application/json"} if data else {}
        sent.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=sent)
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            response = opener.open(req)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            body = response.read()
            if binary:
                return response.status, body, dict(response.headers)
            payload = body.decode("utf-8")
            if raw or not (response.headers.get("Content-Type") or "").startswith(
                "application/json"
            ):
                return response.status, payload, dict(response.headers)
            return response.status, json.loads(payload), dict(response.headers)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None):
        return self.request("POST", path, body if body is not None else {})

    def delete(self, path):
        return self.request("DELETE", path, {})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are part of what is under test — do not follow them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@pytest.fixture
def serve_client():
    """Start a real server on an ephemeral loopback port and drive it."""
    started = []

    def start(session=None):
        from bombista import server

        httpd = server.create_server(session, port=0)
        thread = threading.Thread(
            target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )
        thread.start()
        started.append((httpd, thread))
        host, port = httpd.server_address[:2]
        return Client(f"http://{host}:{port}")

    yield start

    for httpd, thread in started:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
