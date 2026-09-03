"""The deal — step 0 of the song flow (Jorge, 2026-09-03).

**Words earn their place only where effort precedes reward.** This is one
of the three moments on the walk where they do: the person is about to
hand over a lyrics file, a recording, a tapped tempo and a listen-through,
and the payoff — lines that follow the music with nobody at the laptop —
does not arrive until a projection runs days later.

So the assertions here are about the DEAL as a deal: three blocks and no
fourth, one control and no second, the copy word for word, and the one
rule that decides whether it is shown at all — *this machine has produced
no song yet*, answered by each caller from what it already knows.
"""
from __future__ import annotations

import re

import pytest

from bombista import pages, server

from .test_pages import flow_text, visible_text


# ---------------------------------------------------------------------------
# the copy — every clause was argued, so drift is a failure
# ---------------------------------------------------------------------------

WHAT_YOU_GET = (
    "Your lyrics on the wall, in time with you. Add a recording and they follow the "
    "music on their own, so you never touch the laptop. Without one, you move them "
    "yourself."
)

WHAT_IT_COSTS = (
    "One sitting: your lyrics and a take, a tapped tempo, a minute while it works out "
    "where each line falls, and one listen through to fix the ones that landed wrong."
)

WHAT_IT_DOES_NOT_DO = (
    "Your recordings and your lyrics files are never changed. It does not ask you for "
    "translations, but the file it makes has a place for them, so the wall can carry "
    "the room's language too. You fill those in elsewhere, in an LLM session or by hand."
)

BLOCKS = (
    ("What you get", WHAT_YOU_GET),
    ("What it costs", WHAT_IT_COSTS),
    ("What it does not do", WHAT_IT_DOES_NOT_DO),
)


@pytest.fixture
def deal():
    return pages.render_deal()


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@pytest.mark.parametrize("label,body", BLOCKS)
def test_the_three_blocks_say_exactly_what_was_agreed(label, body, deal):
    """**Verbatim, and that is the point.** *One sitting* names the whole
    cost in three words; *elsewhere* is not *outside the suite*, because
    the suite means nothing to somebody running Bombista on its own; and
    the third block is an offer rather than a refusal — it was the last one
    still written as a limitation. A rephrase loses one of those without
    anyone noticing, so the words are pinned."""
    text = squash(visible_text(deal))

    assert label.upper() in squash(deal) or label in text, f"no {label!r} label"
    assert body in text, f"the {label!r} block drifted"


def test_there_are_three_blocks_and_no_fourth(deal):
    """Three and no more (agreed 2026-09-03). A fourth block is how a
    value discussion becomes the explanation people skip."""
    labels = re.findall(r'<h2 class="secthead">([^<]+)</h2>', deal)

    assert labels == [label for label, _ in BLOCKS]


def test_one_control_at_the_foot_and_nothing_else(deal):
    """**`Begin →` is the skip**, and the whole answer to *I am adding song
    65 and I know this by heart*: the screen is met once and dismissed with
    one press. A skip link beside it would be redundant, and would invite
    back the stored *do not show again* flag that was already rejected.

    The step bar is navigation and is not counted here — it is the flow's
    chrome, on this screen exactly as on the other four."""
    body = deal[deal.index("</nav>") :]

    controls = re.findall(r"<button\b|<a\b", body)
    assert len(controls) == 1, f"the deal carries {len(controls)} controls"
    assert re.search(r'<a class="btn1" href="/input">Begin &rarr;</a>', body)


def test_the_prose_is_the_content_and_not_a_note_beside_it():
    """**The body text is the loudest thing on this screen.** Everywhere
    else in the flow prose is a caption in the muted mono register; here it
    is what the person came for, so it is paper-coloured, in the page's own
    sans, and larger than the register `.hint` uses."""
    rules = {}
    for block in re.sub(r"/\*.*?\*/", "", pages.STYLESHEET, flags=re.S).split("}"):
        if "{" in block:
            selector, declarations = block.split("{", 1)
            rules[selector.strip()] = declarations

    assert "color: var(--paper)" in rules[".deal p"]
    assert "var(--sans)" in rules[".deal p"]
    page = pages.render_deal()
    assert 'class="hint"' not in page[page.index("</style>") :], (
        "the deal's prose fell back to the caption register"
    )


def test_the_deal_is_a_screen_and_not_an_overlay(deal):
    """Not a modal over page 1: the flow's own masthead, the flow's own
    step bar, and a place in it to come back to."""
    assert '<header class="mast"' in deal
    assert '<div class="stepband"><nav class="steps"' in deal
    assert "position: fixed" not in deal[deal.index("<body>") :]


def test_the_step_bar_gains_an_unnumbered_leftmost_cell(deal):
    """`THE DEAL · 1 INPUT · 2 REVIEW · 3 OUTPUT` — unnumbered because it
    is not a step of the work, and a link because it stays reachable."""
    bar = re.search(r'<nav class="steps".*?</nav>', deal, re.S).group(0)

    assert re.findall(r'href="([^"]+)"', bar) == ["/deal", "/input", "/review", "/output"]
    assert len(re.findall(r'<span class="n">', bar)) == 3, "the deal was numbered"
    assert bar.index("/deal") < bar.index("/input"), "the deal is not leftmost"


def test_the_deal_is_the_current_cell_on_its_own_page(deal):
    bar = re.search(r'<nav class="steps".*?</nav>', deal, re.S).group(0)

    assert re.search(r'<a href="/deal" class="on">', bar)


def test_the_deal_says_none_of_the_retired_words(deal):
    """§10.1's ban is a ban on the flow's vocabulary, and this is the one
    screen made entirely of words."""
    text = flow_text(deal).lower()

    for retired in ("emit", "align", "alignment", "cp json", "cp song"):
        assert retired not in text


def test_the_deal_can_be_drawn_without_the_product_header():
    """Same page for both callers — the rule this repo already holds, and
    the one that settled the translations note. `--no-header` is a boolean
    about what to draw and it is not what decides the deal."""
    assert '<header class="mast"' not in pages.render_deal(header=False)
    assert WHAT_YOU_GET in squash(visible_text(pages.render_deal(header=False)))


# ---------------------------------------------------------------------------
# when it is shown — one rule, two sources of truth
# ---------------------------------------------------------------------------


def finished_run(root, stem="libertad"):
    """What `Save to the catalogue` leaves in the cache: `<stem>/<stem>.json`,
    which is `server.default_out_path` for a run staged there."""
    directory = root / stem
    directory.mkdir(parents=True)
    (directory / f"{stem}.json").write_text("{}", encoding="utf-8")
    return directory


def test_the_cache_answers_whether_this_machine_has_produced_a_song(staging_root):
    assert server.produced_a_song() is False

    staging_root.mkdir(parents=True, exist_ok=True)
    assert server.produced_a_song() is False, "an empty cache is not a song"

    (staging_root / "libertad").mkdir()
    assert server.produced_a_song() is False, "a staging directory is not a finished run"

    (staging_root / "libertad" / "libertad-timeline.json").write_text("{}", encoding="utf-8")
    assert server.produced_a_song() is False, "a candidate is not the song"

    finished_run(staging_root, "paso")
    assert server.produced_a_song() is True


def test_the_deal_opens_the_flow_when_this_machine_has_produced_no_song(serve_client):
    """The standalone half. **It was missed on the first pass** — *the
    catalogue is empty* means nothing to somebody running Bombista alone,
    so as first written it would have shown the deal every time or never."""
    status, _, headers = serve_client(None).get("/")

    assert status in (302, 303)
    assert headers["Location"] == "/deal"


def test_the_deal_does_not_open_the_flow_once_a_song_has_been_produced(
    serve_client, staging_root
):
    """**The refusal, on the standalone path.** After one finished run the
    screen is never met again, and it takes no remembered flag to do it."""
    finished_run(staging_root)

    status, _, headers = serve_client(None).get("/")

    assert status in (302, 303)
    assert headers["Location"] == "/input"


def test_a_caller_that_knows_better_answers_it_and_the_cache_is_not_consulted(
    serve_client, staging_root
):
    """**The refusal, on the caller's path.** Pregonero's catalogue is the
    truth there, and its staging directory is not this cache — so a caller
    that says *no* is obeyed even with an empty cache, and one that says
    *yes* is obeyed even with a full one. That is what keeps the standalone
    signal off the walk entirely."""
    status, _, headers = serve_client(None, deal=False).get("/")
    assert headers["Location"] == "/input", "the caller's answer was overruled"

    finished_run(staging_root)
    status, _, headers = serve_client(None, deal=True).get("/")
    assert headers["Location"] == "/deal", "the caller's answer was overruled"


def test_the_deal_stays_reachable_after_it_has_been_answered(serve_client, staging_root):
    """It sits in the step bar so it can be returned to. Not showing it at
    the door is not the same as taking it away."""
    finished_run(staging_root)
    client = serve_client(None, deal=False)

    status, body, _ = client.get("/deal")

    assert status == 200
    assert WHAT_IT_COSTS in squash(visible_text(body))


def test_a_review_still_wins_the_door(serve_client, libertad):
    """`serve <staging> <lyrics>` boots straight into the review. Somebody
    who arrived with a finished run to look at is not being asked whether
    to start."""
    session = server.load_session(libertad["staging"], libertad["song_path"], lang="es")

    status, _, headers = serve_client(session).get("/")

    assert status in (302, 303)
    assert headers["Location"] == "/review"


def test_nothing_remembers_that_the_deal_was_seen(serve_client):
    """**No stored dismissal flag** — rejected as remembered state in a
    project whose test discipline is starting from nothing, and it would be
    a fourth thing for the walk's three reset commands to clear.

    Pressing `Begin →` is a navigation and writes nothing; asking the door
    a second time gets the same answer it gave the first time."""
    client = serve_client(None)

    assert client.get("/")[2]["Location"] == "/deal"
    assert client.get("/deal")[0] == 200
    assert client.get("/")[2]["Location"] == "/deal"
