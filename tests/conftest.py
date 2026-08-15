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


def _touch(path: Path) -> Path:
    path.write_bytes(b"\x00" * 32)
    return path


class Client:
    """A tiny JSON/HTML client over the real loopback socket."""

    def __init__(self, base: str) -> None:
        self.base = base

    def request(self, method, path, body=None, *, raw=False):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            response = opener.open(req)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            payload = response.read().decode("utf-8")
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
