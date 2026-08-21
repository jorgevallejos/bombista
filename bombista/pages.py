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

VERSION = "v1.0.2"
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

/* ---------- step bar (§9.2) — navigation, not an announcement ---------- */
.steps { display: flex; align-items: stretch; margin: 1.1rem 0 0;
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
#txtbranch .form { margin-top: 0; border-top: none; }
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
.warnbox { border-left: 2px solid var(--review); background: transparent;
           padding: .1rem 0 .1rem .8rem; margin: 1rem 0 0;
           font: 400 .78rem/1.55 var(--mono); color: var(--dim); max-width: 46rem; }
.warnbox b { display: block; font-weight: 400; text-transform: uppercase;
             letter-spacing: .11em; margin-bottom: .3rem; color: var(--review); font-size: .72rem; }

/* ---------- the file picker — a loopback listing, not a native dialog (§9.6) ---------- */
.picker { position: fixed; inset: 0; z-index: 80; background: rgba(0,0,0,.72);
          display: flex; align-items: center; justify-content: center; padding: 2rem; }
.picker .inner { background: var(--surface); border: 1px solid var(--clay);
                 width: min(44rem, 100%); max-height: 80vh; display: flex; flex-direction: column; }
.picker .head { padding: .6rem .8rem; border-bottom: 1px solid var(--line-2);
                font: 400 .72rem/1.5 var(--mono); color: var(--dim);
                overflow-wrap: anywhere; }
.picker ul { list-style: none; margin: 0; padding: 0; overflow: auto; }
.picker li { border-bottom: 1px solid var(--line); }
.picker li button { width: 100%; text-align: left; border: none; text-transform: none;
                    letter-spacing: 0; font-size: .82rem; color: var(--paper); padding: .45rem .8rem; }
.picker li button:hover { background: var(--surface-2); color: var(--clay); }
.picker li.dir button { color: var(--dim); }
.picker .foot { padding: .55rem .8rem; border-top: 1px solid var(--line-2); text-align: right; }

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
.dlrow { display: flex; gap: 1.6rem; flex-wrap: wrap; align-items: flex-start; margin: 1.7rem 0 0; }
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
.sticky { position: sticky; top: 0; z-index: 20; background: var(--bg);
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
"""

_PICKER_JS = """\
/* §9.6, resolved: a loopback listing rather than <input type="file">.
   The server needs a real path — to read the lyrics, to hash the audio for
   provenance, and to write the re-run command into the report. A browser
   File object has no path, so accepting an upload would mean copying a
   50 MB m4a into a staging directory to recover something the file already
   had two directories away, and every path the tool then recorded would
   name the copy rather than the take. The page shows the file NAME alone
   (§9.3, decision 1) — the path stays the tool's business. */
function browse(startPath, onPick) {
  var box = document.createElement("div");
  box.className = "picker";
  document.body.appendChild(box);
  function close() { box.remove(); }
  function load(path) {
    fetch("/api/browse?path=" + encodeURIComponent(path))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { close(); return; }
        var items = data.entries.map(function (entry) {
          return '<li class="' + (entry.dir ? "dir" : "file") + '">' +
                 '<button type="button" data-path="' + esc(entry.path) + '" data-dir="' +
                 (entry.dir ? "1" : "") + '">' + (entry.dir ? "▸ " : "") +
                 esc(entry.name) + "</button></li>";
        }).join("");
        box.innerHTML =
          '<div class="inner"><div class="head">' + esc(data.path) + "</div><ul>" +
          '<li class="dir"><button type="button" data-path="' + esc(data.parent) +
          '" data-dir="1">▸ ..</button></li>' + items +
          '</ul><div class="foot"><button type="button" data-close="1">Close</button></div></div>';
      });
  }
  box.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest("button");
    if (!btn) { if (ev.target === box) { close(); } return; }
    if (btn.getAttribute("data-close")) { close(); return; }
    var path = btn.getAttribute("data-path");
    if (btn.getAttribute("data-dir")) { load(path); return; }
    close();
    onPick(path);
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
  var txtbranch = document.getElementById("txtbranch");

  document.getElementById("pick-lyrics").addEventListener("click", function () {
    browse(HOME, function (path) {
      state.lyrics = path;
      document.getElementById("lyrics-name").textContent = baseName(path);
      describe(path);
    });
  });

  document.getElementById("pick-media").addEventListener("click", function () {
    browse(HOME, function (path) {
      state.media = path;
      document.getElementById("media-name").textContent = baseName(path);
      ready();
    });
  });

  /* The language dropdown is constrained by the file: a language the file
     does not carry has no lines to anchor. Undeclared options render
     disabled. The caption does not explain the rule (§9.3, decision 5) —
     and the server refuses it too, so this is a courtesy, not the guard. */
  function describe(path) {
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
        txtbranch.className = data.branch === "txt" ? "" : "pageoff";
        document.getElementById("slug").textContent = data.slug;
        if (data.branch === "txt" && !document.getElementById("title").value) {
          document.getElementById("title").value = data.slug;
        }
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

  function ready() {
    document.getElementById("process").disabled = !(state.lyrics && state.media);
  }

  document.getElementById("process").addEventListener("click", function () {
    var body = {
      lyrics: state.lyrics,
      media: state.media,
      lang: langSel.value,
      model: document.getElementById("model").value
    };
    if (state.branch === "txt") {
      body.title = document.getElementById("title").value;
    }
    fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json().then(function (d) { return [r.status, d]; }); })
      .then(function (pair) {
        if (pair[0] >= 400) { refuse(pair[1].error); return; }
        location.href = "/processing";
      });
  });

  /* A refusal is rendered in the page's own warning component rather than
     a browser alert — the skin has one, and a modal from another design
     system is the loudest thing on a page whose budget is spent elsewhere. */
  function refuse(message) {
    var box = document.getElementById("refused");
    box.className = "warnbox";
    document.getElementById("refused-why").textContent = message;
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
  function download(kind, signs) {
    location.href = "/api/download?kind=" + kind;
    if (!signs) { return; }
    setTimeout(function () {
      fetch("/api/session").then(function (r) { return r.json(); }).then(function (data) {
        if (!data.timelineSignedOff) { return; }
        var el = document.getElementById("signoff");
        el.className = "signoff";
        el.textContent = "Signed off " + data.timelineSignedOff + " · your inputs untouched";
        var json = document.getElementById("json");
        json.textContent = json.textContent.replace(
          /"timelineSignedOff": null/, '"timelineSignedOff": "' + data.timelineSignedOff + '"');
      });
    }, 300);
  }

  document.getElementById("dl-song").addEventListener("click", function () {
    download("song", true);
  });
  document.getElementById("dl-timeline").addEventListener("click", function () {
    download("timeline", true);
  });
  document.getElementById("dl-report").addEventListener("click", function () {
    download("report", false);
  });
})();
"""


def _masthead() -> str:
    """§9.1. Without it, page 1's *the format Tramoya promotes* has no
    brand on the page to attach to. It is the only decoration in the
    interface and it earns its place by making the rest of the page's
    vocabulary legible."""
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


def _step_bar(current: str) -> str:
    """Every step clickable, including backwards: going back to step 1 is
    how you re-run with a different model, and going back to step 2 from
    step 3 is how you fix something you noticed while reading the file.
    Nothing is destroyed by moving between them."""
    segments = []
    for number, label, href in STEPS:
        on = ' class="on"' if number == current else ""
        segments.append(f'<a href="{href}"{on}><span class="n">{number}</span> {label}</a>')
    return '<nav class="steps">' + "".join(segments) + "</nav>"


def _shell(*, title: str, current: str, body: str, script: str = "") -> str:
    """One page, inline CSS and JS, nothing fetched from anywhere but this
    process (§8.1)."""
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
        + _masthead()
        + _step_bar(current)
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
    document.getElementById("ph").textContent = t.toFixed(2);
    var all = rows();
    for (var i = 0; i < all.length; i++) {
      var s = startOf(all[i]), e = parseFloat(all[i].getAttribute("data-end"));
      all[i].classList.toggle("current", t >= s && t < e);
    }
  });

  document.getElementById("confirm").addEventListener("click", function () {
    location.href = "/output";
  });
})();
"""


def _f2(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


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
        f'<td class="num"><span class="was mono">{_f2(was_start)}</span>'
        f'<button class="tbtn" data-open="{i}">{start:.2f}</button></td>'
        f'<td class="num"><span class="was mono">{_f2(was_duration)}</span>'
        f'<span class="mono">{duration:.2f}</span></td>'
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


def render_review(payload: dict) -> str:
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
    return _shell(title="Review", current="2", body=body, script=_REVIEW_JS)


def render_input(*, home: str = "") -> str:
    """Page 1 (§9.3). Four rows, and that is the whole form.

    No output-folder picker and no *also write* checkboxes — both cut
    2026-08-15. Step 3 offers downloads and the app does not choose where
    they land.
    """
    body = f"""
<h1>Input song</h1>
<p class="lede">Two files. Two defaults. Nothing typed.</p>

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
    </div>
    <p class="hint">MP3 · M4A · WAV · FLAC · MP4 · MOV. The audio track is read from video too.</p>
  </div>

  <div class="frow">
    <label class="flabel">Language</label>
    <div class="ctl">
      <select id="lang">
        <option value="es">es — Spanish</option>
        <option value="en">en — English</option>
        <option value="nl">nl — Dutch</option>
        <option value="fr">fr — French</option>
      </select>
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

<div id="txtbranch" class="pageoff">
  <div class="form">
    <div class="frow">
      <label class="flabel">Slug</label>
      <div class="ctl"><span class="fname" id="slug">—</span>
        <span class="aside">from the filename</span></div>
    </div>
    <div class="frow">
      <label class="flabel">Title</label>
      <div class="ctl"><input type="text" id="title" value=""></div>
      <p class="hint">The one text field in the whole flow. A <code>.txt</code> carries no
        title.</p>
    </div>
  </div>
  <div class="warnbox">
    <b>Tempo is not Bombista's business</b>
    Bombista answers <i>when</i> a line happens, not in which beat, so the file it writes
    carries no <code>tempo</code> block. Add it by hand from the source that produced
    this audio, where it is exact: all four values together (<code>bpm</code>,
    <code>numerator</code>, <code>denominator</code>, <code>countInBars</code>), because a
    partial block breaks Pregonero's pulse.
  </div>
  <p class="hint pageoff" id="stripped"></p>
</div>
<!--/txtbranch-->

<div id="refused" class="pageoff"><b>The run did not start</b><span id="refused-why"></span></div>

<p class="go"><button class="btn1" id="process" disabled>Process song →</button></p>
"""
    script = f'var HOME = {json.dumps(home)};\n' + _PICKER_JS + _INPUT_JS
    return _shell(title="Input song", current="1", body=body, script=script)


def render_processing(*, media_name: str = "", model: str = "", lang: str = "") -> str:
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
    return _shell(title="Processing", current="1", body=body, script=_PROCESSING_JS)


_CAPTION_PASS = (
    "This is your <b>Song Performance JSON</b> — the file you started from, with the timing "
    "keys filled in. Bombista wrote five: <code>linesHash</code>, "
    "<code>timelineSignedOff</code>, <code>timelineVersion</code>, <code>leadIn</code>, "
    "<code>timeline</code>. Entry 0 is <code>0.00</code> and the lead-in is banked. Everything "
    "above them is passed through untouched, all four languages included. Bands, signals and "
    "the record of what you set by hand are in the <b>report</b>, not here."
)

_CAPTION_NEW = (
    "There was no song file, so this is a new <b>Song Performance JSON</b> built from your "
    "<code>.txt</code>. It carries only what a plain text plus step 1 can honestly supply: "
    "<code>artist</code> and <code>notes</code> are empty for you to fill in, there is no "
    "<code>tempo</code> block — Bombista never measures one, and a partial one breaks "
    "Pregonero's pulse — and <code>lyrics</code> carries the one language you chose. Add "
    "the other languages later; <code>linesHash</code> will catch it if the line count changes."
)


def render_output(sp_json: dict, *, filename: str, from_scratch: bool = False) -> str:
    """Page 3 (§9.5). Read-only, and the JSON in full.

    **No fold, no expand control, no truncation.** An earlier pass added
    one and Jorge cut it: the window scrolls, the file is the file, and a
    control whose only job is to shorten a scroll has to be understood
    before it can be used. The argument for folding — that 19 lines × 4
    languages buries the timing keys — is answered by the caption saying
    which five keys Bombista wrote, not by hiding the rest.
    """
    rendered = json.dumps(sp_json, indent=2, ensure_ascii=False)
    body = f"""
<h1>Output</h1>
<p class="lede">A new file. Nothing you loaded was modified.</p>

<p class="hint">{_CAPTION_NEW if from_scratch else _CAPTION_PASS}</p>

<div class="jsonhead"><span class="fn">{html_escape(filename)}</span></div>
<pre class="json" id="json">{html_escape(rendered)}</pre>

<div class="dlrow">
  <div class="dl">
    <button type="button" class="btn1" id="dl-song">Download JSON file</button>
    <p class="hint">The whole file above. This is the one Tramoya reads.</p>
  </div>
  <div class="dl">
    <button type="button" id="dl-timeline">Download timeline only</button>
    <p class="hint">The five timing keys only — <code>linesHash</code>,
      <code>timelineSignedOff</code>, <code>timelineVersion</code>, <code>leadIn</code>,
      <code>timeline</code> — to paste into a song file you already maintain.</p>
  </div>
  <div class="dl">
    <button type="button" id="dl-report">Download report</button>
    <p class="hint">Bands, signals, provenance and every hand-set line, as markdown. Does not
      count as sign-off.</p>
  </div>
</div>

<p><span class="pageoff" id="signoff"></span></p>
<p class="go"><a href="/review">← Back to review</a></p>
"""
    return _shell(title="Output", current="3", body=body, script=_OUTPUT_JS)
