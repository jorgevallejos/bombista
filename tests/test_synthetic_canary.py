"""
The acceptance case, in two tiers (§6, §8.8, §11.3 — settled 2026-08-16).

**Tier 1, this file's main body: a synthetic fixture, committed, in CI.**
Nineteen invented lines on the canary's timing skeleton, with one line
whose first word the machine mishears by exactly one word. It proves the
*mechanism* — a correction re-anchors rather than ripples, the bands below
recompute, line 0 is the global shift — which is what a regression test is
for. It publishes nothing.

**Tier 2, at the bottom: the pimiento canary, opt-in.** §7 gates `v1.0.0`
on line 3 of pimiento being *fixable through `serve`* — a thing Jorge does
once, by hand, on the real song. Pointed at the private vault by two
environment variables and skipped with a clear message when they are
absent. `songs/pimiento.json` lives in a private vault and Bombista ships
as `pipx install bombista`; vendoring the fixture would publish the
lyrics, irreversibly, to buy a CI test this file already has.

Everything here drives the ROUTES rather than the DOM: the acceptance case
is that a correction reaches a correct output file, and the page is the
hand on the control, not the arithmetic.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bombista import server
from .conftest import (  # noqa: F401 — re-exported for tests/test_page2.py
    FLAGGED_LINE,
    LATE_ONSET,
    LEAD_IN,
    LINE_COUNT,
    MACHINE_START,
    MOVED_LEAD_IN,
    TRUE_ONSET,
)


@pytest.fixture
def client(serve_client, synthetic_session):
    return serve_client(synthetic_session)


def starts(payload: dict) -> list[float]:
    return [line["start"] for line in payload["lines"]]


def bands(payload: dict) -> list[str]:
    return [line["band"] for line in payload["lines"]]


# ---------------------------------------------------------------------------
# tier 1 — the synthetic fixture, and what it is built to prove
# ---------------------------------------------------------------------------


def test_the_fixture_reproduces_the_canarys_shape(client):
    """Asserted rather than assumed, so a change in the anchoring fails
    this file loudly instead of quietly testing something else."""
    _, payload, _ = client.get("/api/session")

    assert len(payload["lines"]) == LINE_COUNT
    assert payload["bands"] == {"HIGH": 18, "REVIEW": 1, "FAIL": 0}
    assert payload["leadIn"]["durationSec"] == LEAD_IN

    flagged = payload["lines"][FLAGGED_LINE]
    assert flagged["band"] == "REVIEW"
    assert flagged["signals"] == ["lead-fallback"]
    assert flagged["start"] == MACHINE_START


def test_the_flagged_line_carries_its_own_words(client):
    """§6's UI requirement, at the route that feeds it: the identity of a
    line must be readable without knowing whether LINE is 0- or 1-indexed."""
    _, payload, _ = client.get("/api/session")

    assert payload["lines"][FLAGGED_LINE]["text"]
    assert payload["lines"][FLAGGED_LINE]["signalGlosses"]["lead-fallback"]


def test_correcting_the_flagged_line_leaves_every_line_below_it_alone(client):
    """§8.8's quiet case, and the proof that a correction re-anchors
    instead of shifting: a delta would have moved all fifteen below by
    1.22 s. They do not move at all, because the forward scan re-derives
    them against the word stream and finds them exactly where they were."""
    _, before, _ = client.get("/api/session")
    _, after, _ = client.post("/api/reanchor", {"overrides": {str(FLAGGED_LINE): TRUE_ONSET}})

    assert after["bands"] == {"HIGH": LINE_COUNT, "REVIEW": 0, "FAIL": 0}
    assert after["lines"][FLAGGED_LINE]["start"] == TRUE_ONSET
    assert starts(after)[FLAGGED_LINE + 1:] == starts(before)[FLAGGED_LINE + 1:]
    assert bands(after)[:FLAGGED_LINE] == bands(before)[:FLAGGED_LINE]


def test_a_typed_correction_re_anchors_exactly_as_a_nudged_one_does(client):
    """§12.1: *type to arrive, nudge to land.* The two controls set one
    number and there is one re-anchor mechanism under them (§8.5), so a
    value that arrived by typing and a value that arrived by stepping are
    the same request and cannot produce different timelines.

    On the canary's numbers — pimiento's line 3, machine 37.54, true
    onset 36.32 — 24 presses of − 0.05 land on 36.34 and typing lands on
    36.32. Both sit inside §8.8's quiet range, where any correction
    leaves all fifteen lines below identical, so the two agree about
    every line but the one that was corrected."""
    nudged_to = round(MACHINE_START - 24 * 0.05, 2)

    _, typed, _ = client.post("/api/reanchor", {"overrides": {str(FLAGGED_LINE): TRUE_ONSET}})
    _, nudged, _ = client.post("/api/reanchor", {"overrides": {str(FLAGGED_LINE): nudged_to}})

    assert typed["lines"][FLAGGED_LINE]["start"] == TRUE_ONSET
    assert nudged["lines"][FLAGGED_LINE]["start"] == nudged_to
    assert typed["bands"] == nudged["bands"] == {"HIGH": LINE_COUNT, "REVIEW": 0, "FAIL": 0}
    assert starts(typed)[FLAGGED_LINE + 1:] == starts(nudged)[FLAGGED_LINE + 1:]
    assert bands(typed) == bands(nudged)


def test_a_correction_the_stepper_could_barely_reach_is_one_request(client):
    """The failure §12.1 is answering: a phrase the ASR did not recognise
    leaves the line with nothing to anchor to, so the error is unbounded
    by construction — 47 s in Luz y Sal, about 940 presses and 42 seconds
    of continuous hold. Line 14 has 16 s of room between its neighbours;
    crossing 15.08 s of it is 302 presses by stepper and one number
    typed. The route takes it whole either way."""
    far = 130.00

    _, payload, _ = client.post("/api/reanchor", {"overrides": {"14": far}})

    assert round(far - 114.92, 2) == 15.08, "the fixture's own distance"
    assert payload["lines"][14]["start"] == far


def test_a_correction_too_late_flips_the_next_line_to_review(client):
    """The other half of §8.8, and the most useful signal on the page: an
    edit recomputes the bands below it, and a HIGH line may come back
    REVIEW. A real threshold inside the allowed range."""
    _, after, _ = client.post("/api/reanchor", {"overrides": {str(FLAGGED_LINE): LATE_ONSET}})
    below = after["lines"][FLAGGED_LINE + 1]

    assert below["band"] == "REVIEW"
    assert "gap-outlier" in below["signals"]
    assert below["signalGlosses"]["gap-outlier"]


def test_moving_line_0_is_the_global_shift(client, tmp_path):
    """§8.6's demonstration, reproduced from the mockup: moving line 0 by
    0.40 s leaves line 1's RAW onset where it was, banks the new value in
    `leadIn`, keeps entry 0 at `0.00`, and shifts every cue-relative value
    by exactly −0.40. One control, no special case, and B6's global nudge
    obtained for free."""
    machine_out = tmp_path / "machine.json"
    moved_out = tmp_path / "moved.json"

    _, before, _ = client.get("/api/session")
    _, after, _ = client.post("/api/reanchor", {"overrides": {"0": MOVED_LEAD_IN}})
    client.post("/api/emit", {"overrides": {}, "out": str(machine_out)})
    client.post("/api/emit", {"overrides": {"0": MOVED_LEAD_IN}, "out": str(moved_out)})

    machine = json.loads(machine_out.read_text(encoding="utf-8"))
    moved = json.loads(moved_out.read_text(encoding="utf-8"))
    shift = round(MOVED_LEAD_IN - LEAD_IN, 2)

    assert starts(after)[1:] == starts(before)[1:]
    assert after["bands"] == before["bands"]
    assert moved["leadIn"] == {
        "durationSec": MOVED_LEAD_IN,
        "source": "manual",
        "confidence": "low",
        "apply": False,
    }
    assert machine["leadIn"]["source"] == "measured"
    assert moved["timeline"][0]["start"] == 0.00
    assert [
        round(new["start"] - old["start"], 2)
        for new, old in zip(moved["timeline"][1:], machine["timeline"][1:])
    ] == [-shift] * (LINE_COUNT - 1)


def test_the_corrected_run_reaches_a_correct_output_file(client, tmp_path):
    """§6's acceptance case, end to end and through the routes: the
    flagged line is resolved and the file that comes out is the file
    Tramoya reads — every key Bombista does not own passed through
    untouched, all languages included, entry 0 at 0.00 and the offset in
    `leadIn`."""
    out = tmp_path / "out.json"

    client.post("/api/reanchor", {"overrides": {str(FLAGGED_LINE): TRUE_ONSET}})
    status, payload, _ = client.post("/api/emit", {"out": str(out)})
    emitted = json.loads(out.read_text(encoding="utf-8"))

    assert status == 200
    assert emitted["timeline"][0]["start"] == 0.00
    assert emitted["leadIn"]["durationSec"] == LEAD_IN
    assert emitted["timeline"][FLAGGED_LINE]["start"] == round(TRUE_ONSET - LEAD_IN, 2)
    assert emitted["linesHash"] and emitted["timelineSignedOff"]
    assert isinstance(emitted["lyrics"][0], dict) and set(emitted["lyrics"][0]) == {"es", "en"}
    assert emitted["tempo"] == {"bpm": 66.67, "numerator": 6, "denominator": 8, "countInBars": 1}
    assert payload["handSet"][0]["line"] == FLAGGED_LINE
    assert payload["handSet"][0]["machineStart"] == MACHINE_START


def test_no_route_rounds_the_correction_coarser_than_the_loop(client):
    """Invariant 2, on this fixture's own numbers: two values 0.05 s apart
    stay two values through the JSON round trip."""
    _, first, _ = client.post("/api/reanchor", {"overrides": {str(FLAGGED_LINE): 36.30}})
    _, second, _ = client.post("/api/reanchor", {"overrides": {str(FLAGGED_LINE): 36.35}})

    assert first["lines"][FLAGGED_LINE]["start"] == 36.30
    assert second["lines"][FLAGGED_LINE]["start"] == 36.35


# ---------------------------------------------------------------------------
# tier 2 — the pimiento canary, opt-in (§7's gate, §11.3's second tier)
# ---------------------------------------------------------------------------

CANARY_SONG = "BOMBISTA_CANARY_SONG"
CANARY_STAGING = "BOMBISTA_CANARY_STAGING"

_SKIP = (
    f"the pimiento canary is opt-in: set {CANARY_SONG} to the song JSON in "
    f"the private vault (e.g. ~/Chango Pepper/songs/pimiento.json) and "
    f"{CANARY_STAGING} to an `align` staging directory for it (e.g. "
    "staging/pimiento). Neither the song nor its ASR stream is committed — "
    "this repository ships as `pipx install bombista` and vendoring the "
    "fixture would publish the lyrics (§11.3)."
)


def _canary_paths() -> tuple[Path, Path]:
    song = os.environ.get(CANARY_SONG)
    staging = os.environ.get(CANARY_STAGING)
    if not song or not staging:
        pytest.skip(_SKIP)
    song_path, staging_path = Path(song), Path(staging)
    if not song_path.is_file() or not (staging_path / "asr-words.jsonl").is_file():
        pytest.skip(_SKIP)
    return staging_path, song_path


@pytest.fixture
def canary(serve_client):
    staging, song = _canary_paths()
    return serve_client(server.load_session(staging, song, lang="es"))


@pytest.mark.canary
def test_canary_line_3_is_resolvable_through_serve(canary):
    """§7's gate for `v1.0.0`, as an assertion rather than a hope. Every
    number here is §6's and §8.8's, measured against the real
    `asr-words.jsonl` — 19 lines, 18 HIGH / 1 REVIEW / 0 FAIL, lead-in
    8.92, line 3 REVIEW `lead-fallback` at 37.54, true onset 36.32."""
    _, before, _ = canary.get("/api/session")

    assert len(before["lines"]) == 19
    assert before["bands"] == {"HIGH": 18, "REVIEW": 1, "FAIL": 0}
    assert before["leadIn"]["durationSec"] == 8.92
    assert before["lines"][3]["band"] == "REVIEW"
    assert before["lines"][3]["signals"] == ["lead-fallback"]
    assert before["lines"][3]["start"] == 37.54

    _, after, _ = canary.post("/api/reanchor", {"overrides": {"3": 36.32}})

    assert after["bands"] == {"HIGH": 19, "REVIEW": 0, "FAIL": 0}
    assert starts(after)[4:] == starts(before)[4:]


@pytest.mark.canary
def test_canary_line_4_goes_gap_outlier_when_line_3_is_set_too_late(canary):
    _, after, _ = canary.post("/api/reanchor", {"overrides": {"3": 40.00}})

    assert after["lines"][4]["band"] == "REVIEW"
    assert "gap-outlier" in after["lines"][4]["signals"]


@pytest.mark.canary
def test_canary_moving_line_0_shifts_the_song_and_nothing_else(canary, tmp_path):
    """The mockup's own numbers on the real song: 8.92 → 9.32 leaves line
    1's raw onset at 18.44, and every cue-relative value moves by −0.40."""
    _, before, _ = canary.get("/api/session")
    _, after, _ = canary.post("/api/reanchor", {"overrides": {"0": 9.32}})

    assert before["lines"][1]["start"] == 18.44
    assert after["lines"][1]["start"] == 18.44
    assert after["bands"] == before["bands"]

    machine_out, moved_out = tmp_path / "a.json", tmp_path / "b.json"
    canary.post("/api/emit", {"overrides": {}, "out": str(machine_out)})
    canary.post("/api/emit", {"overrides": {"0": 9.32}, "out": str(moved_out)})
    machine = json.loads(machine_out.read_text(encoding="utf-8"))
    moved = json.loads(moved_out.read_text(encoding="utf-8"))

    assert moved["leadIn"]["durationSec"] == 9.32
    assert moved["leadIn"]["source"] == "manual"
    assert moved["timeline"][0]["start"] == 0.00
    assert [
        round(new["start"] - old["start"], 2)
        for new, old in zip(moved["timeline"][1:], machine["timeline"][1:])
    ] == [-0.40] * 18
