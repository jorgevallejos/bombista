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
    return pages.render_output(
        server.build_sp_json(session, {})[0],
        filename="libertad.json",
        save_path=str(server.default_out_path(session)),
    )


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


def test_the_masthead_version_is_the_package_version():
    """The masthead's `v0.9.0` and `pyproject.toml`'s `0.9.0` are one fact
    written twice, and the second copy is the one nobody remembers to edit —
    which is how the page went on announcing 0.9.0 after the tool had moved.

    `pages.VERSION` is a plain string on purpose (a header should not go
    reading distribution metadata to render itself), so the duplication is
    kept and *guarded* instead: this fails the moment the two disagree, so
    the next bump is a red test at bump time rather than a wrong number on a
    page anyone can open.
    """
    from importlib.metadata import version

    assert pages.VERSION == f"v{version('bombista')}", (
        f"pages.VERSION is {pages.VERSION!r} but the installed package is "
        f"{version('bombista')!r} — bump both, or re-run `pip install -e \".[dev]\"` "
        "if you have just edited pyproject.toml in an editable checkout."
    )


@pytest.mark.parametrize("name", ALL_PAGES)
def test_the_masthead_shows_that_version(name, rendered):
    """§9.1 puts the version in the masthead, so the guard above is only
    worth anything if the guarded string is what every page actually
    prints."""
    masthead = re.search(r'<header class="mast".*?</header>', rendered[name], re.S)

    assert masthead, "no masthead"
    assert pages.VERSION in masthead.group(0)


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


def test_page_1_still_opens_on_exactly_four_rows(page1):
    """§9.3's four rows survive the augmentation: the form the user meets
    before choosing anything is still Lyrics, Media source, Language,
    Model. The song block that step 6 adds is hidden until a lyrics file
    is chosen, because until then there is no song to describe."""
    main_form = page1[: page1.index('<div id="songbranch"')]
    rows = re.findall(r'<label class="flabel">([^<]+)</label>', main_form)

    assert rows == ["Lyrics", "Media source", "Language", "Model"]


def test_page_1_collects_the_general_information_a_txt_cannot_carry(page1):
    """journey-setup step 6, 2026-09-02: this is where the metadata a
    lyrics `.txt` cannot carry is collected. It is Bombista's own screen
    and appears when Bombista is used on its own, which is the point of
    putting it here."""
    branch = re.search(r'<div id="songbranch".*?<!--/songbranch-->', page1, re.S)

    assert branch, "page 1 has no song block"
    for field in ("title", "artist", "notes"):
        assert f'id="{field}"' in branch.group(0), f"no {field} field"


def test_page_1_does_not_ask_for_a_translation(page1):
    """Walked 2026-09-02, on Jorge's own principle: translation is not
    Bombista's concern. Lyric translations are written outside the suite,
    in the file, and the title follows the same rule — *if it is a
    translation, it was written elsewhere and the file already carries
    it*. A file's own translations still pass through untouched; what
    changed is that nothing here asks for one."""
    for code in ("es", "en", "nl", "fr"):
        assert f'id="tt-{code}"' not in page1
    assert "translation" not in visible_text(page1).lower()


def test_the_song_block_starts_hidden(page1):
    """There is nothing to describe until a lyrics file has been chosen,
    and a form of empty fields over no song is the wall of text step 6's
    walk failed on."""
    branch = re.search(r'<div id="songbranch"[^>]*>', page1).group(0)

    assert "pageoff" in branch


def test_every_free_text_field_on_page_1_belongs_to_the_song_block(page1):
    """§3's *no free text* is now *no free text about the run*. What the
    machine is told — the files, the language, the model — is still
    pickers and dropdowns; what only a human can supply is typed."""
    branch = re.search(r'<div id="songbranch".*?<!--/songbranch-->', page1, re.S).group(0)
    text_inputs = [i for i in re.findall(r"<input[^>]*>", page1) if 'type="text"' in i]

    assert text_inputs, "page 1 has no text field at all"
    for field in text_inputs:
        assert field in branch, f"a text field lives outside the song block: {field}"


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


def test_the_example_link_points_at_the_formats_canonical_home(page1):
    """§9.6's address, pinned to the character.

    This is not a style assertion. `FORMAT_DOC_URL` is baked into every
    installed copy of Bombista and followed forever by tools nobody can
    reach to update, so it is a promise to the outside rather than a
    detail of the page — the URL is permanent, and a page that moves
    redirects rather than renames. Pinning the literal here makes the
    promise something a commit has to break on purpose.

    It asserts the anchor too: a correct constant that page 1 stopped
    interpolating would leave the reader with a dead *See an example*,
    which is the failure this whole change exists to close.
    """
    assert pages.FORMAT_DOC_URL == "https://changopepper.com/tramoya/song-performance-json"

    anchor = re.search(r'<a href="([^"]+)">See an example</a>', page1)

    assert anchor, "page 1 has no 'See an example' link"
    assert anchor.group(1) == pages.FORMAT_DOC_URL


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


def test_the_tempo_control_asks_three_questions_a_musician_can_answer(page1):
    """Walked 2026-09-02: `bpm`, `beats`, `per` and `count-in bars` as four
    bare numbers could not be answered by the person who has to answer
    them. A pulse, a time signature and a number of bars can be.

    **`beats` and `per` must not come back.** A numerator and a denominator
    are the format's business, split at the boundary, and never a question
    put to a musician."""
    assert 'id="t-bpm"' in page1
    assert 'id="t-signature"' in page1
    assert 'id="t-countinbars"' in page1
    assert 'id="t-numerator"' not in page1
    assert 'id="t-denominator"' not in page1

    text = visible_text(page1)
    assert "Bars before the first line" in text
    assert ">beats<" not in page1 and ">per<" not in page1


def test_the_signature_control_offers_the_signatures_that_occur_in_practice(page1):
    options = re.search(r'<select id="t-signature">(.*?)</select>', page1, re.S).group(1)

    assert re.findall(r'value="([^"]*)"', options) == ["", "4/4", "3/4", "6/8", "2/4", "12/8"]


def test_a_signature_the_dropdown_cannot_say_is_added_rather_than_dropped():
    """A file carrying `5/4` must come back out carrying `5/4`. A control
    that could not say it would either drop the block or round it to
    something it can, and both are the control editing the file."""
    assert '<option value="5/4">5/4</option>' in pages._signature_options("5/4")
    assert pages.split_signature("5/4") == (5, 4)


def test_the_bpm_caption_asks_for_the_felt_pulse_and_warns_off_the_daw(page1):
    """**The 1.5x error this exists to stop, walked 2026-09-02.** The old
    caption read *type it from the source that produced this audio, where
    it is exact*, so Jorge went to the source and typed `100` for a `6/8`
    song whose felt pulse is `66.67`. The screen invited it."""
    text = visible_text(page1)

    assert "pulse you feel" in text
    assert "count" in text.lower()
    assert "66.67" in text and "100" in text
    assert "never measures" in text


def test_page_1_does_not_send_the_reader_to_another_step_for_the_tempo(page1):
    """The note that used to point at step 2 goes with the control."""
    assert "step 2" not in visible_text(page1)


def test_the_product_header_can_be_turned_off_and_the_version_survives():
    """Walked 2026-09-02: inside a window somebody else already titled, a
    product introducing itself by name, tagline and *a Tramoya tool by
    Chango Pepper* is the tool talking about itself to a person who did not
    choose it. **The version is the part that must survive** — two builds
    calling themselves the same number is the trap that has cost this
    project a day."""
    bare = pages.render_input(header=False)

    assert "<header" not in bare
    assert "Forced-alignment triage" not in bare
    assert "by <b>Chango Pepper</b>" not in bare
    assert 'class="wordmark"' not in bare
    assert pages.VERSION in bare, "the version went with the branding"

    # *the format Tramoya promotes* stays: it names the FORMAT on the
    # lyrics row, which is a fact about the file being asked for, not the
    # product introducing itself.
    assert "the format Tramoya promotes" in bare


def test_the_header_is_drawn_by_default(page1):
    """It is an option a caller may pass, not a default that quietly
    stripped Bombista's own pages."""
    assert "<header" in page1 and "Forced-alignment triage" in page1


def test_page_1_shows_the_slug_read_only(page1):
    """It names the file the song will be written as, and it comes from
    the lyrics filename — so it is shown, beside the title it is not."""
    branch = re.search(r'<div id="songbranch".*?<!--/songbranch-->', page1, re.S).group(0)

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


def test_page_3_offers_saving_beside_the_downloads_not_instead_of_them(page3):
    """journey-setup step 6: `Save to the catalogue`, beside the three
    downloads rather than replacing them. The words are chosen because the
    flow is also how an existing song is edited, which rules out *Add to
    the library*; and on a screen where everything else hands over bytes,
    naming the destination is the distinction."""
    assert 'id="save"' in page3
    assert "Save to the catalogue" in visible_text(page3)

    buttons = re.findall(r'<button[^>]*id="dl-([a-z]+)"[^>]*>([^<]*)</button>', page3)
    assert [kind for kind, _ in buttons] == ["song", "timeline", "report"]


def test_page_3_names_the_path_it_will_write_before_it_is_pressed(page3):
    """A button that says *the catalogue* and a tool that writes beside the
    working files for this run are only reconcilable if the page says which
    file. It is stated ahead of the press, not only reported after it."""
    assert "libertad.json" in visible_text(page3)
    assert 'id="savepath"' in page3


def test_only_one_control_on_page_3_carries_the_accent(page3):
    """§10.3 — contrast is a budget and the accent marks one thing at a
    time. Adding a second clay button left the page with two endings and
    no answer about which one it is. `Save to the catalogue` is the one
    that ends the flow — inside Pregonero the downloads are not an ending
    at all — so the download that used to be primary is a plain button."""
    primaries = re.findall(r'<button[^>]*class="btn1"[^>]*id="([a-z-]+)"', page3)

    assert primaries == ["save"]


def test_page_3_does_not_send_the_reader_to_step_2_for_the_tempo(page3):
    """The caption named step 2 because the control was there. It moved."""
    assert "step 2" not in visible_text(page3)


def test_saving_is_not_a_download(page3):
    """The three downloads hand over bytes and write nothing; this one
    writes a file. Giving it a `dl-` id would fold it into the row that
    chooses no path."""
    assert not re.search(r'<button[^>]*id="dl-save"', page3)


# ---------------------------------------------------------------------------
# a page's script and a page's markup are one thing (the Confirm regression)
# ---------------------------------------------------------------------------


def wanted_ids(script: str) -> set[str]:
    """Every id a script asks the document for."""
    return set(re.findall(r'getElementById\(\s*"([^"]+)"\s*\)', script))


@pytest.mark.parametrize("name", ALL_PAGES)
def test_no_page_script_reaches_for_an_id_the_page_does_not_carry(name, rendered):
    """**The bug this exists for, walked 2026-09-02.** `v1.2.0` moved the
    tempo control off page 2 and left its wiring behind. The script's
    `getElementById("t-set")` returned null, `null.addEventListener` threw,
    and every statement after it was skipped — which was exactly one:
    `Confirm timeline`'s listener, the last line in the file. The stepper,
    the player and the re-anchor were all registered earlier, so the page
    looked completely alive while the one control that leaves it did
    nothing. It failed standalone, not only in a frame.

    A page's script and a page's markup are one artifact built by one
    function; nothing but a test makes them stay that way. This pins the
    class rather than the instance: the next control that moves takes its
    wiring with it or turns this red.

    Ids the script CREATES are exempt — the picker builds its own dialog —
    so the exemption list is explicit and short, and adding to it is a
    decision rather than an accident.
    """
    html = rendered[name]
    script = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
    markup = _BLOCKS.sub(" ", html)

    # Page 2's stepper popup and the file picker's dialog are both built
    # in the script, so their ids are never in the rendered markup. Every
    # one of these is asserted to be created below, so the exemption
    # cannot quietly grow to cover a real miss.
    built_by_the_script = {"popval", "popbounds", "pick-list", "pick-path", "pick-choose"}
    for ident in built_by_the_script & wanted_ids(script):
        assert f'id="{ident}"' in script, f"{ident} is exempt but the script never builds it"
    wanted = wanted_ids(script)
    present = set(re.findall(r'id="([^"]+)"', markup))

    missing = sorted(wanted - present - built_by_the_script)
    assert not missing, f"{name}'s script reaches for {missing}, which it does not render"


def test_confirm_is_the_last_thing_page_2_wires_and_it_is_wired(page2):
    """The regression's shape, from the other side: the button exists in
    the markup and the script asks for it. Without the test above this one
    passes while the listener never attaches, which is why both are here."""
    assert 'id="confirm"' in page2
    assert 'getElementById("confirm")' in page2


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
    point at the format's canonical home on changopepper.com (§9.6)."""
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


def _rules(css: str) -> list[str]:
    """The stylesheet as whole rules, so a property is judged with the
    selector it belongs to rather than by which line it fell on."""
    return [block + "}" for block in css.split("}")]


def test_the_skin_has_one_palette_no_radius_and_no_blue():
    """§10.3: one palette (no light mode, no prefers-color-scheme block),
    no border radius anywhere, no blue — `--edit: #4b57c4` is gone and clay
    took its jobs.

    **The file picker is the one exception and it is scoped to it**
    (2026-09-02). Everything else here is brutalist by decision; a file
    dialog is the one place a person expects their system's own furniture,
    so it gets soft corners. The rule holds everywhere it is not
    `.picker`, which is what this now asserts — the exception cannot leak
    into the rest of the skin without turning this red.
    """
    css = pages.STYLESHEET
    outside_the_picker = "".join(block for block in _rules(css) if ".picker" not in block)

    assert "color-scheme: dark" in css
    assert "prefers-color-scheme" not in css
    assert {v.strip() for v in re.findall(r"border-radius:([^;]+)", outside_the_picker)} <= {"0"}
    assert "4b57c4" not in css
    assert "--edit" not in css


def test_the_file_picker_has_no_voice():
    """Jorge, 2026-09-02: it is the one surface in the suite that should
    not have a voice. It sits beside Pregonero's real macOS dialogs, which
    cannot be styled, so what has to match is the behaviour and the
    vocabulary rather than the pixels — `Choose` is Pregonero's own word.
    Clay is Bombista talking, and it does not talk here."""
    picker = "".join(block for block in _rules(pages.STYLESHEET) if ".picker" in block)

    assert "--clay" not in picker, "the picker wears Bombista's accent"
    assert "Choose" in pages._PICKER_JS and "Cancel" in pages._PICKER_JS
    assert "text-transform: none" in picker, "uppercase buttons are this page's voice, not a dialog's"


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
