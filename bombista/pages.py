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

__all__ = [
    "STYLESHEET",
    "STEPS",
    "render_input",
    "render_processing",
    "render_output",
]

VERSION = "v0.9.0"

STEPS = (("1", "Input", "/input"), ("2", "Review", "/review"), ("3", "Output", "/output"))
"""§9.2 — one hard-bordered strip, three segments, every one of them a
link. Page 1.5 gets no segment of its own: it is a state of step 1, and a
fourth segment would say the flow has four steps when it has three."""

# The format's five Bombista-owned keys, in the order §10.2 fixes them.
TIMING_KEYS = ("linesHash", "timelineSignedOff", "timelineVersion", "leadIn", "timeline")

FORMAT_DOC_URL = "https://github.com/jorgevallejos/bombista/blob/main/docs/bombista-serve-spec.md"
"""§9.6 is explicit that the SP JSON has no canonical home yet and that
this link may point at the repo until it does. It is an anchor the reader
may click, never a resource the page loads — nothing here reaches off the
machine on its own."""

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
    var tempo = document.getElementById("tempo").value;
    var body = {
      lyrics: state.lyrics,
      media: state.media,
      lang: langSel.value,
      model: document.getElementById("model").value
    };
    if (state.branch === "txt") {
      body.title = document.getElementById("title").value;
      if (tempo) { body.tempo = parseFloat(tempo); }
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
      (<code>.sp.json</code>) — the format Tramoya promotes.
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
    <div class="frow">
      <label class="flabel">Tempo</label>
      <div class="ctl">
        <input type="number" id="tempo" step="0.01" min="1" value="" placeholder="— not set —">
        <span class="aside">BPM</span>
      </div>
    </div>
  </div>
  <div class="warnbox">
    <b>Tempo is never measured</b>
    Bombista answers <i>when</i> a line happens, not in which beat. Take the value from the
    Ableton project that produced this audio, where it is exact. Leave it unset and the key is
    left out of the file entirely — an invented tempo is worse than a missing one.
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
    "<code>artist</code> and <code>notes</code> are empty for you to fill in, <code>tempo</code> "
    "is <b>absent rather than blank</b> — an invented tempo is worse than none, so the key only "
    "appears once it is real — and <code>lyrics</code> carries the one language you chose. Add "
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
