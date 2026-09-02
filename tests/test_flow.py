"""
The flow behind pages 1, 1.5 and 3 — the routes they drive (B20 §5, §9).

PR 2 built `/api/session`, `/api/reanchor` and `/api/emit` against a
staging directory that already existed. Page 1 needs to *make* one, so
this adds a run route; page 1 needs to know what a lyrics file declares
before it can constrain the language dropdown or show what the normaliser
will strip; and page 3 hands over bytes rather than writing files.

`transcribe_words` is patched everywhere — never the whisper model
(CLAUDE.md, Development Protocol).
"""
from __future__ import annotations

import ast
import json
import re
import time
from pathlib import Path
from unittest import mock

import pytest

from bombista import server
from bombista.aligner import save_words
from tests.conftest import LIBERTAD_SONG, words_for


@pytest.fixture
def session(libertad):
    return server.load_session(libertad["staging"], libertad["song_path"], lang="es")


@pytest.fixture
def client(serve_client, session):
    return serve_client(session)


def wait_for(client, state, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, payload, _ = client.get("/api/run")
        if payload["state"] == state:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"run never reached {state!r}: {payload}")


# ---------------------------------------------------------------------------
# the pages are served, and `/` knows where the user is
# ---------------------------------------------------------------------------


def test_the_entry_point_is_step_1_when_there_is_nothing_to_review(serve_client):
    client = serve_client(None)

    status, _, headers = client.get("/")

    assert status in (302, 303)
    assert headers["Location"] == "/input"


def test_the_entry_point_is_the_review_when_a_session_was_booted(client):
    """`serve <staging> <lyrics>` drops the user straight at step 2 — the
    development seam PR 2 built, and how page 2 will be developed."""
    status, _, headers = client.get("/")

    assert status in (302, 303)
    assert headers["Location"] == "/review"


@pytest.mark.parametrize("path", ["/input", "/processing"])
def test_the_pages_are_served_as_html(serve_client, path):
    client = serve_client(None)

    status, body, headers = client.get(path)

    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert body.startswith("<!doctype html>")


def test_the_review_is_served_as_html_once_there_is_something_to_review(client):
    """`/review` answered 404 until page 2 landed — deliberately, rather
    than a stub that could be mistaken for the page (§11.7). It is the
    fourth state now."""
    status, body, headers = client.get("/review")

    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert body.startswith("<!doctype html>")


def test_the_review_sends_you_to_step_1_when_no_song_is_loaded(serve_client):
    """The same answer `/output` gives: there is nothing to review, and a
    page that says so is a page with a dead end on it."""
    status, _, headers = serve_client(None).get("/review")

    assert status in (302, 303)
    assert headers["Location"] == "/input"


@pytest.fixture
def audio_client(serve_client, libertad):
    """A session that knows its take. `serve <staging> <lyrics>` does not
    take an audio argument, so a session booted that way finds the file
    through the run's own provenance instead — see `audio_path_for`."""
    session = server.load_session(
        libertad["staging"], libertad["song_path"], lang="es",
        audio_path=libertad["audio"],
    )
    return serve_client(session)


def test_the_audio_is_served_over_loopback_with_ranges(audio_client, libertad):
    """§8.9: `serve` knows the path from step 1, so the bytes come off a
    route rather than a relative `src`. Ranges because the transport seeks
    — a player that can only start at zero cannot judge a line by ear,
    which is the whole of §6's acceptance case."""
    size = libertad["audio"].stat().st_size
    status, body, headers = audio_client.get("/api/audio", binary=True)

    assert status == 200
    assert headers["Accept-Ranges"] == "bytes"
    assert body == libertad["audio"].read_bytes()

    status, body, headers = audio_client.get(
        "/api/audio", binary=True, headers={"Range": "bytes=8-15"}
    )

    assert status == 206
    assert headers["Content-Range"] == f"bytes 8-15/{size}"
    assert body == libertad["audio"].read_bytes()[8:16]


def test_the_audio_route_serves_nothing_when_the_take_cannot_be_found(serve_client, session):
    """Timeline times are only meaningful against the audio they were
    measured from (CLAUDE.md's audio-clock rule). A missing take is said
    plainly rather than answered with some other file."""
    session.audio_path = None
    session.provenance = None

    status, payload, _ = serve_client(session).get("/api/audio")

    assert status == 404
    assert "audio" in payload["error"]


def test_step_3_is_not_reachable_before_there_is_anything_to_output(serve_client):
    client = serve_client(None)

    status, _, headers = client.get("/output")

    assert status in (302, 303)
    assert headers["Location"] == "/input"


# ---------------------------------------------------------------------------
# GET /api/lyrics — what the file declares (§9.3)
# ---------------------------------------------------------------------------


def test_the_lyrics_route_reports_what_an_sp_json_declares(client, libertad):
    status, payload, _ = client.get(f"/api/lyrics?path={libertad['song_path']}")

    assert status == 200
    assert payload["branch"] == "sp"
    assert payload["slug"] == "libertad"
    assert payload["declaredLanguages"] == ["es", "en", "fr", "nl"]
    assert payload["lineCount"] == len(libertad["lines"])
    assert payload["strippedLines"] == []


def test_the_lyrics_route_reports_what_the_normaliser_will_strip(client, tmp_path):
    """§9.3 and §3: shown BEFORE the run. A silent line-count change
    surfaces much later as a `promote` refusal, which is a bad place to
    learn it."""
    txt = tmp_path / "pimiento.txt"
    txt.write_text("uno dos\n\n[Estribillo]\ntres cuatro\n", encoding="utf-8")

    _, payload, _ = client.get(f"/api/lyrics?path={txt}")

    assert payload["branch"] == "txt"
    assert payload["slug"] == "pimiento"
    assert payload["lineCount"] == 2
    assert [s["reason"] for s in payload["strippedLines"]] == ["blank", "bracketed"]
    assert payload["strippedLines"][1]["text"] == "[Estribillo]"


def test_the_stripped_lines_come_from_the_reader_not_a_second_count(client, tmp_path):
    """From `readers.py`'s own `strippedLines`, never recomputed — two
    implementations of "what counts as a lyric line" is the drift B5's
    boundary exists to prevent."""
    txt = tmp_path / "x.txt"
    txt.write_text("uno\n\n[Coro]\ndos\n", encoding="utf-8")

    with mock.patch.object(
        server, "read_lyrics_input", wraps=server.read_lyrics_input
    ) as reader:
        client.get(f"/api/lyrics?path={txt}")

    assert reader.called


def test_a_txt_declares_every_language(client, tmp_path):
    txt = tmp_path / "x.txt"
    txt.write_text("uno dos\n", encoding="utf-8")

    _, payload, _ = client.get(f"/api/lyrics?path={txt}")

    assert payload["declaredLanguages"] == []
    assert payload["branch"] == "txt"


# ---------------------------------------------------------------------------
# the language constraint is ENFORCED, not merely rendered (§3, §9.3)
# ---------------------------------------------------------------------------


def test_a_language_the_file_does_not_declare_cannot_be_run(client, libertad):
    """A language with no lines has nothing to anchor. A dropdown that
    only *renders* the guard is a guard a page reload removes."""
    status, payload, _ = client.post(
        "/api/run",
        {
            "lyrics": str(libertad["song_path"]),
            "media": str(libertad["audio"]),
            "lang": "de",
            "model": "tiny",
        },
    )

    assert status == 400
    assert "de" in payload["error"]


def test_the_page_disables_what_the_file_does_not_declare(serve_client):
    """And the rendered page carries the same guard, so the user never
    reaches the refusal in the first place."""
    from bombista import pages

    assert "disabled" in pages.render_input()
    assert "declaredLanguages" in pages.render_input()


# ---------------------------------------------------------------------------
# POST /api/run — page 1 -> page 1.5 (§9.4)
# ---------------------------------------------------------------------------


def _start(client, libertad, **overrides):
    body = {
        "lyrics": str(libertad["song_path"]),
        "media": str(libertad["audio"]),
        "lang": "es",
        "model": "tiny",
    }
    body.update(overrides)
    return client.post("/api/run", body)


def test_a_run_transcribes_then_anchors_and_leaves_a_session(serve_client, libertad):
    client = serve_client(None)
    fake = words_for(libertad["lines"])

    with mock.patch.object(server, "transcribe_words", return_value=fake) as transcribe:
        status, payload, _ = _start(client, libertad)
        done = wait_for(client, "done")

    assert status == 200
    assert payload["state"] in ("running", "transcribing")
    assert [phase["name"] for phase in done["phases"]] == ["transcribe", "anchor"]
    assert all(phase["state"] == "done" for phase in done["phases"])
    assert transcribe.call_args.kwargs["model_size"] == "tiny"

    _, session_payload, _ = client.get("/api/session")
    assert len(session_payload["lines"]) == len(libertad["lines"])


def test_the_run_delegates_and_never_reimplements_the_anchoring(serve_client, libertad):
    client = serve_client(None)
    fake = words_for(libertad["lines"])

    with (
        mock.patch.object(server, "transcribe_words", return_value=fake),
        mock.patch.object(server, "anchor_lines", wraps=server.anchor_lines) as anchor,
    ):
        _start(client, libertad)
        wait_for(client, "done")

    assert anchor.called


def test_a_second_run_reuses_the_transcription(serve_client, libertad):
    """§9.4's one line of copy is the whole ergonomics of the correction
    loop: coming back reuses asr-words.jsonl and takes well under a second.
    The staging directory here already holds one."""
    client = serve_client(None)

    with mock.patch.object(server, "transcribe_words") as transcribe:
        _start(client, libertad, staging=str(libertad["staging"]))
        done = wait_for(client, "done")

    assert not transcribe.called
    assert done["phases"][0]["state"] == "cached"


def test_a_run_reports_its_phases_while_it_works(serve_client, libertad):
    client = serve_client(None)
    gate = {"released": False}

    def slow(*args, **kwargs):
        while not gate["released"]:
            time.sleep(0.01)
        return words_for(libertad["lines"])

    with mock.patch.object(server, "transcribe_words", side_effect=slow):
        _start(client, libertad)
        running = wait_for(client, "transcribing")
        assert running["phases"][0]["state"] == "running"
        assert running["phases"][0]["elapsedSec"] >= 0
        assert running["phases"][1]["state"] == "waiting"
        gate["released"] = True
        wait_for(client, "done")


def test_a_run_is_transcribing_only_once_transcription_has_begun(serve_client, libertad):
    """§12.3, and the invariant asserted on the payload rather than read
    off the source: `state == "transcribing"` implies
    `phases[0].state == "running"`. They are one fact with one writer.
    A run claiming transcription while its phase list says nothing has
    started is §9.4's state degraded into a spinner with extra rows, and
    the window was only ever a few milliseconds wide — so this samples
    from the very first payload there is, the one `POST /api/run` hands
    back before the caller can ask for another."""
    client = serve_client(None)
    gate = {"released": False}

    def slow(*args, **kwargs):
        while not gate["released"]:
            time.sleep(0.01)
        return words_for(libertad["lines"])

    with mock.patch.object(server, "transcribe_words", side_effect=slow):
        _, first, _ = _start(client, libertad)
        seen = [first] + [client.get("/api/run")[1] for _ in range(50)]
        gate["released"] = True
        wait_for(client, "done")

    assert any(payload["state"] == "transcribing" for payload in seen)
    for payload in seen:
        if payload["state"] == "transcribing":
            assert payload["phases"][0]["state"] == "running", payload


def test_cancel_stops_the_run_and_installs_no_session(serve_client, libertad):
    client = serve_client(None)
    gate = {"released": False}

    def slow(*args, **kwargs):
        while not gate["released"]:
            time.sleep(0.01)
        return words_for(libertad["lines"])

    with mock.patch.object(server, "transcribe_words", side_effect=slow):
        _start(client, libertad)
        wait_for(client, "transcribing")
        status, payload, _ = client.delete("/api/run")
        gate["released"] = True
        cancelled = wait_for(client, "cancelled")

    assert status == 200
    assert payload["state"] == "cancelled"
    assert cancelled["phases"][1]["state"] == "waiting", "anchoring must never start"
    assert client.get("/api/session")[0] == 404


def test_two_runs_cannot_overlap(serve_client, libertad):
    client = serve_client(None)
    gate = {"released": False}

    def slow(*args, **kwargs):
        while not gate["released"]:
            time.sleep(0.01)
        return words_for(libertad["lines"])

    with mock.patch.object(server, "transcribe_words", side_effect=slow):
        _start(client, libertad)
        wait_for(client, "transcribing")
        status, payload, _ = _start(client, libertad)
        gate["released"] = True
        wait_for(client, "done")

    assert status == 409
    assert "already" in payload["error"]


def test_a_failed_run_says_why_and_does_not_wedge_the_process(serve_client, libertad):
    client = serve_client(None)

    with mock.patch.object(server, "transcribe_words", side_effect=RuntimeError("no model")):
        _start(client, libertad)
        failed = wait_for(client, "failed")

    assert "no model" in failed["error"]
    assert client.get("/api/session")[0] == 404


# ---------------------------------------------------------------------------
# tempo — never derived, and absent rather than blank (rules 4 and 5)
#
# The two structural guards that used to live here — no bpm in the modules
# that touch audio or lyrics, and no tempo anywhere in `server.py` — moved
# to tests/test_validation.py's neighbour, tests/test_tempo.py, when round A
# gave the review page a control. Step 6 moved that control to page 1, so
# the run route is now the door a typed tempo comes through; what it
# accepts and what it refuses is pinned in test_tempo.py beside the gate
# itself. What stays here is the flow's own rule: a run that was told no
# tempo emits no tempo key.
# ---------------------------------------------------------------------------


def test_a_scalar_tempo_posted_by_hand_is_still_refused(serve_client, libertad, tmp_path):
    """The bpm-only block §11.5 closed the door on, in its crudest form.
    The route reaches for the shared gate rather than judging a number
    itself, so `66.67` is refused in the same words `bombista validate`
    refuses it in."""
    client = serve_client(None)
    txt = tmp_path / "cancion.txt"
    txt.write_text("uno dos\ntres cuatro\n", encoding="utf-8")

    status, payload, _ = _start(
        client, libertad, lyrics=str(txt), info={"title": "Canción"}, tempo=66.67
    )

    assert status == 400
    assert "bpm" in payload["error"]


def test_a_txt_run_with_no_tempo_emits_no_tempo_key(serve_client, libertad, tmp_path):
    """songs@c5adf65: removed outright, not replaced with a flag or a null.
    `null` is not neutral once a consumer reads it."""
    client = serve_client(None)
    txt = tmp_path / "cancion.txt"
    txt.write_text("uno dos\ntres cuatro\n", encoding="utf-8")

    with mock.patch.object(
        server, "transcribe_words", return_value=words_for(["uno dos", "tres cuatro"])
    ):
        _start(client, libertad, lyrics=str(txt), info={"title": "Canción"})
        wait_for(client, "done")

    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    assert "tempo" not in emitted


def test_a_passed_through_tempo_is_never_rewritten(client, libertad):
    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    assert emitted["tempo"] == libertad["song"]["tempo"]


# ---------------------------------------------------------------------------
# §10.2.1 — two shapes, one format
# ---------------------------------------------------------------------------


def test_the_round_trip_is_lossless_for_every_key_bombista_does_not_own(client, libertad):
    """Including all four languages on every lyrics entry — the first pass
    flattened them to strings, which would have destroyed every
    translation."""
    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)
    original = libertad["song"]

    for key in ("title", "artist", "notes", "title_translations", "tempo", "intro"):
        assert emitted[key] == original[key]
    assert emitted["lyrics"] == original["lyrics"]
    assert sorted(emitted["lyrics"][0]) == ["en", "es", "fr", "nl"]


def test_the_emitted_file_preserves_the_song_files_own_key_order(client, libertad):
    """§10.2 fixes the order against the real files — and the real files
    disagree with each other (`tempo` sits before `title_translations` in
    libertad, after it in pimiento). Both are valid; nothing reads these by
    position. So the rule is preservation, not a canonical order."""
    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = list(json.loads(payload))
    passed_through = [k for k in libertad["song"] if k != "timeline"]

    assert emitted[: len(passed_through)] == passed_through
    assert emitted[len(passed_through) :] == [
        "linesHash",
        "timelineSignedOff",
        "timelineVersion",
        "leadIn",
        "timeline",
    ]


def test_the_lyrics_route_reports_what_page_1_should_prefill(client, libertad):
    """Step 6: page 1 collects the song's general information, so it has
    to show what the file already says before anyone retypes it. The
    prefill is read off the file by the reader that already normalises it,
    never assembled a second time in the page."""
    _, payload, _ = client.get("/api/lyrics?path=" + str(libertad["song_path"]))
    info = payload["info"]

    assert info["title"] == libertad["song"]["title"]
    assert info["artist"] == libertad["song"]["artist"]
    assert info["notes"] == libertad["song"]["notes"]
    assert info["title_translations"] == libertad["song"]["title_translations"]


def test_a_txt_prefills_a_title_seeded_from_the_slug(client, tmp_path):
    """`hasta-calmar-el-alma` -> `Hasta calmar el alma`, which is what
    `bombista new` seeds. Two doors into the same tool should not disagree
    about the first thing they write."""
    txt = tmp_path / "hasta-calmar-el-alma.txt"
    txt.write_text("uno dos\n", encoding="utf-8")

    _, payload, _ = client.get("/api/lyrics?path=" + str(txt))

    assert payload["info"]["title"] == "Hasta calmar el alma"
    assert payload["info"]["artist"] == ""
    assert payload["info"]["title_translations"] == {}
    assert payload["tempo"] is None


def test_the_general_information_typed_on_page_1_lands_in_the_file(
    serve_client, libertad, tmp_path
):
    """The whole reason the block is on page 1: this is the metadata a
    `.txt` cannot carry, and without it a song made from words and a
    recording has no artist and no translated titles."""
    client = serve_client(None)
    txt = tmp_path / "cancion.txt"
    txt.write_text("uno dos\ntres cuatro\n", encoding="utf-8")

    with mock.patch.object(
        server, "transcribe_words", return_value=words_for(["uno dos", "tres cuatro"])
    ):
        _start(
            client,
            libertad,
            lyrics=str(txt),
            info={
                "title": "Canción",
                "artist": "Chango Pepper",
                "notes": "Capo 5",
                "title_translations": {"es": "Canción", "en": "Song", "nl": "", "fr": ""},
            },
        )
        wait_for(client, "done")

    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    assert emitted["title"] == "Canción"
    assert emitted["artist"] == "Chango Pepper"
    assert emitted["notes"] == "Capo 5"
    assert emitted["title_translations"] == {"es": "Canción", "en": "Song"}


def test_an_existing_song_can_be_edited_through_the_same_screen(
    serve_client, libertad, tmp_path
):
    """`Save to the catalogue` is worded for this: the flow is not always
    about a new song. Editing one means the general information typed on
    page 1 replaces what the file said, and everything else passes
    through."""
    client = serve_client(None)

    with mock.patch.object(
        server, "transcribe_words", return_value=words_for(libertad["lines"])
    ):
        _start(
            client,
            libertad,
            info={"artist": "Alguien más", "title": libertad["song"]["title"]},
        )
        wait_for(client, "done")

    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    assert emitted["artist"] == "Alguien más"
    assert emitted["title"] == libertad["song"]["title"]
    assert emitted["lyrics"] == libertad["song"]["lyrics"]
    assert list(emitted)[: len(libertad["song"]) - 1] == [
        k for k in libertad["song"] if k != "timeline"
    ]


def test_a_language_page_1_did_not_offer_survives_an_edit(serve_client, libertad, tmp_path):
    """The page offers four languages; a song file may carry a fifth. A
    field that was never on screen must not be able to delete a value —
    only the languages the page actually posted are the ones it decides."""
    song = dict(libertad["song"])
    song["title_translations"] = {**song["title_translations"], "de": "Freiheit"}
    path = tmp_path / "with-german.json"
    path.write_text(json.dumps(song, ensure_ascii=False, indent=2), encoding="utf-8")

    client = serve_client(None)
    with mock.patch.object(
        server, "transcribe_words", return_value=words_for(libertad["lines"])
    ):
        _start(
            client,
            libertad,
            lyrics=str(path),
            info={"title_translations": {"en": "Freedom", "es": "", "nl": "", "fr": ""}},
        )
        wait_for(client, "done")

    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    assert emitted["title_translations"] == {"en": "Freedom", "de": "Freiheit"}


def test_a_run_that_says_nothing_about_the_song_changes_nothing(client, libertad):
    """A session booted straight into the review — `serve <staging> <song>`
    — was told no general information at all, and passes every key
    through byte for byte. Page 1's block must not become a rule about
    files that never met it."""
    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    for key in ("title", "artist", "notes", "title_translations"):
        assert emitted[key] == libertad["song"][key]


def test_a_txt_run_emits_the_from_scratch_shape(serve_client, libertad, tmp_path):
    """Jorge's sketch, 2026-08-15, is the contract."""
    client = serve_client(None)
    txt = tmp_path / "cancion.txt"
    txt.write_text("uno dos\ntres cuatro\n", encoding="utf-8")

    with mock.patch.object(
        server, "transcribe_words", return_value=words_for(["uno dos", "tres cuatro"])
    ):
        _start(client, libertad, lyrics=str(txt), info={"title": "Canción"}, lang="es")
        wait_for(client, "done")

    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    assert emitted["title"] == "Canción"
    assert emitted["artist"] == ""
    assert emitted["notes"] == ""
    assert emitted["title_translations"] == {"es": "Canción"}
    assert "intro" not in emitted
    assert "tempo" not in emitted
    assert emitted["lyrics"] == [{"es": "uno dos"}, {"es": "tres cuatro"}]


def test_entry_0_is_zero_and_the_offset_is_in_lead_in(client):
    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    assert emitted["timeline"][0]["start"] == 0.00
    assert emitted["leadIn"]["durationSec"] == 10.00


def test_no_emitted_file_carries_a_qa_block(client):
    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    for key in ("format", "review", "provenance", "_bombista", "bands", "signals"):
        assert key not in emitted


# ---------------------------------------------------------------------------
# the three downloads (§9.5) and B19's surviving clause
# ---------------------------------------------------------------------------


def test_the_timeline_download_is_the_five_timing_keys(client):
    """Never a bare timeline array — that is the unguarded artifact B4
    exists to prevent, and it cannot say a human ever read it."""
    _, payload, headers = client.get("/api/download?kind=timeline", raw=True)
    block = json.loads(payload)

    assert list(block) == [
        "linesHash",
        "timelineSignedOff",
        "timelineVersion",
        "leadIn",
        "timeline",
    ]
    assert "attachment" in headers["Content-Disposition"]


def test_the_report_download_is_markdown_with_the_bands_and_the_hand_set_lines(client):
    _, payload, headers = client.get("/api/download?kind=report", raw=True)

    assert headers["Content-Type"].startswith("text/markdown")
    assert "HIGH" in payload
    assert "Bands:" in payload


def test_both_json_downloads_record_the_sign_off_and_the_report_does_not(client):
    """B19's surviving clause: the report certifies nothing and taking it
    is not a decision."""
    assert client.get("/api/session")[1]["timelineSignedOff"] is None

    client.get("/api/download?kind=report", raw=True)
    assert client.get("/api/session")[1]["timelineSignedOff"] is None

    client.get("/api/download?kind=song", raw=True)
    signed = client.get("/api/session")[1]["timelineSignedOff"]
    assert signed

    client.get("/api/download?kind=timeline", raw=True)
    assert client.get("/api/session")[1]["timelineSignedOff"] == signed, (
        "the sign-off is recorded once; it is not a budget"
    )


def test_every_sp_json_this_tool_can_produce_carries_a_sign_off(client, tmp_path):
    """There is no path to an unsigned one — §3's clause is what makes a
    reviewed timeline distinguishable from a machine one after the file
    leaves the folder its report is in."""
    for kind in ("song", "timeline"):
        _, payload, _ = client.get(f"/api/download?kind={kind}", raw=True)
        assert json.loads(payload)["timelineSignedOff"]

    out = tmp_path / "out.json"
    client.post("/api/emit", {"out": str(out)})
    assert json.loads(out.read_text(encoding="utf-8"))["timelineSignedOff"]


def test_a_download_writes_nothing_to_disk(client, libertad, tmp_path):
    """Invariant 6, trivially: a download hands over bytes. Nothing on
    page 3 chooses a path, so nothing on page 3 can overwrite one."""
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}

    for kind in ("song", "timeline", "report"):
        client.get(f"/api/download?kind={kind}", raw=True)

    after = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_the_download_filename_is_the_slug(client):
    _, _, headers = client.get("/api/download?kind=song", raw=True)

    assert "libertad.json" in headers["Content-Disposition"]


# ---------------------------------------------------------------------------
# §12.2 — the download is a song file
# ---------------------------------------------------------------------------
#
# §10.2 settled that the SP JSON IS the `songs/*.json` format: there is no
# new schema, only a name for the one that exists. A distinct file
# EXTENSION reintroduced the distinction that correction removed, and it
# is the whole reason the reconciliation step looked missing. Called
# `luz-y-sal.json` the download looks like an intermediate artifact you
# must do something with; called `luz-y-sal.json` it is plainly the song
# file, and *replace the old one with it* is the whole procedure.


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        ("song", "libertad.json"),
        ("timeline", "libertad-timeline.json"),
        ("report", "libertad-qa-report.md"),
    ],
)
def test_no_download_carries_the_sp_extension(client, kind, name):
    _, _, headers = client.get(f"/api/download?kind={kind}", raw=True)

    assert f'filename="{name}"' in headers["Content-Disposition"]
    assert ".sp.json" not in headers["Content-Disposition"]


def test_the_downloaded_song_file_is_the_vault_file(client, libertad):
    """§12.2's rule, and the reason no reconciliation is needed anywhere:
    *Bombista receives a file and returns a file. It does not change the
    state of one.* The returned file already carries all five owned keys
    AND every original field untouched, so the vault file IS the returned
    file — replace, do not merge. `linesHash` and `timelineSignedOff` only
    ever went missing on a path that took the returned file apart and
    merged three of its keys into the old one."""
    _, payload, headers = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    assert headers["Content-Disposition"].endswith('filename="libertad.json"')
    for key, value in libertad["song"].items():
        if key not in ("timelineVersion", "leadIn", "timeline"):
            assert emitted[key] == value, key
    for key in ("linesHash", "timelineSignedOff", "timelineVersion", "leadIn", "timeline"):
        assert emitted[key] is not None, key


def test_the_format_is_still_called_the_song_performance_json(client):
    """Only the extension goes (§12.2). The NAME is §10.1 vocabulary and
    it stays in every user-facing string."""
    _, page, _ = client.get("/input")

    assert "Song Performance JSON" in page
    assert "<code>.json</code>" in page
    assert ".sp.json" not in page


def test_a_lyrics_file_is_still_detected_by_its_extension(client, tmp_path):
    """`LYRICS_SUFFIXES` was already `(".json", ".txt")`, so page 1's
    branch detection needs nothing from B22 — verified rather than
    assumed."""
    assert server.LYRICS_SUFFIXES == (".json", ".txt")

    (tmp_path / "luz-y-sal.json").write_text("{}", encoding="utf-8")
    _, payload, _ = client.get(f"/api/browse?path={tmp_path}")

    assert "luz-y-sal.json" in [entry["name"] for entry in payload["entries"]]


# ---------------------------------------------------------------------------
# the file pickers (§9.6) — a loopback browse route, decided in the PR
# ---------------------------------------------------------------------------


def test_the_browse_route_lists_a_directory(client, libertad, tmp_path):
    status, payload, _ = client.get(f"/api/browse?path={tmp_path}")

    assert status == 200
    names = [entry["name"] for entry in payload["entries"]]
    assert "libertad.json" in names
    assert "staging" in names
    assert payload["path"] == str(tmp_path)
    assert payload["parent"] == str(tmp_path.parent)


def test_the_browse_route_marks_directories_and_offers_only_usable_files(
    client, tmp_path
):
    (tmp_path / "notes.docx").write_text("x", encoding="utf-8")
    (tmp_path / "song.json").write_text("{}", encoding="utf-8")

    _, payload, _ = client.get(f"/api/browse?path={tmp_path}")
    by_name = {entry["name"]: entry for entry in payload["entries"]}

    assert by_name["staging"]["dir"] is True
    assert "song.json" in by_name
    assert "notes.docx" not in by_name


def test_the_browse_route_refuses_a_path_that_is_not_a_directory(client, libertad):
    status, payload, _ = client.get(f"/api/browse?path={libertad['song_path']}")

    assert status == 400
    assert "directory" in payload["error"]


def test_the_pickers_never_put_a_path_on_the_page(serve_client):
    """§9.3, decision 1: the path is the tool's business, the file name is
    the user's. The browse route hands the page both; the page renders
    only the name."""
    from bombista import pages

    html = pages.render_input()

    assert "entry.name" in html
    assert not re.search(r'id="lyrics-name"[^>]*>\s*/', html)


# ---------------------------------------------------------------------------
# invariant 7 still holds for everything added here
# ---------------------------------------------------------------------------


def test_the_added_routes_bind_nowhere_new():
    tree = ast.parse(Path(server.__file__).read_text(encoding="utf-8"))

    addresses = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.replace(".", "").isdigit()
        and "." in node.value
    }

    assert addresses <= {"127.0.0.1"}


def test_serve_starts_at_step_1_with_no_arguments():
    """Page 1 is the entry point, so `serve` has to be startable without
    already knowing the answers page 1 asks for. The two-argument form is
    PR 2's development seam and still boots straight into the review."""
    from click.testing import CliRunner

    from bombista.cli import main

    with mock.patch("bombista.cli.create_server") as create:
        create.return_value.server_address = ("127.0.0.1", 51234)
        create.return_value.serve_forever.side_effect = KeyboardInterrupt
        result = CliRunner().invoke(main, ["serve"])

    assert result.exit_code == 0, result.output
    assert create.call_args.args[0] is None


def test_the_report_download_renders_from_a_staging_dir_that_only_has_the_sibling(
    serve_client, libertad
):
    """`asr-words.meta.json` is now a provenance carrier (§11.10), and it
    is a PARTIAL one — no duration, no tool version, because a
    transcription does not establish them in the way the report's other
    carriers do. The report has to render what it was given plus a stated
    unknown for the rest, not fall over on a missing key. A run started
    from page 1 leaves exactly this shape behind."""
    (libertad["staging"] / "asr-words.meta.json").write_text(
        json.dumps(
            {
                "extractedAt": "2026-08-14T20:55:00+02:00",
                "model": "faster-whisper:medium",
                "device": "cpu/int8",
                "lang": "es",
                "sha256": "ab" * 32,
                "audio": str(libertad["audio"]),
            }
        ),
        encoding="utf-8",
    )
    session = server.load_session(libertad["staging"], libertad["song_path"], lang="es")

    status, report, _ = serve_client(session).get("/api/download?kind=report", raw=True)

    assert status == 200
    assert "2026-08-14T20:55:00+02:00" in report
    assert "ab" * 32 in report
    assert "unknown" in report, "the keys the sibling does not carry are said, not guessed"
