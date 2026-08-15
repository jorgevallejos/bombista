"""
Page 2 — Review (B20 §8).

The page is deliberately spare, and that is the design rather than an
unfinished state: a quiet provenance block, a sticky player with the three
band counts, one line of instruction, the list of lines, one button. Most
of what is asserted here is therefore an **absence** — the lead-in panel,
the "needs attention" card, the editor pane, the re-anchor banner and the
JSON preview were all cut, and a page that grows any of them back has
stopped being this page.

The rows are rendered by the server (`pages.render_rows`) rather than by
the page's JavaScript, which is where this departs from the mockup: one
template, in Python, that the tests below can actually read. The page
fetches the same markup back after a re-anchor, so there is no second
renderer to drift.

Synthetic fixtures throughout — no whisper model, no audio (CLAUDE.md).
"""
from __future__ import annotations

import re

import pytest

from bombista import pages, server

from .test_pages import flow_text, visible_text
from .test_synthetic_canary import FLAGGED_LINE, MACHINE_START, TRUE_ONSET


@pytest.fixture
def payload(synthetic_session):
    return server.session_payload(synthetic_session)


@pytest.fixture
def page2(payload):
    return pages.render_review(payload)


def rows_of(html: str) -> list[str]:
    """The `<tr>` of each lyric line, in order — the divider row excluded,
    since it belongs to the edit rather than to a line."""
    return re.findall(r'<tr class="[^"]*" data-line="\d+".*?</tr>', html, re.S)


# ---------------------------------------------------------------------------
# §6 — the requirement the CLI failed
# ---------------------------------------------------------------------------


def test_every_row_carries_its_lines_text_and_not_only_its_index(page2, payload):
    """§6 makes this a UI requirement rather than a documentation one. The
    CLI never answered whether `LINE` was 0- or 1-indexed, and no
    user-facing string in the repo does either. A row that shows a bare
    index expects the user to know a convention that was never written
    down; a row that shows `line 3` beside its words does not."""
    rows = rows_of(page2)

    assert len(rows) == len(payload["lines"])
    for line, row in zip(payload["lines"], rows):
        assert f"line {line['i']}" in row
        assert line["text"].split("\n")[0] in row


def test_every_row_can_be_confirmed_by_ear(page2, payload):
    """The other half of §6: ▶ seeks the player to the line's onset, so a
    user who does not know the base can still act correctly."""
    for line, row in zip(payload["lines"], rows_of(page2)):
        assert f'class="play" data-start="{line["start"]:.2f}"' in row


# ---------------------------------------------------------------------------
# §8.6 — line 0 is not special
# ---------------------------------------------------------------------------


def test_line_0_is_an_ordinary_row(page2):
    """Settled 2026-08-16. No special colour, no `lead-in` row label, no
    popup caption — and no lead-in widget anywhere on the page, not on
    line 0, not above the table, not in the sticky bar. The distinction
    between a lead-in and line 0 is Pregonero's, at performance time."""
    first, second = rows_of(page2)[:2]
    shape = lambda row: re.findall(r'<td class="([^"]+)"', row)

    assert shape(first) == shape(second)
    assert 'data-line="0"' in first
    assert "lead-in" not in first.lower()
    assert "moves the whole song" not in page2


def test_line_0_opens_the_same_stepper_as_every_other_line(page2):
    controls = re.findall(r'<button class="tbtn[^"]*" data-open="(\d+)"', page2)

    assert controls[0] == "0"
    assert len(controls) == len(rows_of(page2))


def test_no_lead_in_control_anywhere_on_the_page(page2):
    """The three options considered in §8.6 — a line-0 widget, a panel
    above the table, a control in the sticky bar — are all dropped. The
    provenance block still *reports* the measured lead-in, because that is
    a fact about the run rather than a control."""
    outside_provenance = re.sub(r"<details class=\"prov\".*?</details>", " ", page2, flags=re.S)

    assert "lead-in" not in flow_text(outside_provenance).lower()
    assert "lead-in" in visible_text(page2).lower(), "provenance still reports it"


# ---------------------------------------------------------------------------
# §8.4 — the start time is the control
# ---------------------------------------------------------------------------


def test_the_popup_contains_exactly_one_stepper_and_no_other_control(page2):
    """No bounds text, no delta readout, no explanation, no buttons. A
    stated bound is one more sentence on a page that should have almost
    none — the bounds are enforced by silently clamping instead."""
    popup = re.search(r"POPUP\s*=\s*'(.*?)';", page2, re.S)

    assert popup, "the popup's markup is not built in one place"
    markup = popup.group(1)
    assert len(re.findall(r"<button", markup)) == 2, "one stepper is two buttons and no more"
    assert re.findall(r'data-step="([^"]+)"', markup) == ["-0.05", "0.05"]
    assert "class=\"cap\"" not in markup, "no popup caption (§8.6)"


def test_the_stepper_step_is_finer_than_the_correction_loop(page2):
    """Invariant 2: the differentiator is a 0.07 s correction loop, so no
    control and no serialisation may round coarser than that."""
    step = float(re.search(r"var STEP = ([\d.]+);", page2).group(1))

    assert step <= 0.07
    assert step == 0.05


def test_the_bounds_are_the_neighbouring_lines_and_clamp_silently(page2):
    """§8.4: the real allowed interval is the neighbouring lines,
    recomputed live — a fixed range is not it. Nothing states the bound;
    the stepper simply stops, because a stated bound is one more sentence
    on a page that should have almost none.

    Line 0's floor is the start of the audio because there is no line
    above it. That is arithmetic, not the special case §8.6 struck."""
    bounds = re.search(r"function boundsFor\(i\) \{(.*?)\n  \}", page2, re.S).group(1)
    nudge = re.search(r"function nudge\(d\) \{(.*?)\n  \}", page2, re.S).group(1)

    assert "all[i - 1]" in bounds and "all[i + 1]" in bounds
    assert "(i === 0) ? 0" in bounds
    assert "b.lo" in nudge and "b.hi" in nudge


def test_press_and_hold_auto_repeats(page2):
    """Load-bearing, not a nicety: the flagged line's error is 1.22 s,
    which is 24 separate presses. A held second crosses it."""
    assert re.search(r"var HOLD_DELAY = 380;", page2)
    assert re.search(r"var HOLD_RATE = 45;", page2)


def test_the_re_anchor_is_debounced_and_not_behind_a_button(page2):
    """Per press repaints the list during exactly the interaction that
    matters; a button leaves the page showing a state that is no longer
    true."""
    assert re.search(r"var DEBOUNCE = 250;", page2)
    assert "Re-anchor" not in visible_text(page2)


def test_the_popup_is_not_repositioned_while_a_button_is_held(page2):
    """Found by building the mockup: reposition mid-press and the button
    moves out from under the cursor."""
    place = re.search(r"function placePopup\(\) \{(.*?)\n  \}", page2, re.S).group(1)

    assert "holdTimer" in place and "repeatTimer" in place


def test_the_debounce_never_fires_while_a_button_is_held(page2):
    """`HOLD_DELAY` is longer than `DEBOUNCE`, so a plain debounce commits
    in the gap between the first press and the start of the auto-repeat —
    and a commit re-renders the list, swapping the button out from under a
    cursor that is still holding it down. This is §8.5's finding a third
    time, in the layer the mockup could not reach: it re-rendered locally
    and instantly, so it never had a round trip to land mid-press."""
    fire = re.search(r"function fire\(\) \{(.*?)\n  \}", page2, re.S).group(1)
    hold = int(re.search(r"var HOLD_DELAY = (\d+);", page2).group(1))
    debounce = int(re.search(r"var DEBOUNCE = (\d+);", page2).group(1))

    assert hold > debounce, "the reason the guard below has to exist"
    assert "holdTimer || repeatTimer" in fire


def test_the_struck_through_previous_value_always_has_its_line_reserved(page2, payload):
    """The row's other half of the same finding: reserve the line always,
    or the row grows mid-press and the control moves out from under the
    cursor."""
    for row in rows_of(page2):
        assert '<span class="was mono">' in row


# ---------------------------------------------------------------------------
# §8.3 — the row, and §8.5 — how a re-anchor shows itself
# ---------------------------------------------------------------------------


def test_clean_anchor_is_not_printed(page2, payload):
    """Eighteen rows repeating the word for "nothing to see" is chrome
    wearing the costume of information. The markdown report still prints
    every signal — it is an audit document with different duties."""
    assert "clean-anchor" not in page2

    for line, row in zip(payload["lines"], rows_of(page2)):
        if line["signals"] == ["clean-anchor"]:
            assert re.search(r'<td class="why">\s*</td>', row), f"line {line['i']}"


def test_a_flagged_row_spells_its_signal_out_in_plain_language(page2):
    """`lead-fallback` means nothing to a user who has not read the
    source. The gloss comes from `anchoring.SIGNAL_GLOSSES`, so the report,
    B16's page and this one say the same words."""
    from bombista.anchoring import SIGNAL_GLOSSES

    flagged = rows_of(page2)[FLAGGED_LINE]

    assert "lead-fallback" in flagged
    assert SIGNAL_GLOSSES["lead-fallback"] in flagged


def test_a_band_that_changed_shows_its_before_and_its_after(synthetic_session):
    """Not a silent repaint (§8.5). The old chip faded, an arrow, the new
    chip, a RE-ANCHORED badge and the previous value struck through."""
    late = 40.00  # far enough that the next line's gap goes outlier
    html = pages.render_rows(server.session_payload(synthetic_session, {FLAGGED_LINE: late}))
    row = rows_of(html)[FLAGGED_LINE + 1]

    assert 'class="chip band-HIGH"' in row and 'class="chip band-REVIEW"' in row
    assert "→" in row
    assert "RE-ANCHORED" in row
    assert "gap-outlier" in row


def test_a_hand_set_row_keeps_its_machine_value_struck_through(synthetic_session):
    html = pages.render_rows(
        server.session_payload(synthetic_session, {FLAGGED_LINE: TRUE_ONSET})
    )
    row = rows_of(html)[FLAGGED_LINE]

    assert "HAND-SET" in row
    assert f'<span class="was mono">{MACHINE_START:.2f}</span>' in row
    assert f">{TRUE_ONSET:.2f}</button>" in row


def test_the_rail_and_one_line_of_text_say_what_moved(synthetic_session):
    """The rail alone is undiscoverable; one line of text is the floor.
    Above the edit is untouched by construction — make that visible too."""
    html = pages.render_rows(
        server.session_payload(synthetic_session, {FLAGGED_LINE: TRUE_ONSET})
    )
    rows = rows_of(html)

    assert 'class="rail above"' in rows[FLAGGED_LINE]
    assert 'class="rail below"' in rows[FLAGGED_LINE + 1]
    assert "below here, re-derived against the audio — above, unchanged" in html


def test_the_divider_keys_off_the_earliest_edit_not_the_last_one(synthetic_session):
    """§8.9's open question, decided: `anchor_lines` takes a mapping and
    the routes already accept one, so the page allows more than one
    correction. Everything below the EARLIEST edit is what was re-derived,
    so that is what the rail and the divider mark."""
    html = pages.render_rows(
        server.session_payload(synthetic_session, {FLAGGED_LINE: TRUE_ONSET, 10: 89.50})
    )
    rows = rows_of(html)

    assert html.count("below here, re-derived against the audio") == 1
    assert 'class="rail above"' in rows[FLAGGED_LINE]
    assert 'class="rail below"' in rows[FLAGGED_LINE + 1]


def test_times_are_raw_audio_clock_seconds(page2, payload):
    """The clock the QA report, `--anchor` and the audio element all use.
    The cue-relative conversion happens on emit and is never shown — two
    clocks on one page is a real risk, and only one of them is visible."""
    assert f'>{payload["lines"][0]["start"]:.2f}</button>' in page2
    assert "raw audio-clock seconds" in visible_text(page2)


# ---------------------------------------------------------------------------
# §8.2 — the page, top to bottom, and nothing else
# ---------------------------------------------------------------------------


def test_provenance_is_open_and_quiet(page2):
    """Collapsed, its summary line was a run-on that "is not
    understandable". The answer was to make it recede, not to hide it: a
    block that recedes can stay open, and open it is legible at a glance."""
    block = re.search(r"<details class=\"prov\"[^>]*>", page2)

    assert block and " open" in block.group(0)
    assert "columns: 2" in pages.STYLESHEET


def test_the_sticky_bar_carries_the_player_and_the_three_band_counts(page2, payload):
    sticky = re.search(r'<div class="sticky">.*?</div>\s*</div>', page2, re.S).group(0)

    for band in ("HIGH", "REVIEW", "FAIL"):
        assert f'{band} {payload["bands"][band]}' in sticky
    assert "<audio" in sticky


def test_the_audio_comes_from_a_loopback_route_not_a_relative_src(page2):
    """§8.9: `serve` knows the path from step 1 and is a running process.
    B16's page needs a relative path because it is a loose file; this one
    does not, and a relative `src` would be a second answer to where the
    audio is."""
    assert re.search(r'<audio[^>]+src="/api/audio"', page2)


def test_the_page_has_exactly_one_line_of_instruction(page2):
    """Its only piece of help copy, and it sits where the hand already is
    — immediately above the table, not in the lede three elements away."""
    hints = re.findall(r'<p class="hint tablehint">(.*?)</p>', page2, re.S)

    assert len(hints) == 1
    instruction = " ".join(hints[0].split())
    assert instruction == (
        "Click a <b>START</b> time to adjust it. Press and hold to move fast "
        "— a whole missed word is about a second."
    )
    assert page2.index(hints[0]) < page2.index("<table")


@pytest.mark.parametrize(
    "cut",
    [
        "needs attention",
        "acknowledge",
        "Re-anchored 15 lines",
        "lines below were re-derived",
    ],
)
def test_none_of_the_five_things_that_were_cut_came_back(page2, cut):
    """Jorge, 2026-08-15: the list of lines IS the interface. A first pass
    put a lead-in panel, a "needs attention" card, an editor pane, a
    re-anchor banner and a JSON preview around it. All five are cut."""
    assert cut.lower() not in page2.lower()


def test_the_page_has_no_json_preview_and_no_acknowledgement_checkbox(page2):
    assert 'type="checkbox"' not in page2
    assert '<pre class="json"' not in page2


def test_confirm_is_the_only_button_below_the_table(page2):
    """§8.7: one button, no preview, no JSON, no acknowledgement. It must
    be pressed even when nothing was flagged, which is what converts
    review from skippable into structurally required."""
    markup = re.sub(r"<script\b.*?</script>", " ", page2, flags=re.S)
    below = markup[markup.index("</table>"):]

    assert re.findall(r"<button[^>]*>(.*?)</button>", below) == ["Confirm timeline →"]
    assert re.search(r'<button class="btn1"[^>]*id="confirm"', below)


def test_the_list_is_never_filtered_to_the_flagged_rows(page2, payload):
    """Filtering would hide the thing the page exists to show — what an
    edit did to the rows that were NOT flagged."""
    text = visible_text(page2).lower()

    assert len(rows_of(page2)) == len(payload["lines"])
    assert "show only" not in text and "filter" not in text


def test_the_lede_is_the_line_count_and_the_clock(page2, payload):
    lede = re.search(r'<p class="lede">(.*?)</p>', page2, re.S).group(1)

    assert lede.strip() == f"{len(payload['lines'])} lines · raw audio-clock seconds"


# ---------------------------------------------------------------------------
# §8.1 — the stack, and §10.3's skin, inherited rather than retrofitted
# ---------------------------------------------------------------------------


def test_page_2_inherits_the_shared_stylesheet(page2):
    assert pages.STYLESHEET in page2


def test_page_2_talks_to_its_own_process_and_loads_nothing(page2):
    """B16's zero-external-reference assertion is scoped to
    `write_html_review`'s output file and must not be extended here:
    `fetch` to the loopback routes is correct on a served page. What must
    not happen is a LOADED resource from off the machine."""
    assert "fetch(" in page2

    resources = re.findall(r'<(?:link|script|img|iframe)\b[^>]*(?:src|href)="([^"]+)"', page2)
    assert not resources
    assert not re.search(r"<script[^>]+src=", page2)


def test_page_2_keeps_the_ink_ground_and_does_not_reintroduce_the_blue(page2):
    assert "4b57c4" not in page2
    assert "border-radius: 0" in pages.STYLESHEET
    assert "prefers-color-scheme" not in page2


def test_the_native_transport_is_inverted_back_down(page2):
    """Chromium renders `<audio>` light regardless of `color-scheme`,
    which would put the brightest object on the page directly above the
    table (§10.3)."""
    assert "invert(.92) hue-rotate(180deg)" in pages.STYLESHEET
