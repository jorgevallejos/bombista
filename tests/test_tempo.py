"""Tempo, typed in on the review page (round A, item 3).

**This reverses §11.5's removal of the control, and the reversal is
narrow.** The control came off page 1 on 2026-08-16 because a whole block
needs four fields on a page whose rule is four rows total, and because
Bombista had no business owning a tempo at all. The second half of that
has changed: Pregonero loses tempo ownership later in this integration, so
Bombista becomes the only remaining home for typing one in. The review
page is the right surface, because it is where the timeline is visible
while it is being changed.

**What §11.5 exists for does not change, and is pinned below:**

- `tempo` is written **whole** — `bpm`, `numerator`, `denominator`,
  `countInBars` — or not at all. `beatScheduler.ts` declares `numerator`
  and `denominator` as required and `getBeatsPerBar` does `numerator % 3`,
  so a bpm-only block gives NaN beats and a broken pulse, while
  `performedTempo.ts` degrades perfectly. Correct scaling, broken pulse,
  no error anywhere.
- Bombista still **never derives, measures or guesses** one. The performer
  types it in, from the source that produced the audio, where it is exact.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from bombista import pages, server

WHOLE = {"bpm": 128, "numerator": 4, "denominator": 4, "countInBars": 2}
FIXTURE_TEMPO = {"bpm": 66.67, "numerator": 6, "denominator": 8, "countInBars": 1}


@pytest.fixture
def client(serve_client, synthetic_session):
    return serve_client(synthetic_session)


def untimed(tmp_path, staging, **overrides):
    """The synthetic song with its tempo block removed — the state ten of
    thirteen catalogue songs were in when this round was written."""
    song = json.loads((tmp_path / "synthetic.json").read_text(encoding="utf-8"))
    song.pop("tempo", None)
    song.update(overrides)
    path = tmp_path / "untimed.json"
    path.write_text(json.dumps(song, ensure_ascii=False, indent=2), encoding="utf-8")
    return server.load_session(staging, path, lang="es")


# ---------------------------------------------------------------------------
# the route
# ---------------------------------------------------------------------------


def test_the_session_reports_the_songs_own_tempo(client):
    status, payload, _ = client.get("/api/session")

    assert status == 200
    assert payload["tempo"] == FIXTURE_TEMPO


def test_a_song_with_no_tempo_reports_none(serve_client, synthetic, tmp_path):
    client = serve_client(untimed(tmp_path, synthetic["staging"]))

    _, payload, _ = client.get("/api/session")

    assert payload["tempo"] is None


def test_a_whole_block_is_accepted_and_comes_back(client):
    status, payload, _ = client.post("/api/tempo", {"tempo": WHOLE})

    assert status == 200
    assert payload["tempo"] == WHOLE
    assert client.get("/api/session")[1]["tempo"] == WHOLE


def test_a_bpm_only_block_is_refused_naming_every_missing_key(client):
    status, payload, _ = client.post("/api/tempo", {"tempo": {"bpm": 128}})

    assert status == 400
    for key in ("numerator", "denominator", "countInBars"):
        assert key in payload["error"]


def test_a_refused_block_leaves_the_session_alone(client):
    client.post("/api/tempo", {"tempo": {"bpm": 128}})

    assert client.get("/api/session")[1]["tempo"] == FIXTURE_TEMPO


@pytest.mark.parametrize(
    "block",
    [
        {"bpm": 0, "numerator": 4, "denominator": 4, "countInBars": 1},
        {"bpm": 128, "numerator": -4, "denominator": 4, "countInBars": 1},
        {"bpm": 128, "numerator": 4, "denominator": 4, "countInBars": -1},
        {"bpm": "fast", "numerator": 4, "denominator": 4, "countInBars": 1},
        {"bpm": 128, "numerator": 4, "denominator": 4, "countInBars": 1, "swing": 0.6},
        "128 bpm",
    ],
)
def test_a_block_that_is_not_whole_and_real_is_refused(client, block):
    status, _, _ = client.post("/api/tempo", {"tempo": block})

    assert status == 400


def test_count_in_bars_may_be_zero(client):
    status, payload, _ = client.post("/api/tempo", {"tempo": {**WHOLE, "countInBars": 0}})

    assert status == 200
    assert payload["tempo"]["countInBars"] == 0


def test_null_clears_the_block(client):
    status, payload, _ = client.post("/api/tempo", {"tempo": None})

    assert status == 200
    assert payload["tempo"] is None


# ---------------------------------------------------------------------------
# what lands in the file
# ---------------------------------------------------------------------------


def test_a_typed_tempo_lands_whole_in_the_emitted_file(
    serve_client, synthetic, tmp_path
):
    session = untimed(tmp_path, synthetic["staging"])
    client = serve_client(session)
    client.post("/api/tempo", {"tempo": WHOLE})

    out = tmp_path / "out.json"
    client.post("/api/emit", {"out": str(out)})

    assert json.loads(out.read_text(encoding="utf-8"))["tempo"] == WHOLE


def test_a_tempo_key_added_to_a_song_that_had_none_sits_in_catalogue_order(
    serve_client, synthetic, tmp_path
):
    """§10.2 fixes the key order against `songs/pimiento.json`:
    `title_translations` then `tempo` then `intro`. A key appended at the
    end would be valid and would still make every file Bombista touches
    look unlike every file it does not."""
    session = untimed(tmp_path, synthetic["staging"])
    client = serve_client(session)
    client.post("/api/tempo", {"tempo": WHOLE})

    out = tmp_path / "out.json"
    client.post("/api/emit", {"out": str(out)})
    keys = list(json.loads(out.read_text(encoding="utf-8")))

    assert keys.index("title_translations") < keys.index("tempo") < keys.index("intro")


def test_an_edited_tempo_keeps_the_position_the_song_already_gave_it(
    client, synthetic, tmp_path
):
    before = list(json.loads((tmp_path / "synthetic.json").read_text(encoding="utf-8")))
    client.post("/api/tempo", {"tempo": WHOLE})

    out = tmp_path / "out.json"
    client.post("/api/emit", {"out": str(out)})
    emitted = json.loads(out.read_text(encoding="utf-8"))

    assert emitted["tempo"] == WHOLE
    assert [k for k in emitted if k in before] == before


def test_a_cleared_tempo_leaves_no_key_behind(client, tmp_path):
    """Absent is the honest state, and Pregonero is already built for it:
    no pulse, no count-in, scale pinned to 1. A null is not neutral once a
    consumer reads it (`songs@c5adf65`)."""
    client.post("/api/tempo", {"tempo": None})

    out = tmp_path / "out.json"
    client.post("/api/emit", {"out": str(out)})

    assert "tempo" not in json.loads(out.read_text(encoding="utf-8"))


def test_an_untouched_tempo_is_passed_through_byte_for_byte(client, tmp_path):
    out = tmp_path / "out.json"
    client.post("/api/emit", {"out": str(out)})

    assert json.loads(out.read_text(encoding="utf-8"))["tempo"] == FIXTURE_TEMPO


# ---------------------------------------------------------------------------
# still never derived
# ---------------------------------------------------------------------------


def test_no_module_that_touches_audio_or_lyrics_mentions_a_tempo():
    """Rules 4 and 5, unchanged by this round. Bombista answers *when* a
    line happens, not in which beat — nothing on the path from audio or
    lyric text to a timeline may so much as name a bpm. B14 was dropped
    for this and nothing here reopens it."""
    package = Path(server.__file__).parent

    for module in ("aligner", "anchoring", "pipeline", "provenance", "serializer", "report"):
        source = (package / f"{module}.py").read_text(encoding="utf-8")
        assert "bpm" not in source, f"{module}.py names a bpm"


def test_the_only_tempo_gate_in_the_server_is_the_shared_one():
    """§11.5's guard, kept but re-aimed. It used to assert that `server.py`
    named no tempo at all, which stopped a bpm-only block coming back
    through the door. Now that a tempo can be typed in, the thing to stop
    is a *second* opinion about what a valid one is: `server.py` must reach
    for `validation.validate_tempo` and must not test bpm, numerator,
    denominator or countInBars itself.
    """
    tree = ast.parse(Path(server.__file__).read_text(encoding="utf-8"))

    prose = {
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    named = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in prose:
                named.add(node.value)
        elif isinstance(node, ast.Name):
            named.add(node.id)
        elif isinstance(node, ast.Attribute):
            named.add(node.attr)
        elif isinstance(node, ast.arg):
            named.add(node.arg)

    for field in ("bpm", "numerator", "denominator", "countInBars"):
        assert field not in named, f"server.py judges {field} itself"
    assert "validate_tempo" in named, "server.py does not use the shared gate"


# ---------------------------------------------------------------------------
# the page
# ---------------------------------------------------------------------------


@pytest.fixture
def page2(synthetic_session):
    return pages.render_review(server.session_payload(synthetic_session))


def test_the_review_page_asks_for_all_four_values(page2):
    """A control that cannot ask for a whole block should not ask for part
    of one — the sentence §11.5 was written around. Four fields is what
    makes the reversal safe."""
    for field in ("t-bpm", "t-numerator", "t-denominator", "t-countinbars"):
        assert f'id="{field}"' in page2, f"the control has no {field} input"


def test_the_review_page_says_the_value_is_typed_not_measured(page2):
    from tests.test_pages import visible_text

    text = visible_text(page2)

    assert "never measures" in text
    assert "all four" in text.lower()


def test_the_review_page_shows_the_songs_current_tempo(page2):
    assert 'value="66.67"' in page2


def test_page_1_still_has_no_tempo_control():
    """The reversal is narrow: the review page gained a control, page 1 did
    not get its old one back. §11.5's other reason stands — a whole block
    needs four fields on a page whose rule is four rows total."""
    page1 = pages.render_input()

    assert 'id="tempo"' not in page1
    assert not __import__("re").search(r"<input[^>]*tempo", page1, __import__("re").I)
