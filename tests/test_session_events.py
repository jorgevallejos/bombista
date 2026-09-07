"""
The session event log — what the app actually writes into it (the spike).

`tests/test_sessionlog.py` pins the writer. This file pins the wiring: the
screens, the run, the corrections and the taps, seen through the same
loopback socket a real session drives, with the log switched on the only
way it can be switched on.

The two tests that matter most are the negatives at the bottom — with the
env var unset the flow produces no file at all, and no lyric line ever
reaches the log even when the log is on.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from bombista import sessionlog


def events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def of_kind(path: Path, kind: str, *, at_least: int = 1) -> list[dict]:
    """The events of one kind, waited for.

    **A request's event is written AFTER its response has gone out** — the
    page never waits on the observer — so a client that has read its body
    can be a few milliseconds ahead of the log. Waiting here is the test
    admitting that, rather than the logger being made synchronous to suit
    it.
    """
    if at_least == 0:
        return [event for event in events(path) if event["kind"] == kind]
    deadline = time.monotonic() + 3.0
    while True:
        found = [event for event in events(path) if event["kind"] == kind]
        if len(found) >= at_least or time.monotonic() > deadline:
            return found
        time.sleep(0.01)


@pytest.fixture
def log_path(tmp_path, monkeypatch) -> Path:
    target = tmp_path / "observed" / "session.jsonl"
    monkeypatch.setenv(sessionlog.ENV_VAR, str(target))
    sessionlog.reset()
    return target


# ---------------------------------------------------------------------------
# screens
# ---------------------------------------------------------------------------


def test_a_screen_is_recorded_with_its_outcome(log_path, serve_client):
    client = serve_client()

    client.get("/input")

    screen = of_kind(log_path, "screen")[-1]
    assert screen["screen"] == "/input"
    assert screen["action"] == "GET"
    assert screen["outcome"] == "ok"
    assert screen["status"] == 200
    assert screen["command"] == "serve"
    assert isinstance(screen["elapsedMs"], (int, float))


def test_a_route_that_refuses_is_recorded_as_an_error(log_path, serve_client):
    client = serve_client()

    client.get("/no-such-page")

    screen = of_kind(log_path, "screen")[-1]
    assert screen["screen"] == "/no-such-page"
    assert screen["outcome"] == "error"
    assert screen["status"] == 404


def test_a_bad_request_body_is_recorded_as_an_error(log_path, serve_client, synthetic_session):
    client = serve_client(synthetic_session)

    client.post("/api/tempo", {})

    screen = of_kind(log_path, "screen")[-1]
    assert screen["screen"] == "/api/tempo"
    assert screen["action"] == "POST"
    assert screen["outcome"] == "error"
    assert screen["status"] == 400


def test_every_screen_of_the_flow_is_recorded_in_order(log_path, serve_client, synthetic_session):
    client = serve_client(synthetic_session)

    client.get("/input")
    client.get("/review")
    client.get("/output")

    seen = [event["screen"] for event in of_kind(log_path, "screen", at_least=3)]
    assert seen == ["/input", "/review", "/output"]


def test_the_gap_between_screens_is_on_every_event(log_path, serve_client):
    client = serve_client()
    client.get("/input")
    client.get("/deal")

    for event in of_kind(log_path, "screen"):
        assert isinstance(event["sinceSec"], float)


# ---------------------------------------------------------------------------
# corrections — the hesitation the review page is made of
# ---------------------------------------------------------------------------


def test_a_re_anchor_records_the_line_and_both_times(log_path, serve_client, synthetic_session):
    client = serve_client(synthetic_session)

    client.post("/api/reanchor", {"overrides": {"3": 36.32}})

    correction = of_kind(log_path, "line")[-1]
    assert correction["action"] == "reanchor"
    assert correction["outcome"] == "ok"
    assert correction["lineIndexes"] == [3]
    assert correction["overrides"] == 1


def test_a_second_pass_over_the_same_line_is_its_own_event(
    log_path, serve_client, synthetic_session
):
    """Re-doing a correction is the signal — it says the first answer did
    not survive a listen."""
    client = serve_client(synthetic_session)

    client.post("/api/reanchor", {"overrides": {"3": 36.32}})
    client.post("/api/reanchor", {"overrides": {"3": 36.10}})

    corrections = of_kind(log_path, "line", at_least=2)
    assert len(corrections) == 2
    assert [event["lineIndexes"] for event in corrections] == [[3], [3]]


# ---------------------------------------------------------------------------
# the run — including the one that was abandoned
# ---------------------------------------------------------------------------


def test_a_run_is_recorded_from_start_to_finish(log_path, serve_client, libertad, tmp_path):
    client = serve_client(staging=tmp_path / "out")

    status, payload, _ = client.post(
        "/api/run",
        {
            "lyrics": str(libertad["song_path"]),
            "media": "",
            "lang": "es",
            "model": "medium",
        },
    )
    assert status == 200

    for _ in range(200):
        status, payload, _ = client.get("/api/run")
        if payload["state"] in ("done", "failed"):
            break

    runs = of_kind(log_path, "run", at_least=2)
    assert runs[0]["action"] == "start"
    assert runs[0]["manual"] is True
    assert runs[-1]["action"] == "end"
    assert runs[-1]["outcome"] == "ok"


def test_a_cancelled_run_is_recorded_as_abandoned(log_path, serve_client, libertad, tmp_path):
    """Cancel is the clearest *abandoned* the app has, and it is exactly
    the event a session's own memory loses first."""
    client = serve_client(staging=tmp_path / "out")
    client.post(
        "/api/run",
        {
            "lyrics": str(libertad["song_path"]),
            "media": "",
            "lang": "es",
            "model": "medium",
        },
    )
    client.delete("/api/run")

    abandoned = [
        event for event in of_kind(log_path, "run", at_least=2)
        if event["outcome"] == "abandoned"
    ]
    assert abandoned
    assert abandoned[-1]["action"] == "cancel"


def test_a_refused_run_is_recorded_as_an_error(log_path, serve_client, tmp_path):
    client = serve_client(staging=tmp_path / "out")

    client.post("/api/run", {"lyrics": str(tmp_path / "nope.txt"), "media": "", "lang": "es"})

    screen = of_kind(log_path, "screen")[-1]
    assert screen["screen"] == "/api/run"
    assert screen["outcome"] == "error"


# ---------------------------------------------------------------------------
# the song that got saved
# ---------------------------------------------------------------------------


def test_saving_the_song_is_recorded_by_slug(log_path, serve_client, synthetic_session, tmp_path):
    client = serve_client(synthetic_session)

    status, payload, _ = client.post("/api/emit", {"out": str(tmp_path / "out" / "s.json")})
    assert status == 200

    saved = of_kind(log_path, "song")[-1]
    assert saved["action"] == "save"
    assert saved["outcome"] == "ok"
    assert saved["song"] == "synthetic"
    assert saved["out"] == "s.json"


# ---------------------------------------------------------------------------
# taps — the browser's half of the session
# ---------------------------------------------------------------------------


TAP_BURST = {
    "kind": "tap",
    "action": "burst",
    "attempt": 1,
    "taps": 6,
    "intervalsMs": [901, 887, 912, 890, 905],
    "beats": 66.5,
    "accepted": False,
}


def test_the_page_can_file_a_tap_burst(log_path, serve_client):
    client = serve_client()

    status, _, _ = client.post("/api/session-log", TAP_BURST)
    assert status == 204

    tap = of_kind(log_path, "tap")[-1]
    assert tap["action"] == "burst"
    assert tap["intervalsMs"] == [901, 887, 912, 890, 905]
    assert tap["taps"] == 6
    assert tap["attempt"] == 1
    assert tap["accepted"] is False
    assert tap["beats"] == 66.5
    assert tap["screen"] == "/input"


def test_a_tempo_that_was_re_tapped_says_how_many_attempts(log_path, serve_client):
    client = serve_client()

    client.post("/api/session-log", dict(TAP_BURST, attempt=1, accepted=False))
    client.post("/api/session-log", dict(TAP_BURST, attempt=2, accepted=True, beats=67.0))

    taps = of_kind(log_path, "tap", at_least=2)
    assert [event["attempt"] for event in taps] == [1, 2]
    assert [event["accepted"] for event in taps] == [False, True]


def test_the_page_cannot_file_an_arbitrary_kind(log_path, serve_client):
    """The route exists for the browser's half of ONE flow. It is not a
    general write endpoint, and a loopback server still gets to say what
    it will record."""
    client = serve_client()

    client.post("/api/session-log", {"kind": "whatever", "action": "x"})
    # A real event behind it, so the assertion waits on a barrier rather
    # than on a timeout.
    client.post("/api/session-log", TAP_BURST)
    of_kind(log_path, "tap")

    assert [event["kind"] for event in events(log_path) if event["kind"] == "whatever"] == []


def test_the_page_cannot_file_song_text(log_path, serve_client):
    client = serve_client()

    client.post("/api/session-log", dict(TAP_BURST, text="una linea cantada"))
    of_kind(log_path, "tap")

    assert "cantada" not in log_path.read_text(encoding="utf-8")


def test_the_route_answers_the_same_when_the_log_is_off(tmp_path, monkeypatch, serve_client):
    monkeypatch.delenv(sessionlog.ENV_VAR, raising=False)
    sessionlog.reset()
    client = serve_client()

    status, _, _ = client.post("/api/session-log", TAP_BURST)

    assert status == 204
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# the negatives
# ---------------------------------------------------------------------------


def test_off_by_default_the_whole_flow_writes_nothing(
    tmp_path, monkeypatch, serve_client, synthetic_session
):
    monkeypatch.delenv(sessionlog.ENV_VAR, raising=False)
    sessionlog.reset()
    client = serve_client(synthetic_session)

    assert client.get("/input")[0] == 200
    assert client.get("/review")[0] == 200
    client.post("/api/reanchor", {"overrides": {"3": 36.32}})
    client.post("/api/emit", {"out": str(tmp_path / "out" / "s.json")})
    assert client.get("/output")[0] == 200

    assert sessionlog.enabled() is False
    assert sessionlog.destination() is None
    assert not (tmp_path / "observed").exists()


def test_a_log_pointed_inside_songs_writes_nothing(tmp_path, monkeypatch, serve_client):
    songs = tmp_path / "songs"
    songs.mkdir()
    monkeypatch.setenv(sessionlog.ENV_VAR, str(songs / "session.jsonl"))
    sessionlog.reset()
    client = serve_client()

    assert client.get("/input")[0] == 200
    client.post("/api/session-log", TAP_BURST)

    assert list(songs.iterdir()) == []


def test_no_lyric_line_reaches_the_log(log_path, serve_client, libertad, tmp_path):
    """The one rule the spike cannot get wrong: slugs and structure only.

    Driven over the real fixture whose lines are real Spanish lyrics, so
    the assertion is against the words themselves rather than against a
    field name.
    """
    session_client = serve_client(staging=tmp_path / "out")
    session_client.get("/input")
    session_client.get("/api/lyrics?path=" + str(libertad["song_path"]))
    session_client.post(
        "/api/run",
        {
            "lyrics": str(libertad["song_path"]),
            "media": "",
            "lang": "es",
            "model": "medium",
            "info": {"title": "Libertad", "artist": "Chango Pepper", "notes": "a private note"},
        },
    )
    for _ in range(200):
        state = session_client.get("/api/run")[1]["state"]
        if state in ("done", "failed"):
            break
    session_client.get("/output")

    raw = log_path.read_text(encoding="utf-8")
    assert raw  # the flow really was observed
    for line in libertad["lines"]:
        for word in line.split():
            if len(word) > 4:
                assert word.lower() not in raw.lower(), word
    assert "a private note" not in raw
    assert "Chango Pepper" not in raw


def test_the_session_log_never_speaks(log_path, serve_client, capfd, synthetic_session):
    client = serve_client(synthetic_session)

    client.get("/input")
    client.post("/api/reanchor", {"overrides": {"3": 36.32}})
    client.post("/api/session-log", TAP_BURST)

    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""


# ---------------------------------------------------------------------------
# the command boundary — a session is not only what happened in the browser
# ---------------------------------------------------------------------------


SANE_SONG = {
    "title": "Libertad",
    "artist": "Chango Pepper",
    "notes": "",
    "title_translations": {"es": "Libertad"},
    "lyrics": [{"es": "uno"}, {"es": "dos"}],
}


def test_a_command_is_recorded_from_start_to_finish(log_path, tmp_path):
    from click.testing import CliRunner

    from bombista.cli import main

    song = tmp_path / "sane.json"
    song.write_text(json.dumps(SANE_SONG, ensure_ascii=False), encoding="utf-8")

    result = CliRunner().invoke(main, ["validate", str(song)])
    assert result.exit_code == 0

    commands = of_kind(log_path, "command")
    assert commands[0]["action"] == "start"
    assert commands[0]["command"] == "validate"
    assert commands[-1]["action"] == "end"
    assert commands[-1]["outcome"] == "ok"


def test_a_command_that_exits_non_zero_is_recorded_as_an_error(log_path, tmp_path):
    from click.testing import CliRunner

    from bombista.cli import main

    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"lyrics": []}), encoding="utf-8")

    CliRunner().invoke(main, ["validate", str(broken)])

    assert of_kind(log_path, "command")[-1]["outcome"] == "error"


def test_an_interrupted_command_is_recorded_as_abandoned(log_path, tmp_path, monkeypatch):
    """Ctrl-C on a long `serve` is how a real session ends, and it is an
    abandonment rather than a failure."""
    from click.testing import CliRunner

    from bombista import cli

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli, "load_and_validate", interrupted)

    song = tmp_path / "sane.json"
    song.write_text(json.dumps(SANE_SONG, ensure_ascii=False), encoding="utf-8")

    CliRunner().invoke(cli.main, ["validate", str(song)])

    assert of_kind(log_path, "command")[-1]["outcome"] == "abandoned"


# ---------------------------------------------------------------------------
# the page behaves identically whether it is being watched or not
# ---------------------------------------------------------------------------


def test_page_1_is_identical_but_for_the_flag():
    """**A screen that behaved differently while being watched would be
    measuring itself.** The only difference between the observed page and
    the ordinary one is the boolean that decides whether the tap control
    speaks."""
    from bombista import pages

    off = pages.render_input(browse_from="/tmp")
    on = pages.render_input(browse_from="/tmp", session_log=True)

    assert "var SESSION_LOG = false;" in off
    assert "var SESSION_LOG = true;" in on
    assert off.replace("var SESSION_LOG = false;", "X") == on.replace(
        "var SESSION_LOG = true;", "X"
    )


def test_the_served_page_carries_the_flag_the_process_was_started_with(
    log_path, serve_client
):
    client = serve_client()

    assert "var SESSION_LOG = true;" in client.get("/input")[1]


def test_the_served_page_says_false_when_the_log_is_off(monkeypatch, serve_client):
    monkeypatch.delenv(sessionlog.ENV_VAR, raising=False)
    sessionlog.reset()
    client = serve_client()

    assert "var SESSION_LOG = false;" in client.get("/input")[1]


def test_the_tap_control_files_the_raw_intervals_and_nothing_else():
    """Read off the script, because the browser is where the gaps between
    presses live and there is no other way to see this from a test."""
    from bombista import pages

    script = pages.render_input(browse_from="/tmp", session_log=True).split("<script>")[1]

    assert '"/api/session-log"' in script
    assert "intervalsMs" in script
    assert "attempt" in script
    assert "accepted" in script
    # Guarded, so an install with the log off does not even build a body.
    assert "if (!SESSION_LOG) { return; }" in script


def test_the_log_does_not_record_its_own_route(log_path, serve_client):
    """An observer that files its own footsteps doubles the file and adds
    nothing — every tap would arrive with a POST event beside it."""
    client = serve_client()

    client.post("/api/session-log", TAP_BURST)
    of_kind(log_path, "tap")

    assert [
        event for event in of_kind(log_path, "screen", at_least=0)
        if event["screen"] == "/api/session-log"
    ] == []
