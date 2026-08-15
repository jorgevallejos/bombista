"""
`bombista serve` — the process and the JSON routes page 2 talks to (B20 §4, §6).

Synthetic `Word` lists throughout, no whisper model, no audio decoding
(CLAUDE.md, Development Protocol). The server is started for real on an
ephemeral loopback port and driven over HTTP, because the things under
test here — the bind address, the round trip's precision, the refusal to
write an input path — are only true of the running process.

The fixture is built so a **re-anchor and a delta shift give different
answers**. Line 2's opening words occur twice in the word stream; moving
line 1 past the first occurrence makes the forward-only scan pick up the
second. If the routes ever applied `original + delta` instead of
re-anchoring, every assertion below that names 20.00 would name 18.00.
"""
from __future__ import annotations

import ast
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import pytest

from bombista import anchoring, pipeline, server, writers
from bombista.aligner import save_words
from bombista.models import Word

# ---------------------------------------------------------------------------
# the fixture — see the module docstring
# ---------------------------------------------------------------------------

WORDS = [
    Word("uno", 10.00, 10.40),
    Word("dos", 10.50, 10.90),
    Word("tres", 11.00, 11.40),
    Word("cuatro", 12.00, 12.40),
    Word("cinco", 12.50, 12.90),
    Word("seis", 13.00, 13.40),
    Word("siete", 14.00, 14.40),
    Word("ocho", 14.50, 14.90),
    Word("nueve", 15.00, 15.40),
    # the second occurrence — the reason an override cannot be a delta
    Word("siete", 20.00, 20.40),
    Word("ocho", 20.50, 20.90),
    Word("nueve", 21.00, 21.40),
    Word("diez", 25.00, 25.40),
    Word("once", 25.50, 25.90),
    Word("doce", 26.00, 26.40),
]

LINES = ["uno dos tres", "cuatro cinco seis", "siete ocho nueve", "diez once doce"]

MACHINE_STARTS = [10.00, 12.00, 14.00, 25.00]
"""What `anchor_lines` gives with no overrides — asserted below rather than
assumed, so a change in the anchoring makes this file fail loudly instead
of quietly testing a different fixture."""

CORRECTED_LINE_1 = 16.00
"""Past line 2's first occurrence (nueve ends 15.40), before its second
(siete starts 20.00)."""

REANCHORED_LINE_2 = 20.00
DELTA_LINE_2 = 18.00  # 14.00 + (16.00 - 12.00) — the answer that must NOT appear

SONG = {
    "title": "Numeros",
    "artist": "Chango Pepper",
    "notes": "",
    "title_translations": {"es": "Numeros", "en": "Numbers"},
    "tempo": {"bpm": 66.67, "numerator": 6, "denominator": 8, "countInBars": 1},
    "intro": {"es": "hola", "en": "hello"},
    "lyrics": [
        {"es": "uno dos tres", "en": "one two three"},
        {"es": "cuatro cinco seis", "en": "four five six"},
        {"es": "siete ocho nueve", "en": "seven eight nine"},
        {"es": "diez once doce", "en": "ten eleven twelve"},
    ],
}


@pytest.fixture
def staging(tmp_path: Path) -> Path:
    """A staging directory as `align` leaves it, plus the song file beside
    it — the shape `serve` boots a session from."""
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    save_words(WORDS, staging_dir / "asr-words.jsonl")
    song_path = tmp_path / "numeros.json"
    song_path.write_text(json.dumps(SONG, ensure_ascii=False), encoding="utf-8")
    return staging_dir


@pytest.fixture
def session(staging: Path):
    return server.load_session(staging, staging.parent / "numeros.json", lang="es")


def test_the_fixture_anchors_where_this_file_assumes(session):
    anchors = anchoring.anchor_lines(WORDS, LINES)

    assert [a.start for a in anchors] == MACHINE_STARTS


# ---------------------------------------------------------------------------
# a live server on the loopback interface
# ---------------------------------------------------------------------------


class Client:
    def __init__(self, base: str) -> None:
        self.base = base

    def request(self, method: str, path: str, body: dict | None = None, *, html=False):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        decode = (lambda raw: raw) if html else json.loads
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, decode(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, decode(exc.read().decode("utf-8"))

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body):
        return self.request("POST", path, body)


@pytest.fixture
def client(session):
    httpd = server.create_server(session, port=0)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield Client(f"http://{host}:{port}")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# invariant 7 — loopback only
# ---------------------------------------------------------------------------


def test_the_server_binds_loopback(session):
    httpd = server.create_server(session, port=0)
    try:
        assert httpd.server_address[0] == "127.0.0.1"
    finally:
        httpd.server_close()


def test_no_bind_address_but_loopback_can_be_reached(session):
    """Invariant 7. A dev server on the LAN is the one way this design
    could accidentally become the hosted service §1 rules out, so the host
    is an argument that only ever accepts one value."""
    for host in ("0.0.0.0", "", "::", "192.168.1.10", "localhost"):
        with pytest.raises(ValueError) as exc:
            server.create_server(session, port=0, host=host)
        assert "127.0.0.1" in str(exc.value)


def test_the_only_bind_address_in_the_module_source_is_loopback():
    """The argument check above can be routed around by a future edit that
    binds somewhere else directly; this reads the module's own string
    literals so there is genuinely no other code path."""
    source = Path(server.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    addresses = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.replace(".", "").replace(":", "").isdigit()
        and ("." in node.value or ":" in node.value)
    }

    assert addresses <= {"127.0.0.1"}


# ---------------------------------------------------------------------------
# invariant 1 — serve imports no logic from cli.py
# ---------------------------------------------------------------------------


def test_server_imports_nothing_from_cli():
    tree = ast.parse(Path(server.__file__).read_text(encoding="utf-8"))

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert not any(name.endswith("cli") for name in imported), imported


# ---------------------------------------------------------------------------
# GET /api/session
# ---------------------------------------------------------------------------


def test_session_route_carries_the_lines_their_anchors_and_the_run(client):
    status, payload = client.get("/api/session")

    assert status == 200
    assert [line["text"] for line in payload["lines"]] == LINES
    assert [line["start"] for line in payload["lines"]] == MACHINE_STARTS
    assert [line["band"] for line in payload["lines"]] == [
        "HIGH",
        "HIGH",
        "REVIEW",
        "REVIEW",
    ]
    assert payload["lines"][2]["signals"] == ["ambiguous"]
    assert payload["lines"][2]["asrContext"]
    assert payload["lines"][2]["signalGlosses"]["ambiguous"]
    assert payload["leadIn"]["durationSec"] == 10.00
    assert payload["linesHash"].startswith("sha256:")
    assert payload["bands"] == {"HIGH": 2, "REVIEW": 2, "FAIL": 0}
    assert "provenance" in payload


def test_session_route_reports_the_runs_provenance_when_staging_recorded_it(
    staging: Path, tmp_path: Path
):
    source = {"audio": "songs/audio/numeros.m4a", "sha256": "ab" * 32, "lang": "es"}
    (staging / "numeros-report.json").write_text(
        json.dumps({"source": source, "linesHash": "sha256:x"}), encoding="utf-8"
    )
    session = server.load_session(staging, tmp_path / "numeros.json", lang="es")

    assert server.session_payload(session)["provenance"] == source


# ---------------------------------------------------------------------------
# POST /api/reanchor — it re-anchors, it never shifts
# ---------------------------------------------------------------------------


def test_reanchor_delegates_to_the_extracted_anchoring_and_pipeline(client):
    """§6's obligation, and the drift risk the whole item is shaped around:
    the routes must call the same functions the CLI calls, not a second
    implementation that can wander away from them."""
    assert server.anchor_lines is anchoring.anchor_lines
    assert server.parse_anchor_overrides is anchoring.parse_anchor_overrides
    assert server.build_timeline is pipeline.build_timeline
    assert server.normalize_to_lead_in is pipeline.normalize_to_lead_in

    with (
        mock.patch.object(
            server, "parse_anchor_overrides", wraps=anchoring.parse_anchor_overrides
        ) as parse,
        mock.patch.object(server, "anchor_lines", wraps=anchoring.anchor_lines) as anchor,
        mock.patch.object(server, "build_timeline", wraps=pipeline.build_timeline) as build,
    ):
        status, _ = client.post("/api/reanchor", {"overrides": {"1": CORRECTED_LINE_1}})

    assert status == 200
    assert parse.called, "the route parsed the override itself"
    assert anchor.called, "the route did not re-run the anchoring"
    assert build.called, "the route did not rebuild the timeline"
    assert anchor.call_args.kwargs["overrides"] == {1: CORRECTED_LINE_1}


def test_an_override_re_anchors_the_lines_below_it_rather_than_shifting_them(client):
    status, payload = client.post("/api/reanchor", {"overrides": {"1": CORRECTED_LINE_1}})
    starts = [line["start"] for line in payload["lines"]]

    assert status == 200
    # above the correction: untouched, by construction
    assert starts[0] == MACHINE_STARTS[0]
    # the corrected line: exactly what was asked for
    assert starts[1] == CORRECTED_LINE_1
    # below it: derived from the word stream, not from the delta
    assert starts[2] == REANCHORED_LINE_2
    assert starts[2] != DELTA_LINE_2
    assert starts[3] == MACHINE_STARTS[3], "a blanket delta reached line 3"


def test_a_re_anchor_reports_which_lines_were_hand_set_and_their_machine_values(client):
    _, payload = client.post("/api/reanchor", {"overrides": {"1": CORRECTED_LINE_1}})
    lines = payload["lines"]

    assert lines[1]["handSet"] is True
    assert lines[1]["machineStart"] == MACHINE_STARTS[1]
    assert lines[0]["handSet"] is False
    assert lines[2]["machineStart"] == MACHINE_STARTS[2], (
        "machineStart must stay the value the machine gave, not the re-anchored one"
    )


def test_the_machines_own_band_travels_with_every_line(client):
    """§8.5: a band that changed shows its BEFORE and its after, on the
    row. The "before" is what the machine said with no overrides at all —
    computed once at load, never re-derived from a run that already
    carries corrections, or the human's answer would quietly become the
    machine's."""
    _, before = client.get("/api/session")
    _, after = client.post("/api/reanchor", {"overrides": {"1": CORRECTED_LINE_1}})

    assert [line["machineBand"] for line in after["lines"]] == [
        line["band"] for line in before["lines"]
    ]
    assert after["lines"][2]["machineBand"] != after["lines"][2]["band"]


def test_a_re_anchor_re_bands_the_lines_below_it(client):
    """The most useful signal on the page (§3): an edit recomputes the
    bands under it, and a HIGH line may come back REVIEW."""
    _, before = client.get("/api/session")
    _, after = client.post("/api/reanchor", {"overrides": {"1": CORRECTED_LINE_1}})

    assert before["lines"][2]["band"] != after["lines"][2]["band"]


def test_reanchor_rejects_an_out_of_range_line(client):
    status, payload = client.post("/api/reanchor", {"overrides": {"9": 12.0}})

    assert status == 400
    assert "0..3" in payload["error"]


# ---------------------------------------------------------------------------
# line 0 is not special (§8.6, settled 2026-08-16)
#
# These tests read the opposite way round from the ones this file shipped
# with. §3 used to argue that a stepper on line 0 "silently breaks the v2
# contract"; it does not. The normaliser runs on emit no matter how the
# value got there — it banks line 0's onset into `leadIn.durationSec` and
# writes entry 0 as `0.00`. **Invariant 3 is enforced by the normaliser,
# not by refusing the edit**, and refusing it was defending the invariant
# at the wrong layer.
#
# Jorge, 2026-08-16: line timestamps change independently, line 0 included.
# The lead-in is a performance concept and belongs to Pregonero, at
# performance time. A timeline extractor that grows a lead-in control is
# answering a question that was not asked of it.
# ---------------------------------------------------------------------------

MOVED_LINE_0 = 10.40
"""Line 0, forward by 0.40 s — the synthetic twin of the mockup's
8.92 → 9.32 (§8.6). Far enough that every cue-relative value has to move
and no raw one may."""


def test_line_0_moves_like_any_other_line(client):
    status, payload = client.post("/api/reanchor", {"overrides": {"0": MOVED_LINE_0}})

    assert status == 200
    assert payload["lines"][0]["start"] == MOVED_LINE_0
    assert payload["lines"][0]["handSet"] is True
    assert payload["lines"][0]["machineStart"] == MACHINE_STARTS[0]


def test_moving_line_0_leaves_every_raw_onset_below_it_where_it_was(client):
    """§8.6, and it is the part that looks like two things at once: line
    0's own word is where it always was, so the forward scan reaches line
    1 exactly as before. Nothing below is re-derived differently."""
    _, before = client.get("/api/session")
    _, after = client.post("/api/reanchor", {"overrides": {"0": MOVED_LINE_0}})

    assert [line["start"] for line in after["lines"]][1:] == MACHINE_STARTS[1:]
    assert [line["band"] for line in after["lines"]] == [
        line["band"] for line in before["lines"]
    ]
    assert after["bands"] == before["bands"]


def test_moving_line_0_is_the_global_shift_and_entry_0_stays_zero(client, tmp_path):
    """The mockup's demonstration, reproduced: the raw onsets below do not
    move, `leadIn.durationSec` takes line 0's new value, entry 0 is still
    `0.00`, and every cue-relative value shifts by exactly the amount line
    0 moved. So moving line 0 *is* B6's global nudge, obtained for free
    from the same control as everything else — no second widget, no
    special case."""
    machine_out = tmp_path / "machine.sp.json"
    moved_out = tmp_path / "moved.sp.json"
    client.post("/api/emit", {"overrides": {}, "out": str(machine_out)})
    _, payload = client.post(
        "/api/emit", {"overrides": {"0": MOVED_LINE_0}, "out": str(moved_out)}
    )

    machine = json.loads(machine_out.read_text(encoding="utf-8"))
    moved = json.loads(moved_out.read_text(encoding="utf-8"))
    shift = MOVED_LINE_0 - MACHINE_STARTS[0]

    assert moved["leadIn"]["durationSec"] == MOVED_LINE_0
    assert moved["timeline"][0]["start"] == 0.00
    assert [
        round(new["start"] - old["start"], 2)
        for new, old in zip(moved["timeline"][1:], machine["timeline"][1:])
    ] == [round(-shift, 2)] * (len(machine["timeline"]) - 1)
    assert payload["handSet"] == [
        {
            "line": 0,
            "machineStart": MACHINE_STARTS[0],
            "start": MOVED_LINE_0,
            "setAt": payload["timelineSignedOff"],
        }
    ]


def test_a_hand_set_lead_in_says_so_in_the_contracts_own_word(client, tmp_path):
    """`leadIn.source` is `"measured"` when Bombista computed it and
    `"manual"` when a human overrode it — the timeline v2 contract's own
    two words, and the only two it accepts besides `"none"`. The mockup
    writes `"hand-set"`, which the contract does not carry; the fact it
    records is right and the spelling is not (docs/timeline-v2-contract.md).
    """
    machine_out = tmp_path / "machine.sp.json"
    moved_out = tmp_path / "moved.sp.json"

    client.post("/api/emit", {"overrides": {}, "out": str(machine_out)})
    client.post("/api/emit", {"overrides": {"0": MOVED_LINE_0}, "out": str(moved_out)})

    assert json.loads(machine_out.read_text())["leadIn"]["source"] == "measured"
    assert json.loads(moved_out.read_text())["leadIn"]["source"] == "manual"


def test_moving_a_line_that_is_not_line_0_leaves_the_lead_in_measured(client, tmp_path):
    """Only line 0 sets the lead-in. A correction anywhere else is not a
    claim about where the song starts."""
    out = tmp_path / "out.sp.json"
    client.post("/api/emit", {"overrides": {"1": CORRECTED_LINE_1}, "out": str(out)})

    assert json.loads(out.read_text())["leadIn"]["source"] == "measured"


def test_the_lead_offset_lands_in_lead_in_and_entry_0_is_zero(client, tmp_path):
    out = tmp_path / "out.sp.json"

    _, payload = client.post(
        "/api/emit", {"overrides": {"1": CORRECTED_LINE_1}, "out": str(out)}
    )
    emitted = json.loads(out.read_text(encoding="utf-8"))

    assert emitted["timeline"][0]["start"] == 0.00
    assert emitted["leadIn"]["durationSec"] == MACHINE_STARTS[0]
    # every emitted time is the raw one minus the lead-in, nothing else
    assert emitted["timeline"][1]["start"] == round(CORRECTED_LINE_1 - MACHINE_STARTS[0], 2)
    assert emitted["timeline"][2]["start"] == round(REANCHORED_LINE_2 - MACHINE_STARTS[0], 2)
    assert payload["leadIn"]["durationSec"] == MACHINE_STARTS[0]


# ---------------------------------------------------------------------------
# invariant 2 — nothing rounds coarser than 0.07 s
# ---------------------------------------------------------------------------


def test_no_route_rounds_coarser_than_the_correction_loop(client, tmp_path):
    """The differentiator is a 0.07 s correction loop. Two values 0.05 s
    apart must stay two values, in and out, on every route."""
    near = 16.30
    nearer = 16.35

    _, first = client.post("/api/reanchor", {"overrides": {"1": near}})
    _, second = client.post("/api/reanchor", {"overrides": {"1": nearer}})

    assert first["lines"][1]["start"] == near
    assert second["lines"][1]["start"] == nearer

    out = tmp_path / "out.sp.json"
    client.post("/api/emit", {"overrides": {"1": nearer}, "out": str(out)})
    emitted = json.loads(out.read_text(encoding="utf-8"))

    assert emitted["timeline"][1]["start"] == round(nearer - MACHINE_STARTS[0], 2)
    assert emitted["timeline"][1]["start"] != round(near - MACHINE_STARTS[0], 2)


# ---------------------------------------------------------------------------
# POST /api/emit
# ---------------------------------------------------------------------------


def test_emit_writes_through_the_one_merge_path(client, tmp_path):
    out = tmp_path / "out.sp.json"

    with mock.patch.object(
        server, "merge_envelope", wraps=writers.merge_envelope
    ) as merge:
        status, _ = client.post("/api/emit", {"out": str(out)})

    assert status == 200
    assert merge.called, "the emit route merged the envelope itself"
    assert server.merge_envelope is writers.merge_envelope


def test_the_emitted_file_carries_lines_hash_and_the_sign_off(client, tmp_path):
    out = tmp_path / "out.sp.json"

    _, payload = client.post("/api/emit", {"overrides": {"1": CORRECTED_LINE_1}, "out": str(out)})
    emitted = json.loads(out.read_text(encoding="utf-8"))

    assert emitted["linesHash"] == payload["linesHash"]
    assert emitted["linesHash"].startswith("sha256:")
    assert emitted["timelineSignedOff"] == payload["timelineSignedOff"]
    # §10.2: linesHash sits between what it guards and what it protects
    keys = list(emitted)
    assert keys.index("lyrics") < keys.index("linesHash") < keys.index("timelineVersion")
    assert keys.index("linesHash") + 1 == keys.index("timelineSignedOff")


def test_the_emit_response_records_which_lines_were_hand_set_and_when(client, tmp_path):
    """§6 wants the hand-set record — which lines, their machine values,
    when they were set. §10.2 keeps it OUT of the song file: bands,
    signals and the per-line hand-set record all belong to the report, and
    the file keeps one scalar, `timelineSignedOff`. So the record travels
    on the response, for the report to render."""
    out = tmp_path / "out.sp.json"

    _, payload = client.post("/api/emit", {"overrides": {"1": CORRECTED_LINE_1}, "out": str(out)})

    assert payload["handSet"] == [
        {
            "line": 1,
            "machineStart": MACHINE_STARTS[1],
            "start": CORRECTED_LINE_1,
            "setAt": payload["timelineSignedOff"],
        }
    ]


def test_the_emitted_file_carries_no_qa_block(client, tmp_path):
    """§10.2, verbatim: no invented `format` key, no `review` block, no
    `provenance` block in the song file. QA output belongs in the report."""
    out = tmp_path / "out.sp.json"

    client.post("/api/emit", {"out": str(out)})
    emitted = json.loads(out.read_text(encoding="utf-8"))

    for key in ("format", "review", "provenance", "_bombista", "handSet", "bands"):
        assert key not in emitted


def test_the_emitted_file_passes_every_other_key_through_untouched(client, tmp_path):
    """`lyrics` entries are objects keyed by language — flattening them
    would destroy every translation on the round trip (§10.2)."""
    out = tmp_path / "out.sp.json"

    client.post("/api/emit", {"out": str(out)})
    emitted = json.loads(out.read_text(encoding="utf-8"))

    for key in ("title", "artist", "notes", "title_translations", "tempo", "intro", "lyrics"):
        assert emitted[key] == SONG[key]


def test_emit_refuses_to_write_to_the_lyrics_file_it_read(client, staging, tmp_path):
    """Invariant 6. Always a new file — it removes the
    file-changed-on-disk race and keeps the merge a pure function."""
    song_path = tmp_path / "numeros.json"
    before = song_path.read_text(encoding="utf-8")

    status, payload = client.post("/api/emit", {"out": str(song_path)})

    assert status == 400
    assert "input" in payload["error"]
    assert song_path.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("name", ["asr-words.jsonl", "numeros-report.json"])
def test_emit_refuses_to_write_to_a_staging_input(client, staging, name):
    target = staging / name
    target.write_text("{}", encoding="utf-8")

    status, payload = client.post("/api/emit", {"out": str(target)})

    assert status == 400
    assert "input" in payload["error"]
    assert target.read_text(encoding="utf-8") == "{}"


def test_emitting_twice_to_the_same_path_is_not_an_input_collision(client, tmp_path):
    """The refusal is about the run's inputs, not about anything that
    happens to be on disk — a correction loop re-emits over its own
    previous output constantly."""
    out = tmp_path / "out.sp.json"

    first, _ = client.post("/api/emit", {"out": str(out)})
    second, payload = client.post(
        "/api/emit", {"overrides": {"1": CORRECTED_LINE_1}, "out": str(out)}
    )

    assert (first, second) == (200, 200)
    assert json.loads(out.read_text(encoding="utf-8"))["timeline"][2]["start"] == round(
        REANCHORED_LINE_2 - MACHINE_STARTS[0], 2
    )


def test_emit_refuses_an_input_path_reached_by_another_route(client, staging, tmp_path):
    """`..` and a symlink both reach the same file under a different
    spelling; the refusal compares resolved paths, not strings."""
    sneaky = staging / ".." / "numeros.json"

    status, payload = client.post("/api/emit", {"out": str(sneaky)})

    assert status == 400
    assert "input" in payload["error"]


# ---------------------------------------------------------------------------
# the routes page 2 turned out to need
# ---------------------------------------------------------------------------


def test_the_entry_point_is_the_review_when_a_session_was_booted(client):
    """`serve <staging> <lyrics>` drops the user at step 2. This asserted a
    404 until page 2 landed: `/review` was deliberately a hole rather than
    a stub that could be mistaken for the page."""
    status, body = client.get("/review", html=True)

    assert status == 200
    assert body.startswith("<!doctype html>")


def test_load_session_says_what_is_missing(tmp_path):
    empty = tmp_path / "staging"
    empty.mkdir()
    song = tmp_path / "numeros.json"
    song.write_text(json.dumps(SONG), encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        server.load_session(empty, song, lang="es")

    assert "asr-words.jsonl" in str(exc.value)


def test_serve_is_wired_into_the_cli():
    """Wiring only, matching how align/promote/migrate are wired: options,
    help text, and translating ValueError into a ClickException."""
    from bombista import cli

    command = cli.main.commands["serve"]
    params = {p.name for p in command.params}

    assert {"staging_dir", "lyrics", "lang", "port"} <= params
    assert cli.load_session is server.load_session
    assert cli.create_server is server.create_server


def test_the_cli_falls_back_to_an_emitted_songjson_when_no_lyrics_are_given(staging):
    """`align --emit songjson` leaves a song file in staging; that is the
    one case the lyrics argument can be omitted."""
    from click.testing import CliRunner

    from bombista.cli import main

    (staging / "numeros-song.json").write_text(
        json.dumps(SONG, ensure_ascii=False), encoding="utf-8"
    )

    with mock.patch("bombista.cli.create_server") as create:
        create.return_value.server_address = ("127.0.0.1", 51234)
        result = CliRunner().invoke(main, ["serve", str(staging)])

    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:51234/" in result.output
    assert create.call_args.args[0].lyrics_path.name == "numeros-song.json"


def test_the_cli_says_so_when_it_has_no_lyrics_to_fall_back_on(staging):
    from click.testing import CliRunner

    from bombista.cli import main

    result = CliRunner().invoke(main, ["serve", str(staging)])

    assert result.exit_code != 0
    assert "no lyrics argument" in result.output


def test_the_cli_renders_a_session_failure_as_a_click_error(tmp_path):
    from click.testing import CliRunner

    from bombista.cli import main

    empty = tmp_path / "staging"
    empty.mkdir()
    song = tmp_path / "numeros.json"
    song.write_text(json.dumps(SONG), encoding="utf-8")

    result = CliRunner().invoke(main, ["serve", str(empty), str(song)])

    assert result.exit_code != 0
    assert "asr-words.jsonl" in result.output
    assert "Traceback" not in result.output
