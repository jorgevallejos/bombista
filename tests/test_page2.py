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

from bombista import pages, server, writers

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
    outside_provenance = re.sub(r'<p class="prov">.*?</p>', " ", page2, flags=re.S)

    assert "lead-in" not in flow_text(outside_provenance).lower()
    assert "lead-in" in visible_text(page2).lower(), "provenance still reports it"


# ---------------------------------------------------------------------------
# §8.4 — the start time is the control
# ---------------------------------------------------------------------------


@pytest.fixture
def popup_markup(page2):
    """The popup's markup, built in one place in the page's JS."""
    found = re.search(r"POPUP\s*=\s*'(.*?)';", page2, re.S)

    assert found, "the popup's markup is not built in one place"
    return found.group(1)


def js(page2: str, name: str) -> str:
    """One function's body, as the page ships it."""
    found = re.search(r"function " + name + r"\([^)]*\) \{(.*?)\n  \}", page2, re.S)

    assert found, f"no function {name} on the page"
    return found.group(1)


def test_the_popup_contains_one_stepper_and_no_second_control(popup_markup):
    """§8.4's stepper is untouched by §12.1: two step buttons and no
    more. What the popup grew is a FIELD — the number itself became
    typeable — not another control beside the stepper."""
    assert len(re.findall(r"<button", popup_markup)) == 2, "one stepper is two buttons and no more"
    assert re.findall(r'data-step="([^"]+)"', popup_markup) == ["-0.05", "0.05"]
    assert "class=\"cap\"" not in popup_markup, "no popup caption (§8.6)"


def test_the_stepper_step_is_finer_than_the_correction_loop(page2):
    """Invariant 2: the differentiator is a 0.07 s correction loop, so no
    control and no serialisation may round coarser than that."""
    step = float(re.search(r"var STEP = ([\d.]+);", page2).group(1))

    assert step <= 0.07
    assert step == 0.05


def test_the_bounds_are_the_neighbouring_lines(page2):
    """§8.4: the real allowed interval is the neighbouring lines,
    recomputed live — a fixed range is not it.

    Line 0's floor is the start of the audio because there is no line
    above it. That is arithmetic, not the special case §8.6 struck."""
    bounds = js(page2, "boundsFor")

    assert "all[i - 1]" in bounds and "all[i + 1]" in bounds
    assert "(i === 0) ? 0" in bounds


def test_one_clamp_holds_the_bound_for_every_way_of_setting_a_value(page2):
    """The stepper stops at `lo + 0.01` / `hi - 0.01`, exclusive of the
    neighbours. §12.1 adds a second way to set the value and NOT a second
    answer about what the allowed interval is: the typed commit clamps
    through the same function, so the two cannot drift apart."""
    clamp = js(page2, "clamp")

    assert "round2(b.lo + 0.01)" in clamp and "round2(b.hi - 0.01)" in clamp
    assert "boundsFor(i)" in clamp
    assert "clamp(" in js(page2, "nudge")
    assert "clamp(" in js(page2, "commitTyped")


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
# §12.1 — type to arrive, nudge to land
# ---------------------------------------------------------------------------
#
# The stepper was calibrated on a 1.22 s error: 24 presses, a held second
# crosses it. A phrase the ASR did not recognise leaves the line with
# nothing to anchor to, so where it lands has no relation to where it
# belongs and the error is unbounded by construction — 47 s of it in Luz y
# Sal, about 940 presses. Jorge, 2026-08-16: it is not the rare case.
#
# BOTH controls, because they answer different questions. The typed number
# ARRIVES — getting near the right place must not be a distance problem.
# The stepper LANDS — the exact onset is found by ear with the player, and
# by-ear work is nudge-and-listen, which a text field cannot do.


def test_the_number_itself_is_typeable(popup_markup):
    """The value span becomes a field. Everything else in the popup is
    what §8.4 already had."""
    assert re.search(r'<input[^>]+id="popval"', popup_markup), "the value is not a field"
    assert len(re.findall(r"<input", popup_markup)) == 1
    assert 'class="val"' in popup_markup


def test_a_typed_value_commits_on_enter_and_on_blur(page2):
    """Enter is the deliberate commit; blur is the one the hand makes on
    the way to the player or the next line, and a value typed and then
    abandoned would otherwise be silently lost."""
    assert re.search(r'ev\.key === "Enter"[^\n]*commitTyped\(\)', js(page2, "fieldKey"))
    assert re.search(r'addEventListener\("blur", commitTyped\)', page2)


def test_escape_still_closes_the_popup_without_committing(page2):
    """Unchanged from §8.4, and it has to survive the field: the way out
    of a value you did not mean to type is the way out that already
    existed."""
    escape = [line for line in js(page2, "fieldKey").splitlines() if "Escape" in line]

    assert len(escape) == 1
    assert "closePopup()" in escape[0] and "commitTyped" not in escape[0]


def test_the_arrows_do_caret_work_while_the_typed_value_is_uncommitted(page2):
    """A number being typed is text, and moving through it is what those
    keys do everywhere else. Nudging resumes once the value is committed —
    that is the by-ear pass, and it is the half a field cannot do."""
    field_key = js(page2, "fieldKey")

    assert "dirty()" in field_key, "the field does not know whether it holds uncommitted text"
    assert re.search(r"if \(dirty\(\)\) \{ return; \}", field_key)
    assert "nudge(" in field_key, "a committed field still nudges"
    assert 'ev.target.id === "popval"' in page2, "the field's keys never reach the page's handler"


def test_a_typed_value_takes_the_same_debounced_re_anchor_path_as_a_nudge(page2):
    """One re-anchor mechanism (§8.5), not two. A typed value is
    scheduled and debounced exactly as a press is, which is also what
    puts it behind the held-button guard below."""
    commit_typed = js(page2, "commitTyped")

    assert "schedule(" in commit_typed
    assert "fetch(" not in commit_typed, "a second commit path"
    assert len(re.findall(r'fetch\("/api/reanchor"', page2)) == 1


def test_a_typed_commit_cannot_fire_while_a_step_button_is_held(page2):
    """§11.11's finding a fourth time: the commit re-renders the row
    list, and a re-render mid-press moves the button out from under the
    cursor. The typed value goes through the SAME `schedule`/`fire` pair,
    so it is the same guard rather than a second one."""
    assert "holdTimer || repeatTimer" in js(page2, "fire")
    assert len(re.findall(r"holdTimer \|\| repeatTimer", page2)) == 2, (
        "the guard is `fire` and `placePopup`, and no third copy"
    )


def test_a_non_numeric_entry_keeps_the_last_good_value_and_says_nothing(page2):
    """No error state, no red field, no message. The value the field
    goes back to is the one that was already committed."""
    commit_typed = js(page2, "commitTyped")

    assert re.search(r"if \(!isFinite\(typed\)\) \{ show\(value\); return; \}", commit_typed)
    assert "error" not in commit_typed.lower()


def test_a_typed_value_is_rounded_to_two_decimals_and_never_snapped_to_the_step(page2):
    """0.05 is coarser than what the user typed, and invariant 2 forbids
    only what is coarser than 0.07 s. 0.01 granularity is correct and is
    what the stepper already lands on."""
    commit_typed = js(page2, "commitTyped")

    assert "round2(typed)" in commit_typed
    assert "STEP" not in commit_typed, "a typed value must not be snapped to the stepper's grid"


def test_the_popup_states_the_allowed_interval(page2, popup_markup):
    """§8.4 clamps silently because you FEEL a stepper stop. You do not
    feel a text field clamp: type 13, get 30.20, and nothing on screen
    explains it. §12.1 authorises the departure — the interval, dim and
    small, with no label, under the field."""
    bounds = js(page2, "showBounds")

    assert re.search(r'<div class="bounds" id="popbounds">', popup_markup)
    assert 'b.lo.toFixed(2) + " – " + b.hi.toFixed(2)' in bounds
    assert ".pop .bounds" in pages.STYLESHEET
    assert "var(--dimmer)" in re.search(r"\.pop \.bounds \{(.*?)\}", pages.STYLESHEET, re.S).group(1)


def test_the_stated_interval_is_the_bound_and_carries_no_label(page2):
    """One line. It says two numbers and a dash, because a label on it
    would be the second sentence this page has spent since the design
    closed rather than the first."""
    bounds = js(page2, "showBounds")
    stated = [line.strip() for line in bounds.splitlines() if ".textContent" in line]

    assert "boundsFor(open)" in bounds
    assert stated == ['el.textContent = b.lo.toFixed(2) + " – " + b.hi.toFixed(2);']


def test_the_bound_is_restated_after_the_rows_are_re_rendered(page2):
    """A re-anchor moves the neighbours, so it moves the interval. The
    popup stays open across the round trip and would otherwise state a
    bound that is no longer true."""
    commit = js(page2, "commit")

    assert "showBounds()" in commit


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


@pytest.fixture
def provenance():
    """A run's recorded provenance, as `<stem>-report.json` carries it."""
    return {
        "audio": "../../songs/audio/pimiento.m4a",
        "sha256": "ab" * 32,
        "durationSec": 173.376,
        "model": "faster-whisper:medium",
        "device": "cpu/int8",
        "lang": "es",
        "extractedAt": "2026-08-14T20:55:00+02:00",
        "toolVersion": "bombista 0.9.0",
    }


@pytest.fixture
def provenanced(synthetic_session, provenance):
    synthetic_session.provenance = provenance
    synthetic_session.song["title"] = "Pimiento"
    return pages.render_review(server.session_payload(synthetic_session))


def test_provenance_is_one_quiet_line(provenanced, payload):
    """§8.2, reduced 2026-08-16. Three passes to get here. Pass one hid a
    full table because it was loud; pass two opened it and made it recede,
    which fixed the volume but not the *relevance*. Jorge's is the third:
    "I would refrain from showing any of this info to the final user."
    What survives is the one question a correcting user does ask — am I
    looking at the right song and the right take?"""
    line = re.search(r'<p class="prov">(.*?)</p>', provenanced, re.S)

    assert line, "the provenance line is gone entirely"
    assert visible_text(line.group(1)).strip() == (
        "Pimiento · pimiento.m4a · faster-whisper medium (es) · measured lead-in 8.92 s"
    )
    assert "<details" not in provenanced, "no fold"
    assert "<table" not in re.sub(r"<table>.*?</table>", "", provenanced, flags=re.S), "no table"


def test_the_page_carries_none_of_what_only_an_audit_needs(provenanced, provenance):
    """Everything removed STAYS in `<stem>-report.json` — it is filed, not
    lost. The page is for judging lines by ear; the report is the audit
    artifact and may be as technical as it likes. §1's claim that the
    report's trustworthiness is the entire product is about the report."""
    text = visible_text(provenanced)

    assert provenance["sha256"] not in provenanced
    assert "sha256" not in text.lower()
    assert provenance["toolVersion"] not in provenanced
    assert "toolVersion" not in provenanced
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", provenanced), "an ISO timestamp"
    assert "173.37" not in provenanced, "the audio duration"
    assert "cpu/int8" not in provenanced


def test_the_provenance_line_names_the_file_and_never_its_path(provenanced):
    """The same rule page 1's picker follows (§9.3, decision 1):
    `songs/audio/pimiento.m4a` is the tool's business, `pimiento.m4a` is
    the user's."""
    assert "pimiento.m4a" in provenanced
    assert "../../songs/audio" not in provenanced


def test_the_report_json_still_carries_everything_the_page_dropped(
    synthetic_session, provenance
):
    """Filed, not lost."""
    synthetic_session.provenance = provenance
    report = writers.write_report_json(
        provenance=provenance,
        lines_hash=synthetic_session.lines_hash,
        lead_in_block={"durationSec": 8.92, "source": "measured", "confidence": "high",
                       "apply": False},
        anchors=server._anchor(synthetic_session, {})["anchors"],
        lines=synthetic_session.lines,
        line_entries=server._anchor(synthetic_session, {})["entries"],
        out_path=synthetic_session.staging_dir / "written-report.json",
    )

    assert report["source"]["sha256"] == provenance["sha256"]
    assert report["source"]["toolVersion"] == provenance["toolVersion"]
    assert report["source"]["extractedAt"] == provenance["extractedAt"]


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
