# B20 — `bombista serve`: a local web interface

**Status:** PRs 1, 2 and 4 merged (#22, #23, #24); **page 2 is PR #26 — open, 454 tests green.**
One cleanup PR (PR 5) left. Jorge's design, 2026-08-14. Supersedes and absorbs
**B19** — the editable review page is page 2 of this flow, not a separate item.

## Where things are in this document

`§` means a section of *this file*. Referenced constantly in the code prompts and in Cowork, so:

| § | what is in it |
|---|---|
| **1** | what `serve` is, and the four things it must never become |
| **2** | the refactor that has to land first (extracting `promote`'s merge) — **done, PR #18** |
| **3** | the four states, one paragraph each: what every page must **do** |
| **4** | the seven invariants |
| **5** | the plain-text branch — what a `.txt` cannot supply |
| **6** | test obligations, and the pimiento acceptance case |
| **7** | open product questions, and what gates `v1.0.0` |
| **8** | **page 2 (Review) — what it looks like.** 8.1 stack · 8.2 the page top to bottom · 8.3 the row · 8.4 the stepper · 8.5 how a re-anchor shows · 8.6 line 0 (settled) · 8.7 confirming · 8.8 the fixture · 8.9 open |
| **9** | **the chrome and the other three pages.** 9.1 masthead · 9.2 step bar · 9.3 page 1 Input · 9.4 page 1.5 Processing · 9.5 page 3 Output · 9.6 open |
| **10** | **vocabulary, format, skin.** 10.1 names · 10.2 the SP JSON is the song JSON · **10.2.1 the two shapes** · 10.3 the skin |
| **11** | **what building it found.** 11.1 corrected in place · 11.2 the lyrics argument · **11.3 the fixture** · 11.4 smaller · 11.5–11.10 what PR 4 found · **11.11 what page 2 found** · **11.12 how the docs nearly lost half of themselves** · **11.13 what the cleanup found** |

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
- ~~**Set from playhead.**~~ **Superseded by §8.4's press-and-hold — flagged 2026-08-16.** The
  requirement behind it stands and is the important part: *a stepper alone cannot span a 1.2 s
  misdetection — that is 24 clicks.* §8.4 answers it with **press-and-hold auto-repeat** (380 ms,
  then 45 ms) rather than a playhead-capture control, on the argument that the onset is found by ear
  with the player and the stepper only has to reach where the ear already went — a held second
  crosses 1.22 s.
  **This is now the only place §8 departs from §3** — §8.6's line-0 departure was resolved on
  2026-08-16 by changing §3 rather than §8. Claude Code caught this one while building PR 2.
  Recorded rather than reopened: if press-and-hold does not close the canary in practice, *Set from
  playhead* is the fallback and this clause comes back.
- **Bounds come from the neighbouring lines**, recomputed live. That is the real allowed interval;
  a fixed range is not.
- **Line 0 has a stepper like every other line.** ⚠ **Reversed 2026-08-16 — see §8.6.** This clause
  used to read *"Line 0 has no stepper"*, on the argument that a stepper there silently breaks the
  v2 contract. It does not: the v2 normaliser runs on emit regardless, banks line 0's onset in
  `leadIn` and writes `0.00`. Invariant 3 is enforced by the normaliser, not by refusing the edit.
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
- The file carries **`linesHash`** (B4) and **`timelineSignedOff`** — the edit provenance reduced
  to one scalar (§10.2); the per-line record lives in the report. Without the
  hash the download routes around B4's guard: you save the file, a line gets added to the canonical
  lyrics upstream, you copy yours over it, and everything after that line misaligns silently —
  the precise scenario B4 exists to prevent. Without the sign-off stamp, a machine timeline and a
  reviewed one are indistinguishable.
- The merge is the extracted one from §2. Page 3 does not hand-roll a write.

---

## 4. Invariants

1. `serve` imports no logic from `cli.py`; both call the same extracted modules.
2. No timestamp control or serialisation step rounds coarser than 0.07 s.
3. Line 0 is always 0 in a v2 timeline; any lead offset lives in `leadIn`. **This is enforced by
   the normaliser at emit, not by making line 0 uneditable** (§8.6).
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
- A test asserts **line 0 can be moved like any other line**, and that its onset lands in `leadIn`
  with entry 0 written as `0.00`. ✅ **Inverted and done, page 2's PR.** This read *"line 0 cannot
  be moved"*; PR 2 implemented the refusal on every route and page 2's PR removed it. Note the
  second half of the old clause did not survive the inversion either: moving line 0 **does**
  re-anchor — it goes through `anchor_lines` like every other override. What is true, and what the
  test now asserts, is that **no raw onset below it moves and no band changes** (§11.11).
- A test asserts the emitted file carries `linesHash` and `timelineSignedOff`.
  ⚠ **Amended 2026-08-16.** This clause used to read *"and the hand-set provenance"*, which §10.2
  later contradicted by moving the per-line record to the report and leaving one scalar in the
  song file. Both could not hold; **§10.2 is the settled position** and Claude Code correctly
  followed it while building PR 2. The per-line record still exists — it comes back on
  `/api/emit`'s response, for the report to render — it is simply not a key in the song file.

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
`v1.0.0`, the pimiento acceptance case. §8.6 is settled — line 0 is not special — so the one
remaining departure from §3 is §8.4's press-and-hold replacing *Set from playhead*.

Reference: `docs/mockups/bombista-serve-mockup.html` — pimiento's real 19 lines, with every
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

1. **Provenance — one quiet line, and that is all.** ⚠ **Reduced 2026-08-16.**

   ```
   Pimiento · pimiento.m4a · faster-whisper medium (es) · measured lead-in 8.92 s
   ```

   Three passes to get here and the third is Jorge's: *"I would refrain from showing any of this
   info to the final user."* He is right, and the earlier reasoning was half-right in a way worth
   recording. Pass one collapsed a full provenance table behind a `<details>` because it was loud.
   Pass two opened it and made it quiet, on the rule *quiet, not hidden* — which fixed the volume
   but not the **relevance**. Nothing on this page should be there unless it helps judge a line by
   ear, and `sha256`, `device`, `toolVersion`, `extractedAt` and the audio duration help with
   nothing while correcting. They answer questions nobody is asking at that moment.

   What survives is the one question a correcting user does ask — *am I looking at the right
   song and the right take?* — which is the filename, the model that heard it, and the measured
   lead-in.

   **Everything removed stays in `<stem>-report.json`.** It is not lost, it is filed. The report is
   the audit artifact and can be as technical as it likes; the page cannot. §1's claim that *the
   report's trustworthiness is the entire product* is about the report, and this is the sentence
   that finally separates the two.
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

### 8.6 Line 0 — settled: it is not special

**Jorge's decision, 2026-08-16, and it closes this section.** In his words:

> We decided that line timestamps can change independently without any ripple effect. Line 0
> should be the same. Changing the start time of line 0 should not trigger ripple changes, so the
> first value should not be considered anything special. It is Pregonero that will make a
> distinction between lead-in and line 0 — it is a performance-time topic, not a
> timeline-extractor one.

**Line 0 gets the same stepper as every other line, with no special colour, no `lead-in` label and
no popup caption.** There is no lead-in widget on this page — not on line 0, not above the table,
not in the sticky bar. All three options considered are dropped.

**Why the v2 contract is not at risk.** §3 used to argue that a stepper on line 0 *"silently breaks
the v2 contract"*. It does not. The normaliser runs on emit no matter how the value got there: it
banks line 0's onset into `leadIn.durationSec` and writes entry 0 as `0.00`. **Invariant 3 is
enforced by the normaliser, not by refusing the edit.** Making line 0 uneditable was defending the
invariant at the wrong layer.

**What moving line 0 actually does**, and it is worth being exact because it looks like two things
at once:

- The **raw** onsets of lines 1–18 do not move. Nothing below is re-derived differently — line 0's
  own word is where it always was, so the forward scan reaches line 1 the same way.
- The **cue-relative** timeline shifts by exactly the amount line 0 moved, because `leadIn` changed
  and every entry is measured from it.

So moving line 0 *is* the global shift, obtained for free, without a second widget and without any
special case. B6's global nudge has a home after all, and it is the same control as everything else.

**The deeper point, which is Jorge's and which generalises:** Bombista measures when things happen
in a recording. *Lead-in* is not a measurement — it is a performance concept, meaningful at the
moment someone counts a band in. That distinction belongs to Pregonero, at performance time. A
timeline extractor that grows a lead-in control is answering a question that was not asked of it.

**Consequence for the code, and it is a reversal — now done.** §3's *"Line 0 has no stepper"* is
struck, §6's *"a test asserts line 0 cannot be moved"* is inverted, and PR 2's refusal is gone.
Line 0 goes through `/api/reanchor` with bounds `[0, line 1's onset)` like any other line. The one
thing the reversal needed that was not written down: **`leadIn.source` has to be able to say a
human set it** — see §11.11.

### 8.7 Confirming

One button: **`Confirm timeline →`**. No preview, no JSON, no acknowledgement. B19's surviving clause
holds — it must be pressed **even when nothing was flagged**, which is what converts review from
skippable into structurally required. The user confirms against the list they have just read; the
page does not restate it back to them.

What the press writes is unchanged from §3: always a new file, never an input path, carrying
`linesHash` (B4) and `timelineSignedOff`. The per-line hand-set record — which lines, their machine
values, when — travels on `/api/emit`'s response into the report, not into the song file (§10.2).

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

### 8.9 Answered while building page 2

- ~~**One correction at a time?**~~ **Many, settled by building it.** `anchor_lines` takes a
  mapping and PR 2's routes already accept one, so limiting the page to a single correction would
  have been a new restriction rather than a simplification. The rail and the divider key off the
  **earliest** hand-set line, exactly as this clause predicted they would have to: everything below
  the earliest edit is what was re-derived.
- ~~**Where the audio comes from.**~~ **A loopback route, `GET /api/audio`, with ranges.** Ranges
  are not optional: a transport that cannot seek cannot be used to judge a line by ear, and judging
  by ear is the whole of §6's acceptance case. One thing this turned up — `serve <staging>
  <lyrics>` has no audio argument, so a session booted straight into a review finds the take
  through the run's own provenance. See §11.11.

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
- ~~**tempo**~~ — **the control is removed, decided 2026-08-16. See §11.5.** Bombista emits no
  `tempo` key at all, on either branch. What remains is a note, in the REVIEW colour, where the
  control used to be:

  > **Tempo is not Bombista's business.** Bombista answers *when* a line happens, not in which
  > beat, so the file it writes carries no `tempo` block. Add it by hand from the Ableton project
  > that produced this audio, where it is exact — all four values together (`bpm`, `numerator`,
  > `denominator`, `countInBars`), because a partial block breaks Pregonero's pulse.

  ⚠ *"the emitted file"* until 2026-08-16 — **§10.1 forbids "emit" in a user-facing string**, and
  PR 4's test enforces it on every page. See §11.13.

  The original clause, kept so the removal is legible: a control starting at *— not set —*, with a
  warning block beside it in the REVIEW colour: *Tempo is never measured. Bombista answers when a line happens, not in which beat. Type the
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
  §8.6 — **now settled, 2026-08-16.** Everything in this spec is buildable as written.

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

**The masthead is exempt from the *alignment* ban, and the exemption is exactly one string.**
Claude Code found the collision in PR 4: §10.1 forbids *alignment* on a page while §9.1 mandates
the tagline **Forced-alignment triage** on every page. Its reading was right and is now the rule.
The ban governs **the words of the flow** — its own rationale is that *alignment* named the
mechanism rather than the user's move, and a user moving through Input → Review → Output should
never have to learn the machinery. **The masthead is not part of the flow; it is the tool saying
what it is**, to someone who may have arrived from a search result, and there the field's own term
is the honest one. A test pins the tagline verbatim so the exemption cannot widen to a third
string.

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

---

## 11. What building it found

PRs 1 and 2 shipped 2026-08-16 (bombista#22 merged, #23 open; 263 → 304 tests). Claude Code
surfaced six problems in this spec while building. Four are corrected in place above; the two that
changed the code are recorded here, with the decisions they force.

### 11.1 Corrected in place

| finding | where | fix |
|---|---|---|
| §6 and §10.2 contradicted each other on the hand-set record | §6, §3 page 3, §8.7 | §10.2 wins. The song file carries `linesHash` + `timelineSignedOff`; the per-line record returns on `/api/emit`'s response for the report. Code followed §10.2 unprompted and was right. |
| §8 pointed at `bombista-serve-page2-mockup.html`, a file renamed two sessions ago | §8 | now `bombista-serve-mockup.html`. **This would have tripped PR 3 on its first read.** |
| §8.6 claims to be the only place §8 departs from §3 | §3 controls, §8.6 | it is not. §8.4 also drops *Set from playhead* for press-and-hold. Recorded as a second departure, with the fallback stated. |
| "a lead offset lands in `leadIn`" is not a test | §6 | true by construction — `normalize_to_lead_in` always banks line 0. The real question is §8.6's global shift control, which is why §8.6 is still open. |

### 11.2 `serve` cannot boot from a staging directory alone

**§3's development seam was wrong, and it would have failed on the one fixture it exists for.**
`align` never copies its lyrics input into staging: a staging dir holds `asr-words.jsonl`, a QA
report and a bare envelope, and **nothing in it carries lyric text.** `staging/pimiento` is exactly
this.

`serve` therefore takes the lyrics as a **second argument**, falling back to `<stem>-song.json`
when omitted. This is not a workaround — it is the honest signature, and it matches page 1, where
lyrics and media are two separate pickers.

**Consequence for `/api/session`'s provenance.** The default `--emit timeline` writes a bare
envelope which by contract cannot carry provenance, so Code reads it from `<stem>-report.json`
rather than recomputing — recomputing would stamp *now*, not the run on screen, which is the
opposite of what a provenance block is for. **On `staging/pimiento` it currently returns `null`.**

⚠ **Action before PR 3:** re-run the canary with `--emit report-json` so `staging/pimiento` carries
a report JSON. §8.2's provenance block has nothing to show until that exists.

### 11.3 The fixture — settled 2026-08-16

Code verified the routes against the real canary by hand and reproduced **every measured number in
§6 and §8.8**: 19 lines, HIGH 18 / REVIEW 1 / FAIL 0, lead-in 8.92, line 3 REVIEW `lead-fallback`
at 37.54; line 3 → 36.32 gives all 19 HIGH with the 15 below unchanged; line 3 → 40.00 returns line
4 as REVIEW `gap-outlier`. **Those are PR 3's acceptance tests and the routes already pass them.**

They are not committed, because `songs/pimiento.json` lives in the private `songs` vault and
Bombista is a public repo — §7 has it shipping as `pipx install bombista`. **Vendoring the fixture
publishes Jorge's lyrics.**

**Settled 2026-08-16 (Jorge): two tiers.**

1. **A synthetic fixture, committed, runs in CI.** Nineteen invented lines and a hand-built
   `asr-words.jsonl` constructed so one line misdetects by one word. Proves the *mechanism* —
   re-anchor not ripple, bands recomputing, bounds clamping — which is what a regression test is
   for. Publishes nothing.
2. **The pimiento canary as an opt-in acceptance run**, pointed at the vault by an env var and
   skipped with a clear message when it is absent. §7 gates `v1.0.0` on line 3 being *fixable
   through `serve`* — that is a thing Jorge does once, by hand, not a thing CI asserts on every
   push.

The alternative — vendoring the real lyrics — was rejected: it buys a CI test that reproduces §8.8
exactly, at the cost of publishing the songs from a repo that ships as `pipx install bombista`.
Irreversible once pushed, and a product decision rather than a testing one.

**So: no song lyrics, no real `asr-words.jsonl` and no audio ever enter this repository.** The
synthetic fixture must be built by hand rather than trimmed from the real one, because a trimmed
ASR stream still contains the sung words. If the synthetic fixture cannot be made to reproduce a
one-word misdetection convincingly, say so rather than reaching for the real data.

### 11.4 Smaller

- **`signalGlosses`** is the report-JSON key PR 1's prompt failed to name: a signal → sentence map,
  omitted when a line's signals have nothing to say. Recorded so PR 3 and PR 4 use the same name.
- **Invariant 7 was self-contradictory** — "an explicit host argument that is never configurable to
  `0.0.0.0`". Code made the argument explicit and validated it against a one-value allowlist, plus
  a source-level test that no other bind literal exists in the module. That satisfies the intent;
  the invariant's wording should be read as *the bind address is explicit in the signature and
  cannot be set to anything but loopback.*

---

## 11.5 — 11.9: what PR 4 found

PR 4 shipped 2026-08-16 (bombista#24, 304 → 389 tests). It added four routes beyond PR 2's three —
`/api/run` (start, poll, cancel), `/api/lyrics`, `/api/browse`, `/api/download` — and surfaced six
more spec problems. The two that changed the code are in §9.3 and §10.1 above; the rest are here.

### 11.5 Tempo cannot be a bpm-only block — checked against Pregonero

PR 4 built the tempo control as a stepper, correctly: §9.3 said *dropdown*, and pimiento's real bpm
is **66.67**, which no dropdown expresses. Code then asked the right follow-up — neither §9.3 nor
§10.2.1 says anything about `numerator`, `denominator` or `countInBars`, so a from-scratch file
would get `{"bpm": 66.67}` alone. **Is that safe for Pregonero?**

**Checked in `pregonero/src`, 2026-08-16. It is not.**

- `performedTempo.ts` **degrades perfectly**: `getTempoScale` returns exactly `1` when either bpm is
  unusable, and the comment says so — *"a song with no tempo block behaves exactly as it does today
  — no fallback BPM is invented."*
- `beatScheduler.ts` **does not**. `SongTempo` declares `numerator: number` and
  `denominator: number` as **required**; only `countInBars` is optional. `getBeatsPerBar` does
  `numerator % 3` and returns `numerator / 3` or `numerator` — on a bpm-only block that is `NaN`,
  and `getBeatPhase` then produces `NaN` beats, bars and count-in. There is no runtime guard: the
  one check in the codebase is `{tempo && …}`, and a bpm-only object is truthy.

So a bpm-only block gives **correct scaling and a broken pulse** — the same split-brain that
`songs@c5adf65` deleted the placeholder blocks to avoid, one key further in. The rule generalises:

> **`tempo` is written whole — `bpm`, `numerator`, `denominator`, `countInBars` — or not written at
> all.** There is no valid partial tempo block.

**Decided 2026-08-16 (Jorge): remove the tempo control from page 1 entirely.** He had assumed it
was already gone — the mockup's `.sp.json` branch has four rows and no tempo, and the control only
ever appeared on the `.txt` branch, which is why it was invisible in review. PR 4 shipped it as
`pages.py`'s `<input type="number" id="tempo">` and `server.py`'s `out["tempo"] = {"bpm": tempo_bpm}`
— **a bpm-only block, exactly the shape that NaNs `getBeatsPerBar`.** Both come out.

The reasoning that stands: Reasons: a
whole block needs four fields on a page whose rule is four rows total; tempo is never Bombista's
business (rules 4 and 5); and Jorge already types these in by hand — `songs@104b1ec` is literally
*"Add tempo to seven songs (Jorge, typed in by hand)"*. §5's warning stays as a **note** rather than a
control, and it now names all four keys, because "add the tempo by hand" is bad advice if it leads
to a bpm-only block. The `.txt` branch emits no `tempo` key at all, which is already what §10.2.1
specifies.

### 11.6 Cancel abandons the worker rather than killing it

`faster_whisper`'s transcribe is not interruptible without taking the process down. PR 4's cancel
marks the run, refuses to start the anchoring phase, and discards the result; the user is back on
step 1 immediately. **That is the honest half of §9.6's open question and it is the right half** —
the user's experience of cancel is correct, and the cost is a worker thread finishing work nobody
will read. Killing the transcription outright stays open and is not worth a subprocess boundary yet.

### 11.7 Four more, resolved in PR 4

| finding | resolution |
|---|---|
| §8.1's *"one page per step"* vs PR 3's *"page 2 is the HTML for `/`"* | a redirect, so PR 3's sentence stays true in the case PR 3 develops in |
| the step bar renders on three states, not four — `/review` 404s before PR 3 | expected; PR 3 makes the fourth real |
| *"no external URL of any kind"* collides with §9.3's *See an example* link | the test is scoped to **loaded resources**, not hyperlinks. Correct: the guard exists so the page never phones out, and a link the user clicks is not the page phoning out |
| the mockup's page-1.5 lede still said *"on this machine"* | the wording §10.1 retired; fixed in the mockup |

### 11.8 A test that passed while proving nothing

Worth recording because it is a class of bug, not an instance. PR 4's first test pass wrote to the
real `~/.cache/bombista`. A later test then silently picked up that cache path and **stopped testing
transcription at all — it passed, and proved nothing.** An autouse fixture now redirects the staging
root at `tmp_path`, and the directory the run had created on Jorge's machine was removed.

**The general rule for this repo:** a test that touches a real user path is not slow or untidy, it
is *unsound* — it can start passing for reasons unrelated to the code. Redirect the root, always.

### 11.9 Still outstanding

- ~~**§11.2's action** — re-run the canary with `--emit report-json`.~~ **Done 2026-08-15 19:07.**
  `staging/pimiento/pimiento-report.json` exists and carries everything §8.2's provenance block
  needs: `source.sha256`, `durationSec` 173.376, `model` `faster-whisper:medium`, `device`
  `cpu/int8`, `lang` `es`, `toolVersion`, plus `linesHash` and `leadIn.durationSec` 8.92. The run
  reproduced the canary exactly — **HIGH 18 / REVIEW 1 / FAIL 0**. `/api/session` will now return a
  populated `provenance` instead of `null`.
- ~~**§11.5** — Jorge's yes or no on removing the tempo control.~~ **Decided: remove it.**
- ~~**§11.10** — `extractedAt`.~~ **Decided: not displayed; not invented in the report either.**
- ~~**The docs are not on GitHub.**~~ **Done.** §11.1–11.10 merged as #25; §11.11 and this
  amendment ride on #26. **See §11.12 for the accident that nearly lost half of them.**
- ~~**Three things now ship in one cleanup PR** (PR 5), after page 2: the tempo control out,
  `extractedAt` honest, and §11.11's audio path.~~ **Shipped 2026-08-16, plus §8.2's provenance
  reduction — four items, 454 → 479 tests.** They were one idea and stayed one — *the page shows
  what helps you judge a line, the report records what an audit needs, and nothing anywhere states
  a fact it did not establish.* **What building them found is §11.13.**

### 11.10 `extractedAt` lies on a `--words` re-run

Found while doing §11.2's action, 2026-08-15. The re-run passed `--words` to reuse the saved word
stream, so **faster-whisper never ran** — and the report it wrote says:

```
source.extractedAt   2026-08-15T19:07:09+02:00     ← when the report was written
asr-words.jsonl      mtime 2026-08-14 20:55        ← when the audio was actually transcribed
```

Nothing about *what* was aligned is misrepresented: the audio sha256, the model and the language
are all still true. But `extractedAt` is a claim about **when the machine listened**, and on any
`--words` run it silently becomes the time the report was written instead. §8.2 puts that value on
screen under the word *provenance*, and the whole product rests on the report being trustworthy —
so a field that is right by accident and wrong on the fast path is exactly the wrong field to
leave alone. Note that the fast path is not the exception: §9.4 makes reusing the word stream *the*
correction loop, so most runs will be `--words` runs.

`asr-words.jsonl` cannot answer this itself — it is bare word records, `{"text","start","end"}`, one
per line, with no header (and adding one would break every reader).

**Decided 2026-08-16.** Jorge, on being shown this: *"I find the underlying problem very technical.
I would refrain from showing any of this info to the final user."* That answers it twice over, and
the fix is smaller than the original recommendation:

1. **`extractedAt` is no longer displayed anywhere.** §8.2's provenance block is now one line —
   filename, model, lead-in — and the timestamp is not on it. The user-visible half of the problem
   is gone by deletion rather than by repair.
2. **In the report JSON it must still not lie.** `save_words` writes a sibling
   `asr-words.meta.json` — `extractedAt`, `model`, `device`, `lang`, audio `sha256` and, added
   2026-08-16 for §11.11, the **absolute** audio path — and `--words` reads it back instead of
   stamping fresh. A sibling file stays true when the staging directory is copied, which an mtime
   does not. If it is missing (an older staging dir), **omit `extractedAt` entirely and set
   `wordsReused: true`** rather than invent a time.

A wrong timestamp in an audit file is worse than an absent one, and absent is cheap. Note the
asymmetry this settles: *not shown* and *not recorded* are different decisions, and the report gets
to be as technical as it likes precisely because nobody reads it while working.

**Not a PR 3 blocker.** Ships with §11.5's tempo removal in one cleanup PR — and, since 2026-08-16,
with §11.11's audio path, which is the same file answering the same kind of question.

---

## 11.11 What page 2 found

Page 2 shipped 2026-08-16 (389 → 454 tests). It closed §8.6's reversal, §8.9's two open
questions and §11.3's fixture decision. Six more things, three of which changed the code.

### The mockup writes a `leadIn.source` the contract does not carry

**Changed the code.** The mockup demonstrates the line-0 move by setting
`leadIn: { durationSec: 9.32, source: "hand-set", … }`, and *hand-set* is the word this
whole spec reaches for. **`docs/timeline-v2-contract.md` does not have it.** `leadIn.source`
takes `"measured" | "manual" | "none"` — frozen, shared with Pregonero, and validated on
both sides — and the contract's own gloss is *`manual` = a human overrode it*, which is
exactly the fact being recorded. Copying the mockup would have written a file
`validate_v2_envelope` rejects, in the one place the reversal makes newly reachable.

So `to_dict` grew a `source` argument, `serve` passes `manual` exactly when line 0 carries
an override, and `"hand-set"` is refused at the serialiser rather than discovered two tools
downstream. ~~**The mockup should be corrected**~~ — **done 2026-08-16**, it now writes
`manual`. It is the reference implementation and the next reader will copy the string.

This is the one thing the §8.6 reversal needed that was not written down anywhere. Before
it, every lead-in in the format was measured by definition, so the field had nothing to
distinguish. Making line 0 editable made `source` load-bearing for the first time.

### The debounce fires in the gap before the auto-repeat starts

**Changed the code, and it is §8.5's finding a third time.** `HOLD_DELAY` is 380 ms and
`DEBOUNCE` is 250 ms, so a plain debounce commits at t=250 — after the first press and
*before* the auto-repeat begins. The commit re-renders the list, which swaps the button out
from under a cursor that is still holding it down. Same failure as an unreserved struck-
through line or a repositioned popup, one layer further in.

**The mockup could not have found this**, and that is the interesting part: it re-rendered
locally and instantly from a table of pre-computed outcomes, so it had no round trip to land
mid-press. The fix is small — the timer waits out the hold rather than racing it — but the
class of bug is *the mockup's fidelity ends where the network begins*, and it is worth
expecting more of it in anything else built against it.

### The one line of instruction names line 0 in the mockup

**Did not follow the mockup.** §8.2 fixes the copy as *"Click a **START** time to adjust it.
Press and hold to move fast — a whole missed word is about a second."* The mockup, updated
for the reversal, reads *"Click any **START** time to adjust it — line 0 included."*

Built §8.2's wording. §8.6 lists three ways line 0 must not be marked — no colour, no row
label, no popup caption — and the page's only sentence of help copy is a fourth it did not
think to name. A line singled out in the instructions is a special line; the point of the
reversal is that it is not one. If a user needs telling that line 0 is clickable, every
other row has already told them.

**The mockup was corrected to match, 2026-08-16**, along with the `hand-set` string above.
§8.6 is now a fourth item: *not named in the help copy either.*

### Page 2 needed a row template the tests can read

**A deliberate departure from the mockup, recorded so it is not "fixed" back.** The mockup
renders its rows in JavaScript. §6 makes *every row carries its line's text, not only its
index* a hard requirement — it is the requirement the CLI failed — and a row built by
client-side JS can only be asserted by reading the JS as a string, which tests the spelling
of the template rather than what a row says.

So the rows are rendered by `pages.render_rows`, and the page fetches that same markup back
from `GET /review/rows` after a re-anchor. One template, in one language, and the assertions
are about rows rather than about source code. The page keeps the popup, the hold, the
debounce and the player; it does not keep a second opinion about what a row contains.

### `serve <staging> <lyrics>` cannot name its own audio

**Adjacent to §11.10, and the same shape of problem.** The audio route needs the take —
timeline times are only meaningful against the audio they were measured from — and a session
booted into a review has no media argument to read it from. It falls back to the run's
provenance, which is honest but fragile twice over: `align` stores that path **as it was
given**, so `staging/pimiento` records `../../songs/audio/pimiento.m4a`, which resolves only
from the directory that run happened in. Copy the staging directory somewhere else and the
player has nothing.

Not fixed here — the fallback works for the canary and the failure is loud rather than
silent (the route says the take is not where the run recorded it, and never substitutes some
other file). **The fix belongs with §11.10's `asr-words.meta.json`**: both are "the staging
directory cannot say what it was made from", and an absolute path recorded once would answer
both. A `--audio` option on `serve` is the smaller half of it.

**Decided 2026-08-16: both halves ship in PR 5**, with §11.5 and §11.10. Reasoning, so it is
not reopened: `asr-words.meta.json` is being written in that PR anyway, so the absolute path
costs one key rather than a new file; and `--audio` is not a new concept but the third of
three arguments page 1 already collects — `serve <staging> <lyrics> --audio <take>` says out
loud what page 1 says with three pickers. **Resolution order is fixed and must be tested as
such:** `--audio` if given, else the absolute path in `asr-words.meta.json`, else the run's
recorded relative path resolved against the staging directory's parent, else fail loudly.
**Never substitute another file** — an audio route that silently plays the wrong take makes
every judgement made against it wrong, which is worse than a player that says it cannot find
the take.

### The payload had no "before" for a band

Minor, mentioned because it is the sort of thing a spec cannot notice. §8.5 wants a changed
band to show *its before and its after* on the row, and PR 2's `/api/session` carried
`machineStart` but not `machineBand` — the machine's value but not the machine's verdict. It
is computed once at load beside the starts, for the same reason they are: re-deriving it
from a run that already carries corrections would quietly turn the human's answer into the
machine's.

---

## 11.12 The docs diverged in two places at once

**Recorded because it is a process bug with a repo-shaped fix, and it cost half a spec.**

On 2026-08-15 the spec was being edited from two directions in the same hour. Cowork was writing
the design decisions — §8.2's provenance reduction, §9.3's tempo removal, §11.5 and §11.10's
verdicts — into the working tree. Claude Code, on `feat/b20-page2`, was writing §11.11 and closing
§6, §8.6 and §8.9 against the version of the spec that was on `main` when it branched.

Both were correct. Both were newer than `main`. **Neither contained the other**, and the second
commit to land wrote its whole file over the first:

| commit | 20:42 `886bfa8` (Code) | 20:49 `2cb5af2` (Cowork's tree) |
|---|---|---|
| §11.11, §6/§8.6/§8.9 closures | ✅ | ✗ reverted |
| §8.2, §9.3, §11.5, §11.9, §11.10 decisions | ✗ absent | ✅ |
| `docs/_to_delete/` | deleted | ✗ resurrected |

It survived only because `886bfa8` had been pushed to #26 before `2cb5af2` was made locally, so
the losing half was still recoverable from the remote. **Had the push happened in the other order,
§11.11 would have been gone with no copy anywhere.** Reconstructed 2026-08-16 by three-way merge
against `0d4b999` as the base; one conflict, in a single sentence.

**The rules this earns:**

1. **A whole-file write is not an edit.** A session that holds a file in memory and writes it back
   silently reverts anything committed under it. Diff before writing a doc the branch may have
   moved: `git diff HEAD -- docs/<file>` should show *your* changes and nothing you do not
   recognise. A stat line with more deletions than you made is the tell — `2cb5af2` deleted 144.
2. **The spec is edited by one writer at a time.** Design decisions go in on `main` or on their own
   docs branch and are merged before a build branch starts; findings from building go in on the
   build branch. Never both in the same hour.
3. **A resurrected `_to_delete/` is a stale-tree alarm.** Files deleted two commits ago reappearing
   means the tree they came from predates the deletion, and whatever else that tree carries is
   equally old.

The wider point, and the reason this sits in §11 rather than in a commit message: **§11 is the only
record of most of these decisions.** Losing it loses the reasoning, not the code — and the reasoning
is what stops a later pass reintroducing a bpm-only tempo block or a lead-in widget. A spec that
can be silently truncated by a routine `git commit` is a single point of failure for everything
this document exists to prevent.

---

## 11.13 What the cleanup found

PR 5 shipped 2026-08-16 (454 → 479 tests). It implemented §11.5's tempo removal, §11.10's
honest `extractedAt`, §8.2's one-line provenance and §11.11's audio path. Five things worth
recording; two of them changed a decision's *wording* rather than the decision.

### §9.3's replacement note used a retired word

**Did not follow the spec.** §9.3 fixes the note that replaces the tempo control as *"so the
emitted file carries no `tempo` block"*. **§10.1 forbids "emit" in a user-facing string**, and
PR 4's own test enforces it on every page. The note was built as *"so the file it writes
carries no `tempo` block"* — same claim, one word.

Worth a line because it is the second time a section wrote copy without checking it against
§10.1 (§11.11 has the first, in the line-0 instruction). §10.1 governs the page; a later
section quoting a sentence is not an exemption from it. **§9.3's note text is corrected above.**

### `tempo` passes through; Bombista never *constructs* one

The PR 5 prompt asks for a test that *"no emitted file on either branch contains a `tempo`
key"*. Taken literally that contradicts §10.2, which passes `tempo` through untouched — and
libertad and pimiento both carry a real one. The rule that holds both is the one §11.5 states:
**Bombista never constructs a tempo key.** Passing one through is not writing one.

So the tests are: the `.txt` branch emits no `tempo`; the `.sp.json` branch emits byte-identically
what it was handed; and `server.py` has no code path that names a tempo at all. That last one is
structural rather than a grep, because the *reasoning* for the removal lives in `server.py`'s
docstrings and should stay there — a grep for `bpm` over the whole file would forbid the comment
explaining why there is no bpm.

### A `--words` run establishes some of its provenance and not the rest

§11.10 says the sibling carries `extractedAt`, `model`, `device`, `lang` and the audio `sha256`,
and that `--words` reads it back "instead of stamping fresh". Building it forced the question of
*which* fields, and the answer follows from the PR's own headline — **nothing states a fact it
did not establish**:

- **carried forward** — `extractedAt`, `model`, `device`, `lang`. Facts about *when and how the
  machine listened*, which a run that skipped transcription did not establish.
- **still this run's own** — `sha256`, `durationSec`, `audio`. That run *did* hash the file it
  was pointed at, and the three are one coherent description of one file on disk, which is the
  whole of what B1 exists to record. Overwriting a live description with a recorded one would
  split it across two runs — the same split brain §11.5 deletes elsewhere.

The sibling still records `sha256`, which is what would make a future "this is not the audio that
was transcribed" warning possible. That warning is not in this PR.

### The sibling is a provenance carrier, and a partial one

`asr-words.meta.json` is now the third thing `_find_provenance` reads, after the report JSON and
an `--emit songjson` output. It is the poorest of the three — no duration, no tool version — and
the only one **a run started from page 1 leaves behind at all**, which is why it is read.

That made the markdown report's header raise `KeyError` on the download route, on a shape that had
never existed before this PR. Fixed by laying the unknowns down first and the recorded facts over
them, so the report renders `unknown` where a carrier says nothing. An audit document that says
`unknown` is telling the truth; one that cannot render tells the user nothing.

### The mockup still had both removals in it

**Corrected, on §11.11's precedent.** The mockup carried the tempo dropdown, an `out.tempo` that
filled the meter in from pimiento's real 6/8 — the invention §11.5 forbids, since the tool cannot
know the next song's meter — and page 2's full provenance table. It is the reference
implementation and the next reader copies from it, so both were brought in line and the reasoning
left as a comment where each used to be.

The general rule, now three for three: **a decision is not landed until the mockup agrees with
it.** §11.11 found `hand-set`, the line-0 instruction, and now these.
