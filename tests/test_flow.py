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


def test_the_entry_point_is_step_1_when_there_is_nothing_to_review(serve_client, staging_root):
    """**Once this machine has produced a song.** Before that the door
    opens on the deal instead — one screen, met once, in front of a flow
    that asks for a sitting before anything works. The rule and both of its
    sources of truth are in tests/test_deal.py; what is asserted here is
    that the deal is the only thing in front of step 1, and that it stops
    being there on its own."""
    (staging_root / "libertad").mkdir(parents=True)
    (staging_root / "libertad" / "libertad.json").write_text("{}", encoding="utf-8")
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
    # ...and the sibling, which is `audio_path_for`'s second source: the
    # take is unfindable only when nothing on disk names it either.
    (session.staging_dir / "asr-words.meta.json").unlink()

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
# tempo emits no tempo key — and, since 2026-09-02, that the RUN is not
# where a half-typed one is refused. Alignment never reads a tempo, so the
# file answers for it and the ninety seconds are not withheld.
# ---------------------------------------------------------------------------


def test_a_scalar_tempo_posted_by_hand_never_reaches_a_file(
    serve_client, libertad, tmp_path, staging_root
):
    """The bpm-only block §11.5 closed the door on, in its crudest form.
    Since 2026-09-02 the run carries it and the FILE refuses it — through
    the shared gate, so it is refused in the same words `bombista
    validate` refuses it in."""
    client = serve_client(None)
    txt = tmp_path / "cancion.txt"
    txt.write_text("uno dos\ntres cuatro\n", encoding="utf-8")

    with mock.patch.object(
        server, "transcribe_words", return_value=words_for(["uno dos", "tres cuatro"])
    ):
        status, _, _ = _start(
            client, libertad, lyrics=str(txt), info={"title": "Canción"}, tempo=66.67
        )
        assert status == 200
        wait_for(client, "done")

    status, payload, _ = client.get("/api/download?kind=song")

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
    # No translations: the page has no field for one since 2026-09-02, and
    # reporting a value nothing renders invites the field to be rebuilt.
    assert "title_translations" not in info


def test_an_edit_no_longer_prefills_the_take(serve_client, libertad, tmp_path):
    """**THE PREFILL GOES WITH THE MEDIA REFERENCE** (Jorge, 2026-09-04).

    It was added on 2026-09-02 — *being asked is not the problem; being asked
    silently is* — and it is correct to remove now for the reason that made it
    possible: **the song recorded the take it was aligned against, and it does
    not any more.** Under *the song holds no media* this tool emits no media
    reference at all, so both of `previous_take`'s sources describe a fact
    nothing writes.

    **The cost was named and weighed:** a timeline will no longer say what
    produced it. Jorge: *the principle of clean boundaries is worth more*, and
    *I just have to process the audio again, it is a matter of seconds*.

    **Page 1 still ASKS for a recording** — that is the alignment input and it
    stays. The field simply starts empty.
    """
    client = serve_client(None, staging=libertad["staging"])

    _, payload, _ = client.get("/api/lyrics?path=" + str(libertad["song_path"]))

    assert payload["media"] is None


# ---------------------------------------------------------------------------
# page 1 describes the FILE, never what the server did last (2026-09-02)
#
# The class of bug, not the instance. `previous_take` read the take out of
# the staging directory with no reference to which song was being described,
# so a shared staging directory handed every song the last one's recording.
# Walked: a `.txt` that had never been aligned against anything arrived with
# a 2:40 take attached, the consent popup never appeared because a media
# source was set, and the review came back with every line `no-anchor`.
#
# The guard below is the general statement — what `/api/lyrics` says about a
# file must not depend on what ran before it — in the same spirit as the
# missing-id test written for `Confirm timeline`.
# ---------------------------------------------------------------------------


def _describe(client, path):
    return client.get("/api/lyrics?path=" + str(path))[1]


def test_describing_a_file_says_the_same_thing_before_and_after_another_run(
    serve_client, libertad, tmp_path
):
    """**The invariant this class violates.** Page 1's fields are derived
    from the file being described. A run that happened first may make the
    answer *slower* to compute, never *different* — so describing a file on
    a server that has just run another song must equal describing it on a
    server that has run nothing.

    Anything page 1 prefills is covered, not just the media source: the
    same shared-staging leak would reach a title or a tempo the same way.
    """
    other = tmp_path / "another-song.txt"
    other.write_text("palabras distintas\nde otra cancion\n", encoding="utf-8")
    # EMPTY, so the run is what puts a previous take in it. Pointing this at
    # a directory that already held one would let the leak hide: both
    # answers would be equally wrong.
    staging = tmp_path / "shared-staging"
    staging.mkdir()

    fresh = _describe(serve_client(None, staging=staging), other)
    assert fresh["media"] is None, "the empty directory already answered something"

    used = serve_client(None, staging=staging)
    with mock.patch.object(
        server, "transcribe_words", return_value=words_for(libertad["lines"])
    ):
        _start(used, libertad, staging=str(staging))
        wait_for(used, "done")

    assert (staging / "asr-words.meta.json").exists(), "the run recorded nothing to leak"
    assert _describe(used, other) == fresh


def test_a_txt_never_arrives_with_a_recording_attached(serve_client, libertad, tmp_path):
    """The instance, pinned where it happened. A plain text file carries no
    record of any recording, so there is no honest source for one — and a
    prefilled media source is what silently skipped the consent popup and
    sent a song's words to be aligned against another song's audio."""
    other = tmp_path / "another-song.txt"
    other.write_text("palabras distintas\n", encoding="utf-8")

    client = serve_client(None, staging=libertad["staging"])

    assert _describe(client, other)["media"] is None


def test_a_song_is_never_handed_the_take_of_a_different_song(
    serve_client, libertad, tmp_path
):
    """A staging directory is not necessarily one song's. The meta names
    the song it transcribed for, and a meta that names another one is not
    a match — an unknown or foreign provenance answers no."""
    stranger = tmp_path / "stranger.json"
    stranger.write_text(
        json.dumps({"title": "S", "lyrics": [{"es": "uno"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    client = serve_client(None, staging=libertad["staging"])

    # **Neither is handed one now**, because nothing is prefilled at all — which
    # is the strongest form of this guard rather than a weakening of it.
    assert _describe(client, libertad["song_path"])["media"] is None
    assert _describe(client, stranger)["media"] is None


def test_a_cached_transcription_is_not_reused_for_a_different_take(
    serve_client, libertad, tmp_path
):
    """The same wrong-take failure, arriving through the cache. The words
    file is a transcription of ONE recording; a staging directory may be
    reused for another. Reusing it regardless would have the machine report
    it listened when it listened to something else (§11.11)."""
    another_take = tmp_path / "another-take.m4a"
    another_take.write_bytes(b"\0" * 64)
    client = serve_client(None)

    with mock.patch.object(
        server, "transcribe_words", return_value=words_for(libertad["lines"])
    ) as transcribe:
        _start(
            client,
            libertad,
            media=str(another_take),
            staging=str(libertad["staging"]),
        )
        done = wait_for(client, "done")

    assert transcribe.called, "the previous take's transcription was reused"
    assert done["phases"][0]["state"] == "done"


def test_the_take_is_not_guessed_when_nothing_recorded_one(serve_client, libertad):
    """Never another file. A prefill that quietly named a different
    recording would make every judgement about it wrong, and the person
    would not know."""
    client = serve_client(None)

    _, payload, _ = client.get("/api/lyrics?path=" + str(libertad["song_path"]))

    assert payload["media"] is None


def test_a_txt_prefills_a_title_seeded_from_the_slug(client, tmp_path):
    """`hasta-calmar-el-alma` -> `Hasta calmar el alma`, the catalogue's
    own convention — a seed to edit, not a claim."""
    txt = tmp_path / "hasta-calmar-el-alma.txt"
    txt.write_text("uno dos\n", encoding="utf-8")

    _, payload, _ = client.get("/api/lyrics?path=" + str(txt))

    assert payload["info"]["title"] == "Hasta calmar el alma"
    assert payload["info"]["artist"] == ""
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
            info={"title": "Canción", "artist": "Chango Pepper", "notes": "Capo 5"},
        )
        wait_for(client, "done")

    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    assert emitted["title"] == "Canción"
    assert emitted["artist"] == "Chango Pepper"
    assert emitted["notes"] == "Capo 5"


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


def test_an_edit_never_touches_the_songs_translations(serve_client, libertad, tmp_path):
    """Walked 2026-09-02: translation is not Bombista's concern, so page 1
    stopped asking. The other half of that rule is that the file's own
    translations are **untouched** — Bombista reads what is there and never
    collects, rewrites or drops it, whatever languages it is in."""
    song = dict(libertad["song"])
    song["title_translations"] = {**song["title_translations"], "de": "Freiheit"}
    path = tmp_path / "with-german.json"
    path.write_text(json.dumps(song, ensure_ascii=False, indent=2), encoding="utf-8")

    client = serve_client(None)
    with mock.patch.object(
        server, "transcribe_words", return_value=words_for(libertad["lines"])
    ):
        _start(client, libertad, lyrics=str(path), info={"artist": "Alguien más"})
        wait_for(client, "done")

    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    assert emitted["artist"] == "Alguien más"
    assert emitted["title_translations"] == song["title_translations"]


def test_a_run_that_says_nothing_about_the_song_changes_nothing(client, libertad):
    """A session booted straight into the review — `serve <staging> <song>`
    — was told no general information at all, and passes every key
    through byte for byte. Page 1's block must not become a rule about
    files that never met it."""
    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    for key in ("title", "artist", "notes", "title_translations"):
        assert emitted[key] == libertad["song"][key]


# ---------------------------------------------------------------------------
# a song with no recording — legitimate, and performed by hand (2026-09-02)
# ---------------------------------------------------------------------------


def test_a_run_with_no_recording_needs_no_transcription_and_leaves_a_session(
    serve_client, tmp_path, staging_root
):
    """**A song with words and no recording is a legitimate song.** It is
    performed by advancing the lines by hand. There is nothing to align,
    so `transcribe_words` must never be reached — and if it were, the
    absence of a recording would be an error rather than a mode."""
    client = serve_client(None)
    txt = tmp_path / "cancion.txt"
    txt.write_text("uno dos\ntres cuatro\n", encoding="utf-8")

    with mock.patch.object(server, "transcribe_words") as never:
        status, _, _ = client.post(
            "/api/run",
            {"lyrics": str(txt), "lang": "es", "model": "tiny", "info": {"title": "Canción"}},
        )
        assert status == 200
        wait_for(client, "done")

    assert not never.called, "a song with no recording was sent to the transcriber"


def test_the_run_reports_both_phases_as_skipped_rather_than_done(
    serve_client, tmp_path, staging_root
):
    """Page 1.5 is a state, not a spinner (§9.4). A run that said *done*
    about work it never did would be that page lying about the only thing
    it exists to show."""
    client = serve_client(None)
    txt = tmp_path / "cancion.txt"
    txt.write_text("uno dos\n", encoding="utf-8")

    client.post("/api/run", {"lyrics": str(txt), "lang": "es", "info": {"title": "C"}})
    payload = wait_for(client, "done")

    assert [phase["state"] for phase in payload["phases"]] == ["skipped", "skipped"]


def test_the_review_sends_a_manual_song_straight_to_the_output(
    serve_client, tmp_path, staging_root
):
    """There is no timeline to review. A page of empty rows would be the
    flow pretending a step happened."""
    client = serve_client(None)
    txt = tmp_path / "cancion.txt"
    txt.write_text("uno dos\n", encoding="utf-8")

    client.post("/api/run", {"lyrics": str(txt), "lang": "es", "info": {"title": "C"}})
    wait_for(client, "done")
    status, _, headers = client.get("/review")

    assert status == 303
    assert headers["Location"] == "/output"


def test_a_manual_song_carries_none_of_the_five_timing_keys(
    serve_client, tmp_path, staging_root
):
    """Not even `linesHash`, which guards a timeline that is not there, and
    not `timelineSignedOff`, which would claim a human reviewed one."""
    client = serve_client(None)
    txt = tmp_path / "cancion.txt"
    txt.write_text("uno dos\ntres cuatro\n", encoding="utf-8")

    client.post(
        "/api/run",
        {
            "lyrics": str(txt),
            "lang": "es",
            "info": {"title": "Canción", "artist": "Chango Pepper"},
            "tempo": {"bpm": 120, "numerator": 4, "denominator": 4, "countInBars": 0},
        },
    )
    wait_for(client, "done")
    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    for key in ("linesHash", "timelineSignedOff", "timelineVersion", "leadIn", "timeline"):
        assert key not in emitted, f"a song with no recording carries {key}"
    assert emitted["title"] == "Canción"
    assert emitted["artist"] == "Chango Pepper"
    assert emitted["lyrics"] == [{"es": "uno dos"}, {"es": "tres cuatro"}]
    assert emitted["tempo"] == {"bpm": 120, "numerator": 4, "denominator": 4}


def test_the_file_a_manual_song_saves_passes_the_performance_gate_as_manual(
    serve_client, tmp_path, staging_root
):
    """The whole point: this file is performable. The gate names the mode
    and does not refuse it, so nothing downstream drops the song."""
    from bombista.validation import errors, load_and_validate, modes

    client = serve_client(None)
    txt = tmp_path / "cancion.txt"
    txt.write_text("uno dos\ntres cuatro\n", encoding="utf-8")

    client.post("/api/run", {"lyrics": str(txt), "lang": "es", "info": {"title": "Canción"}})
    wait_for(client, "done")
    _, written = client.post("/api/emit", {"out": str(tmp_path / "out.json")})[:2]

    found = load_and_validate(tmp_path / "out.json", for_performance=True)

    assert errors(found) == []
    assert [f.where for f in modes(found)] == ["timeline"]


def test_a_manual_song_offers_no_timeline_and_no_report_download(
    serve_client, tmp_path, staging_root
):
    """There is no timeline to paste and no bands to report. Offering
    either would hand over an empty file or a refusal."""
    client = serve_client(None)
    txt = tmp_path / "cancion.txt"
    txt.write_text("uno dos\n", encoding="utf-8")

    client.post("/api/run", {"lyrics": str(txt), "lang": "es", "info": {"title": "C"}})
    wait_for(client, "done")

    assert client.get("/api/download?kind=song")[0] == 200
    for kind in ("timeline", "report"):
        status, payload, _ = client.get(f"/api/download?kind={kind}")
        assert status == 400, f"{kind} was offered on a song with no recording"
        assert "no recording" in payload["error"]


def test_the_output_page_says_the_song_is_advanced_by_hand(
    serve_client, tmp_path, staging_root
):
    """One caption cannot claim a timeline that is not there. The second
    ending says what will happen on the night rather than what is missing
    from the file — and the step bar says step 2 was skipped rather than
    implying a review happened."""
    client = serve_client(None)
    txt = tmp_path / "cancion.txt"
    txt.write_text("uno dos\n", encoding="utf-8")

    client.post("/api/run", {"lyrics": str(txt), "lang": "es", "info": {"title": "C"}})
    wait_for(client, "done")
    page = client.get("/output")[1]

    assert "advanced by hand during the performance" in page
    assert "skipped" in page
    assert 'id="dl-timeline"' not in page
    assert 'id="save"' in page
    # `/review` would only send you back here, and a link that returns you
    # to the page you are on is the flow pretending a step exists.
    assert 'href="/review"' not in page


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


def test_no_emitted_file_carries_a_media_reference(client, libertad):
    """**THE SONG HOLDS NO MEDIA** (Jorge, 2026-09-03).

    A recording derives a timeline and is then irrelevant — **a use-and-forget
    relationship** — and a song never carries something that has to be present
    on the night. What appears on the wall is the visuals, named in
    `visuals.json` by Muralista.

    **The test is whether the media is an INPUT or part of the OUTPUT**, which
    is why the two tools differ rather than disagree: **Bombista consumes a
    recording and produces a timeline, so forgetting it is correct**; Muralista
    consumes a file and produces a shape BOUND to it, so it keeps the name.

    **It is asserted on a run that WAS given a recording**, because the field is
    stripped rather than merely not added: page 1 can be opened on a song file
    that still carries the key, and passing it through would keep re-emitting a
    reference this tool has stopped standing behind.
    """
    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    emitted = json.loads(payload)

    assert "media" not in emitted
    # And the timeline it did produce is still there — this removes a reference,
    # not the work.
    assert emitted["timelineVersion"] == 2
    assert emitted["timeline"]


def test_the_emitted_lead_in_says_nothing_about_whether_it_applies(client):
    """**`leadIn` splits the way the media did** (Jorge, 2026-09-04).

    Its measured VALUE stays with the timeline — a real measurement of the
    words. **The DECISION to apply it is Pregonero's**, from whether a video is
    assigned to the song for a gig; after the split Pregonero is the only party
    that could know. Bombista derived it from `media.type == "video"`, and once
    no song declares media that default would have **silently flipped to False
    and cost every video song its lead-in correction.**
    """
    _, payload, _ = client.get("/api/download?kind=song", raw=True)
    lead_in = json.loads(payload)["leadIn"]

    assert set(lead_in) == {"durationSec", "source", "confidence"}


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


def test_the_pickers_open_where_the_caller_said(serve_client, tmp_path):
    """Walked 2026-09-02: they opened at the home folder, on a screen whose
    whole job is to find a lyrics file and a recording that live in the
    same folder as each other. A caller that knows where the songs are can
    say so — and Bombista learns a directory and nothing else."""
    songs = tmp_path / "songs"
    songs.mkdir()
    client = serve_client(None, browse_from=songs)

    page = client.get("/input")[1]
    _, listing, _ = client.get("/api/browse")

    assert f'var BROWSE_FROM = "{songs}"' in page
    assert listing["path"] == str(songs)


def test_the_home_folder_is_still_the_standalone_default(serve_client):
    """The option exists because the default is wrong for a caller, not
    because it was wrong for somebody running Bombista on its own."""
    client = serve_client(None)

    assert f'var BROWSE_FROM = "{Path.home()}"' in client.get("/input")[1]


def test_a_handed_over_song_prefills_page_1(serve_client, libertad):
    """What makes an edit an edit rather than a second new song. The page
    reaches it through the same route a pick takes, so there is one answer
    to *what does this file say*."""
    client = serve_client(None, song=libertad["song_path"])

    page = client.get("/input")[1]

    assert f'var SONG = "{libertad["song_path"]}"' in page
    assert "if (SONG) {" in page, "the page never acts on it"


def test_no_song_is_handed_over_by_default(serve_client):
    client = serve_client(None)

    assert 'var SONG = "";' in client.get("/input")[1]


def test_the_product_header_can_be_turned_off_on_every_page(serve_client, session):
    """Inside a window somebody else already titled, the product
    introducing itself is the tool talking about itself to a person who did
    not choose it.

    **And the version comes off with it** (Jorge, 2026-09-03), on all three
    pages rather than page by page. The rule it was protecting is intact
    and lives next door in `test_pages.py`: the version has to survive
    somewhere, and it does — in standalone Bombista's masthead and in
    `bombista --version`."""
    from bombista import pages

    client = serve_client(session, header=False)

    for route in ("/deal", "/input", "/review", "/output"):
        page = client.get(route)[1]
        assert "Forced-alignment triage" not in page, f"{route} still introduces the product"
        assert pages.VERSION not in page, f"{route} still carries the version"


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


# ── Where a page-1 run works, when the caller named a directory ────────────────
#
# journey-setup step 6, 2026-09-02. The default is a cache under
# ~/.cache/bombista, which is right for running Bombista on its own and wrong
# for a caller that means to read the `<stem>.json` `Save to the catalogue`
# writes back out: it would have to know this module's cache layout to find the
# file. `serve --staging` is a directory in and a file path on the page — the
# whole of what passes.


def test_a_run_works_in_the_directory_the_caller_named(serve_client, libertad, tmp_path):
    named = tmp_path / "named-staging"
    client = serve_client(None, staging=named)

    with mock.patch.object(server, "transcribe_words", return_value=words_for(libertad["lines"])):
        _start(client, libertad)
        wait_for(client, "done")

    assert (named / "asr-words.jsonl").exists()
    _, payload, _ = client.get("/api/session")
    assert payload  # the session is the run's, and it is in the named directory


def test_the_page_names_the_file_it_will_write_in_that_directory(
    serve_client, libertad, tmp_path
):
    """`Save to the catalogue` writes `<staging>/<stem>.json`, and the page
    prints the path before the press. That is the file the caller promotes."""
    named = tmp_path / "named-staging"
    client = serve_client(None, staging=named)

    with mock.patch.object(server, "transcribe_words", return_value=words_for(libertad["lines"])):
        _start(client, libertad)
        wait_for(client, "done")

    _, body, _ = client.get("/output", raw=True)
    assert str(named / f"{libertad['song_path'].stem}.json") in body


def test_the_body_still_wins_over_the_named_directory(serve_client, libertad, tmp_path):
    named = tmp_path / "named-staging"
    client = serve_client(None, staging=named)

    with mock.patch.object(server, "transcribe_words") as transcribe:
        _start(client, libertad, staging=str(libertad["staging"]))
        wait_for(client, "done")

    assert not transcribe.called  # it used the body's directory, which is cached
    assert not named.exists()


def test_without_a_named_directory_the_cache_is_unchanged(serve_client, libertad, staging_root):
    client = serve_client(None)

    with mock.patch.object(server, "transcribe_words", return_value=words_for(libertad["lines"])):
        _start(client, libertad)
        wait_for(client, "done")

    assert (staging_root / libertad["song_path"].stem / "asr-words.jsonl").exists()


def test_the_file_the_manual_flow_writes_is_the_file_promote_accepts(
    serve_client, tmp_path, staging_root
):
    """**The end-to-end check the previous five mismatches each lacked.**
    Each of them was one side producing a value deliberately and the other
    refusing it, found by walking rather than by testing. This runs the
    real flow's output through the real `promote`, so the two cannot drift
    apart again without a red test.
    """
    from bombista.promotion import promote_candidate

    client = serve_client(None)
    txt = tmp_path / "manual.txt"
    txt.write_text("uno dos\ntres cuatro\n", encoding="utf-8")

    client.post(
        "/api/run",
        {
            "lyrics": str(txt),
            "lang": "es",
            "info": {"title": "Manual", "artist": "Chango Pepper"},
            "tempo": {"bpm": 66.67, "numerator": 6, "denominator": 8, "countInBars": 0},
        },
    )
    wait_for(client, "done")
    _, written = client.post("/api/emit", {})[:2]

    catalogue = tmp_path / "song-performance" / "manual.json"
    promote_candidate(Path(written["path"]), catalogue, note=lambda message: None)

    song = json.loads(catalogue.read_text(encoding="utf-8"))
    assert song["title"] == "Manual"
    assert song["artist"] == "Chango Pepper"
    assert song["tempo"] == {"bpm": 66.67, "numerator": 6, "denominator": 8}
    assert song["lyrics"] == [{"es": "uno dos"}, {"es": "tres cuatro"}]
    for key in ("linesHash", "timelineSignedOff", "timelineVersion", "leadIn", "timeline"):
        assert key not in song


def test_that_promoted_file_then_passes_the_performance_gate(
    serve_client, tmp_path, staging_root
):
    """And the far end of the same chain: the song the flow made is one the
    gate calls performable, naming the mode."""
    from bombista.promotion import promote_candidate
    from bombista.validation import errors, load_and_validate, modes

    client = serve_client(None)
    txt = tmp_path / "manual.txt"
    txt.write_text("uno dos\n", encoding="utf-8")

    client.post("/api/run", {"lyrics": str(txt), "lang": "es", "info": {"title": "M"}})
    wait_for(client, "done")
    _, written = client.post("/api/emit", {})[:2]

    catalogue = tmp_path / "song-performance" / "manual.json"
    promote_candidate(Path(written["path"]), catalogue, note=lambda message: None)
    found = load_and_validate(catalogue, for_performance=True)

    assert errors(found) == []
    assert [f.where for f in modes(found)] == ["timeline"]


# ---------------------------------------------------------------------------
# the step bar is navigation, not a reset (2026-09-02)
#
# Page 1 rendered empty whatever the session held, so pressing `1 Input`
# discarded the files, the language, the model and everything typed about
# the song. It also made the tempo backstop a wall: the refusal at `Save to
# the catalogue` says to finish the tempo on page 1, and the only way to
# page 1 threw away the answers the refusal was about.
# ---------------------------------------------------------------------------


def _restored(client):
    """What page 1 hands its own script when a session exists."""
    page = client.get("/input")[1]
    return json.loads(re.search(r"var ANSWERS = (.*?);\n", page).group(1))


def test_returning_to_step_1_keeps_every_answer(serve_client, tmp_path, staging_root):
    """The files, the language, the model, and everything typed about the
    song. Nothing here is new state — the session has held all of it since
    the run; page 1 simply never asked."""
    client = serve_client(None)
    txt = tmp_path / "manual.txt"
    txt.write_text("uno dos\ntres cuatro\n", encoding="utf-8")

    client.post(
        "/api/run",
        {
            "lyrics": str(txt),
            "lang": "es",
            "model": "tiny",
            "info": {"title": "Sin Grabación", "artist": "Chango Pepper", "notes": "Capo 3"},
            "tempo": {"bpm": 66.67, "numerator": 6, "denominator": 8, "countInBars": 0},
        },
    )
    wait_for(client, "done")
    answers = _restored(client)

    assert answers["lyrics"]["path"] == str(txt)
    assert answers["lang"] == "es"
    assert answers["model"] == "tiny", "the model was chosen and must come back"
    assert answers["info"] == {
        "title": "Sin Grabación",
        "artist": "Chango Pepper",
        "notes": "Capo 3",
    }
    assert answers["tempo"] == {"bpm": 66.67, "numerator": 6, "denominator": 8}


def test_a_half_typed_tempo_comes_back_so_the_backstop_can_be_acted_on(
    serve_client, tmp_path, staging_root
):
    """**The wall this fix exists for.** `Save to the catalogue` refuses a
    half-typed tempo and says to finish it on page 1. If page 1 discards
    it, the instruction cannot be followed."""
    client = serve_client(None)
    txt = tmp_path / "manual.txt"
    txt.write_text("uno dos\n", encoding="utf-8")

    client.post(
        "/api/run",
        {
            "lyrics": str(txt),
            "lang": "es",
            "info": {"title": "M"},
            "tempo": {"numerator": 6, "denominator": 8, "countInBars": 0},
        },
    )
    wait_for(client, "done")
    answers = _restored(client)

    assert answers["tempo"] is None
    assert answers["tempoIncomplete"] == {"numerator": 6, "denominator": 8}


def test_going_back_with_no_recording_costs_nothing_and_says_nothing(
    serve_client, tmp_path, staging_root
):
    """There is no run to redo, so there is nothing to warn about. A
    warning here would be the page inventing a cost."""
    client = serve_client(None)
    txt = tmp_path / "manual.txt"
    txt.write_text("uno dos\n", encoding="utf-8")

    client.post("/api/run", {"lyrics": str(txt), "lang": "es", "info": {"title": "M"}})
    wait_for(client, "done")

    assert _restored(client)["handSetLines"] == 0


def test_going_back_after_corrections_says_what_running_again_costs(
    serve_client, libertad, tmp_path
):
    """**Said, rather than discovered.** A new run re-anchors from the
    machine's timings, so the lines corrected on step 2 go — and the old
    page discarded them in silence."""
    client = serve_client(None)

    with mock.patch.object(
        server, "transcribe_words", return_value=words_for(libertad["lines"])
    ):
        _start(client, libertad, staging=str(libertad["staging"]))
        wait_for(client, "done")

    client.post("/api/reanchor", {"overrides": {"1": 4.5, "2": 9.0}})

    assert _restored(client)["handSetLines"] == 2
    assert "Running again starts the timing over" in client.get("/input")[1]


def test_page_1_is_empty_when_there_is_no_session(serve_client):
    """The from-nothing case is untouched: nothing is restored because
    nothing was answered."""
    page = serve_client(None).get("/input")[1]

    assert "var ANSWERS = null;" in page
