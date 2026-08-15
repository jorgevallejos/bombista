"""
Pages 1, 1.5 and 3, the step bar and the masthead — B20 §9, §10.

These assert the page's *shape and vocabulary*, which is where this design
is opinionated: four rows and no fifth, no free text but the title, no
fold on page 3, no external reference anywhere, and none of the retired
words on a user-facing string.

Page 2 joined this file when it landed: the chrome, the vocabulary and
the skin are shared, so its assertions about *those* belong here beside
the other three. What is page 2's own — the row, the stepper, the popup,
what an edit shows — is in tests/test_page2.py.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from bombista import pages

# ---------------------------------------------------------------------------
# helpers — a page is HTML, and only some of it is user-facing
# ---------------------------------------------------------------------------

_BLOCKS = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")


def visible_text(html: str) -> str:
    """The words a reader actually sees: markup, CSS and JS removed.

    The distinction matters — `text-align` and `align-items` are CSS
    properties, and a substring search over the raw file would read them
    as the retired verb *align*.
    """
    return _TAGS.sub(" ", _BLOCKS.sub(" ", html))


def flow_text(html: str) -> str:
    """`visible_text` minus the masthead. The masthead carries the
    product's tagline, *Forced-alignment triage* (§9.1) — the one place
    the mechanism is named on purpose, as positioning rather than as a
    step in the flow. §10.1's ban governs the flow's own words."""
    return visible_text(re.sub(r'<header class="mast".*?</header>', " ", html, flags=re.S))


ALL_PAGES = ["input", "processing", "review", "output"]


def render(name: str, **kwargs) -> str:
    return getattr(pages, f"render_{name}")(**kwargs)


@pytest.fixture
def page1():
    return pages.render_input()


@pytest.fixture
def page3(libertad):
    from bombista import server

    session = server.load_session(libertad["staging"], libertad["song_path"], lang="es")
    return pages.render_output(server.build_sp_json(session, {})[0], filename="libertad.sp.json")


@pytest.fixture
def page2(synthetic_session):
    from bombista import server

    return pages.render_review(server.session_payload(synthetic_session))


@pytest.fixture
def rendered(page1, page2, page3):
    """The four states, by the name `ALL_PAGES` parametrises on. Page 1.5
    is a state of step 1 (§9.2) and is rendered by `render` on demand;
    pages 2 and 3 need a session, so they arrive as fixtures."""
    return {
        "input": page1,
        "processing": pages.render_processing(),
        "review": page2,
        "output": page3,
    }


# ---------------------------------------------------------------------------
# the masthead and the step bar — on every page (§9.1, §9.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_PAGES)
def test_every_page_carries_the_masthead(name, rendered):
    html = rendered[name]

    assert "Bombista" in html
    assert "Forced-alignment triage" in html
    assert "Tramoya" in html
    assert "Chango Pepper" in html


@pytest.mark.parametrize("name", ALL_PAGES)
def test_every_page_carries_the_step_bar_and_reaches_every_step(name, rendered):
    html = rendered[name]
    bar = re.search(r'<nav class="steps".*?</nav>', html, re.S)

    assert bar, "no step bar"
    assert re.findall(r'href="([^"]+)"', bar.group(0)) == ["/input", "/review", "/output"]
    for label in ("Input", "Review", "Output"):
        assert label in bar.group(0)


def test_page_1_5_is_a_state_of_step_1_not_a_fourth_step():
    """§9.2 — inventing a segment for it would say the flow has four steps
    when it has three. Its heading is Processing."""
    html = pages.render_processing()
    bar = re.search(r'<nav class="steps".*?</nav>', html, re.S).group(0)

    assert len(re.findall(r"<a ", bar)) == 3
    assert "Processing" in html
    assert re.search(r"<h1[^>]*>\s*Processing\s*</h1>", html)


@pytest.mark.parametrize("name", ALL_PAGES)
def test_the_current_step_is_marked(name, rendered):
    html = rendered[name]
    bar = re.search(r'<nav class="steps".*?</nav>', html, re.S).group(0)

    assert len(re.findall(r'class="on"', bar)) == 1


# ---------------------------------------------------------------------------
# page 1 — four rows and nothing else (§9.3)
# ---------------------------------------------------------------------------


def test_page_1_renders_exactly_four_rows(page1):
    """§9.3: four rows, and that is the whole form. The plain-text branch
    grows it in place with three more, and is hidden until a .txt is
    chosen — so the form the user meets is always four."""
    main_form = page1[: page1.index('<div id="txtbranch"')]
    rows = re.findall(r'<label class="flabel">([^<]+)</label>', main_form)

    assert rows == ["Lyrics", "Media source", "Language", "Model"]


def test_page_1_has_no_free_text_input(page1):
    """§3, taken literally: every field is a picker, a dropdown, a radio or
    a stepper. The title is the one exception and it belongs to the .txt
    branch, which is hidden until a .txt is chosen."""
    inputs = re.findall(r"<input[^>]*>", page1)
    text_inputs = [i for i in inputs if 'type="text"' in i]

    assert len(text_inputs) == 1
    assert 'id="title"' in text_inputs[0]
    branch = re.search(r'<div id="txtbranch"[^>]*>.*?</div>\s*<!--/txtbranch-->', page1, re.S)
    assert branch and text_inputs[0] in branch.group(0), (
        "the title input must live inside the plain-text branch"
    )
    assert "pageoff" in branch.group(0), "the .txt branch must start hidden"


def test_page_1_has_no_output_directory_control_and_no_format_checkboxes(page1):
    """Both cut 2026-08-15 (§9.3, decision 3) — step 3 offers downloads and
    the app does not choose where they land."""
    assert 'type="checkbox"' not in page1
    text = visible_text(page1).lower()
    for cut in ("output folder", "output directory", "also write", "destination"):
        assert cut not in text


def test_page_1_captions_say_what_9_3_requires(page1):
    text = visible_text(page1)

    assert "The language on the recording and the lyrics file." in text
    assert "Runs on your local machine. Nothing is uploaded." in text
    assert "Song Performance" in text


def test_the_language_caption_does_not_explain_the_constraint(page1):
    """§9.3, decision 5 — the dropdown enforces the rest by disabling what
    it cannot offer; a caption teaching an exception is a caption too many."""
    caption = re.search(
        r"The language on the recording and the lyrics file\.(.*?)</p>", page1, re.S
    )

    assert caption and not visible_text(caption.group(1)).strip()


def test_page_1_offers_the_three_models_with_their_cost(page1):
    models = re.search(r'<select id="model".*?</select>', page1, re.S).group(0)

    for size in ("medium", "small", "tiny"):
        assert f'value="{size}"' in models
    assert "~50 s" in models


def test_page_1_has_no_tempo_control_at_all(page1):
    """§9.3 and §11.5, decided 2026-08-16: the control comes out. PR 4
    shipped it as a stepper that could only ever produce `{"bpm": …}`, and
    a bpm-only block NaNs Pregonero's `getBeatsPerBar` — correct scaling,
    broken pulse. A control that cannot ask for a whole tempo block should
    not ask for part of one."""
    assert 'id="tempo"' not in page1
    assert not re.search(r"<input[^>]*tempo", page1, re.I)


def test_page_1_says_tempo_is_not_bombistas_business_and_names_all_four_keys(page1):
    """The note that replaces the control (§9.3). It must name all four
    keys: *add the tempo by hand* is bad advice on its own, because it
    leads to exactly the bpm-only block this note exists to prevent."""
    text = visible_text(page1)

    assert "Tempo is not Bombista's business" in text
    assert "Ableton" in text
    for key in ("bpm", "numerator", "denominator", "countInBars"):
        assert key in text, f"the note does not name {key}"


def test_page_1_shows_the_slug_read_only(page1):
    branch = re.search(r'<div id="txtbranch".*?<!--/txtbranch-->', page1, re.S).group(0)

    assert "Slug" in branch
    assert 'id="slug"' in branch
    assert not re.search(r'<input[^>]*id="slug"', branch), "the slug is shown, not typed"


# ---------------------------------------------------------------------------
# page 1.5 — a state, not a spinner (§9.4)
# ---------------------------------------------------------------------------


def test_page_1_5_has_two_phase_rows_a_cancel_and_the_cache_line():
    html = pages.render_processing()

    phases = re.findall(r'<div class="phase"[^>]*>', html)
    assert len(phases) == 2
    text = visible_text(html)
    assert "Transcribing the audio" in text
    assert "Anchoring the lines" in text
    assert "Cancel" in text
    assert "asr-words.jsonl" in text
    assert "cached" in text


def test_the_phase_dot_blinks_on_steps_and_does_not_fade():
    """§10.3 — no easing anywhere; the dot blinks on steps(2)."""
    css = pages.STYLESHEET

    assert "steps(2" in css
    assert "ease" not in css.replace("ease-", "")


# ---------------------------------------------------------------------------
# page 3 — read-only, in full (§9.5)
# ---------------------------------------------------------------------------


def test_page_3_renders_the_whole_json_with_no_fold(page3):
    """An earlier pass added a fold control and Jorge cut it: the window
    scrolls, the file is the file."""
    window = re.search(r'<pre class="json"[^>]*>(.*?)</pre>', page3, re.S)

    assert window
    assert "…" not in window.group(1) and "..." not in window.group(1)
    assert "<details" not in page3
    text = visible_text(page3).lower()
    for cut in ("expand", "show more", "show all", "collapse"):
        assert cut not in text


def test_page_3_names_the_five_keys_bombista_wrote(page3):
    text = visible_text(page3)

    for key in (
        "linesHash",
        "timelineSignedOff",
        "timelineVersion",
        "leadIn",
        "timeline",
    ):
        assert key in text


def test_page_3_offers_exactly_three_downloads(page3):
    buttons = re.findall(r'<button[^>]*id="dl-([a-z]+)"[^>]*>([^<]*)</button>', page3)

    assert [kind for kind, _ in buttons] == ["song", "timeline", "report"]
    assert "Download JSON file" in page3
    assert "Download timeline only" in page3
    assert "Download report" in page3


def test_page_3_download_buttons_are_pressable_when_nothing_was_flagged(page3):
    """B19's surviving clause. Nothing on this page disables a download —
    a run with no flagged line still has to be signed off."""
    for button in re.findall(r"<button[^>]*>", page3):
        assert "disabled" not in button


def test_page_3_has_no_ready_to_write_line_and_no_file_list(page3):
    """Both cut 2026-08-15 — they described a write to a folder the app no
    longer chooses."""
    text = visible_text(page3).lower()

    for cut in ("ready to write", "will be written", "into staging", "files to be"):
        assert cut not in text


def test_page_3_links_back_to_review(page3):
    assert 'href="/review"' in page3


# ---------------------------------------------------------------------------
# §10.1 — the vocabulary, and it is not negotiable in user-facing strings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_PAGES)
def test_no_page_uses_a_retired_word(name, rendered):
    html = rendered[name]
    text = flow_text(html).lower()

    for retired in ("emit", "align", "alignment", "cp json", "cp song"):
        assert retired not in text, f"{name} says {retired!r}"


def test_the_masthead_keeps_the_products_own_tagline():
    """The one exemption above, made explicit so it cannot be widened: the
    tagline names the technique as positioning (§9.1, Jorge's wording), not
    as a step the user takes."""
    masthead = re.search(r'<header class="mast".*?</header>', pages.render_input(), re.S)

    assert "Forced-alignment triage" in masthead.group(0)


@pytest.mark.parametrize("name", ALL_PAGES)
def test_the_steps_are_named_input_review_output(name, rendered):
    html = rendered[name]
    bar = re.search(r'<nav class="steps".*?</nav>', html, re.S).group(0)

    assert "Set up" not in bar and "Correct" not in bar and "Emit" not in bar


@pytest.mark.parametrize("name", ALL_PAGES)
def test_the_audio_row_is_called_media_source(name, rendered):
    html = rendered[name]

    assert not re.search(r'<label class="flabel">Audio</label>', html)


# ---------------------------------------------------------------------------
# §10.3 — the skin, and §8.1's stack
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_PAGES)
def test_no_page_references_anything_external(name, rendered):
    """Narrower than B16's assertion, which forbids `fetch` too: these
    pages talk to their own process over loopback, and must. What they
    must not do is LOAD anything off the machine — no font CDN, no CSS
    host, no remote image. A hyperlink the reader may click is not a
    resource the page fetches, which is what lets §9.3's *See an example*
    point at the repo until the format has a canonical home (§9.6)."""
    html = rendered[name]

    resources = re.findall(r'<(?:link|script|img|iframe)\b[^>]*(?:src|href)="([^"]+)"', html)
    resources += re.findall(r"url\(\s*['\"]?([^)'\"]+)", pages.STYLESHEET)
    resources += re.findall(r"@import\s+['\"]?([^;'\"]+)", pages.STYLESHEET)

    assert not resources, f"{name} loads {resources}"
    assert "fonts.googleapis" not in html
    assert "Montserrat" not in html


@pytest.mark.parametrize("name", ALL_PAGES)
def test_every_page_is_self_contained(name, rendered):
    """§8.1's stack: one page, inline CSS and JS, no build step."""
    html = rendered[name]

    assert "<style>" in html
    assert not re.search(r"<link[^>]+stylesheet", html)
    assert not re.search(r"<script[^>]+src=", html)


def test_the_palette_is_10_3s_tokens():
    css = pages.STYLESHEET

    for token, value in (
        ("--bg", "#121211"),
        ("--surface", "#1a1a18"),
        ("--surface-2", "#232320"),
        ("--paper", "#e6dfd1"),
        ("--dim", "#8b8478"),
        ("--dimmer", "#635d54"),
        ("--line", "#2c2a26"),
        ("--line-2", "#423e37"),
        ("--clay", "#d98b7a"),
        ("--clay-dim", "#8f5a4e"),
        ("--high", "#4f7d63"),
        ("--review", "#e0a437"),
        ("--fail", "#ef7a70"),
    ):
        assert f"{token}: {value}" in css


def test_the_skin_has_one_palette_no_radius_and_no_blue():
    """§10.3: one palette (no light mode, no prefers-color-scheme block),
    no border radius anywhere, no blue — `--edit: #4b57c4` is gone and clay
    took its jobs."""
    css = pages.STYLESHEET

    assert "color-scheme: dark" in css
    assert "prefers-color-scheme" not in css
    assert {value.strip() for value in re.findall(r"border-radius:([^;]+)", css)} <= {"0"}
    assert "4b57c4" not in css
    assert "--edit" not in css


@pytest.mark.parametrize("name", ALL_PAGES)
def test_the_shared_stylesheet_is_shared(name, rendered):
    """One skin, defined once. Page 2 INHERITED it rather than being
    retrofitted with it — the reason PR 4 ran before this one."""
    assert pages.STYLESHEET in rendered[name]


def test_the_step_bar_renders_on_all_four_states(rendered):
    """§9.2, and the last of PR 4's four findings closed: the bar rendered
    on three states while `/review` 404ed. It renders on four now, and
    every step is reachable from every other."""
    for name in ALL_PAGES:
        bar = re.search(r'<nav class="steps".*?</nav>', rendered[name], re.S)
        assert bar, name
        assert re.findall(r'href="([^"]+)"', bar.group(0)) == ["/input", "/review", "/output"]
