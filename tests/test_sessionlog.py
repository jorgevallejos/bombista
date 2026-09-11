"""
The session event log — the writer itself (the spike, 2026-09-07).

`projects/tramoya-integration/agent-design.md` fixes what this is for: one
real work session is observed so an agent's read of it can be compared
against Jorge's own memory of it. Everything here is about the ONE
constraint that makes the spike safe to run on the catalogue rebuild:

    the logger must not disturb the session it observes.

So the tests below are mostly tests of what it does *not* do — no file
when the env var is unset, no bytes inside `songs/`, no exception out of
any failure path, nothing on stdout or stderr, and no lyric text in the
file under any circumstance.

No song text enters this repository (§11.3, tests/conftest.py) — the
"never logs the words" tests use invented strings.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from bombista import sessionlog


def lines(path: Path) -> list[dict]:
    """Every event on disk, parsed. One JSON object per line, always."""
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


@pytest.fixture
def enabled(tmp_path, monkeypatch) -> Path:
    """The log switched on the only way it can be switched on."""
    target = tmp_path / "logs" / "session.jsonl"
    monkeypatch.setenv(sessionlog.ENV_VAR, str(target))
    sessionlog.reset()
    return target


# ---------------------------------------------------------------------------
# off by default — the first requirement, and the one with teeth
# ---------------------------------------------------------------------------


def test_off_when_the_env_var_is_unset(tmp_path, monkeypatch):
    monkeypatch.delenv(sessionlog.ENV_VAR, raising=False)
    sessionlog.reset()

    assert sessionlog.enabled() is False
    assert sessionlog.destination() is None

    sessionlog.log("screen", screen="/input", action="GET", outcome="ok")

    assert list(tmp_path.iterdir()) == []


def test_off_when_the_env_var_is_empty(monkeypatch):
    monkeypatch.setenv(sessionlog.ENV_VAR, "   ")
    sessionlog.reset()

    assert sessionlog.enabled() is False
    sessionlog.log("screen", screen="/input")


def test_nothing_but_the_env_var_switches_it_on(tmp_path, monkeypatch):
    """No flag, no config file, no default path. One switch, and it is the
    env var — so a session cannot be observed by accident."""
    monkeypatch.delenv(sessionlog.ENV_VAR, raising=False)
    sessionlog.reset()
    assert sessionlog.enabled() is False

    monkeypatch.setenv(sessionlog.ENV_VAR, str(tmp_path / "on.jsonl"))
    sessionlog.reset()
    assert sessionlog.enabled() is True


# ---------------------------------------------------------------------------
# the binding rule: never inside songs/
# ---------------------------------------------------------------------------


def test_refuses_a_path_inside_songs(tmp_path, monkeypatch):
    songs = tmp_path / "songs"
    songs.mkdir()
    monkeypatch.setenv(sessionlog.ENV_VAR, str(songs / "session.jsonl"))
    sessionlog.reset()

    assert sessionlog.enabled() is False
    assert "songs" in (sessionlog.refused() or "")

    sessionlog.log("screen", screen="/input")
    assert list(songs.iterdir()) == []


def test_refuses_a_path_nested_deeper_inside_songs(tmp_path, monkeypatch):
    deep = tmp_path / "songs" / "libertad" / "logs"
    deep.mkdir(parents=True)
    monkeypatch.setenv(sessionlog.ENV_VAR, str(deep / "session.jsonl"))
    sessionlog.reset()

    assert sessionlog.enabled() is False
    sessionlog.log("screen", screen="/input")
    assert list(deep.iterdir()) == []


def test_refuses_songs_reached_through_a_dot_dot(tmp_path, monkeypatch):
    """The rule is about the file that ends up written, not about how the
    path was spelled — so the check is made on the RESOLVED path."""
    songs = tmp_path / "songs"
    songs.mkdir()
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.setenv(
        sessionlog.ENV_VAR, str(tmp_path / "elsewhere" / ".." / "songs" / "s.jsonl")
    )
    sessionlog.reset()

    assert sessionlog.enabled() is False
    assert list(songs.iterdir()) == []


def test_refuses_songs_whatever_its_case(tmp_path, monkeypatch):
    """macOS is case-insensitive, so `Songs` and `songs` are one directory
    and the guard has to see them as one name."""
    songs = tmp_path / "Songs"
    songs.mkdir()
    monkeypatch.setenv(sessionlog.ENV_VAR, str(songs / "session.jsonl"))
    sessionlog.reset()

    assert sessionlog.enabled() is False


def test_a_directory_called_songs_only_matters_as_a_whole_name(tmp_path, monkeypatch):
    """`songs-log` is not `songs`. The guard is a path component, not a
    substring — otherwise it would refuse perfectly good destinations."""
    ok = tmp_path / "songs-log"
    ok.mkdir()
    monkeypatch.setenv(sessionlog.ENV_VAR, str(ok / "session.jsonl"))
    sessionlog.reset()

    assert sessionlog.enabled() is True


def test_refuses_an_existing_directory_as_the_target(tmp_path, monkeypatch):
    monkeypatch.setenv(sessionlog.ENV_VAR, str(tmp_path))
    sessionlog.reset()

    assert sessionlog.enabled() is False


# ---------------------------------------------------------------------------
# what one line says
# ---------------------------------------------------------------------------


def test_writes_one_json_line_per_event(enabled):
    sessionlog.log("screen", screen="/input", action="GET", outcome="ok")
    sessionlog.log("screen", screen="/review", action="GET", outcome="ok")

    events = lines(enabled)
    assert [event["kind"] for event in events] == ["screen", "screen"]
    assert [event["screen"] for event in events] == ["/input", "/review"]


def test_an_event_carries_both_clocks_and_the_gap_before_it(enabled):
    sessionlog.log("screen", screen="/input")
    sessionlog.log("screen", screen="/review")

    first, second = lines(enabled)
    for event in (first, second):
        assert isinstance(event["mono"], float)
        assert event["wall"].startswith("20")
        assert isinstance(event["sinceSec"], float)

    # The monotonic clock is what measures; the wall clock is what makes
    # the log comparable to Jorge's own notes of the same afternoon.
    assert second["mono"] >= first["mono"]
    assert first["sinceSec"] == 0.0
    assert second["sinceSec"] >= 0.0


def test_hesitation_is_visible_as_the_gap_between_events(enabled, monkeypatch):
    """`sinceSec` is the whole reason the monotonic clock is in here: a
    two-minute pause before a tap is the signal, and a wall clock that a
    laptop's sleep can move is not the thing to measure it with."""
    clock = {"t": 100.0}
    monkeypatch.setattr(sessionlog.time, "monotonic", lambda: clock["t"])
    sessionlog.reset()

    sessionlog.log("screen", screen="/input")
    clock["t"] = 130.5
    sessionlog.log("screen", screen="/review")

    first, second = lines(enabled)
    assert first["sinceSec"] == 0.0
    assert second["sinceSec"] == pytest.approx(30.5)


def test_events_are_numbered_so_a_lost_line_is_visible(enabled):
    for _ in range(5):
        sessionlog.log("screen", screen="/input")

    assert [event["seq"] for event in lines(enabled)] == [1, 2, 3, 4, 5]


def test_extra_fields_travel_beside_the_reserved_ones(enabled):
    sessionlog.log("run", command="serve", action="start", outcome="ok", lineCount=19)

    event = lines(enabled)[0]
    assert event["command"] == "serve"
    assert event["action"] == "start"
    assert event["outcome"] == "ok"
    assert event["lineCount"] == 19


def test_an_error_is_recorded_with_the_same_shape_as_a_success(enabled):
    """Errors and abandoned flows are the events with the most signal —
    they are not a lesser kind of event and they are not summarised."""
    sessionlog.log("screen", screen="/api/emit", action="POST", outcome="error", status=400)
    sessionlog.log("run", action="cancel", outcome="abandoned")

    first, second = lines(enabled)
    assert first["outcome"] == "error"
    assert first["status"] == 400
    assert second["outcome"] == "abandoned"


# ---------------------------------------------------------------------------
# append-only, and immediate
# ---------------------------------------------------------------------------


def test_appends_and_never_truncates(enabled):
    sessionlog.log("screen", screen="/input")
    sessionlog.reset()
    sessionlog.log("screen", screen="/review")

    assert len(lines(enabled)) == 2


def test_appends_to_a_file_that_is_already_there(enabled):
    enabled.parent.mkdir(parents=True, exist_ok=True)
    enabled.write_text('{"seq": 0, "kind": "earlier"}\n', encoding="utf-8")

    sessionlog.log("screen", screen="/input")

    events = lines(enabled)
    assert events[0]["kind"] == "earlier"
    assert events[1]["screen"] == "/input"


def test_each_event_is_on_disk_before_the_call_returns(enabled):
    """Never buffered across a crash: the process could be killed between
    these two statements and the first event would still be there."""
    sessionlog.log("screen", screen="/input")

    assert len(lines(enabled)) == 1


def test_makes_the_directory_it_was_pointed_at(tmp_path, monkeypatch):
    target = tmp_path / "a" / "b" / "session.jsonl"
    monkeypatch.setenv(sessionlog.ENV_VAR, str(target))
    sessionlog.reset()

    sessionlog.log("screen", screen="/input")

    assert target.exists()


def test_expands_a_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(sessionlog.ENV_VAR, "~/session.jsonl")
    sessionlog.reset()

    sessionlog.log("screen", screen="/input")

    assert (tmp_path / "session.jsonl").exists()


def test_concurrent_threads_produce_whole_lines_and_unique_numbers(enabled):
    """`serve` is a ThreadingHTTPServer: the page polls a run while it
    streams audio and re-anchors. Interleaved half-lines would make the
    log unreadable exactly when the session was busiest."""

    def burst() -> None:
        for _ in range(25):
            sessionlog.log("screen", screen="/api/run", action="GET", outcome="ok")

    threads = [threading.Thread(target=burst) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    events = lines(enabled)
    assert len(events) == 200
    assert sorted(event["seq"] for event in events) == list(range(1, 201))


# ---------------------------------------------------------------------------
# silent, and harmless when it breaks
# ---------------------------------------------------------------------------


def test_says_nothing_on_stdout_or_stderr(enabled, capsys):
    sessionlog.log("screen", screen="/input", outcome="ok")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_a_refusal_says_nothing_either(tmp_path, monkeypatch, capsys):
    songs = tmp_path / "songs"
    songs.mkdir()
    monkeypatch.setenv(sessionlog.ENV_VAR, str(songs / "s.jsonl"))
    sessionlog.reset()

    sessionlog.log("screen", screen="/input")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_an_unwritable_destination_is_swallowed(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file, not a directory", encoding="utf-8")
    monkeypatch.setenv(sessionlog.ENV_VAR, str(blocker / "under" / "s.jsonl"))
    sessionlog.reset()

    sessionlog.log("screen", screen="/input")  # must not raise

    assert sessionlog.enabled() is False
    assert capsys.readouterr().err == ""


def test_a_write_that_fails_mid_session_is_swallowed(enabled, monkeypatch, capsys):
    """The session it observes must not be affected by it, at all — which
    includes the case where the disk fills up halfway through."""
    sessionlog.log("screen", screen="/input")

    def boom(*args, **kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(sessionlog.os, "write", boom)

    sessionlog.log("screen", screen="/review")  # must not raise

    assert capsys.readouterr().err == ""
    assert len(lines(enabled)) == 1


def test_a_value_that_cannot_be_serialised_does_not_lose_the_event(enabled):
    sessionlog.log("screen", screen="/input", thing=object(), outcome="ok")

    event = lines(enabled)[0]
    assert event["outcome"] == "ok"
    assert event["thing"] == "<object>"


# ---------------------------------------------------------------------------
# no lyrics, no song text, no file contents
# ---------------------------------------------------------------------------


def test_denied_keys_never_reach_the_file(enabled):
    """Slugs and structure only. The call sites are ours, so this is
    defence in depth — the guard is here so a field added later cannot
    quietly start writing the words down."""
    sessionlog.log(
        "screen",
        screen="/api/emit",
        text="una linea cantada",
        lyrics="todas las lineas",
        notes="something Jorge typed",
        title="Some Title",
        lineText="another line",
        outcome="ok",
    )

    event = lines(enabled)[0]
    raw = enabled.read_text(encoding="utf-8")
    assert event["outcome"] == "ok"
    for denied in ("text", "lyrics", "notes", "title", "lineText"):
        assert denied not in event
    assert "cantada" not in raw
    assert "Jorge" not in raw


def test_a_denied_key_is_recorded_as_a_shape_not_a_value(enabled):
    """Dropping it silently would hide that the field was filled in at
    all, which is a fact worth having — so the LENGTH survives and the
    value does not."""
    sessionlog.log("screen", screen="/input", notes="something Jorge typed")

    event = lines(enabled)[0]
    assert event["notesLen"] == len("something Jorge typed")


def test_a_denied_key_nested_in_a_dict_is_caught_too(enabled):
    sessionlog.log("screen", screen="/input", info={"title": "Libertad", "artist": "x"})

    raw = enabled.read_text(encoding="utf-8")
    assert "Libertad" not in raw


def test_a_path_is_recorded_as_its_own_name_and_nothing_above_it(enabled):
    sessionlog.log("screen", screen="/input", picked="/Users/j/vault/songs/libertad/words.txt")

    event = lines(enabled)[0]
    assert event["picked"] == "words.txt"


def test_a_long_string_is_truncated(enabled):
    sessionlog.log("screen", screen="/input", why="x" * 500)

    event = lines(enabled)[0]
    assert len(event["why"]) <= sessionlog.MAX_STRING + 1


def test_a_list_is_kept_but_bounded(enabled):
    sessionlog.log("tap", intervalsMs=list(range(500)))

    event = lines(enabled)[0]
    assert event["intervalsMs"][:3] == [0, 1, 2]
    assert len(event["intervalsMs"]) <= sessionlog.MAX_ITEMS


def test_deeply_nested_structure_does_not_recurse_forever(enabled):
    nest: dict = {"a": 1}
    for _ in range(20):
        nest = {"a": nest}

    sessionlog.log("screen", screen="/input", nest=nest, outcome="ok")

    assert lines(enabled)[0]["outcome"] == "ok"


# ---------------------------------------------------------------------------
# the shape a tap is recorded in
# ---------------------------------------------------------------------------


def test_a_tap_burst_keeps_the_raw_intervals(enabled):
    """The tap is the one interaction the spike was designed around: the
    RAW gaps, how many attempts, and whether the answer was kept."""
    sessionlog.log(
        "tap",
        screen="/input",
        action="burst",
        outcome="ok",
        attempt=2,
        taps=6,
        intervalsMs=[901, 887, 912, 890, 905],
        bpm=66.5,
        accepted=False,
    )

    event = lines(enabled)[0]
    assert event["attempt"] == 2
    assert event["taps"] == 6
    assert event["intervalsMs"] == [901, 887, 912, 890, 905]
    assert event["bpm"] == 66.5
    assert event["accepted"] is False


# ---------------------------------------------------------------------------
# resolving, once
# ---------------------------------------------------------------------------


def test_the_destination_is_resolved_once_and_not_per_event(enabled, monkeypatch):
    """A `getenv` per event would let the destination change under a
    running session, and would put a syscall in a hot path for nothing."""
    sessionlog.log("screen", screen="/input")
    monkeypatch.setenv(sessionlog.ENV_VAR, str(enabled.parent / "other.jsonl"))
    sessionlog.log("screen", screen="/review")

    assert len(lines(enabled)) == 2
    assert not (enabled.parent / "other.jsonl").exists()


def test_destination_reports_where_it_is_writing(enabled):
    assert sessionlog.destination() == enabled.resolve()


def test_the_file_is_the_users_own(enabled):
    sessionlog.log("screen", screen="/input")

    assert oct(enabled.stat().st_mode)[-3:] == "600"


def test_ordinary_data_survives_the_scrub_unchanged(enabled):
    sessionlog.log(
        "line",
        screen="/review",
        action="reanchor",
        outcome="ok",
        line=7,
        fromSec=37.54,
        toSec=36.32,
        band="LOW",
        overrides=3,
    )

    event = lines(enabled)[0]
    assert event["line"] == 7
    assert event["fromSec"] == 37.54
    assert event["toSec"] == 36.32
    assert event["band"] == "LOW"
    assert event["overrides"] == 3
