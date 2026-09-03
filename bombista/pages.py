"""
The HTML `serve` returns — pages 1, 1.5 and 3, plus the chrome every page
shares (B20 §9, §10.1, §10.3).

Built by string composition, the way `writers.write_html_review` already
builds B16's page: stdlib only, one page per step, inline CSS and JS,
vanilla JS, no framework, no build step, no npm, no webfont (§8.1).

**The skin is defined once, here** — `STYLESHEET` is the whole of §10.3 and
every page carries it verbatim. Page 2 inherits it rather than being
retrofitted with it; that is why this item was built before page 2.

**Contrast is a budget** (§10.3). The page has one job — put a musician's
eye on the one line that needs judging and their hand on the control that
fixes it. Structure is hairlines, colour is reserved, and the accent marks
one thing at a time. There are no radii, no shadows outside the popup, and
no transitions — removed, not eased.

**The vocabulary is §10.1's and it is not negotiable in user-facing
strings.** The steps are `1 Input · 2 Review · 3 Output`; the format is the
Song Performance JSON; the audio row is Media source. The words *align*,
*alignment* and *emit* name the mechanism, not the user's move, and do not
appear on a page. The one exemption is the masthead's tagline, *Forced-
alignment triage*, which is the product's own positioning line (§9.1) and
is not a step in the flow.
"""
from __future__ import annotations

import json
from html import escape as html_escape
from pathlib import Path

__all__ = [
    "STYLESHEET",
    "STEPS",
    "render_input",
    "render_processing",
    "render_review",
    "render_rows",
    "render_output",
]

VERSION = "v1.10.0"
"""The masthead's version string — the package version with a `v` in front.

It is a second copy of what `pyproject.toml` declares, and a second copy
drifts: nothing about editing one file makes anyone edit the other, so the
public page kept saying `v0.9.0` while the tool it belongs to had moved on.
The copy stays (the masthead is a string, and importing distribution
metadata to render a header would be its own kind of wrong), but it is
guarded — `tests/test_pages.py` fails when the two disagree, which turns a
silent drift into a red test at bump time."""

STEPS = (("1", "Input", "/input"), ("2", "Review", "/review"), ("3", "Output", "/output"))
"""§9.2 — one hard-bordered strip, three segments, every one of them a
link. Page 1.5 gets no segment of its own: it is a state of step 1, and a
fourth segment would say the flow has four steps when it has three."""

# The format's five Bombista-owned keys, in the order §10.2 fixes them.
TIMING_KEYS = ("linesHash", "timelineSignedOff", "timelineVersion", "leadIn", "timeline")

LANGUAGES = (("es", "Spanish"), ("en", "English"), ("nl", "Dutch"), ("fr", "French"))
"""The languages page 1 offers, and it is ONE list because two controls
read it: the dropdown that says what was sung, and the title-translation
fields the song block collects. A dropdown offering a language the
translation row does not is a language whose title can never be typed.

A song file may of course carry a language this list does not — the merge
in `server._merge_translations` leaves those alone rather than deleting
what was never on screen."""

FORMAT_DOC_URL = "https://changopepper.com/tramoya/song-performance-json"
"""§9.6's canonical home for the Song Performance JSON, live since
2026-08-16. It replaces the placeholder that pointed at this repo's
1,100-line `serve` spec — the reader who clicks *See an example* on page 1
is a musician looking for a sample file, not a maintainer reading a design
document.

**This URL is permanent and must never be renamed.** Every installed copy
of Bombista carries it as a literal and follows it forever: a released tool
cannot be asked to update its own links, so the copy running on someone
else's machine a year from now still points here. If the page ever moves,
that address redirects — it does not change. The site shipped before this
PR for exactly this reason, so the constant could be set once to something
already true.

It is an anchor the reader may click, never a resource the page loads —
nothing here reaches off the machine on its own."""

STYLESHEET = """\
/* bombista serve — brutalist, ink ground, quiet register (B20 §10.3).
   Contrast is a budget: it is spent on the one flagged line and the
   control the hand is going to. Navigation, provenance and structure all
   sit below that on purpose. Rules are hairlines, not slabs. Clay is the
   only accent and marks the active thing. One palette — no light mode and
   no colour-scheme media block; two palettes is two things to keep true.
   No webfont: a local-first tool does not phone a font CDN. */
:root {
  color-scheme: dark;
  --bg: #121211;
  --surface: #1a1a18;
  --surface-2: #232320;
  --paper: #e6dfd1;
  --dim: #8b8478;
  --dimmer: #635d54;
  --line: #2c2a26;
  --line-2: #423e37;
  --clay: #d98b7a;
  --clay-dim: #8f5a4e;
  /* The pinned step band's height, so page 2's player sits UNDER it rather
     than behind it — two sticky things at `top: 0` overlap, and the one
     that loses is the one that says where you are.

     **Derived from the band's own declarations, not measured off a
     screenshot**: `.stepband`'s padding (1.1 + .6), `.steps a`'s padding
     (.55 twice), its `line-height: 1` at .72rem, and the bar's 1px
     borders. Change any of those and this follows; a copied number would
     not. */
  --stepband: calc(1.1rem + .6rem + .55rem + .55rem + .72rem + 2px);
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  /* HIGH is muted on purpose — 18 of 19 rows are HIGH and none of them need you */
  --high: #4f7d63;
  --review: #e0a437;
  --fail: #ef7a70;
  --tint-review: #241d11;
  --tint-fail: #251715;
}
* { box-sizing: border-box; }
html { background: var(--bg); }
body {
  margin: 0; padding: 0 clamp(16px, 4vw, 40px) 6rem;
  background: var(--bg); color: var(--paper);
  font: 15px/1.55 var(--sans);
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 66rem; margin: 0 auto; }
h1 { font-size: clamp(1.35rem, 2.2vw, 1.7rem); font-weight: 800; text-transform: uppercase;
     letter-spacing: .01em; line-height: 1.1; margin: 1.6rem 0 .3rem; }
.lede { font: 400 .78rem/1.5 var(--mono); color: var(--dim); margin: 0 0 1.2rem; }
.hint { font: 400 .76rem/1.55 var(--mono); color: var(--dim); margin: .45rem 0 0; max-width: 46rem; }
.hint b { color: var(--paper); font-weight: 400; }
.hint code { color: #b0a898; }
code { font-family: var(--mono); font-size: .88em; }
.mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
a { color: var(--paper); text-decoration: none; border-bottom: 1px solid var(--clay-dim); }
a:hover { border-bottom-color: var(--clay); color: var(--clay); }
.pageoff { display: none; }
/* THE TRANSLATION STEP, AT THE FOOT OF PAGE 3 AND NOWHERE ELSE (Jorge,
   2026-09-03). It was Pregonero's line, drawn beside the frame — which meant
   every page of the flow, because Pregonero draws Bombista in a frame with no
   preload and cannot tell which page is showing. It appears once now, at the
   end, under the actions.

   RED, and that is a decision rather than a derivation. Cowork argued for
   dropping it — red is this suite's refusal colour, and this is a permanently
   true fact rather than a fault — and Jorge overruled: once the note appears in
   one place only, the risk it is written against is being MISSED, not being
   mistaken for an error. Not to be reopened from the colour taxonomy.

   The left rule and the inset are `.warnbox`'s device in the fail colour, so it
   reads as this page's furniture rather than as a fifth kind of message. */
.outside { border-left: 2px solid var(--fail); background: transparent;
           margin: 2.4rem 0 0; padding: .55rem 0 .55rem .9rem;
           font: 400 .8rem/1.5 var(--sans); color: var(--fail); max-width: 46rem; }
.outside b { font-weight: 700; }

/* ---------- masthead (§9.1) ---------- */
.mast { display: flex; align-items: flex-end; justify-content: space-between; gap: 1.5rem;
        flex-wrap: wrap; padding: 1.4rem 0 .9rem; border-bottom: 1px solid var(--line-2); }
.mast .wordmark { display: block; font-weight: 800; text-transform: uppercase;
                  letter-spacing: -.01em; line-height: 1; font-size: 1.35rem; }
.mast .tagline { display: block; margin-top: .35rem;
                 font: 400 .7rem/1 var(--mono); text-transform: uppercase;
                 letter-spacing: .14em; color: var(--dimmer); }
.mast .by { text-align: right; font: 400 .68rem/1.7 var(--mono); text-transform: uppercase;
            letter-spacing: .11em; color: var(--dimmer); }
.mast .by b { color: var(--dim); font-weight: 400; }
.mast .by .tramoya { color: var(--clay-dim); }

/* ---------- step bar (§9.2) — navigation, not an announcement ----------
   **Pinned, and it is the only thing that is** (2026-09-02). On a long page
   the bar scrolled out of view, so *where am I* depended on scroll position
   and the way back looked like a reset.

   The BAND is what sticks, not the bar: `.steps` is `width: max-content`,
   so pinning it directly would leave the page scrolling through the gap
   beside it. The band is full width and opaque, and the masthead scrolls
   away behind it — deliberately, so standalone ends with the same single
   fixed band the embedded case has rather than two.

   Nothing else is pinned. `Save to the catalogue` sits after the JSON box
   so the file is read before it is written, and a permanently pressable
   save would quietly restore the order that was rejected. */
.stepband { position: sticky; top: 0; z-index: 40; background: var(--bg);
            padding: 1.1rem 0 .6rem; }
.steps { display: flex; align-items: stretch;
         border: 1px solid var(--line-2); width: max-content; max-width: 100%; }
.steps a { display: flex; align-items: center; gap: .5rem; text-decoration: none;
           color: var(--dim); border-bottom: none;
           font: 400 .72rem/1 var(--mono); text-transform: uppercase; letter-spacing: .12em;
           padding: .55rem .85rem; border-right: 1px solid var(--line-2); }
.steps a:last-child { border-right: none; }
.steps a:hover { color: var(--paper); background: var(--surface); border-bottom: none; }
.steps a.on { color: var(--clay); background: var(--surface-2); }
.steps a.on:hover { color: var(--clay); background: var(--surface-2); }
.steps a .n { font-variant-numeric: tabular-nums; color: var(--dimmer); }
/* a step that did not happen: present, so the flow still reads as three,
   but not a link and not silent about why (2026-09-02) */
.steps .skip { display: flex; align-items: center; gap: .5rem;
               font: 400 .72rem/1 var(--mono); text-transform: uppercase;
               letter-spacing: .12em; color: var(--dimmer);
               padding: .55rem .85rem; border-right: 1px solid var(--line-2);
               text-decoration: line-through; text-decoration-color: var(--line-2); }
.steps .skip .n { font-variant-numeric: tabular-nums; }
.steps .skip .why { text-decoration: none; color: var(--clay-dim); letter-spacing: .1em; }
.steps a.on .n { color: var(--clay); }

/* ---------- buttons ---------- */
button { font: 400 .76rem/1 var(--mono); text-transform: uppercase; letter-spacing: .1em;
         cursor: pointer; border: 1px solid var(--line-2); border-radius: 0;
         background: transparent; color: var(--dim); padding: .5rem .75rem;
         box-shadow: none; transition: none; }
button:hover:not(:disabled) { color: var(--paper); border-color: var(--paper); }
button:active:not(:disabled) { background: var(--surface-2); }
button:disabled { opacity: .35; cursor: default; }
button:focus-visible { outline: 2px solid var(--clay); outline-offset: 2px; }
.btn1 { background: var(--clay); border-color: var(--clay); color: #1a100d;
        font-weight: 700; font-size: .82rem; padding: .62rem 1rem; }
.btn1:hover:not(:disabled) { background: #e79b8a; border-color: #e79b8a; color: #1a100d; }
.go { margin: 1.5rem 0 0; }

/* ---------- page 1 — the form (§9.3) ---------- */
.form { margin: 1.3rem 0 0; border-top: 1px solid var(--line-2); }
#songbranch .form { margin-top: .9rem; }
.frow { padding: .85rem 0; border-bottom: 1px solid var(--line); }
.frow .flabel { display: block; font: 400 .7rem/1 var(--mono); text-transform: uppercase;
                letter-spacing: .14em; margin: 0 0 .5rem; color: var(--dim); }
.frow .ctl { display: flex; align-items: center; gap: .65rem; flex-wrap: wrap; }
.fname { font: 400 .86rem/1 var(--mono); color: var(--paper);
         border-bottom: 1px solid var(--line-2); padding: .3rem .1rem; }
.aside { font: 400 .72rem/1 var(--mono); color: var(--dimmer); }
select { font: 400 .84rem/1 var(--mono); padding: .45rem .5rem; border: 1px solid var(--line-2);
         border-radius: 0; background: var(--surface); color: var(--paper); }
select:hover { border-color: var(--dim); }
select:focus-visible { outline: 2px solid var(--clay); outline-offset: 2px; }
select option:disabled { color: var(--dimmer); }
input[type="text"], input[type="number"] {
         font: 400 .86rem/1 var(--mono); padding: .42rem .5rem;
         border: 1px solid var(--line-2); border-radius: 0;
         background: var(--surface); color: var(--paper); }
/* the song block's own heading (step 6) — it is a second half of the page,
   not a fifth row, and it says so once rather than in every caption */
.secthead { font: 800 .78rem/1 var(--sans); text-transform: uppercase;
            letter-spacing: .13em; color: var(--dim); margin: 2.2rem 0 .35rem; }
.sectlede { margin: 0; }
.warnbox { border-left: 2px solid var(--review); background: transparent;
           padding: .1rem 0 .1rem .8rem; margin: 1rem 0 0;
           font: 400 .78rem/1.55 var(--mono); color: var(--dim); max-width: 46rem; }
.warnbox b { display: block; font-weight: 400; text-transform: uppercase;
             letter-spacing: .11em; margin-bottom: .3rem; color: var(--review); font-size: .72rem; }

/* ---------- the file picker — a plain dialog, deliberately (§9.6, 2026-09-02) ----------
   The rest of this page is brutalist on purpose. A file dialog is the one
   place a person expects their system's own furniture, and the brutalist
   treatment was too far for it: hard clay border, uppercase buttons, rows
   that lit up in an accent. So this one object steps out of the skin —
   soft border, ordinary rows, a highlighted selection, Cancel and Choose
   where every dialog on the machine puts them. It is still served by this
   process and still hands back a real path, because a web page cannot. */
.picker { position: fixed; inset: 0; z-index: 80; background: rgba(0,0,0,.55);
          display: flex; align-items: center; justify-content: center; padding: 2rem; }
.picker .inner { background: var(--surface-2); border: 1px solid var(--line-2);
                 border-radius: 6px; box-shadow: 0 16px 48px rgba(0,0,0,.55);
                 width: min(40rem, 100%); height: min(28rem, 80vh);
                 display: flex; flex-direction: column; overflow: hidden; }
.picker .head { padding: .7rem .9rem; border-bottom: 1px solid var(--line-2);
                font: 400 .78rem/1.4 var(--sans); color: var(--dim);
                overflow-wrap: anywhere; flex: none; }
.picker ul { list-style: none; margin: 0; padding: .25rem 0; overflow: auto; flex: 1 1 auto;
             background: var(--surface); }
.picker li button { width: 100%; text-align: left; border: none; background: transparent;
                    text-transform: none; letter-spacing: 0; border-radius: 0;
                    font: 400 .84rem/1.4 var(--sans); color: var(--paper);
                    padding: .34rem .9rem; display: flex; gap: .5rem; }
.picker li button:hover { background: rgba(255,255,255,.05); color: var(--paper);
                          border-color: transparent; }
.picker li button .kind { color: var(--dimmer); width: .9rem; flex: none; }
.picker li.dir button { color: var(--paper); }
.picker li.on button { background: #4a4a44; color: var(--paper); }
.picker li.on button .kind { color: var(--paper); }
/* The foot is NOT a flex row, and that is deliberate (2026-09-02). Flex laid
   the two buttons out at 53.5px and 29.5px, and every align-items value left
   them on different lines — one obeyed the container and one did not. Two
   dialog buttons are the same size as each other or the dialog is not one,
   so this is the dullest thing that cannot go wrong: a block, text-align
   right, two inline-blocks of a pinned size. */
.picker .foot { padding: .7rem .9rem; border-top: 1px solid var(--line-2); flex: none;
                display: block; text-align: right; background: var(--surface-2);
                font-size: 0; }
.picker .foot button { display: inline-block; vertical-align: top; margin-left: .55rem;
                       text-transform: none; letter-spacing: 0; border-radius: 4px;
                       font: 400 .82rem/2rem var(--sans); padding: 0 1.1rem;
                       min-width: 6.5rem; height: 2rem; color: var(--paper); }
/* `pickgo`, not `go`: `.go` is page 1's own wrapper class and carries
   `margin: 1.5rem 0 0`. Naming the confirm button `go` inherited that
   24px top margin and pushed it below Cancel — the "two buttons at
   different heights" of the 2026-09-02 walk. Every class inside this
   dialog is prefixed for that reason. */
.picker .foot button.pickgo { background: #4a4a44; border-color: #565650; color: var(--paper); }
.picker .foot button.pickgo:hover:not(:disabled) { background: #565650; border-color: #6a6a62;
                                                   color: var(--paper); }

/* ---------- the one consent popup (2026-09-02) ----------
   The third and last kind of popup the suite allows: a commitment whose
   consequence is not visible on the screen, asked AT the commitment rather
   than while the page is still being filled in. Interrupting someone
   mid-form to say what they have not done yet is nagging; asking once as
   they commit is consent. It borrows the file dialog's calm shape because
   both are asking, not announcing. */
.ask { position: fixed; inset: 0; z-index: 90; background: rgba(0,0,0,.55);
       display: flex; align-items: center; justify-content: center; padding: 2rem; }
.ask.pageoff { display: none; }
.ask .inner { background: var(--surface-2); border: 1px solid var(--line-2);
              border-radius: 6px; box-shadow: 0 16px 48px rgba(0,0,0,.55);
              width: min(28rem, 100%); padding: 1.1rem 1.2rem 1rem; }
.ask .head { font: 700 .95rem/1.3 var(--sans); color: var(--paper); margin-bottom: .5rem; }
.ask p { margin: 0 0 .7rem; font: 400 .84rem/1.5 var(--sans); color: var(--dim); }
.ask p b { color: var(--paper); font-weight: 600; }
.ask .foot { text-align: right; font-size: 0; margin-top: 1rem; }
.ask .foot button { display: inline-block; vertical-align: top; margin-left: .55rem;
                    text-transform: none; letter-spacing: 0; border-radius: 4px;
                    font: 400 .82rem/2rem var(--sans); padding: 0 1.1rem;
                    min-width: 6.5rem; height: 2rem; color: var(--paper); }
/* ONE CONSENT-DIALOG SHAPE ACROSS THE SUITE (Jorge, 2026-09-03): left-aligned
   title and text, TWO OUTLINED BUTTONS, the leaving or destructive action on
   the right. Pregonero's `Leave without saving?` asks the same kind of
   question across a seam the person cannot see, and the two were in different
   visual languages — that one centred, this one carrying a filled `Continue`.
   This dialog was nearly there; the fill is what moved. It cannot be a shared
   component across the two repos, so the shape is written down in
   `tramoya-integration/journey-setup.md` and built twice.
   `askgo` keeps NO rules at all: the base `button` already draws an outline and
   hovers it to `--paper`, so both buttons are one control drawn twice and the
   only difference between them is which side they are on. The class stays as
   the hook the markup and the script name. */

/* ---------- page 1.5 — the run (§9.4) ---------- */
.phase { display: flex; align-items: center; gap: .8rem; padding: .8rem 0;
         border-bottom: 1px solid var(--line);
         font: 400 .8rem/1 var(--mono); text-transform: uppercase; letter-spacing: .1em;
         color: var(--dim); }
.phase:first-child { border-top: 1px solid var(--line-2); }
.phase.run { color: var(--paper); }
.phase .dot { width: .55rem; height: .55rem; border: 1px solid var(--line-2);
              background: transparent; flex: none; }
/* it blinks on steps(2) — it does not fade. No easing anywhere (§10.3). */
.phase.run .dot { background: var(--clay); border-color: var(--clay);
                  animation: blink .8s steps(2, jump-none) infinite; }
.phase.ok .dot { background: var(--high); border-color: var(--high); }
@keyframes blink { 0%, 49% { opacity: 1 } 50%, 100% { opacity: .2 } }
.phase .t { margin-left: auto; color: var(--dimmer); font-variant-numeric: tabular-nums; }

/* ---------- page 3 — output (§9.5) ---------- */
.jsonhead { display: flex; align-items: center; justify-content: space-between; gap: 1rem;
            flex-wrap: wrap; margin: 1.2rem 0 .45rem; }
.jsonhead .fn { font: 400 .78rem/1 var(--mono); color: var(--dim); letter-spacing: .05em; }
pre.json { background: var(--surface); border: 1px solid var(--line-2);
           padding: .85rem .95rem; font: 400 .73rem/1.6 var(--mono); overflow: auto;
           max-height: 30rem; margin: 0; white-space: pre; color: #cdc6b9; }
.dlrow { display: flex; gap: 1.6rem; flex-wrap: wrap; align-items: flex-start; margin: .9rem 0 0; }
.dl { display: flex; flex-direction: column; gap: .45rem; max-width: 16rem; }
.dl .hint { margin: 0; }
.signoff { display: inline-block; margin: 1.5rem 0 0; border-left: 2px solid var(--high);
           padding: .1rem 0 .1rem .7rem; color: var(--dim);
           font: 400 .74rem/1.5 var(--mono); letter-spacing: .04em; }
.chip { display: inline-block; font: 400 .68rem/1 var(--mono); text-transform: uppercase;
        letter-spacing: .09em; padding: .26rem .4rem; border: 1px solid currentColor;
        white-space: nowrap; }
.band-HIGH { color: var(--high); }
.band-REVIEW { color: var(--review); }
.band-FAIL { color: var(--fail); }

/* ---------- page 2 — provenance: one quiet line, one hairline (§8.2) ---------- */
p.prov { margin: 1.2rem 0 0; padding: 0 0 .55rem;
         border-bottom: 1px solid var(--line);
         font: 400 .72rem/1.7 var(--mono); color: var(--dimmer);
         overflow-wrap: anywhere; }

/* ---------- page 2 — the sticky player, and nothing else is pinned ---------- */
.sticky { position: sticky; top: var(--stepband); z-index: 20; background: var(--bg);
          padding: .6rem 0 .5rem; border-bottom: 1px solid var(--line-2); }
/* the native transport refuses the palette; invert it back down to the ground
   rather than leave a light slab as the brightest object on the page */
.sticky audio { width: 100%; height: 34px; filter: invert(.92) hue-rotate(180deg);
                opacity: .72; }
.sticky audio:hover { opacity: 1; }
.barrow { display: flex; align-items: center; gap: .45rem; flex-wrap: wrap; margin-top: .5rem; }
.playhead { font: 400 .72rem/1 var(--mono); color: var(--dimmer); }
.playhead b { color: var(--dim); font-weight: 400; }

/* ---------- page 2 — the list of lines IS the interface ---------- */
.tablehint { margin: 1.3rem 0 .4rem; max-width: none; color: var(--dim); }
.tablehint b { color: var(--paper); }
table { border-collapse: collapse; width: 100%; font-size: .85rem; margin-top: 0;
        border-top: 1px solid var(--line-2); }
th { font: 400 .64rem/1 var(--mono); text-transform: uppercase; letter-spacing: .13em;
     color: var(--dimmer); border-bottom: 1px solid var(--line-2); padding: .5rem;
     text-align: left; }
td { padding: .5rem; border-bottom: 1px solid var(--line); vertical-align: top; }
td.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
tr.band-REVIEW td { background: var(--tint-review); }
tr.band-FAIL td { background: var(--tint-fail); }
tr.editing td { background: var(--surface-2); }
tr.current td { box-shadow: inset 3px 0 0 var(--dim); }
tr.band-REVIEW .chip.band-REVIEW, tr.band-FAIL .chip.band-FAIL { font-weight: 700; }
td.rail { width: 1rem; padding-left: .1rem; padding-right: .1rem; }
.rail i { display: block; width: 2px; height: 100%; min-height: 1.5rem; }
.rail.above i { background: var(--line-2); }
.rail.below i { background: repeating-linear-gradient(to bottom,
                var(--clay-dim) 0 3px, transparent 3px 8px); }
td.idx { white-space: nowrap; font: 400 .68rem/1.35 var(--mono);
         letter-spacing: .04em; color: var(--dimmer); }
td.text { white-space: pre-wrap; min-width: 16rem; color: var(--paper); }
tr.band-HIGH td.text { color: #cdc6b9; }
.play { padding: .24rem .38rem; font-size: .66rem; color: var(--dimmer); }
.why { font: 400 .73rem/1.45 var(--mono); color: var(--dim); }
.why .tok { color: var(--paper); }
tr.band-HIGH .why .tok { color: var(--dimmer); }
tr.divider td { background: var(--bg); border-bottom: none;
                border-top: 1px dashed var(--clay-dim); padding: .45rem .5rem .1rem;
                font: 400 .66rem/1.4 var(--mono); text-transform: uppercase;
                letter-spacing: .11em; color: var(--clay-dim); }

/* the start time IS the control (§8.4) */
.tbtn { font: 400 .9rem/1 var(--mono); text-transform: none; letter-spacing: 0;
        font-variant-numeric: tabular-nums; background: transparent; color: var(--paper);
        border: 1px solid transparent; border-bottom-color: var(--line-2);
        padding: .14rem .3rem; }
.tbtn:hover { background: var(--surface-2); border-color: var(--line-2); color: var(--paper); }
.tbtn:active { background: var(--surface-2); }
.tbtn.open { background: var(--clay); color: #1a100d; border-color: var(--clay); }
/* the line is RESERVED whether or not there is a previous value in it: without
   it the row grows mid-press and the button moves out from under the cursor */
.was { display: block; font: 400 .68rem/1.2 var(--mono); min-height: 1.2em;
       color: var(--dimmer); text-decoration: line-through; padding-right: .3rem; }
.was:empty { text-decoration: none; }
.arrow { color: var(--dim); }
.badge { display: inline-block; font: 400 .6rem/1 var(--mono); letter-spacing: .1em;
         padding: .24rem .32rem; margin-left: .3rem; border: 1px solid var(--clay-dim);
         color: var(--clay); }
.badge.changed { border-color: var(--line-2); color: var(--dim); }
.badge.handset { border-color: var(--clay-dim); color: var(--clay); }

/* the popup is the loudest object on the page, and that is correct: it appears
   only when the hand is already there, and it is the only place a value changes */
.pop { position: absolute; z-index: 60; background: var(--surface-2);
       border: 1px solid var(--clay); box-shadow: 0 8px 26px rgba(0,0,0,.65);
       padding: .45rem; }
.pop .stepper { display: flex; align-items: center; gap: .4rem; }
.pop input.val { font: 400 1.4rem/1 var(--mono); font-variant-numeric: tabular-nums;
            width: 5.6rem; text-align: right; color: var(--paper);
            background: var(--surface); border: 1px solid var(--line-2);
            border-radius: 0; padding: .16rem .3rem; }
.pop input.val:focus { outline: none; border-color: var(--clay); }
.pop .unit { font: 400 .76rem/1 var(--mono); color: var(--dim); margin-right: .2rem; }
.pop button.step { min-width: 3.2rem; color: var(--paper); border-color: var(--line-2); }
.pop button.step:hover { border-color: var(--clay); color: var(--clay); }
/* §12.1's one departure from §8.4's "no bounds text", and the reason for it:
   you FEEL a stepper stop, and you do not feel a text field clamp. Type 13,
   get 30.20, and nothing on screen would explain it. Two numbers, no label,
   dim — the smallest sentence that closes that gap. */
.pop .bounds { margin: .32rem .1rem 0; text-align: right; color: var(--dimmer);
               font: 400 .68rem/1 var(--mono); font-variant-numeric: tabular-nums; }
.confirm { margin: 1.7rem 0 0; }

/* ---------- page 3 — save (step 6) ----------
   It is not a download and does not sit in the download row: those hand over
   bytes and choose no path, this one writes a file. The path is printed
   before the press and again after it, because *the catalogue* is a name and
   a file is a fact. */
.save { margin: 1.5rem 0 1.9rem; padding-bottom: 1.6rem;
        border-bottom: 1px solid var(--line-2);
        display: flex; flex-direction: column; gap: .5rem; align-items: flex-start; }
.dlhead { margin: 0 0 .2rem; }
.save .hint { margin: 0; }
.save .path { font: 400 .76rem/1.5 var(--mono); color: var(--paper);
              overflow-wrap: anywhere; }
.save .sstate { font: 400 .74rem/1.5 var(--mono); color: var(--dimmer); }
.save .sstate.bad { color: var(--fail); }
.save .sstate.ok { color: var(--high); }

/* ---------- page 1 — tempo, typed in (round A; moved here at step 6) ----------
   Quiet register on purpose: this is a fact about the song, so it sits with
   the rest of the song's general information rather than competing with the
   pickers for the contrast budget. Four fields, because a control that
   cannot ask for a whole block should not ask for part of one. */
.tempo { padding: .85rem 0; border-bottom: 1px solid var(--line); }
.ttrow { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }
.ttrow label { display: inline-flex; align-items: center; gap: .35rem;
               font: 400 .7rem/1 var(--mono); color: var(--dimmer); }
.frow input[type="text"] { width: 100%; max-width: 34rem; }
.ttrow input[type="text"] { width: 10rem; }
.tempo .trow { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }
.tempo .tlabel { font: 400 .7rem/1 var(--mono); text-transform: uppercase;
                 letter-spacing: .14em; color: var(--dim); margin-right: .25rem; }
.tempo label { display: inline-flex; align-items: center; gap: .35rem;
               font: 400 .7rem/1 var(--mono); color: var(--dimmer); }
.tempo input[type="number"] { width: 5.4rem; }
.tempo .tstate { font: 400 .72rem/1.5 var(--mono); color: var(--dimmer);
                 flex: 1 1 14rem; }
.tempo .tapstate { font: 400 .72rem/1 var(--mono); color: var(--dim);
                   font-variant-numeric: tabular-nums; min-width: 8rem; }
.tapbar { display: flex; align-items: center; gap: .8rem; flex-wrap: wrap; margin: .7rem 0 0; }
/* `.pageoff` is declared earlier, so a later `display: flex` beats it at equal
   specificity — the player showed itself over a song with no recording. Every
   component that sets its own display has to say this. */
.tapbar.pageoff { display: none; }
/* the native transport refuses the palette; invert it down to the ground the
   way page 2's player is, rather than leaving a light slab on a dark page */
.tapbar audio { height: 32px; max-width: 22rem; flex: 1 1 16rem;
                filter: invert(.92) hue-rotate(180deg); opacity: .72; }
.tapbar audio:hover { opacity: 1; }
.tempo .tstate.bad { color: var(--fail); }
.tempo .tstate.ok { color: var(--high); }
"""

_PICKER_JS = """\
/* §9.6, resolved: a loopback listing rather than <input type="file">.
   The server needs a real path — to read the lyrics, to hash the audio for
   provenance, and to write the re-run command into the report. A browser
   File object has no path, so accepting an upload would mean copying a
   50 MB m4a into a staging directory to recover something the file already
   had two directories away, and every path the tool then recorded would
   name the copy rather than the take. The page shows the file NAME alone
   (§9.3, decision 1) — the path stays the tool's business.

   **It looks like a file dialog and not like the rest of this page**
   (walked 2026-09-02). Everything else here is brutalist by decision; a
   file dialog is the one place a person expects their system's own
   furniture, and the brutalist treatment read as a different application.
   Path at the top, a plain list, Cancel and Choose at the bottom. One
   implementation serves both contexts, because there is only one thing
   that works standalone. */
function browse(startPath, onPick) {
  var box = document.createElement("div");
  box.className = "picker";
  box.innerHTML =
    '<div class="inner">' +
      '<div class="head" id="pick-path"></div>' +
      '<ul id="pick-list"></ul>' +
      '<div class="foot">' +
        '<button type="button" data-close="1">Cancel</button>' +
        '<button type="button" class="pickgo" id="pick-choose" disabled>Choose</button>' +
      '</div>' +
    "</div>";
  document.body.appendChild(box);

  var chosen = null;
  var list = box.querySelector("#pick-list");
  var choose = box.querySelector("#pick-choose");

  function close() { box.remove(); }

  /* A directory row opens; a file row selects and `Choose` confirms.
     One click either way, and the button that commits is the one at the
     bottom right, where every dialog on this machine puts it. */
  function select(li, path) {
    var on = list.querySelector("li.on");
    if (on) { on.className = on.className.replace(" on", ""); }
    li.className += " on";
    chosen = path;
    choose.disabled = false;
  }

  function take() {
    if (!chosen) { return; }
    var path = chosen;
    close();
    onPick(path);
  }

  function load(path) {
    fetch("/api/browse?path=" + encodeURIComponent(path))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { close(); return; }
        chosen = null;
        choose.disabled = true;
        box.querySelector("#pick-path").textContent = data.path;
        list.innerHTML =
          '<li class="dir"><button type="button" data-path="' + esc(data.parent) +
          '" data-dir="1"><span class="kind">&#9656;</span>..</button></li>' +
          data.entries.map(function (entry) {
            return '<li class="' + (entry.dir ? "dir" : "file") + '">' +
                   '<button type="button" data-path="' + esc(entry.path) + '" data-dir="' +
                   (entry.dir ? "1" : "") + '"><span class="kind">' +
                   (entry.dir ? "&#9656;" : "") + "</span>" +
                   esc(entry.name) + "</button></li>";
          }).join("");
        list.scrollTop = 0;
      });
  }

  box.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest("button");
    if (!btn) { if (ev.target === box) { close(); } return; }
    if (btn === choose) { take(); return; }
    if (btn.getAttribute("data-close")) { close(); return; }
    var path = btn.getAttribute("data-path");
    if (btn.getAttribute("data-dir")) { load(path); return; }
    select(btn.parentNode, path);
  });

  box.addEventListener("dblclick", function (ev) {
    var btn = ev.target.closest && ev.target.closest("li.file button");
    if (btn) { take(); }
  });

  load(startPath);
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, function (ch) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
  });
}

function baseName(path) {
  var parts = String(path).split("/");
  return parts[parts.length - 1] || path;
}
"""

_INPUT_JS = """\
(function () {
  var state = { lyrics: null, media: null, declaredLanguages: [], branch: null };
  var langSel = document.getElementById("lang");
  var songbranch = document.getElementById("songbranch");

  /* The four tempo fields and the general information travel with
     `Process song →`, like every other answer on this page. There is no
     Set button and no pre-flight check here: the SERVER decides whether a
     block is whole, because a second opinion about what a valid tempo is
     is exactly what §11.5's rule exists to prevent. A blank field is left
     out, so the refusal names it. */
  function val(id) { return document.getElementById(id).value.trim(); }

  /* Tap tempo. **The only method that yields the felt pulse** rather than
     a number read off something that measured something else — which is
     the 1.5x error the caption alone did not stop (walked 2026-09-02):
     a 6/8 song counted in two is 66.67 where the DAW says 100.

     Intervals, not a total: the bpm is the mean gap between consecutive
     taps, so it settles as you keep going instead of being thrown by when
     you started. A gap longer than RESET means you stopped and started
     again — a fresh count rather than one enormous interval averaged in.
     Nothing is derived from the audio; the machine times the person. */
  var TAP_RESET_MS = 3000;
  var taps = [];

  function tapSay(text) { document.getElementById("t-tapstate").textContent = text; }

  function tap() {
    var now = Date.now();
    if (taps.length && now - taps[taps.length - 1] > TAP_RESET_MS) { taps = []; }
    taps.push(now);
    if (taps.length < 2) { tapSay("keep tapping\u2026"); return; }
    var span = taps[taps.length - 1] - taps[0];
    /* **Settles on halves, and only what tapping produces** (2026-09-02).
       A hand cannot resolve a hundredth of a beat per minute, so a long
       decimal here is noise wearing the costume of precision. A HALF is
       the finest thing tapping can honestly claim.

       A TYPED value is left alone: `66.67` is a real felt pulse, exact
       from the source that produced the audio, and rounding it to `67` is
       drift a long song will show. Only this function rounds. */
    var bpm = Math.round((60000 * (taps.length - 1)) / span * 2) / 2;
    document.getElementById("t-bpm").value = String(bpm);
    tapSay(taps.length + " taps \u00b7 " + bpm);
    checkTempo();
  }

  document.getElementById("t-tap").addEventListener("click", tap);

  /* **Said at the field, while it can still be fixed.** The run used to
     refuse a half-typed block, which withheld ninety seconds of
     transcription over a value nothing in transcription or anchoring
     reads. Whole-or-nothing is unchanged; it is the FILE that answers for
     it now, and this is the sentence that stops anyone getting there.
     Silent when the block is whole, and silent when it is empty — no
     tempo is a real answer. */
  var tstate = document.getElementById("t-state");

  function checkTempo() {
    var bpm = val("t-bpm"), signature = val("t-signature");
    if (bpm === "" && signature === "") { tstate.textContent = ""; tstate.className = "tstate"; return; }
    if (bpm !== "" && signature !== "") { tstate.textContent = ""; tstate.className = "tstate"; return; }
    tstate.className = "tstate bad";
    tstate.textContent = bpm === ""
      ? "Needs a pulse too \u2014 a tempo is written whole or not at all."
      : "Needs a time signature too \u2014 a tempo is written whole or not at all.";
  }

  ["t-bpm", "t-signature"].forEach(function (id) {
    document.getElementById(id).addEventListener("input", checkTempo);
    document.getElementById(id).addEventListener("change", checkTempo);
  });

  /* A pulse and a signature, split into the four keys the format fixes at
     the boundary and nowhere else. **Neither given means no tempo at all**,
     which is a real state — so the bars field, which always has a value,
     never makes a block on its own. One given and not the other is a
     partial block, and it goes up to be refused by name rather than being
     pre-judged here: a second opinion about a valid tempo is exactly what
     the whole-or-nothing rule exists to prevent. */
  function tempoBlock() {
    var bpm = val("t-bpm"), signature = val("t-signature");
    if (bpm === "" && signature === "") { return {}; }
    var block = { countInBars: Number(val("t-countinbars") || "0") };
    if (bpm !== "") { block.bpm = Number(bpm); }
    if (signature !== "") {
      var halves = signature.split("/");
      block.numerator = Number(halves[0]);
      block.denominator = Number(halves[1]);
    }
    return block;
  }

  function information() {
    return { title: val("title"), artist: val("artist"), notes: val("notes") };
  }

  /* Prefilled from the file, never invented here: an SP JSON already
     carries all of this, and a screen that showed it empty would invite a
     human to retype a value that was already right. */
  function prefill(data) {
    /* **The take the file was aligned against** (2026-09-02). The lyrics
       field prefilled and this one did not, so nothing told you whether
       the app had forgotten or was waiting. It stays changeable:
       re-aligning against a different take is the normal reason to edit a
       song, not an edge case. */
    if (data.media && !state.media) {
      state.media = data.media.path;
      document.getElementById("media-name").textContent = data.media.name;
      document.getElementById("t-audio").src =
        "/api/audio?path=" + encodeURIComponent(data.media.path);
      document.getElementById("tapbar").className = "tapbar";
      document.getElementById("clear-media").className = "";
    }

    var info = data.info || {};
    document.getElementById("title").value = info.title || "";
    document.getElementById("artist").value = info.artist || "";
    document.getElementById("notes").value = info.notes || "";

    var tempo = data.tempo || {};
    document.getElementById("t-bpm").value =
      tempo.bpm === undefined || tempo.bpm === null ? "" : String(tempo.bpm);
    document.getElementById("t-countinbars").value =
      tempo.countInBars === undefined || tempo.countInBars === null
        ? "0" : String(tempo.countInBars);
    /* A signature the dropdown cannot say is ADDED to it rather than
       dropped — the file keeps its own 5/4, and the control does not
       quietly edit what it was handed. */
    var select = document.getElementById("t-signature");
    var signature = tempo.numerator && tempo.denominator
      ? tempo.numerator + "/" + tempo.denominator : "";
    if (signature && !select.querySelector('option[value="' + signature + '"]')) {
      var option = document.createElement("option");
      option.value = signature;
      option.textContent = signature;
      select.appendChild(option);
    }
    select.value = signature;
    checkTempo();
  }

  document.getElementById("pick-lyrics").addEventListener("click", function () {
    browse(BROWSE_FROM, function (path) {
      state.lyrics = path;
      document.getElementById("lyrics-name").textContent = baseName(path);
      describe(path);
    });
  });

  document.getElementById("pick-media").addEventListener("click", function () {
    browse(BROWSE_FROM, function (path) {
      state.media = path;
      document.getElementById("media-name").textContent = baseName(path);
      /* The take, playable at step 1, because tapping a tempo along with a
         recording you cannot hear is tapping along with nothing. */
      document.getElementById("t-audio").src =
        "/api/audio?path=" + encodeURIComponent(path);
      document.getElementById("tapbar").className = "tapbar";
      document.getElementById("clear-media").className = "";
      ready();
    });
  });

  /* The language dropdown is constrained by the file: a language the file
     does not carry has no lines to anchor. Undeclared options render
     disabled. The caption does not explain the rule (§9.3, decision 5) —
     and the server refuses it too, so this is a courtesy, not the guard. */
  function describe(path, keepAnswers) {
    fetch("/api/lyrics?path=" + encodeURIComponent(path))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { return; }
        state.declaredLanguages = data.declaredLanguages || [];
        state.branch = data.branch;
        for (var i = 0; i < langSel.options.length; i++) {
          var opt = langSel.options[i];
          opt.disabled = state.declaredLanguages.length > 0 &&
                         state.declaredLanguages.indexOf(opt.value) === -1;
        }
        if (langSel.selectedOptions[0] && langSel.selectedOptions[0].disabled) {
          langSel.value = state.declaredLanguages[0];
        }
        songbranch.className = "";
        document.getElementById("slug").textContent = data.slug;
        /* Coming back to this page is not choosing a file again. The
           language options still have to be constrained by what the file
           declares, and the stripped-line count still has to be shown —
           but what the person typed is theirs and the FILE does not get
           to overwrite it. */
        if (!keepAnswers) { prefill(data); }
        stripped(data);
        ready();
      });
  }

  /* Shown BEFORE the run, from the reader's own strippedLines — a silent
     line-count change surfaces much later as a promote refusal (§3). */
  function stripped(data) {
    var el = document.getElementById("stripped");
    var list = data.strippedLines || [];
    if (!list.length) { el.className = "hint pageoff"; el.textContent = ""; return; }
    var blank = 0, marked = [];
    list.forEach(function (s) {
      if (s.reason === "blank") { blank++; } else { marked.push(s.text); }
    });
    var parts = [];
    if (blank) { parts.push(blank + " blank"); }
    if (marked.length) {
      parts.push(marked.length + " section marker" + (marked.length > 1 ? "s" : "") +
                 " (" + marked.join(", ") + ")");
    }
    el.className = "hint";
    el.innerHTML = "<b>" + list.length + " line" + (list.length > 1 ? "s" : "") +
      " will be removed before processing</b> — " + esc(parts.join(", ")) + ". " +
      data.lineCount + " lyric lines remain.";
  }

  /* **The lyrics alone are enough** (2026-09-02). A song with words and no
     recording is performed by advancing the lines by hand; there is
     nothing to align, so there is nothing to require. */
  function ready() {
    document.getElementById("process").disabled = !state.lyrics;
  }

  function clearMedia() {
    state.media = null;
    document.getElementById("media-name").textContent = "\u2014";
    document.getElementById("clear-media").className = "pageoff";
    document.getElementById("t-audio").removeAttribute("src");
    document.getElementById("tapbar").className = "tapbar pageoff";
    ready();
  }

  document.getElementById("clear-media").addEventListener("click", clearMedia);

  /* Asked ONCE, at the commitment, and never while the page is being
     filled in. The consequence of going on without a recording is not
     visible on this screen, which is exactly what earns a popup here —
     and nagging about it from the moment the page loads is what does
     not. */
  var ask = document.getElementById("ask-manual");

  document.getElementById("ask-no").addEventListener("click", function () {
    ask.className = "ask pageoff";
  });
  document.getElementById("ask-yes").addEventListener("click", function () {
    ask.className = "ask pageoff";
    start();
  });

  document.getElementById("process").addEventListener("click", function () {
    if (!state.media) { ask.className = "ask"; return; }
    start();
  });

  function start() {
    var body = {
      lyrics: state.lyrics,
      media: state.media || "",
      lang: langSel.value,
      model: document.getElementById("model").value,
      info: information(),
      tempo: tempoBlock()
    };
    fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json().then(function (d) { return [r.status, d]; }); })
      .then(function (pair) {
        if (pair[0] >= 400) { refuse(pair[1].error); return; }
        location.href = "/processing";
      });
  }

  /* A refusal is rendered in the page's own warning component rather than
     a browser alert — the skin has one, and a modal from another design
     system is the loudest thing on a page whose budget is spent elsewhere. */
  function refuse(message) {
    var box = document.getElementById("refused");
    box.className = "warnbox";
    document.getElementById("refused-why").textContent = message;
  }

  /* A song handed to `serve` prefills this page through exactly the path a
     pick takes — same route, same prefill, same readiness check. A second
     branch that filled the fields directly would be a second answer to
     *what does this file say*, and the two would drift. It is what makes
     an edit an edit rather than a second new song. */
  /* **The step bar is navigation, not a reset** (2026-09-02). Everything
     the session already holds comes back, including a half-typed tempo —
     which is the whole point, because the refusal that sends people here
     is about exactly that, and a backstop that cannot be acted on is a
     wall. */
  function restore(a) {
    state.lyrics = a.lyrics.path;
    document.getElementById("lyrics-name").textContent = a.lyrics.name;
    if (a.media) {
      state.media = a.media.path;
      document.getElementById("media-name").textContent = a.media.name;
      document.getElementById("t-audio").src =
        "/api/audio?path=" + encodeURIComponent(a.media.path);
      document.getElementById("tapbar").className = "tapbar";
      document.getElementById("clear-media").className = "";
    }
    langSel.value = a.lang;
    document.getElementById("model").value = a.model;

    songbranch.className = "";
    var info = a.info || {};
    document.getElementById("title").value = info.title || "";
    document.getElementById("artist").value = info.artist || "";
    document.getElementById("notes").value = info.notes || "";

    var tempo = a.tempo || a.tempoIncomplete || {};
    document.getElementById("t-bpm").value =
      tempo.bpm === undefined || tempo.bpm === null ? "" : String(tempo.bpm);
    document.getElementById("t-countinbars").value =
      tempo.countInBars === undefined || tempo.countInBars === null
        ? "0" : String(tempo.countInBars);
    var select = document.getElementById("t-signature");
    var signature = tempo.numerator && tempo.denominator
      ? tempo.numerator + "/" + tempo.denominator : "";
    if (signature && !select.querySelector('option[value="' + signature + '"]')) {
      var option = document.createElement("option");
      option.value = signature;
      option.textContent = signature;
      select.appendChild(option);
    }
    select.value = signature;
    checkTempo();

    /* **What running again costs, said rather than discovered.** A new run
       re-anchors from the machine's timings, so the lines corrected on
       step 2 go. With no recording there is nothing to redo and nothing
       to warn about — going back is free, which is the case that made
       this defect matter. */
    if (a.handSetLines > 0) {
      var note = document.getElementById("rerun-cost");
      note.className = "hint";
      note.innerHTML = "<b>Running again starts the timing over.</b> The " +
        a.handSetLines + " line" + (a.handSetLines === 1 ? "" : "s") +
        " you set by hand on step 2 would go back to what the machine heard. " +
        "Everything on this page is kept either way.";
    }

    describe(a.lyrics.path, true);
  }

  if (ANSWERS) {
    restore(ANSWERS);
  } else if (SONG) {
    state.lyrics = SONG;
    document.getElementById("lyrics-name").textContent = baseName(SONG);
    describe(SONG);
  }

  ready();
})();
"""

_PROCESSING_JS = """\
(function () {
  var rows = { transcribe: document.getElementById("ph-transcribe"),
               anchor: document.getElementById("ph-anchor") };

  function paint(data) {
    (data.phases || []).forEach(function (phase) {
      var row = rows[phase.name];
      if (!row) { return; }
      row.className = "phase" + (phase.state === "running" ? " run" :
                     (phase.state === "done" || phase.state === "cached") ? " ok" : "");
      var t = row.querySelector(".t");
      if (phase.state === "cached") { t.textContent = "cached"; }
      else if (phase.elapsedSec === null || phase.elapsedSec === undefined) { t.textContent = "—"; }
      else { t.textContent = phase.elapsedSec.toFixed(1) + " s"; }
    });
    if (data.state === "done") { location.href = "/review"; }
    if (data.state === "cancelled") { location.href = "/input"; }
    if (data.state === "failed") {
      document.getElementById("failed").className = "warnbox";
      document.getElementById("failed-why").textContent = data.error || "";
    }
  }

  function poll() {
    fetch("/api/run").then(function (r) { return r.json(); }).then(function (data) {
      paint(data);
      if (data.state === "transcribing" || data.state === "anchoring") {
        setTimeout(poll, 250);
      }
    });
  }

  document.getElementById("cancel").addEventListener("click", function () {
    fetch("/api/run", { method: "DELETE" }).then(function () { location.href = "/input"; });
  });

  poll();
})();
"""

_OUTPUT_JS = """\
(function () {
  /* B19's surviving clause: a JSON download must be pressed even when
     nothing was flagged, and the report does not count — it certifies
     nothing and taking it is not a decision. Nothing here disables after
     the press: wanting the timing block as well as the whole file is
     normal, and the sign-off is recorded once, not spent. */
  function signedOff(stamp) {
    if (!stamp) { return; }
    var el = document.getElementById("signoff");
    el.className = "signoff";
    el.textContent = "Signed off " + stamp + " · your inputs untouched";
    var json = document.getElementById("json");
    json.textContent = json.textContent.replace(
      /"timelineSignedOff": null/, '"timelineSignedOff": "' + stamp + '"');
  }

  function download(kind, signs) {
    location.href = "/api/download?kind=" + kind;
    if (!signs) { return; }
    setTimeout(function () {
      fetch("/api/session").then(function (r) { return r.json(); }).then(function (data) {
        signedOff(data.timelineSignedOff);
      });
    }, 300);
  }

  document.getElementById("dl-song").addEventListener("click", function () {
    download("song", true);
  });
  /* Absent on a song with no recording — there is no timeline to paste
     and no report to write. `on` rather than a bare getElementById, so
     this page keeps the rule that a script never reaches for an id its
     markup does not carry. */
  function on(id, run) {
    var el = document.getElementById(id);
    if (el) { el.addEventListener("click", run); }
  }

  on("dl-timeline", function () { download("timeline", true); });
  on("dl-report", function () { download("report", false); });

  /* Save (step 6). It writes a file rather than handing over bytes, so
     unlike the three downloads it can fail — and it reports the path it
     actually wrote rather than the one the page promised, because those
     are two different claims. Signing off is the server's, on the same
     footing as a download: writing a file is the programmatic equivalent
     of pressing one. */
  var savestate = document.getElementById("savestate");

  function ssay(text, kind) {
    savestate.textContent = text;
    savestate.className = "sstate" + (kind ? " " + kind : "");
  }

  document.getElementById("save").addEventListener("click", function () {
    ssay("Saving\u2026", "");
    fetch("/api/emit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}"
    }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, data: data }; });
    }).then(function (res) {
      if (!res.ok) { ssay(res.data.error || "Refused.", "bad"); return; }
      document.getElementById("savepath").textContent = res.data.path;
      ssay("Saved.", "ok");
      signedOff(res.data.timelineSignedOff);
    });
  });
})();
"""


def _masthead() -> str:
    """§9.1. Without it, page 1's *the format Tramoya promotes* has no
    brand on the page to attach to. It is the only decoration in the
    interface and it earns its place by making the rest of the page's
    vocabulary legible.

    **It can be turned off** (2026-09-02). Inside a window somebody else
    already titled, a product introducing itself by name, tagline and
    *a Tramoya tool by Chango Pepper* is the tool talking about itself to
    a person who did not choose it.

    **And the version goes with it** (Jorge, 2026-09-03, revising the same
    day's earlier ruling). It used to survive `--no-header` as a dim line
    of its own under the step bar; walked inside Pregonero it read as a
    build number on somebody else's screen. **The rule it was protecting
    is unchanged — the version has to survive SOMEWHERE**, because two
    builds calling themselves the same number is the trap that cost this
    project a day. It survives here: standalone Bombista draws this header
    on every page, and `bombista --version` answers regardless. What went
    is the one place it was never for anyone."""
    return (
        '<header class="mast">'
        "<div>"
        '<span class="wordmark">Bombista</span>'
        '<span class="tagline">Forced-alignment triage</span>'
        "</div>"
        '<div class="by">'
        f"<div>{VERSION}</div>"
        '<div>A <span class="tramoya">Tramoya</span> tool</div>'
        "<div>by <b>Chango Pepper</b></div>"
        "</div>"
        "</header>"
    )


def _step_bar(current: str, *, skipped: str = "") -> str:
    """Every step clickable, including backwards: going back to step 1 is
    how you re-run with a different model, and going back to step 2 from
    step 3 is how you fix something you noticed while reading the file.
    Nothing is destroyed by moving between them.

    **It is wrapped in a band that sticks to the top of the page** — see
    `.stepband`. The bar itself is `width: max-content`, so pinning it
    directly would leave the page scrolling through the gap beside it.

    *skipped* names a step that did not happen — step 2 on a song with no
    recording, where there is no timeline to review. **It is rendered as a
    span rather than a link**, struck through and labelled: a bar that
    still offered `2 Review` would say a review is available, and one that
    silently marked step 3 current would say a review happened. Neither is
    true, and the difference matters on the one screen that reports what
    the file contains.
    """
    segments = []
    for number, label, href in STEPS:
        if number == skipped:
            segments.append(
                f'<span class="skip"><span class="n">{number}</span> {label}'
                f'<span class="why">skipped</span></span>'
            )
            continue
        on = ' class="on"' if number == current else ""
        segments.append(f'<a href="{href}"{on}><span class="n">{number}</span> {label}</a>')
    return (
        '<div class="stepband"><nav class="steps">' + "".join(segments) + "</nav></div>"
    )


def _shell(
    *,
    title: str,
    current: str,
    body: str,
    script: str = "",
    header: bool = True,
    skipped: str = "",
) -> str:
    """One page, inline CSS and JS, nothing fetched from anywhere but
    this process (§8.1).

    *header* is the product header — name, tagline, version, *a Tramoya
    tool by Chango Pepper*. **Turning it off replaces it with nothing**
    (2026-09-03): the version went with the branding, and survives in
    standalone Bombista's own header and in `bombista --version`. See
    `_masthead` for why that still honours *the version has to survive
    somewhere*. **Bombista learns nothing about who is calling**: this is a
    boolean about what to draw, and every caller may pass it."""
    scripts = f"<script>\n{script}</script>" if script else ""
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html_escape(title)} — Bombista</title>\n"
        f"<style>\n{STYLESHEET}</style>\n"
        "</head>\n"
        "<body>\n"
        '<div class="wrap">\n'
        + (_masthead() if header else "")
        + _step_bar(current, skipped=skipped)
        + body
        + "\n</div>\n"
        + scripts
        + "\n</body>\n</html>\n"
    )


_REVIEW_JS = """\
(function () {
  "use strict";

  var STEP = 0.05;         /* invariant 2 — the correction loop is 0.07 s, so
                              neither this nor any serialisation may be coarser */
  var DEBOUNCE = 250;      /* re-anchor once the stepping stops, not per press */
  var HOLD_DELAY = 380;    /* press and hold before the auto-repeat starts */
  var HOLD_RATE = 45;      /* and how fast it then repeats */

  /* §8.4's stepper, with §12.1's field where its number was. *Type to
     arrive, nudge to land*: a phrase the ASR did not recognise leaves a
     line with nothing to anchor to, so the error is unbounded by
     construction — 47 s in Luz y Sal, about 940 presses — and getting
     near the right place must not be a distance problem. Finding the
     exact onset is still done by ear with the player, which is
     nudge-and-listen and is the half a text field cannot do.

     So the popup GROWS A FIELD; it does not grow a second control. Two
     step buttons and no more, no delta readout, no explanation, and no
     caption, because line 0 is not special (§8.6).

     The one line under it is the allowed interval, and it is a
     deliberate departure from §8.4's "no bounds text" that §12.1
     authorises: a stepper stop is felt, a text field clamp is not. */
  var POPUP = '<div class="stepper">' +
              '<button class="step" data-step="-0.05">− 0.05</button>' +
              '<input class="val" id="popval" type="text" inputmode="decimal" ' +
              'autocomplete="off" spellcheck="false">' +
              '<span class="unit">s</span>' +
              '<button class="step" data-step="0.05">+ 0.05</button>' +
              '</div>' +
              '<div class="bounds" id="popbounds"></div>';

  var tbody = document.getElementById("tbody");
  var audio = document.getElementById("audio");
  var overrides = {};
  var pop = null, open = null, value = null;
  var holdTimer = null, repeatTimer = null, settle = null, pending = null;

  function round2(x) { return Math.round(x * 100) / 100; }
  function rows() { return tbody.querySelectorAll("tr[data-line]"); }
  function startOf(row) { return parseFloat(row.getAttribute("data-start")); }

  /* The bounds are the neighbouring lines, recomputed live off the rows —
     that is the real allowed interval, and a fixed range is not. Line 0's
     floor is the start of the audio because it has no line above it; that
     is arithmetic, not a special case. */
  function boundsFor(i) {
    var all = rows();
    var lo = (i === 0) ? 0 : startOf(all[i - 1]);
    var hi = (i + 1 < all.length)
      ? startOf(all[i + 1])
      : parseFloat(all[i].getAttribute("data-end"));
    return { lo: lo, hi: hi };
  }

  function openPopup(i) {
    closePopup();
    open = i;
    value = startOf(rows()[i]);
    pop = document.createElement("div");
    pop.className = "pop";
    pop.innerHTML = POPUP;
    document.body.appendChild(pop);
    /* The field is not focused on open: Space belongs to the transport,
       and judging is the player's job (§8.4). Clicking into it selects
       what is there, because arriving somewhere else means replacing the
       number rather than editing it. */
    var el = field();
    el.addEventListener("focus", function () { el.select(); });
    el.addEventListener("blur", commitTyped);
    show(value);
    mark();
    placePopup();
    /* Focused on open (Jorge, 2026-09-03). It was deliberately NOT focused
       — Space belongs to the transport, and judging is the player's job
       (§8.4) — and walking it cost two presses for one act: one on the
       number to open the popup, a second on the field to type in it. A
       control that opens somewhere other than where you have to press
       next is a control that opens twice.
       Selected rather than caret-placed, because arriving here means
       replacing the number, not editing it — the `focus` listener above.
       **Space is not lost to this**: `fieldKey` sends it to the transport,
       so the one reason the field was left unfocused still holds. */
    el.focus();
  }

  function field() { return document.getElementById("popval"); }

  function show(v) {
    var el = field();
    if (el) { el.value = v.toFixed(2); }
    showBounds();
  }

  /* The interval, restated whenever it can have changed — a re-anchor
     moves the neighbours, and a bound that is no longer true is worse
     than the silence §8.4 asked for. Two numbers and a dash: a label on
     this line would be the second sentence page 2 has spent since the
     design closed rather than the first. */
  function showBounds() {
    var el = document.getElementById("popbounds");
    if (!el || open === null) { return; }
    var b = boundsFor(open);
    el.textContent = b.lo.toFixed(2) + " – " + b.hi.toFixed(2);
  }

  /* Never while a button is held: the row would move out from under the
     cursor mid-press, which is the same finding as the reserved line. */
  function placePopup() {
    if (!pop || holdTimer || repeatTimer) { return; }
    var anchor = tbody.querySelector('.tbtn[data-open="' + open + '"]');
    if (!anchor) { closePopup(); return; }
    var box = anchor.getBoundingClientRect();
    pop.style.top = (window.scrollY + box.bottom + 6) + "px";
    pop.style.left = Math.max(8, window.scrollX + box.right - pop.offsetWidth) + "px";
  }

  /* The state goes first and the node second: removing a focused field
     can raise a blur, and a blur that arrives after Escape must find
     nothing to commit. Escape closes WITHOUT committing (§8.4). */
  function closePopup() {
    var node = pop;
    pop = null;
    open = null;
    value = null;
    if (node) { node.parentNode.removeChild(node); }
    mark();
  }

  function mark() {
    var all = rows();
    for (var i = 0; i < all.length; i++) {
      all[i].classList.toggle("editing", i === open);
      var btn = all[i].querySelector(".tbtn");
      if (btn) { btn.classList.toggle("open", i === open); }
    }
  }

  /* ONE clamp, for every way of setting a value. §12.1 adds a second way
     in and not a second answer about what the allowed interval is: the
     edges are the neighbours, exclusive, and both paths come through
     here. */
  function clamp(i, v) {
    var b = boundsFor(i);
    if (v <= b.lo) { return round2(b.lo + 0.01); }
    if (v >= b.hi) { return round2(b.hi - 0.01); }
    return v;
  }

  function nudge(d) {
    if (open === null) { return; }
    var i = open, v = clamp(i, round2(value + d));
    value = v;
    show(v);
    schedule(i, v);
  }

  /* The typed value, corrected in this order (§12.1):
       - a non-numeric entry keeps the last good value, and says nothing.
         There is no error state on this page and this is not the place
         to open one;
       - round to 2 decimals, and NEVER snap to a multiple of STEP. 0.05
         is coarser than what the user typed and invariant 2 forbids only
         what is coarser than 0.07 s — 0.01 is what the stepper itself
         lands on;
       - clamp with the same exclusive edges a nudge uses.
     Then it is SCHEDULED, exactly as a press is. One re-anchor mechanism
     (§8.5), which is also what puts a typed commit behind the held-button
     guard rather than needing a second one. */
  function commitTyped() {
    if (open === null) { return; }
    var el = field();
    if (!el) { return; }
    var text = el.value.trim();
    var typed = /^-?[0-9]*\\.?[0-9]+$/.test(text) ? parseFloat(text) : NaN;
    if (!isFinite(typed)) { show(value); return; }
    var v = clamp(open, round2(typed));
    value = v;
    show(v);
    schedule(open, v);
  }

  function dirty() {
    var el = field();
    return !!el && value !== null && el.value.trim() !== value.toFixed(2);
  }

  /* 250 ms after the last press — and never DURING one.
     HOLD_DELAY is 380 ms and DEBOUNCE is 250 ms, so a plain debounce fires
     in the gap between the first press and the start of the auto-repeat.
     Committing there swaps the whole list out from under a cursor that is
     still holding the button down: the same failure as an unreserved line
     or a repositioned popup (§8.5), one layer further in, and one the
     mockup could not meet because it re-rendered locally and instantly.
     So the timer waits out the hold rather than racing it. */
  function schedule(i, v) {
    pending = { i: i, v: v };
    clearTimeout(settle);
    settle = setTimeout(fire, DEBOUNCE);
  }

  function fire() {
    if (holdTimer || repeatTimer) { settle = setTimeout(fire, DEBOUNCE); return; }
    if (pending) { commit(pending.i, pending.v); pending = null; }
  }

  /* The server re-anchors and the server renders the rows. There is no
     arithmetic on this page: a correction re-derives every line below it
     against the word stream, and a blanket delta would displace exactly the
     rows the report exists to certify (§3, invariant 5). */
  function commit(i, v) {
    overrides[String(i)] = v;
    fetch("/api/reanchor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ overrides: overrides })
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { return; }
        counts(data.bands);
        return fetch("/review/rows").then(function (r) { return r.text(); })
          .then(function (html) {
            tbody.innerHTML = html; mark(); placePopup(); showBounds();
          });
      });
  }

  /* The whole-song announcement, and there is no banner: 18/1/0 -> 19/0/0 in
     the sticky bar is the confirmation that the recompute ran and helped. */
  function counts(bands) {
    ["HIGH", "REVIEW", "FAIL"].forEach(function (band) {
      document.getElementById("c" + band).textContent = band + " " + bands[band];
    });
  }

  function startHold(d) {
    nudge(d);
    holdTimer = setTimeout(function () {
      repeatTimer = setInterval(function () { nudge(d); }, HOLD_RATE);
    }, HOLD_DELAY);
  }

  function endHold() {
    clearTimeout(holdTimer);
    clearInterval(repeatTimer);
    holdTimer = repeatTimer = null;
  }

  document.addEventListener("mousedown", function (ev) {
    var step = ev.target.closest && ev.target.closest("[data-step]");
    if (step) { ev.preventDefault(); startHold(parseFloat(step.getAttribute("data-step"))); }
  });
  document.addEventListener("mouseup", endHold);
  window.addEventListener("blur", endHold);

  document.addEventListener("click", function (ev) {
    var el = ev.target, hit;
    if (!el || !el.closest) { return; }
    if (el.closest("[data-step]")) { return; }
    if ((hit = el.closest(".play"))) {
      audio.currentTime = parseFloat(hit.getAttribute("data-start"));
      audio.play();
      return;
    }
    if ((hit = el.closest("[data-open]"))) {
      var i = parseInt(hit.getAttribute("data-open"), 10);
      if (open === i) { closePopup(); } else { openPopup(i); }
      return;
    }
    if (!el.closest(".pop") && open !== null) { closePopup(); }
  });

  /* The field's own keys. ArrowLeft/ArrowRight belong to the CARET while
     there is uncommitted text — a number being typed is text, and moving
     through it is what those keys do everywhere else. Once the value is
     committed the field shows the committed number again and the arrows
     go back to nudging, which is the by-ear pass and the reason the
     stepper stays (§12.1). */
  function fieldKey(ev) {
    if (ev.key === "Escape") { closePopup(); return; }
    if (ev.key === "Enter") { ev.preventDefault(); commitTyped(); return; }
    /* SPACE STAYS THE TRANSPORT'S, even with the caret in here (§8.4).
       The field is focused on open now, and the general handler below
       hands every key to a focused INPUT — so without this the one thing
       the field was left unfocused to protect would have gone silently.
       Nothing is lost: this is a decimal field, and a space in it is not
       a value. */
    if (ev.key === " ") {
      ev.preventDefault();
      if (audio.paused) { audio.play(); } else { audio.pause(); }
      return;
    }
    if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") { return; }
    if (dirty()) { return; }
    ev.preventDefault();
    nudge(ev.key === "ArrowLeft" ? -STEP : STEP);
  }

  document.addEventListener("keydown", function (ev) {
    if (ev.target && ev.target.id === "popval") { fieldKey(ev); return; }
    if (ev.target && /INPUT|TEXTAREA|SELECT/.test(ev.target.tagName)) { return; }
    if (ev.key === " ") {
      ev.preventDefault();
      if (audio.paused) { audio.play(); } else { audio.pause(); }
      return;
    }
    if (open === null) { return; }
    if (ev.key === "Escape") { closePopup(); return; }
    if (ev.key === "ArrowLeft") { ev.preventDefault(); nudge(-STEP); return; }
    if (ev.key === "ArrowRight") { ev.preventDefault(); nudge(STEP); return; }
  });

  window.addEventListener("scroll", placePopup);
  window.addEventListener("resize", placePopup);

  /* Judging is the player's job (§8.4). The row under the playhead is
     marked so the ear and the eye are on the same line. */
  audio.addEventListener("timeupdate", function () {
    var t = audio.currentTime;
    /* A tenth here too: this is a readout, not a value anything keeps. */
    document.getElementById("ph").textContent = t.toFixed(1);
    var all = rows();
    for (var i = 0; i < all.length; i++) {
      var s = startOf(all[i]), e = parseFloat(all[i].getAttribute("data-end"));
      all[i].classList.toggle("current", t >= s && t < e);
    }
  });

  /* The tempo control moved to page 1 in v1.2.0. Its wiring stayed here
     and reached for `t-set`, which this page no longer renders, so the
     whole script threw on load and `Confirm timeline` — the very next
     statement, and the last one in the file — was never given a listener.
     Everything above had already been registered, so the page looked
     entirely alive while the one control that leaves it did nothing.
     tests/test_pages.py pins the class of bug rather than this instance:
     no page's script may reach for an id its own markup does not carry. */
  document.getElementById("confirm").addEventListener("click", function () {
    location.href = "/output";
  });
})();
"""


def _f1(value: float | None) -> str:
    """A time as the LIST shows it: one decimal, and the value is not
    touched.

    **Round the display, never the value** (Jorge, 2026-09-02). Hundredths
    on a cue nobody can place to a tenth is precision a person cannot act
    on, and it made the column harder to read for nothing. What must not
    be rounded is the stored number: it comes from alignment, and coarsening
    it to half-seconds would put a cue a quarter of a second out on lines
    three seconds apart.

    So this is a formatter and nothing else. The row still carries the full
    value in `data-start`, the popup edits it at hundredths, and what
    reaches the file is what the aligner measured.
    """
    return "" if value is None else f"{value:.1f}"


def _why_cell(line: dict) -> str:
    """§8.3. `clean-anchor` is not printed: eighteen rows repeating the word
    for "nothing to see" is chrome wearing the costume of information, and
    the dim HIGH chip already says it. So the only text in this column
    belongs to the line that needs you.

    The markdown report still prints every signal — it is an audit document
    and has different duties. The asymmetry is deliberate.

    A signal that is printed is spelled out underneath in plain language,
    from `anchoring.SIGNAL_GLOSSES`, so this page, the report and B16's page
    say the same words."""
    shown = [signal for signal in line["signals"] if signal != "clean-anchor"]
    if not shown:
        return ""
    cell = ", ".join(f'<span class="tok">{html_escape(s)}</span>' for s in shown)
    gloss = (line.get("signalGlosses") or {}).get(shown[0])
    if line["band"] != "HIGH" and gloss:
        cell += "<br>" + html_escape(gloss)
    return cell


def _band_cell(line: dict) -> str:
    """§8.5: a band that changed shows its BEFORE and its after, on the row
    — old chip faded, arrow, new chip, `RE-ANCHORED`. Not a silent repaint,
    because what an edit did to the rows that were *not* flagged is the most
    useful thing on the page."""
    band, was = line["band"], line.get("machineBand")
    if was and was != band:
        cell = (
            f'<span class="chip band-{was}" style="opacity:.4">{was}</span> '
            '<span class="arrow">→</span> '
            f'<span class="chip band-{band}">{band}</span>'
        )
        if not line["handSet"]:
            cell += '<span class="badge changed">RE-ANCHORED</span>'
    else:
        cell = f'<span class="chip band-{band}">{band}</span>'
    if line["handSet"]:
        cell += '<span class="badge handset">HAND-SET</span>'
    return cell


def _row(line: dict, *, pivot: int | None, machine_duration: float | None) -> str:
    """One lyric line, and every fact about it that §8.3 asks for.

    **The index never appears alone.** §6 makes that a UI requirement: the
    CLI never said whether `LINE` was 0- or 1-indexed and no user-facing
    string in the repo does either, so a row shows `line 3` *and* the line's
    own words, and ▶ confirms it by ear. A page that shows a bare index has
    failed in exactly the way the CLI failed — it just fails in a browser.

    **Times are raw audio-clock seconds**, the clock the QA report, `--anchor`
    and the player all use. The cue-relative conversion happens on emit and
    is never shown: two clocks on one page is a real risk, and only one of
    them is ever visible.
    """
    i, start, end = line["i"], line["start"], line["end"]
    machine = line.get("machineStart")
    was_start = None if machine is None or round(machine, 2) == start else round(machine, 2)
    duration = round(end - start, 2)
    was_duration = (
        None
        if machine_duration is None or round(machine_duration, 2) == duration
        else round(machine_duration, 2)
    )

    rail = "rail" if pivot is None else ("rail above" if i <= pivot else "rail below")
    row = (
        f'<tr class="band-{line["band"]}" data-line="{i}" '
        f'data-start="{start:.2f}" data-end="{end:.2f}">'
        f'<td class="{rail}"><i></i></td>'
        f'<td><button class="play" data-start="{start:.2f}">▶</button></td>'
        f'<td class="idx">line {i}</td>'
        f'<td class="text">{html_escape(line["text"])}</td>'
        f'<td class="num"><span class="was mono">{_f1(was_start)}</span>'
        f'<button class="tbtn" data-open="{i}">{_f1(start)}</button></td>'
        f'<td class="num"><span class="was mono">{_f1(was_duration)}</span>'
        f'<span class="mono">{_f1(duration)}</span></td>'
        f'<td>{_band_cell(line)}</td>'
        f'<td class="why">{_why_cell(line)}</td>'
        "</tr>"
    )
    if pivot is not None and i == pivot:
        # The rail alone is undiscoverable; one line of text is the floor.
        row += (
            '<tr class="divider"><td colspan="8">'
            "below here, re-derived against the audio — above, unchanged</td></tr>"
        )
    return row


def render_rows(payload: dict) -> str:
    """The `<tbody>` of the list of lines — the whole of it, always.

    Never filtered to the flagged rows: filtering would hide the thing the
    page exists to show, which is what an edit did to the rows that were
    *not* flagged (§8.2).

    The rows are rendered here rather than in the page's JavaScript so that
    there is one template, in one language, that a test can read — and the
    page fetches this same markup back after a re-anchor rather than
    building a second copy of it.

    The rail and the divider key off the EARLIEST hand-set line, which is
    §8.9's open question answered: `anchor_lines` takes a mapping and the
    routes accept one, so more than one correction is allowed, and
    everything below the earliest of them is what was re-derived.
    """
    lines = payload["lines"]
    hand_set = [line["i"] for line in lines if line["handSet"]]
    pivot = min(hand_set) if hand_set else None

    machine = [line.get("machineStart") for line in lines]
    rows = []
    for k, line in enumerate(lines):
        nxt, here = (machine[k + 1] if k + 1 < len(machine) else None), machine[k]
        duration = None if nxt is None or here is None else nxt - here
        rows.append(_row(line, pivot=pivot, machine_duration=duration))
    return "".join(rows)


def _provenance(payload: dict) -> str:
    """§8.2, item 1: **one quiet line**, and that is all.

    Three passes to get here, and the third is Jorge's — *"I would refrain
    from showing any of this info to the final user."* Pass one collapsed a
    full provenance table behind a `<details>` because it was loud; pass
    two opened it and made it recede, on the rule *quiet, not hidden*,
    which fixed the volume but not the **relevance**. Nothing on this page
    belongs here unless it helps judge a line by ear, and `sha256`,
    `device`, `toolVersion`, `extractedAt` and the audio duration help
    with nothing while correcting.

    What survives is the one question a correcting user does ask — *am I
    looking at the right song and the right take?* Everything removed
    stays in `<stem>-report.json`: it is filed, not lost. The report is
    the audit artifact and can be as technical as it likes; the page
    cannot.

    **The file name, never the path** — the same rule page 1's picker
    follows (§9.3, decision 1). And the lead-in is labelled by
    `leadIn.source`, not by the word *measured* hardcoded: since §8.6 line
    0 can be hand-set, and a line that says *measured* about a value a
    human typed is the kind of small lie this whole PR is deleting.
    """
    source = payload.get("provenance") or {}
    lead_in = payload["leadIn"]
    parts = [payload.get("title") or "—"]

    audio = source.get("audio")
    if audio:
        parts.append(Path(str(audio)).name)

    model = source.get("model")
    if model:
        parts.append(f'{str(model).replace(":", " ")} ({payload.get("lang") or "—"})')

    parts.append(f'{lead_in.get("source", "measured")} lead-in {lead_in["durationSec"]:.2f} s')

    return f'<p class="prov">{html_escape(" · ".join(parts))}</p>'


TIME_SIGNATURES = ("4/4", "3/4", "6/8", "2/4", "12/8")
"""The signatures that occur in practice, and the whole of the control.

**A `numerator` and a `denominator` are not a question a musician can be
asked** — walked 2026-09-02, where two bare number fields labelled *beats*
and *per* were unanswerable by the person who has to answer them. A time
signature is: it is what is written at the front of the stave, it is one
choice, and these five cover the catalogue and most of everything else.

A song declaring a signature outside this list keeps it — `_signature_options`
adds it rather than offering to silently change it. Losing a `5/4` to a
dropdown that could not say it would be the control editing the file."""


def split_signature(value: str) -> tuple[int, int]:
    """`"6/8"` -> `(6, 8)`. The one place the two halves are separated,
    shared with the page's JavaScript by shape rather than by copy."""
    numerator, _, denominator = value.partition("/")
    return int(numerator), int(denominator)


def _signature_options(current: str = "") -> str:
    """The five, plus whatever the song already declares.

    A file carrying `5/4` must come back out carrying `5/4`. A control that
    could not say it would either drop the block or quietly round it to
    something it can, and both are the control editing the file."""
    offered = TIME_SIGNATURES + ((current,) if current and current not in TIME_SIGNATURES else ())
    return "".join(f'<option value="{sig}">{sig}</option>' for sig in offered)


def _tempo() -> str:
    """The tempo control, and the four fields are the design.

    **§11.5 removed this control from page 1 on 2026-08-16; round A put a
    four-field one on page 2; step 6 brings it back here.** The half that
    changed in round A: Pregonero loses tempo ownership later in the
    Tramoya integration, so Bombista becomes the only remaining home for
    typing one in. The half that changed at step 6: page 2's claim to it
    was that the timeline is visible there while it is being changed — but
    **a tempo changes no timing in this tool and is never read against the
    audio**, so nothing about typing one waits on having heard the take.
    It belongs with the rest of the song's general information.

    The half that has never changed: a block is written **whole or not at
    all** — `beatScheduler` needs `numerator` and `denominator` and
    computes `numerator % 3`, so a bpm-only block gives a broken pulse
    while the scaling keeps working, with no error anywhere. Hence four
    fields, and a run route that refuses anything less.

    **There is no Set button**, because there is nothing to set yet: the
    block travels with `Process song →` like every other answer on this
    page, and the server refuses the whole run rather than one control.

    **Three controls, not four fields** (walked 2026-09-02). `bpm`,
    `beats`, `per` and `count-in bars` as four bare numbers were
    unanswerable by the person who has to answer them — Jorge did not know
    what the last two meant here, in Ableton or in GarageBand, and a field
    nobody can answer is a field that gets guessed. What replaced them:

    - **Beats per minute**, relabelled from `bpm` and told what value is
      wanted. On the same walk Jorge typed `100` for a `6/8` song whose
      felt pulse is `66.67`, because the old caption said *type it from the
      source that produced this audio, where it is exact* — and the source
      says `100`. That is a **1.5x error the screen invited**, and the
      caption now names the felt pulse and warns about the DAW's number.
    - **Time signature**, one choice from `TIME_SIGNATURES`, which is what
      a musician actually knows. The two halves are split at the boundary.
    - **Bars before the first line**, which is what `countInBars` means
      said in words.

    **`0` bars is the one proposed value on this page, and it is not a
    guess** — it is the answer for every song that has no count-in, which
    is most of them, and it cannot be wrong in the way a `120 / 4 / 4`
    would be. It also never makes a block on its own: the page sends no
    tempo at all unless a pulse or a signature was given, so a song with no
    tempo stays a song with no tempo (`songs@c5adf65`).
    """
    return f"""
  <div class="tempo">
    <div class="trow">
      <label class="tf">Beats per minute
        <input type="number" id="t-bpm" step="any" min="0" autocomplete="off" value=""></label>
      <button type="button" id="t-tap">Tap</button>
      <span class="tapstate" id="t-tapstate">no taps yet</span>
      <label class="tf">Time signature
        <select id="t-signature"><option value="">—</option>{_signature_options()}</select></label>
      <label class="tf">Bars before the first line
        <input type="number" id="t-countinbars" step="1" min="0" autocomplete="off"
          value="0"></label>
      <span class="tstate" id="t-state"></span>
    </div>
    <div class="tapbar pageoff" id="tapbar">
      <audio id="t-audio" controls preload="none"></audio>
      <span class="aside">Play it, tap the beat you would count out loud.</span>
    </div>
    <p class="hint"><b>Beats per minute is the pulse you feel</b> — the beat you would count
      out loud, or tap, while the song plays. Nobody can count beats for a minute, so
      <b>tap it</b>: press <b>Tap</b> in time with the recording, or hit the space bar once the
      button has focus, and the field fills from your taps. Stop for a few seconds and the next
      tap starts a fresh count.</p>
    <p class="hint">Tapping is the only way to get the pulse you actually feel. It is <b>not</b>
      always the number the software that made the recording reports: a <code>6/8</code> song
      counted in two is <code>66.67</code> here where a DAW says <code>100</code>.</p>
    <p class="hint">Bombista never measures any of this — your taps are yours. <b>The pulse and
      the signature go together or not at all</b>; half a tempo breaks Pregonero's pulse while
      its scaling keeps working, which is worse than leaving it out. Leave both blank for a song
      that has no tempo: that is a real answer and nothing downstream minds it. <b>Bars before
      the first line is left out of the file when it is zero</b>, which is how the format says
      no count-in.</p>
  </div>
"""


def render_review(payload: dict, *, header: bool = True) -> str:
    """Page 2 — Review (§8). The heart of B20, and B19 absorbed.

    **The list of lines is the interface** (Jorge, 2026-08-15). A first pass
    put a lead-in panel, a *needs attention* card, an editor pane, a
    re-anchor banner and a JSON preview around it; all five are cut. The
    user judges the timeline by reading the lines and their times and
    hearing the audio, and anything that explains, repeats or restates that
    is weight. What survives is the player, the list, one popup and one
    button — and that is the design, not an unfinished state.

    **Line 0 is an ordinary row** (§8.6, settled 2026-08-16): same stepper,
    no special colour, no `lead-in` label, no popup caption, and no lead-in
    widget anywhere on this page. Moving it *is* the global shift, because
    the normaliser banks its onset into `leadIn` at emit; the distinction
    between a lead-in and line 0 belongs to Pregonero, at performance time.
    """
    counts = payload["bands"]
    body = f"""
<h1>Review</h1>
<p class="lede">{len(payload["lines"])} lines · raw audio-clock seconds</p>

{_provenance(payload)}

<div class="sticky">
  <audio id="audio" controls preload="metadata" src="/api/audio"></audio>
  <div class="barrow">
    <span class="chip band-HIGH" id="cHIGH">HIGH {counts["HIGH"]}</span>
    <span class="chip band-REVIEW" id="cREVIEW">REVIEW {counts["REVIEW"]}</span>
    <span class="chip band-FAIL" id="cFAIL">FAIL {counts["FAIL"]}</span>
    <span class="playhead">playhead <b class="mono" id="ph">0.00</b> s</span>
  </div>
</div>

<p class="hint tablehint">Click a <b>START</b> time to adjust it. Press and hold to move
  fast — a whole missed word is about a second.</p>

<table>
  <thead><tr>
    <th></th><th></th><th>line</th><th>text</th><th class="num">start</th>
    <th class="num">dur</th><th>band</th><th>why</th>
  </tr></thead>
  <tbody id="tbody">{render_rows(payload)}</tbody>
</table>

<p class="confirm"><button class="btn1" id="confirm">Confirm timeline →</button></p>
"""
    return _shell(title="Review", current="2", body=body, script=_REVIEW_JS, header=header)


def render_input(
    *,
    browse_from: str = "",
    song: str = "",
    header: bool = True,
    answers: dict | None = None,
) -> str:
    """Page 1 (§9.3), augmented at step 6 with the song itself.

    **Four rows still, until a lyrics file is chosen.** The form the user
    meets is the same one §9.3 fixed — Lyrics, Media source, Language,
    Model — and the song block below it is hidden until there is a song to
    describe. No output-folder picker and no *also write* checkboxes,
    both cut 2026-08-15: step 3 offers downloads and the app does not
    choose where they land.

    **The song block is what step 6 adds** (journey-setup, 2026-09-02):
    title, artist, notes, title translations and the tempo. This is the
    metadata a lyrics `.txt` cannot carry, and without it the flow can only
    ever make a song with no artist and no translated title — which is
    what the skeleton `bombista new` writes existed to supply. It is
    Bombista's own screen and it appears when Bombista is used on its own.

    **§3's *no free text* survives as a sharper rule.** What the machine is
    told — which files, which language, which model — is still pickers and
    dropdowns, because those are answers with a right shape. What only a
    human is the source of record for is typed, because there is no other
    way to get it.

    An SP JSON prefills every field from itself, which is the other half of
    step 6's wording: this flow is also how an existing song is edited.

    **Title translations came off this page on 2026-09-02.** Translation is
    not Bombista's concern: lyric translations are written outside the
    suite, in the file, and the title follows the same rule — *if it is a
    translation, it was written elsewhere and the file already carries it*
    (tramoya-integration `project-context.md`). What the file carries still
    passes through untouched; what changed is that nothing here asks.

    *browse_from* is the directory the file pickers open in, and *song* is
    a song file this page starts prefilled from. Both are answers a caller
    may supply and neither tells Bombista anything about who is calling.

    *answers* is what a session already holds, so **coming back here is
    navigation rather than a reset** (2026-09-02). Everything typed
    returns: the two files, the language, the model, the title, artist and
    notes, and whatever tempo was given — including a half-typed one,
    which is the whole point, since the refusal that sends people here is
    about exactly that. Where a run has happened the page says what
    running again costs instead of discarding step 2's corrections in
    silence.
    """
    lang_options = "".join(
        f'<option value="{code}">{code} — {name}</option>' for code, name in LANGUAGES
    )
    tempo = _tempo()
    body = f"""
<h1>Input song</h1>
<p class="lede">Two files, two defaults, and the song itself.</p>

<div class="form">
  <div class="frow">
    <label class="flabel">Lyrics</label>
    <div class="ctl">
      <button type="button" id="pick-lyrics">Choose file</button>
      <span class="fname" id="lyrics-name">—</span>
    </div>
    <p class="hint">Plain text (<code>.txt</code>), or a <b>Song Performance JSON</b>
      (<code>.json</code>) — the format Tramoya promotes.
      <a href="{FORMAT_DOC_URL}">See an example</a></p>
  </div>

  <div class="frow">
    <label class="flabel">Media source</label>
    <div class="ctl">
      <button type="button" id="pick-media">Choose file</button>
      <span class="fname" id="media-name">—</span>
      <button type="button" id="clear-media" class="pageoff">Remove</button>
    </div>
    <p class="hint"><b>With a recording, the lines change themselves as the song plays</b> and
      the projection follows without you touching it. Without one, you advance them by hand.
      That is a real way to perform a song, and it is what happens if you leave this empty.</p>
    <p class="hint">MP3 · M4A · WAV · FLAC · MP4 · MOV. The audio track is read from video too.</p>
  </div>

  <div class="frow">
    <label class="flabel">Language</label>
    <div class="ctl">
      <select id="lang">{lang_options}</select>
    </div>
    <p class="hint">The language on the recording and the lyrics file.</p>
  </div>

  <div class="frow">
    <label class="flabel">Model</label>
    <div class="ctl">
      <select id="model">
        <option value="medium">medium — ~50 s per song</option>
        <option value="small">small — ~20 s per song</option>
        <option value="tiny">tiny — ~5 s per song</option>
      </select>
    </div>
    <p class="hint"><b>Runs on your local machine. Nothing is uploaded.</b> A bigger model
      recognises more of the sung words, so fewer lines come back flagged — and it takes
      longer. Change it and come back if a run reads badly.</p>
  </div>
</div>

<div id="songbranch" class="pageoff">
  <h2 class="secthead">The song</h2>
  <p class="hint sectlede">What the recording and the words cannot say. A
    <code>.txt</code> carries none of it; a <b>Song Performance JSON</b> carries all of it,
    and what is below is then what that file already says.</p>

  <div class="form">
    <div class="frow">
      <label class="flabel">Title</label>
      <div class="ctl"><input type="text" id="title" value="" autocomplete="off">
        <span class="aside" id="slug">—</span></div>
      <p class="hint">The name of the song, as you would print it on a poster.</p>
    </div>
    <div class="frow">
      <label class="flabel">Artist</label>
      <div class="ctl"><input type="text" id="artist" value="" autocomplete="off"></div>
    </div>
    <div class="frow">
      <label class="flabel">Notes</label>
      <div class="ctl"><input type="text" id="notes" value="" autocomplete="off"></div>
      <p class="hint">For you, at a music stand. <code>Capo 5, acordes de Lam</code>.</p>
    </div>
{tempo}  </div>
  <p class="hint pageoff" id="stripped"></p>
</div>
<!--/songbranch-->

<div id="refused" class="pageoff"><b>The run did not start</b><span id="refused-why"></span></div>

<div class="ask pageoff" id="ask-manual">
  <div class="inner">
    <div class="head">No recording</div>
    <p>This song will be <b>advanced by hand</b> during the performance: you move to the next
      line yourself, and nothing follows the audio on its own.</p>
    <p>You can give it a recording later, and the lines will follow it on their own.</p>
    <div class="foot">
      <button type="button" id="ask-no">Go back</button>
      <button type="button" class="askgo" id="ask-yes">Continue</button>
    </div>
  </div>
</div>

<p class="hint pageoff" id="rerun-cost"></p>

<p class="go"><button class="btn1" id="process" disabled>Process song →</button></p>
"""
    script = (
        f"var BROWSE_FROM = {json.dumps(browse_from)};\n"
        f"var SONG = {json.dumps(song)};\n"
        f"var ANSWERS = {json.dumps(answers)};\n"
        + _PICKER_JS
        + _INPUT_JS
    )
    return _shell(title="Input song", current="1", body=body, script=script, header=header)


def render_processing(
    *, media_name: str = "", model: str = "", lang: str = "", header: bool = True
) -> str:
    """Page 1.5 (§9.4). A state, not a spinner.

    The lede says *on your local machine*, not *on this machine* — §10.1,
    Jorge's wording: on a page served over HTTP, *this machine* is
    ambiguous about whose.
    """
    lede = " · ".join(
        part
        for part in (media_name, f"faster-whisper {model}" if model else "", lang,
                     "on your local machine")
        if part
    )
    body = f"""
<h1>Processing</h1>
<p class="lede">{html_escape(lede)}</p>
<div style="max-width:34rem">
  <div class="phase" id="ph-transcribe"><span class="dot"></span> Transcribing the audio
    <span class="t">—</span></div>
  <div class="phase" id="ph-anchor"><span class="dot"></span> Anchoring the lines
    <span class="t">—</span></div>
</div>
<p class="go"><button type="button" id="cancel">Cancel</button></p>
<p class="hint">Transcription is the slow part and it is cached. Coming back here from step 2
  reuses <code>asr-words.jsonl</code> and takes well under a second.</p>
<div id="failed" class="pageoff"><b>The run stopped</b><span id="failed-why"></span></div>
"""
    return _shell(
        title="Processing", current="1", body=body, script=_PROCESSING_JS, header=header
    )


_TRANSLATIONS_NOTE = (
    '<p class="outside" id="translations">'
    "<b>Translations are written outside the suite</b>, in the song file itself, "
    "in an LLM session — the lyrics and the title alike. No tool here asks for "
    "one or performs one."
    "</p>"
)
"""**Page 3 only, and it is the last thing on it** (Jorge, 2026-09-03).

Pregonero owned this sentence and drew it beside the frame, which put it
on page 1, page 2 and page 3 alike — Pregonero draws Bombista in a frame
with no preload and reads nothing out of it, so it cannot tell which page
is showing, and it must not learn: that boundary is load-bearing. The
sentence has to appear once, at the end, below the actions, so **the page
that is the end renders it.**

**This is one line of copy, not a transfer of ownership.** Bombista still
does not ask for a translation, does not perform one, and has no
translation field anywhere — the title-translation field came off page 1
on exactly that principle. What it says here is what it does NOT do, on
the one screen where a person has just finished making the file and is
about to take it somewhere else. That is a fact about the file in front
of them, which is the same footing as the caption above it.

**It is on standalone Bombista too, and that is right rather than
tolerated.** The sentence is true of Bombista alone, and rendering it only
with `--no-header` would mean Bombista drawing a different page depending
on who called it. It learns nothing about its caller.
"""

_CAPTION_PASS = (
    "Your song file, with the timeline you just confirmed in it. Everything you loaded is "
    "passed through untouched, translations included."
)

_CAPTION_NEW = (
    "A new song file: the lines in the language you chose, the timeline you just confirmed, "
    "and the tempo if you typed one. Anything else is empty and can be filled in later."
)

_CAPTION_MANUAL = (
    "A new song file with the words and no timeline: <b>this song is advanced by hand during "
    "the performance.</b> Give it a recording later and the lines will follow it on their "
    "own."
)
"""Three sentences, one per ending, and each is one sentence because that is
what it took to get `Save to the catalogue` above the fold (walked
2026-09-02): the button that finishes the flow was reachable only by
scrolling, behind a paragraph explaining what a `.txt` can honestly supply.

**There are two endings and not one**, because a single caption cannot
claim a timeline that is not there. A song with no recording gets the third
one, which says what will happen on the night rather than what is missing
from the file."""


def _timeline_downloads(manual: bool) -> str:
    """The two downloads that only exist when a timeline does.

    A song with no recording has no timing keys to paste and no bands to
    report, so offering either would hand over an empty file or a refusal.
    The whole-file download stays: it carries the words, which is the whole
    of what this song is.
    """
    if manual:
        return ""
    return """  <div class="dl">
    <button type="button" id="dl-timeline">Download timeline only</button>
    <p class="hint">The five timing keys only &mdash; <code>linesHash</code>,
      <code>timelineSignedOff</code>, <code>timelineVersion</code>, <code>leadIn</code>,
      <code>timeline</code> &mdash; to paste into a song file you already maintain.</p>
  </div>
  <div class="dl">
    <button type="button" id="dl-report">Download report</button>
    <p class="hint">Bands, signals, provenance and every hand-set line, as markdown. Does not
      count as sign-off.</p>
  </div>
"""


def render_output(
    sp_json: dict,
    *,
    filename: str,
    save_path: str,
    from_scratch: bool = False,
    manual: bool = False,
    header: bool = True,
) -> str:
    """Page 3 (§9.5). Read-only, the JSON in full, and a way to finish.

    **No fold, no expand control, no truncation.** An earlier pass added
    one and Jorge cut it: the window scrolls, the file is the file, and a
    control whose only job is to shorten a scroll has to be understood
    before it can be used. The argument for folding — that 19 lines × 4
    languages buries the timing keys — is answered by the caption saying
    which five keys Bombista wrote, not by hiding the rest.

    **`← Back to review` is absent on a manual song.** There is no review
    to go back to — `/review` would only send you here again — and a link
    that returns you to the page you are on is the flow pretending a step
    exists.

    **`Save to the catalogue` sits after the JSON box and before the three
    downloads.** It was moved above the box on 2026-09-02 to be reachable
    at all, behind a paragraph explaining what a `.txt` can honestly
    supply — and that was the wrong repair: **the answer is a shorter
    explanation, not a different order** (Jorge, the same day). The page
    reads as the file, then what to do with it, and each caption is one
    sentence, which is what makes the button visible without scrolling.

    It stays ahead of the downloads: it is the way through and they are an
    escape hatch. The words are chosen for two reasons: the flow is not
    always about a new song — it is also how an existing one is edited,
    which rules out *Add to the library* — and on a screen where
    everything else hands over bytes, naming the destination is the
    distinction that was invisible on 2026-09-02. `Confirm` was rejected:
    the timeline is confirmed one screen earlier, so a third would stop
    meaning anything.

    **The path is on the page before the button is pressed.** *The
    catalogue* is a name; a file is a fact, and the two are only
    reconcilable if the person can see which file. `save_path` comes from
    `server.default_out_path`, the same one the route writes to, so the
    promise and the write cannot disagree.
    """
    rendered = json.dumps(sp_json, indent=2, ensure_ascii=False)
    if manual:
        caption = _CAPTION_MANUAL
    elif from_scratch:
        caption = _CAPTION_NEW
    else:
        caption = _CAPTION_PASS
    body = f"""
<h1>Output</h1>
<p class="hint">{caption}</p>

<div class="jsonhead"><span class="fn">{html_escape(filename)}</span></div>
<pre class="json" id="json">{html_escape(rendered)}</pre>

<div class="save">
  <button type="button" class="btn1" id="save">Save to the catalogue</button>
  <p class="hint">This is the way out. It writes the file above — nothing you loaded is
    changed — here:</p>
  <p class="path mono" id="savepath">{html_escape(save_path)}</p>
  <p class="sstate" id="savestate"></p>
</div>

<p class="hint dlhead">Or take the bytes yourself, if you keep this song somewhere else.</p>

<div class="dlrow">
  <div class="dl">
    <button type="button" id="dl-song">Download JSON file</button>
    <p class="hint">The whole file above. This is the one Tramoya reads.</p>
  </div>
{_timeline_downloads(manual)}</div>

<p><span class="pageoff" id="signoff"></span></p>
{'' if manual else '<p class="go"><a href="/review">← Back to review</a></p>'}
{_TRANSLATIONS_NOTE}
"""
    return _shell(
        title="Output",
        current="3",
        body=body,
        script=_OUTPUT_JS,
        header=header,
        skipped="2" if manual else "",
    )
