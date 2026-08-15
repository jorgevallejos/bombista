# B20 — `bombista serve`: a local web interface

**Status:** specced, not built. Jorge's design, 2026-08-14. Supersedes and absorbs **B19** — the
editable review page is page 2 of this flow, not a separate item.

---

## 1. What it is, and what it is not

`bombista serve` starts an HTTP server **on the user's own machine**, binds to `127.0.0.1`, and
opens a browser at a three-page flow: **input → review → output**. The alignment runs
locally, in the same Python process that the CLI uses.

**Naming, settled 2026-08-15 (Jorge).** The steps are `1 Input · 2 Review · 3 Output`. The words
*alignment* and *emit* are retired from the interface — both named the machinery rather than the
user's move. The mechanism is still alignment and the code may still call it that; the page does
not. See §10.1 for the vocabulary and **§10.2 for what the Song Performance JSON actually is** —
it is the existing `songs/*.json` format, named at last, not a new one.

**It is:** a front end for the CLI that a non-technical person can drive.

**It is not, and must never become:**

| not | why |
|---|---|
| a hosted service on changopepper.com | Holding other people's audio is a legal posture Jorge does not want, and it would make him a data controller. Nothing leaves the machine, so GDPR does not arise rather than being answered. |
| a second aligner (WASM / transformers.js) | Two implementations of the confidence banding drift, and the report's trustworthiness is the entire product. Also: the real quality bar is `--model-size medium`, which does not fit in a browser or a serverless function. |
| Electron, a packaged app, a second codebase | The no-GUI decision stands. This is a flag on the existing CLI serving HTML, using the stdlib. |
| a place tempo gets derived | Rules 4 and 5, and B14 was dropped for this reason. See §5. |

**Bind to `127.0.0.1` explicitly, never `0.0.0.0`.** A dev server on the LAN is the one way this
design could accidentally become the thing it is avoiding.

---

## 2. Step 0 — a prerequisite that must land first

**`promote`'s merge does not currently exist as a reusable function.** It lives inside
`cli.py` as a Click command plus private helpers: `_load_promotable_candidate`,
`_extract_envelope`, `_find_candidate_lines_hash`, `_lines_hash_mismatch_warning`,
`_timeline_diff`, `_back_up_and_replace`. `_parse_anchor_overrides` is in the same position.

B2's rule — *one merge path* — is therefore not yet satisfied, and `serve` cannot honour it by
importing from `cli.py`.

**Extract first, build second.** Move the merge and the anchor-override parsing into modules that
both `promote` and `serve` import. `promote`'s behaviour must not change; its existing tests are
the proof. This is a refactor with no feature in it, and it is the first commit of B20.

---

## 3. The four states

Three pages, plus one that is easy to forget.

### Page 1 — input

**No free text anywhere.** Every field is a picker, a dropdown, a radio or a stepper.

**Four rows, and that is the whole form** (Jorge, 2026-08-15 — *"I aim to have a lean interface,
few options for this first version"*):

| field | control | note |
|---|---|---|
| Lyrics | file picker, `.txt` or `.sp.json` | Chooses the branch in §5. The branch is **read off the file**, not chosen from a second dropdown. |
| Media source | file picker | Audio or video; the audio track is read from video. Filename convention is `songs/audio/<slug>.<ext>`, but the picker takes any path. |
| Language | dropdown | Default `es`, matching the CLI. **Constrained by the file** — see below. |
| Model | dropdown | Default `medium`, matching the CLI. The label states the impact *and* that it runs locally. |

**Cut, 2026-08-15:** the *emit* checkboxes and the *output directory* picker. Nothing is written to
a path the user chose; step 3 produces files and offers them for download, and where the browser
puts a download is not this tool's business. This also removes the last directory picker from the
flow, which shrinks §9.6's file-picker problem to a single control.

**The language dropdown is constrained by the lyrics file.** An SP JSON declares the languages it
carries; a language the file does not carry has no lines to anchor, so it must not be selectable.
Undeclared options render disabled. A `.txt` declares nothing, so every language is open. **The
caption does not explain the rule** — it reads *"The language on the recording and the lyrics
file"* and nothing more (Jorge, 2026-08-15). In practice the constraint rarely bites: Chango Pepper
song files carry `es`, `en`, `fr` and `nl`, so all four are usually live. The rule is a guard, not a
feature to teach.

If the input is `.txt`, page 1 grows the fields in §5 and **shows what the normaliser stripped**
before running. B3 removes section markers; a silent line-count change surfaces much later as a
`promote` refusal, which is a bad place to learn it.

### Page 1.5 — the run

Alignment takes real time — `medium` on a full song is not instant. This is a state, not a spinner
between pages:

- Two visible phases: transcribe, then anchor.
- A working **cancel**.
- **Re-runs from page 2 skip transcription entirely**, reusing the saved `asr-words.jsonl`. Say so
  on screen — the difference between a 90-second wait and a 2-second one is the whole ergonomics of
  the correction loop.

### Page 2 — review and correct

This is B19, and the heart of it. It inherits B16's page: provenance header, sticky player,
per-line seek, band highlighting.

**Editing a timestamp re-anchors; it does not shift.**

`anchoring.py` is forward-only — the scan position only ever advances, and an override advances it
to the first word *after* the corrected time before anchoring the next line. So a correction
re-derives every following line **against the audio**. Subsequent values do change, which is the
behaviour Jorge asked for, but by re-matching rather than by arithmetic. A rigid delta shift would
displace lines that were measured correctly, destroying exactly the HIGH-confidence rows the report
exists to certify. **Never implement a ripple.**

Consequences the UI must show rather than hide:

- An edit **recomputes the bands below it**. A HIGH line may come back REVIEW. That is the most
  useful signal on the page — mark every band that changed, do not just repaint silently.
- Lines *above* the edit are untouched, by construction. Make that visible too.

Controls:

- **Stepper, ±0.05 s.** The differentiator is a 0.07 s correction loop, so the step must sit below
  it; neither the control nor the JSON round trip may round coarser.
- **Set from playhead.** A stepper alone cannot span a 1.2 s misdetection — that is 24 clicks. Play
  the audio, press a key at the moment the line starts, then use the stepper for the last hundred
  milliseconds. This is how a musician finds an onset.
- **Bounds come from the neighbouring lines**, recomputed live. That is the real allowed interval;
  a fixed range is not.
- **Line 0 has no stepper.** Timeline v2 normalises line 0 to zero and banks the offset in
  `leadIn`. A stepper on line 0 silently breaks the v2 contract. If the whole song sits late that is
  a `leadIn` control at the top of the page — which is also where B6's global nudge belongs. Local
  error and global drift are different problems and get different widgets.
- Every hand-set line is **recorded as hand-set**, with its original machine value and a timestamp.

### Page 3 — output

- **Always a new file. Never edits the input.** This is Jorge's call, 2026-08-14, and it is the
  right one: it removes the file-changed-on-disk race entirely and keeps the merge a pure
  input → output function.
- Renders the resulting **Song Performance JSON read-only**, in full. No editing at this stage.
- **Three downloads, no other controls:** the whole SP JSON · the `timeline` section only · the QA
  report. Per B19's original clause **one of the two JSON downloads must be pressed even when no
  line was flagged**. That clause is the point of the whole design: it converts review from
  something skippable into something the pipeline structurally requires, so every timeline reaching
  an SP JSON carries a conscious human sign-off. **The report does not count as sign-off** — it
  certifies nothing and downloading it is not a decision.
- The file carries **`linesHash`** (B4) and the **edit provenance** from page 2. Without the
  hash the download routes around B4's guard: you save the file, a line gets added to the canonical
  lyrics upstream, you copy yours over it, and everything after that line misaligns silently —
  the precise scenario B4 exists to prevent. Without the provenance, a machine timeline and a
  reviewed one are indistinguishable.
- The merge is the extracted one from §2. Page 3 does not hand-roll a write.

---

## 4. Invariants

1. `serve` imports no logic from `cli.py`; both call the same extracted modules.
2. No timestamp control or serialisation step rounds coarser than 0.07 s.
3. Line 0 is always 0 in a v2 timeline; any lead offset lives in `leadIn`.
4. Onsets are monotonic; a stepper's bounds are its neighbours.
5. A correction re-anchors. Nothing anywhere applies a blanket delta except the explicit global
   `leadIn` / `--lead` control.
6. The emitted file never overwrites an input path.
7. Bind `127.0.0.1` only.

---

## 5. The plain-text branch (B5)

A `.txt` carries lines and nothing else. A Song Performance JSON needs more, so page 1 asks for
it — as controls, not free text where avoidable:

- **slug** — derived from the filename, shown for confirmation.
- **title**, **language**.
- **tempo** — a **clearly marked placeholder**, never derived. Rules 4 and 5 stand, and B14 was
  dropped precisely because tempo comes from the Ableton project that produced the audio, where it
  is exact. The UI must make it obvious this is a value Jorge fills in by hand, not a measurement.
- **stripped meta lines** — shown before the run, not after.

---

## 6. Test obligations

- `promote`'s existing tests pass unchanged after the §2 extraction. That is the refactor's proof.
- A test asserts the `serve` layer **delegates** to the extracted anchoring and merge rather than
  reimplementing them — the drift risk is the whole reason this item is shaped this way.
- A test asserts an override re-anchors: lines after a correction take values derived from the word
  stream, not `original + delta`.
- A test asserts line 0 cannot be moved and that a lead offset lands in `leadIn`.
- A test asserts the emitted file carries `linesHash` and the hand-set provenance.

### The acceptance case for page 2 — the pimiento canary

**Page 2 is accepted when a user who has never read the CLI docs can resolve line 3 of pimiento and reach a correct emit.** Not "can edit a timestamp" — can resolve *this* line, unaided.

The fixture is real and already on disk, so this is reproducible rather than hypothetical:

| | |
|---|---|
| song | `songs/pimiento.json` |
| audio | `songs/audio/pimiento.m4a` |
| bands | **HIGH 18 · REVIEW 1 · FAIL 0** (19 lyric lines) |
| measured lead-in | **8.92 s** |
| the flagged line | **line 3**, `desde niño quiere más que latir`, band **REVIEW**, signal **`lead-fallback`** |
| candidate start | **37.54 s**, raw audio-clock seconds |

**Why this is the acceptance case and not an invented one.** Jorge ran the canary by hand on 2026-08-15. The alignment itself was fine — 18 of 19 lines HIGH, nothing failed. What he could not do was **act on the one flagged line through the CLI**. The report told him which line to check and why; it did not give him a way to judge and fix it in the same place. He promoted the timeline with line 3 still unresolved, which is where it sits today. That gap — a correction loop that identifies but cannot resolve — is the entire reason B20 exists. If page 2 does not close it for this exact line, it has not been built.

**The specific ambiguity that must not survive: is `LINE` 0- or 1-indexed?** The CLI never answered this for Jorge, and it is not answerable from any user-facing text — `README.md`, `docs/`, and every `--help` string are silent on it. The only place the base is stated at all is the *out-of-range error* in `parse_anchor_overrides` (`"song has N lyric lines (0..N-1)"`), which a user sees only by first getting it wrong.

For the record, it is **0-indexed**, and this canary proves it arithmetically rather than by assertion. The promoted timeline is cue-relative, so raw = cue-relative + `leadIn`:

- entry **3** → `28.62 + 8.92 = 37.54` ✅ matches the candidate start
- entry **2** → `20.54 + 8.92 = 29.46` ❌

So "line 3" is index 3, the **fourth** line — `desde niño quiere más que latir`, not `Con el corazón afuera nací`.

**This is a UI requirement, not a documentation one.** Page 2 must make the identity of a line unmistakable without the user knowing the base at all: show the line's **text** next to any number, and let the row be confirmed by ear through the seek button. A page that shows a bare index and expects the user to know the convention has failed in exactly the way the CLI failed — it just fails in a browser instead of a terminal.

---

## 7. Open

- ~~Does `serve` ship in `v1.0.0` or after? The pimiento canary gates 1.0.0.~~ **Settled 2026-08-15
  — `serve` ships *in* `v1.0.0`. The gate moved.** It used to be "the canary runs clean end to
  end". The canary has now run, and it ran clean enough to promote — 18 HIGH, 1 REVIEW, 0 FAIL —
  so on the old wording the gate is met. But pimiento's timeline is promoted **with line 3 still
  unresolved**, because the CLI gave no way to resolve it (§6). Cutting `v1.0.0` on that would
  certify a loop that identifies problems it cannot fix, which is precisely the thing the
  positioning claims Bombista is *for*.
  **`v1.0.0` is therefore now gated on two things: `serve` shipping, and line 3 of pimiento being
  fixable through it.** The canary is no longer the gate — it is the test case for the gate.
- Installation is still `pipx install bombista` — one line, but a line. A packaged binary is the
  answer if that ever needs to go, **not** a hosted service.
- `changopepper.com/tramoya/bombista` remains a shopfront: what it does, the *Río de Sal* worked
  example as a clickable page, install instructions. It is no longer a dependency of this item.

---

## 8. Page 2 — what it looks like

Design session 2026-08-15. §3 says what page 2 must **do**; this says what it **is**. §3, §4 and §6
stand — the four states, the invariants, re-anchor-never-ripple, 0-indexed lines, `serve` in
`v1.0.0`, the pimiento acceptance case. §8.6 records the one place this section departs from §3's
prose, and why.

Reference: `docs/mockups/bombista-serve-page2-mockup.html` — pimiento's real 19 lines, with every
re-anchor outcome taken from `anchoring.py` run against the real `asr-words.jsonl`.

**The governing decision, Jorge's, 2026-08-15: the list of lines is the interface.** A first pass put
a lead-in panel, a "needs attention" card, an editor pane, a re-anchor banner and a JSON preview
around it. All five are cut. The user judges the timeline by reading the lines and their times and
hearing the audio; anything that explains, repeats or restates that is weight. What survives is the
player, the list, one popup, and one button.

### 8.1 The stack — the smallest thing that works

| decision | why |
|---|---|
| **`http.server.ThreadingHTTPServer` + `BaseHTTPRequestHandler`**, stdlib | Bombista's runtime dependencies are `click` and `faster-whisper`. A web framework would be the third, and the first that exists only to serve one user one page on one loopback socket. |
| **One page, inline CSS and JS**, built by string composition as `writers.py` already builds B16's page | A working, tested precedent for exactly this already sits in the repo. |
| **Vanilla JS, no framework, no build step** | No bundler to maintain, no `node_modules` in a Python repo, no lockfile to keep current on a tool that must still `pipx install` cleanly in 2030. The whole page is ~300 lines. |
| **`fetch` to `POST /api/reanchor` and `POST /api/emit`** | The server owns the anchoring; the page owns none of it (invariant 1). |

**The offline guard does not transfer.** B16's page is asserted to contain *zero* external references
because it is a loose file that must work from a USB stick in five years. `serve`'s page is served by
the running process and talks to it over loopback — `fetch(` is correct there. Keep the assertion
scoped to `write_html_review`'s output, or a future agent will "fix" it.

**Share the vocabulary, not the page.** Extract the signal glosses (8.3) so the markdown report,
B16's page and `serve` say the same words. Do not merge the templates: one is a frozen artifact, the
other is live.

### 8.2 The page, top to bottom

1. **Provenance, open by default** — audio, sha256, model, when, measured lead-in, in two quiet
   columns of dim mono under a hairline. Jorge, 2026-08-15: collapsed, the summary line was a
   run-on that *"is not understandable"*. The first pass collapsed it because it was loud; the
   answer was to make it quiet, not to hide it. A block that recedes can stay open, and open it
   is legible at a glance. This is the general rule of §10.3 applied: **quiet, not hidden.**
2. **Sticky: the player, and the three band counts.** Nothing else is pinned.
3. **One line of instruction, immediately above the table** — *Click a **START** time to adjust it.
   Press and hold to move fast — a whole missed word is about a second.* Jorge, 2026-08-15: it was
   in the page lede, three elements away from the thing it describes, where it read as a subtitle
   rather than as an instruction. The lede is now just *19 lines · raw audio-clock seconds*.
   This is the page's only piece of help copy and it sits where the hand already is.
4. **The 19 lines.** Always all of them, never filtered — filtering to the flagged rows would hide
   the thing the page exists to show, which is what an edit did to the rows that were *not* flagged.
5. **`Confirm timeline →`.**

That is the whole page.

### 8.3 The row

`rail · ▶ · line N · text · start · dur · band · why`

- **The index never appears alone.** §6 makes this a UI requirement: every row carries `line 3` *and*
  `desde niño quiere más que latir.`, and ▶ confirms it by ear. A user who does not know the base can
  still act correctly.
- **Times are raw audio-clock seconds**, as in the QA report and `--anchor`. The cue-relative
  conversion happens on emit and is never shown — two clocks on one page is a real risk, and only
  one of them is ever visible.
- **`clean-anchor` is not printed.** Eighteen rows repeating the word for "nothing to see" is
  chrome wearing the costume of information, and the dim HIGH chip already says it. The `why`
  column is empty on clean rows, so the only text in it belongs to the line that needs you. The
  markdown report still prints every signal — it is an audit document and has different duties.
- **HIGH is deliberately dim** (§10.3). Eighteen of nineteen rows are HIGH and none of them need
  attention; a bright green chip repeated eighteen times is the single loudest thing on a page
  whose whole job is to point at one line.
- **A flagged row differs three ways:** the band tint, the coloured band chip, and the signal
  **spelled out in plain language** under the token. `lead-fallback` means nothing to a user who has
  not read the source; *"the first word was not recognised, so this line was anchored on its second
  word — the start is usually late by one word"* tells them where to listen. **These glosses belong
  in `anchoring.py`, beside the signal names**, so the markdown report and B16's page can print them
  too. All three print bare tokens today.

### 8.4 The start time is the control

Clicking a start time opens a popup containing **one stepper and nothing else**:

```
[ − 0.05 ]   37.54 s   [ + 0.05 ]
```

No bounds text, no delta readout, no explanation, no buttons. Escape or a click outside closes it.
Arrow keys nudge while it is open. Bounds are the neighbouring lines and are enforced by silently
clamping — a stated bound is one more sentence on a page that should have almost none.

**Press and hold auto-repeats** (380 ms, then every 45 ms). This is what replaces the first pass's
*Set from playhead*, and it is load-bearing rather than a nicety: line 3's error is **1.22 s**, which
is 24 separate presses. A held second crosses it. The finding of the onset is done by ear with the
player — that is what the player is for — and the stepper only has to be able to reach where the ear
already went.

**Judging is the player's job, not the page's.** No per-line loop control, no playhead capture, no
hint text. Play, listen, click, hold, listen again.

### 8.5 How a re-anchor shows itself

There is **no banner**. Three things carry it, all inside the list or the chrome already present:

| fact | where |
|---|---|
| the current bands, whole-song | the **HIGH / REVIEW / FAIL counts** in the sticky bar — always visible, so 18/1/0 → 19/0/0 is the confirmation that the recompute ran and helped |
| what the last edit changed, per line | on the row: `HIGH → REVIEW`, old chip faded, new chip solid, a `RE-ANCHORED` badge, and the previous value struck through above the new one |
| hand-set provenance | a `HAND-SET` badge, permanent, with the machine value struck through |

And around the edited row: a left rail, solid above and dashed below, plus one short line —
*below here, re-derived against the audio — above, unchanged*. The rail alone is undiscoverable; one
line of text is the floor.

**Known trade-off, taken deliberately.** The first pass announced the *null* result in words — "15
lines below were re-derived and came back identical" — on the argument that silence is
indistinguishable from not having recomputed. The counts row now carries that load implicitly. It is
weaker, and it is the right trade for a page this quiet; revisit only if a run ever leaves the user
unsure whether an edit took effect.

**Timing: debounced 250 ms** after the last press, not per press and not behind a button. Per press
repaints the list during exactly the interaction that matters; a button leaves the page showing a
state that is no longer true.

Two consequences the implementation must handle, both found by building it:

- **Rows must not change height when a value changes.** The struck-through previous value needs its
  line reserved always, or the row grows mid-press and the control moves out from under the cursor.
- **The popup must not be repositioned while a button is held**, for the same reason.

### 8.6 Line 0 — the one departure from §3, flagged for confirmation

§3 says *"Line 0 has no stepper"*, because a stepper there **silently** breaks the v2 contract. Here,
line 0's start **is** the control for the lead-in: its number is rendered in the edit colour, its row
is labelled `line 0 / lead-in`, and its popup carries the caption **lead-in · moves the whole song**.

- Invariant 3 is untouched: line 0 is still `0.00` in the emitted timeline; the offset is still
  banked in `leadIn`.
- The two behaviours stay different: moving line 0 shifts every line together and **re-anchors
  nothing**; moving any other line re-anchors everything below it. Nothing is silent — different
  colour, different label, different caption, different effect.
- What it costs: §3 wanted *different widgets*, and this is the same widget shape with a different
  label. It also removes an explicit lead-in control from the page, which is where B6's global nudge
  was going to live.

**Jorge to confirm.** The alternative is a lead-in row above the table, which is one of the panels
this pass cut.

### 8.7 Confirming

One button: **`Confirm timeline →`**. No preview, no JSON, no acknowledgement. B19's surviving clause
holds — it must be pressed **even when nothing was flagged**, which is what converts review from
skippable into structurally required. The user confirms against the list they have just read; the
page does not restate it back to them.

What the press writes is unchanged from §3: always a new file, never an input path, carrying
`linesHash` (B4) and the hand-set provenance — which lines, their machine values, when.

### 8.8 What the fixture proved

Measured against the real `asr-words.jsonl`, not estimated:

- **Line 3's true onset is 36.32 s.** The ASR heard *"Este"* for *"desde"* at 36.32; anchoring fell
  back to the second token *"niño"* at 37.54. The error is exactly one word, **1.22 s** — the number
  the press-and-hold exists for.
- **Any correction in `[29.47, 39.86]` leaves all 15 lines below identical**, including 36.32. The
  right answer is the quiet case.
- **At ≥ 39.88 s, line 4 flips HIGH → REVIEW (`gap-outlier`)** — the gap to line 4 falls below a
  third of the song's median gap. A real threshold inside the allowed range, and the demonstration
  the mockup exists for.
- Beyond the range — ≥ 43.36 line 4 also moves, ≥ 44.30 it `no-anchor`s — the neighbour bounds make
  these unreachable. The bound is doing real work.

### 8.9 Open

- **One correction at a time?** The mockup carries one; `anchor_lines` already takes a mapping. The
  rail and the divider would then have to key off the *earliest* edited line, not the last one
  touched. Decide before building.
- **Line 0 as the lead-in control** — 8.6, Jorge's to confirm.
- **Where the audio comes from.** `serve` knows the path from page 1, so serve the bytes on a
  loopback route rather than a relative `src`. B16's page needs the relative path because it is a
  loose file; `serve` does not.

---

## 9. Pages 1, 1.5 and 3 — what they look like

Design session 2026-08-15, same pass as §8. §3 already says what these pages must **do**; this is the
form. They are cheap because page 2 is settled — that was the premise of designing it first. Same
mockup: `docs/mockups/bombista-serve-mockup.html`, hash-routed (`#1`, `#1.5`, `#2`, `#3`).

### 9.1 The masthead — on every page

```
BOMBISTA                                             v0.9.0
Forced-alignment triage                       A TRAMOYA tool
                                              by CHANGO PEPPER
────────────────────────────────────────────────────────────
```

Jorge, 2026-08-15: *"I miss a title Bombista and that it's featured by Tramoya. Otherwise 'the
format Tramoya promotes' feels out of context."* He is right, and the fix is small — the phrase on
page 1 was doing brand work with no brand on the page to attach to.

Wordmark 800-weight uppercase, tagline in mono underneath, the attribution right-aligned in three
mono lines with **Tramoya** in clay. A 3px rule under the whole thing. It sits above the step bar on
every page, and it is the only decoration in the interface — it earns its place by making the rest
of the page's vocabulary legible.

### 9.2 The step bar — on every page

```
┌──────────────┬───────────────┬────────────────┐
│  1  INPUT    │  2  REVIEW    │  3  OUTPUT     │
└──────────────┴───────────────┴────────────────┘
```

Jorge's request, 2026-08-15; renamed the same day from *Set up · Review and correct · Emit*. One
hard-bordered strip divided by 3px rules — not free-floating pills, which is the friendly-wizard
shape this design is not. Current segment filled clay; completed segments carry a green numeral
block. **Every step is clickable**, including backwards: going back to step 1 from step 2 is how you
re-run with a different model, and going back to step 2 from step 3 is how you fix something you
noticed while reading the file. Nothing is destroyed by moving between them.

Page 1.5 has no segment of its own — it is a *state* of step 1, and inventing a fourth segment for
it would say the flow has four steps when it has three. Its heading is **Processing**.

### 9.3 Page 1 — input

Heading **Input song**, lede *Two files. Two defaults. Nothing typed.*

**No free text anywhere except the title**, and the title only appears on the plain-text branch,
where there is no other source for it. Everything else is a file picker or a dropdown — §3's rule,
taken literally. Revised 2026-08-15 on Jorge's review; the governing note is his, and it is the same
note that governs page 2: *a lean interface, few options for this first version.*

A flat list of labelled rows separated by 3px rules, one control each, no panels. **Every row
carries a mono caption under the control** — this is the one place the page explains itself, because
these four values decide everything downstream and the user sets them before they have seen any
output to learn from:

| row | control | caption under it |
|---|---|---|
| Lyrics | file picker, then **the file name alone** | *Plain text (`.txt`), or a Song Performance JSON (`.sp.json`) — the format Tramoya promotes.* Plus a link to a worked example. |
| Media source | file picker, then the file name alone | *MP3 · M4A · WAV · FLAC · MP4 · MOV. The audio track is read from video too.* |
| Language | dropdown, default `es`, **options constrained by the file** | *The language on the recording and the lyrics file.* — and nothing more. The constraint is enforced, not explained (§3). |
| Model | dropdown: *medium — ~50 s per song* / *small — ~20 s* / *tiny — ~5 s* | ***Runs on your local machine. Nothing is uploaded.** A bigger model recognises more of the sung words, so fewer lines come back flagged — and it takes longer. Change it and come back if a run reads badly.* |

Then one button: **`Process song →`**, primary weight — paper fill, clay shadow, the only filled
button on the page. *`Align →`* was too quiet for the one control that starts a 50-second job.

**Four decisions from Jorge's review, and why each holds:**

1. **The path is never shown, only the file name.** `songs/pimiento.json` is the tool's business;
   `pimiento.sp.json` is the user's. A path in a picker's result slot is a leak of the filesystem
   into a page that is otherwise about a song.
2. **The branch dropdown is gone.** A first pass had `as CP song JSON / as plain text` beside the
   picker. The extension already answers it, and a control that restates what the file said is a
   control that can disagree with the file.
3. **No output folder, no *Also write* checkboxes.** See §3. What gets produced is decided in §9.4
   and offered as downloads; the app does not choose where a download lands.
4. **The model row must say it runs locally.** The single most common wrong assumption about a
   browser interface is that a server somewhere is doing the work. §1 says this tool must never
   become that; the page should say so where the user is choosing the thing that would have been
   the API call. The wording is **"Runs on your local machine"** — Jorge's, 2026-08-15; *"this
   machine"* is ambiguous about whose.
5. **The language caption states the fact, not the rule.** A first pass explained the whole
   constraint in the caption. Cut to *"The language on the recording and the lyrics file"* — the
   dropdown already enforces the rest by disabling what it cannot offer, and a caption that
   explains a guard the user will rarely hit is a caption teaching an exception.

**The plain-text branch (§5) grows the form in place**, it does not open a second page:

- **slug** — derived from the filename, shown read-only.
- **title** — the one text input on the whole flow.
- **tempo** — a dropdown that starts at *— not set —*, with a warning block beside it in the REVIEW
  colour: *Tempo is never measured. Bombista answers when a line happens, not in which beat. Type the
  value from the Ableton project that produced this audio, where it is exact.* Rules 4 and 5 stand,
  and B14 was dropped for this reason; the UI has to make it obvious this is a value Jorge supplies,
  never one the tool derived. **Left unset, the key is omitted from the emitted file entirely** —
  see §10.2.1 and `songs@c5adf65`.
- **what the normaliser will strip, shown before the run** — *3 lines will be removed before processing
  — 2 blank, 1 section marker (`[Estribillo]`). 19 lyric lines remain.* §3 is explicit that this
  comes before, not after: a silent line-count change surfaces much later as a `promote` refusal,
  which is a bad place to learn it.

### 9.4 Page 1.5 — the run

A state, not a spinner. Two rows, one per phase, each with a dot and an elapsed readout:

```
●  Transcribing the audio          12.4 s of ~50 s
○  Anchoring the lines                       —
```

The dot pulses while running and turns green when done. Below them, one button: **`Cancel`**, which
actually cancels and returns to step 1.

And one line of text, which is the whole ergonomics of the correction loop and therefore earns its
place: *Transcription is the slow part and it is cached. Coming back here from step 2 reuses
`asr-words.jsonl` and takes well under a second.* The difference between a 90-second wait and a
0.07-second one is why anyone corrects until it is right instead of settling.

### 9.5 Page 3 — output

Heading **Output**, lede *A new file. Nothing you loaded was modified.* Read-only: nothing on this
page changes anything.

Rewritten twice on 2026-08-15, both times on Jorge's review. **First pass cut two blocks** — the
*Ready to write `pimiento-timeline.json` into `staging/pimiento/`* line and the three-item file
list beneath it; both described a write to a folder the app no longer chooses (§9.3, decision 3).
**Second pass rebuilt the payload** against the real `songs/*.json` format — see §10.2, which is
the substantive change and governs this section.

Top to bottom:

1. **One caption**, mono: this is your SP JSON — the same file you started from, with the timing
   keys filled in. Bombista wrote five of them: `linesHash`, `timelineSignedOff`,
   `timelineVersion`, `leadIn`, `timeline`. Entry 0 is `0.00` and the lead-in is banked. Everything above them is passed through
   untouched, *which is why `lyrics` is folded here*. The bands, the signals and the record of what
   was set by hand are in the **report**, not in the song.
2. **The filename**, quiet, above the code window: `pimiento.sp.json`.
3. **The JSON itself, read-only, in full**, in a bordered code window. **No fold, no expand
   control** — a second pass added one and Jorge cut it: *"not needed"*. He is right. The window
   scrolls, the file is the file, and a control whose only job is to shorten a scroll is a control
   that has to be understood before it can be used. The earlier argument for folding — that 19
   lines × 4 languages buries the timing keys — is answered by the caption saying which five keys
   Bombista wrote, not by hiding the rest.
4. **Three downloads, side by side:**

| button | what it is | sign-off? |
|---|---|---|
| **`Download JSON file`** — primary | the whole SP JSON above, the file Tramoya reads | **yes** |
| `Download timeline only` | the five timing keys only — `linesHash`, `timelineSignedOff`, `timelineVersion`, `leadIn`, `timeline` — to paste into a song file you already maintain | **yes** |
| `Download report` | bands, signals, provenance and every hand-set line, as markdown | **no** |

  Each carries one mono line under it saying which is which. B19's clause attaches to the two JSON
  downloads: pressing either records the sign-off band — *Signed off 2026-08-15 23:31 · your inputs
  untouched* — and pressing neither means the run was never signed off. The report is excluded on
  purpose: it certifies nothing and taking it is not a decision.
  **The buttons do not disable after the press.** Wanting the timing block as well as the whole file
  is normal; the sign-off is recorded once and is not a budget.

5. **`← Back to review`**, because noticing something in the JSON is a legitimate reason to go back.

**Why `timeline only` is the five keys and not just `timeline`.** Someone who maintains a song file
by hand wants the block they can paste in — and `timeline` without `linesHash` is the exact
unguarded artifact B4 exists to prevent, while `timeline` without `timelineSignedOff` cannot say a
human ever read it. Handing over a bare array would make the convenient path the unsafe one. The
five keys travel together or not at all.

### 9.6 Open

- Page 1's file pickers are native `<input type="file">` in the mockup. `serve` runs on the user's
  own machine, so the *server* needs a real path, not a browser File object. Either a small
  loopback route that lists the filesystem, or accept the browser's file and stage it — decide in
  the PR. This is the only place the local-tool-in-a-browser shape actually bites, and cutting the
  output-folder picker (§9.3) reduced it from three controls to two.
- **Where the SP JSON format is documented.** Jorge, 2026-08-15: likely a section on the **Tramoya
  tab of changopepper.com**, which is also where page 1's *See an example* link should point. Not a
  dependency of B20 — the link can go to the repo until the page exists — but the format needs one
  canonical home before anyone outside this repo is asked to produce one.
- Whether `Cancel` on page 1.5 must also kill the faster-whisper worker or just abandon it.
- Pages 1, 1.5 and 3 have had **three rounds of Jorge's review** (2026-08-15) and this section
  reflects them. Page 2 is signed off. `timelineSignedOff` and the `title_translations` correction
  are **settled** (§10.2). **The only design item still open is line 0 as the lead-in control,
  §8.6.** Everything else in this spec is buildable as written.

---

## 10. The vocabulary, the format and the visual language

Added 2026-08-15, revised the same day after Jorge's second review. §8 and §9 say what the pages
contain; this says what things are called, what the file actually is, and what the whole thing
looks like.

### 10.1 Names, and what each one replaced

| now | was | why it changed |
|---|---|---|
| **Input · Review · Output** | Set up · Review and correct · Emit | *Emit* is a compiler's word. *Alignment* named the mechanism, not the user's move. The triad now reads as one sentence and step 3's name is literally true — the page is three download buttons. |
| **Song Performance JSON**, short **SP JSON**, extension `.sp.json` | CP song JSON / song JSON | *CP* was a private initialism. Plain *song JSON* was already ambiguous in this spec — it named both the canonical lyrics file and the merged output. **Song** is the content; **Performance** is the timing half that makes the format worth having. See §10.3 — the rename is the important part of it, but not the whole of it. |
| **Media source** | Audio | The picker takes video too, and the audio track is read out of it. *Audio* told the user to convert first. |
| **Process song →** | Align → | It starts a job that takes the better part of a minute. The button's weight and its verb both have to say so. |
| **Processing** | Aligning | Follows *Process song*. |
| **Runs on your local machine** | Runs on this machine | *This machine* is ambiguous about whose, on a page served over HTTP. |

### 10.2 The format — the SP JSON **is** the Chango Pepper song JSON

**This is the substantive correction from Jorge's second review, 2026-08-15.** A first pass invented
a shape — `format: "song-performance/1"`, a flat `lines` array of strings, a `review` block, a
`provenance` block. Jorge: *"Make it consistent with Chango Pepper songs JSON format. Right now it
is not connected at all."* He is right, and the fix is not a tweak to the shape. **There is no new
format.** `songs/*.json` already exists, already carries lyrics in four languages, already carries
`timelineVersion`, `leadIn` and `timeline`. *Song Performance JSON* is the **name** for that
existing format — the thing it never had — not a second one beside it.

Verified against the real `songs/pimiento.json`, whose top-level keys in order are:

```
title · artist · notes · title_translations · tempo · intro · lyrics
  · timelineVersion · leadIn · timeline
```

**Bombista owns exactly five keys** and passes everything else through byte-for-byte:

| key | who writes it | note |
|---|---|---|
| `linesHash` | **Bombista** | New. B4's guard, over the canonical lyric lines. Sits between `lyrics` and `timelineVersion` — the boundary between what it guards and what it protects. |
| `timelineSignedOff` | **Bombista** | New, settled 2026-08-15. ISO timestamp, written when a JSON download is pressed. The whole of §3's provenance clause, in one scalar; the detail is in the report. |
| `timelineVersion` | **Bombista** | `2`. Already in the format. |
| `leadIn` | **Bombista** | `{ durationSec, source, confidence, apply }`. Already in the format. |
| `timeline` | **Bombista** | `[{ start, end }]`, cue-relative, entry 0 at `0.00`. Already in the format. |
| everything else | the song file | `title`, `artist`, `notes`, `title_translations`, `tempo`, `intro`, `lyrics`. Read, never written. |

Three consequences, all load-bearing:

- **`tempo` is passed through, never touched.** It is a real key with a real value in
  `pimiento.json` (`{bpm: 66.67, numerator: 6, denominator: 8, countInBars: 1}`). Rules 4 and 5 say
  Bombista never derives it; the plain-text branch (§5) asks for it because a `.txt` has no source
  for it, and even there the user supplies it. Bombista reading a tempo it did not compute is fine.
  Bombista writing one is not.
- **`lyrics` entries are objects, not strings** — `{es, en, fr, nl}`. The first pass flattened them
  to strings, which would have destroyed every translation on the round trip. This is the concrete
  damage the "not connected at all" note was pointing at.
- **The one open question in the format is `intro`.** It exists in `pimiento.json` and in
  `_template.json`, it is a translated block like a line, and it is **not** in the `lyrics` array —
  so it has no timeline entry and `linesHash` does not cover it. Bombista passes it through and
  ignores it. Flagged rather than solved: if `intro` is ever projected, it needs a timeline entry
  and the line count changes, which is a B4 problem.

### 10.2.1 Two shapes, one format

A `.txt` produces a file that did not exist; an `.sp.json` produces the file you handed in. Same
format, different amounts of truth available. **Jorge's sketch of the from-scratch shape,
2026-08-15, is the contract:**

| key | pass-through (`.sp.json` in) | from scratch (`.txt` in) |
|---|---|---|
| `title` | as given | from page 1's one text field |
| `artist` | as given | `""` — Bombista does not know it |
| `notes` | as given | `""` |
| `title_translations` | as given (`en`/`fr`/`nl`) | `{ "<chosen lang>": "<title>" }` — the only one that exists |
| `tempo` | as given, **never rewritten** | **omitted** unless page 1 supplied a real value — never a null scaffold |
| `intro` | as given | **omitted** — a `.txt` has no source for it |
| `lyrics` | as given, all four languages | `[{ "<chosen lang>": "…" }]` — one language, the one that was sung |
| `linesHash` · `timelineSignedOff` · `timelineVersion` · `leadIn` · `timeline` | **written** | **written** |

**Why `tempo` is omitted and not a null scaffold — this was got wrong once, do not get it wrong
again.** A design pass argued for a null scaffold on the grounds that a key present with nulls says
*this belongs here and I left it for you*, while an absent key says nothing. **That argument is
already settled the other way, in `songs@c5adf65`, and Jorge's reasoning there is better:**

> Removed outright — not replaced with a flag or a null. […] `tempo.bpm` has two consumers that
> need opposite things when the number is made up. It is the scaling denominator in
> `performedTempo.ts`, and it also drives the visual pulse. A placeholder that keeps the pulse
> looking sane is the wrong denominator for scaling, and a value chosen to make scaling behave is
> the wrong pulse — so there is no single setting, and no live toggle, that corrects for both. The
> block can only be right when the number is real. […] Pregonero already degrades safely when the
> block is absent: no pulse, no count-in, and scale pinned to 1.

`null` is not neutral once a consumer reads it. **Absent is the honest state, and Pregonero is
already built for it.** So: `tempo` appears in a Bombista-written file only when page 1 supplied a
real number, and `songs/_template.json` does not carry the block either — a template that ships a
placeholder manufactures the exact thing c5adf65 deleted, one song at a time.

**Where this shape came from.** Jorge pasted it, 2026-08-15, after the first pass produced something
"not connected at all" to the real files. Two deviations from his sketch, both deliberate, both
confirmed by Jorge the same day: `timelineVersion` is kept (his sketch omitted it, but the v2
contract needs it and the real files carry it), and `title_translations` is keyed by the *chosen*
language rather than hard-coded to `es`, so a `.txt` in another language does the right thing.

**`songs/_template.json` was wrong and has been corrected** (Jorge's call, 2026-08-15). It seeded
`title_translations` with `en`/`fr`/`nl` only, assuming a Spanish base — while `intro` and `lyrics`
in the same file already carried all four languages including `es`. One file cannot hold two
opinions about whether the base language is a translation of itself. The template now reads:

```json
{
  "title": "",
  "artist": "Chango Pepper",
  "notes": "",
  "title_translations": { "es": "", "en": "", "fr": "", "nl": "" },
  "intro": { "es": "", "en": "", "fr": "", "nl": "" },
  "lyrics": [ { "es": "", "en": "", "fr": "", "nl": "" } ]
}
```

**One change: `es` added to `title_translations`.** Nothing else. A first attempt also added a
`tempo` scaffold and that was wrong — see the tempo note above; the template must not ship the
placeholder c5adf65 removed. The timing keys are likewise deliberately absent: a human starting a
song does not write them, Bombista does.

**The catalogue was backfilled to match, 2026-08-15.** All 13 song files in `songs/` now carry
`es` as the first key of `title_translations`, set to the file's own `title`. **One line per file,
14 lines in total including the template. Nothing else was touched** — no key reordered, no value
changed, no key added. A dump-and-compare confirmed every file round-trips byte-for-byte before
the edit, so the diff contains only the intended lines. **The commit is Jorge's**, in the `songs`
submodule.

`don-bonifacio`, `la-pajita` and `quien-fuera` still have **no `tempo` key**, and that is correct
(c5adf65). A first pass at this backfill added a null scaffold to those three and it was reverted
before anything was committed.

Note one thing the backfill deliberately did **not** touch: `tempo` sits *before*
`title_translations` in some files (`libertad`, `tragedia-de-cerdo-asado`) and *after* it in others
(`pimiento`). Both are valid — nothing reads these by position — and normalising would have turned
a 14-line diff into a rewrite of every file. Bombista preserves whatever order it is given.

**`linesHash`: stays in the song file. Jorge asked; this is the judgement.** Its whole job is to
detect that the lyrics in *this file* no longer match the timeline in *this file*. Separated from
what it guards it is decorative — a hash in a report cannot stop you copying a stale timeline over
a song that gained a line. It should *also* appear in the report, for the audit trail, but the
song file is where it is load-bearing.

**Everything else moves to the report, with one exception.** Jorge, 2026-08-15: *"All the rest
corresponds to the report, not to the song."* Agreed — bands, signals, ASR provenance, model,
sha256 and the per-line hand-set record all leave the song file for `pimiento-qa-report.md`. A song
file is a song, and every consumer downstream would otherwise have to step around a QA blob.

**The exception, settled 2026-08-15 (Jorge: yes): one scalar, `timelineSignedOff`.** An ISO
timestamp beside `linesHash`, and nothing else. Without it, §3's clause — *a machine timeline and a
reviewed one are indistinguishable* — becomes unenforceable the moment the file leaves the folder
its report is in: hand someone a `.sp.json` and there is no way to tell whether a human ever looked
at it, and `promote` cannot refuse an unreviewed timeline. One string buys that back at a cost of
one line.

**So Bombista owns five keys, not four:** `linesHash`, `timelineSignedOff`, `timelineVersion`,
`leadIn`, `timeline`. All five travel together in the "timeline only" download, for the same reason
the hash does — a timing block that cannot say whether it was reviewed is the artifact this whole
item exists to stop shipping.

**Where the format is documented:** a section on the Tramoya tab of changopepper.com (Jorge,
2026-08-15). Tracked in §9.6, not blocking B20. It is also the target for page 1's *See an example*
link.

### 10.3 The skin — brutalist, ink ground, quiet register

Jorge's call, 2026-08-15: `serve` is a Chango Pepper tool and should look like one — **but black
predominant, not the site's paper**. Then, on seeing it: *"a lot of contrast… things compete with
your attention which are not relevant for the main flow."* Both notes are the same note, and the
second is the governing one.

**Contrast is a budget.** The page has one job — put a musician's eye on the one line that needs
judging and their hand on the control that fixes it. Everything else (navigation, provenance,
structure, the eighteen rows that are fine) has to sit *below* that in the visual order, not merely
be smaller. The first ink pass spent the budget on chrome: 3px paper borders on every container,
filled numeral blocks in the step bar, hard paper shadows under every button, bright green chips
eighteen times. All of it read as important because all of it was loud.

The correction, and it is a rule rather than a set of tweaks: **structure is hairlines, colour is
reserved, and the accent marks one thing at a time.**

| was | now | why |
|---|---|---|
| 3px paper borders everywhere | **1px `--line` / `--line-2`**, paper borders nowhere except where a thing is genuinely active | a border is a wall; a hairline is a boundary. Most of these were boundaries. |
| hard offset shadows on every button | **no shadows**; buttons are a hairline that brightens on hover | the shadow was decoration pretending to be affordance |
| paper-filled primary button | **clay-filled** primary | the one action on the page, warm, unmistakable, and not a white slab |
| step-bar numerals in filled green/paper blocks | **plain dim numerals**, current segment clay on `surface-2` | navigation should be findable, not announced |
| `h1` at `clamp(1.9rem, 4vw, 3rem)` | **`clamp(1.35rem, 2.2vw, 1.7rem)`** | the heading names the page; it is not the content |
| HIGH `#6cc08b` bright | **HIGH `#4f7d63` muted** | eighteen of nineteen rows are HIGH; a bright chip repeated eighteen times outshouts the one row that matters |
| `clean-anchor` printed 18× | **not printed** | see §8.3 |
| provenance collapsed behind a run-on summary | **open, two dim columns** | quiet, not hidden — §8.2 |
| `Expand lyrics` control on page 3 | **cut** | §9.5 |

**The loudest object on the page is the stepper popup**, and that is correct: it appears only when
the hand is already there, and it is the only place a value changes.

It borrows changopepper.com's vocabulary on an inverted ground:

| token | value | used for |
|---|---|---|
| bg | `#121211` | the page |
| surface | `#1a1a18` | code windows, the mock bar |
| surface-2 | `#232320` | the current step, the row being edited, the popup |
| paper | `#e6dfd1` | body type and the text of the line |
| dim | `#8b8478` | captions, labels, secondary button text |
| dimmer | `#635d54` | provenance values, table headers, indices |
| line / line-2 | `#2c2a26` / `#423e37` | row rules / structural rules and control borders |
| clay | `#d98b7a` | the accent: the primary button, the current step, the open time control, the hand-set badge, the Tramoya mark |
| clay-dim | `#8f5a4e` | the re-anchor rail, link underlines, line 0's lead-in mark |

Rules: **1px borders** for structure, **no border radius anywhere**, **no shadows** except the
popup's drop (it floats, so it casts). **No easing**: transitions are removed, not eased, and the
page-1.5 phase dot blinks on `steps(2)` rather than fading. Labels are **mono, uppercase, `.13em`
tracking**; headings are 800-weight uppercase but small. `color-scheme: dark` on `:root`.

**The native `<audio>` element is the one thing that refuses the palette.** Chromium renders it
light regardless of `color-scheme`, which put the brightest object on page 2 directly above the
table. It is inverted back down (`filter: invert(.92) hue-rotate(180deg)`, `opacity: .72`, full
opacity on hover). A custom transport would be cleaner and is not worth the code today; if the
filter ever breaks, build one rather than accepting the light slab.

**The bands were re-tuned twice** — once for the dark ground, once for the quiet register. Now HIGH
`#4f7d63` (deliberately recessive), REVIEW `#e0a437`, FAIL `#ef7a70`, tints `#241d11` and `#251715`.

**No webfont.** The site uses Montserrat; `serve` does not load it. A local-first tool that phones a
font CDN on every launch contradicts §1 more visibly than any feature would, and the brutalist voice
here comes from weight, case, tracking and rules — not from the typeface. System sans for prose,
system mono for everything technical.

**The bands keep their hue — the one deliberate exception.** Everything else obeys ink/paper/clay,
but HIGH / REVIEW / FAIL must be readable across 19 rows in half a second, and shape alone does not
carry that.

**Light mode is dropped, as dark mode was before it.** One palette. The paper variant survives as a
token block in the git history if it is ever wanted; two palettes is two things to keep true.

Two consequences worth recording, both found by building it:

- **The blue edit colour is gone.** `--edit: #4b57c4` had no place in either palette. Clay took its
  jobs — the open time control, the `HAND-SET` badge, line 0's lead-in underline — and reads as an
  accent rather than a second semantic colour competing with the bands.
- **The edited row is `surface-2`, not tinted.** A clay wash behind the open row landed close enough
  to the FAIL tint to be a real misread. The row being edited is marked by the clay-filled time
  control and a lifted background; the band chip keeps telling the truth underneath.
- **Inline `<code>` in captions is `#b0a898`, not clay.** Clay means *the active thing*. A caption
  with six clay tokens in it speckles the page and spends the accent on nothing.
