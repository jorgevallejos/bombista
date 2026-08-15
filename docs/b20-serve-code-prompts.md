# B20 `serve` — Claude Code prompts

Five PRs. **All five are built.** PRs 1, 2, 4 and 3 merged 2026-08-16 (#22, #23, #24, #26);
**PR 5, the cleanup, is built on `chore/b20-cleanup`** — 479 tests green, and what it found is
**§11.13** of the spec. Nothing here is left to run. Each is paste-ready. House rules apply
throughout and are restated in each prompt
because Code does not carry them between sessions: feature branch off `main`, strict
red → green → refactor, Conventional Commits, `gh pr create --base main`, merge and pull `main`
before starting the next.

**Read §11 first — all of it.** Building PRs 1–4 found nineteen problems in the spec. Most are
corrected in place; the ones that change what PR 5 can assume are §11.2 (`serve` takes lyrics as a
second argument), §11.5 (tempo is whole or absent — checked against Pregonero), §11.8 (tests must
never touch a real user path), §11.10 (`extractedAt` and the `asr-words.meta.json` sibling) and
§11.11 (`leadIn.source` is `manual`, never `hand-set`; and the audio path).

Reference material Code should read before touching anything: `docs/bombista-serve-spec.md`
(§3 the four states, §4 invariants, §6 obligations, **§8 page 2's design**, **§9 pages 1/1.5/3**,
**§10 the vocabulary and the skin**) and `docs/mockups/bombista-serve-mockup.html` (the clickable
reference for all three steps, on pimiento's real numbers).

**Vocabulary — §10.1, and it is not negotiable in user-facing strings.** The steps are
`1 Input · 2 Review · 3 Output`. The format is the **Song Performance JSON** (`SP JSON`,
`.sp.json`) — never "CP JSON", never a bare "song JSON". The audio row is **Media source**. The
words *alignment* and *emit* may appear in code and internal docs; they must not appear on a page.
The report-JSON key for the glosses is **`signalGlosses`** (a signal → sentence map, omitted when a
line's signals say nothing) — set by PR 1, §11.4.

**The format — §10.2, read it before writing any serialiser.** The SP JSON **is** the existing
`songs/*.json` format; there is no new schema. Bombista owns exactly `linesHash`,
`timelineSignedOff`, `timelineVersion`, `leadIn`, `timeline` — FIVE keys, and passes `title`,
`artist`, `notes`, `title_translations`, `tempo`, `intro` and `lyrics` through untouched. `lyrics` entries are
OBJECTS keyed by language (`{es, en, fr, nl}`), never strings: flattening them destroys every
translation on the round trip. Do not invent a `format:` key, a `review:` block or a
`provenance:` block in the song file — QA output belongs in the report.

**Two shapes, one format — §10.2.1.** A `.sp.json` in means pass-through: fill five keys, touch
nothing else. A `.txt` in means the song file does not exist yet, so write one with only what a
plain text plus step 1 can honestly supply — `artist: ""`, `notes: ""`, `title_translations`
keyed by the CHOSEN language, **`tempo` OMITTED unless page 1 supplied a real number — never a
null scaffold, never a placeholder** (songs@c5adf65 removed placeholder tempo blocks "outright —
not replaced with a flag or a null", because tempo.bpm drives both Pregonero's scaling denominator
and its visual pulse and an invented number cannot serve both; Pregonero degrades safely when the
key is absent), no `intro`, and `lyrics` carrying that one language. §10.2.1 has the table.
**§11.5 sharpens this:** `tempo` is written **whole** — `bpm`, `numerator`, `denominator`,
`countInBars` — **or not at all**. A bpm-only block breaks Pregonero's pulse (`getBeatsPerBar`
returns `NaN` without a time signature) while the scaling path keeps working. There is no valid
partial tempo block.

---

## PR 1 — signal glosses, one source of truth

**Branch:** `feat/b20-signal-glosses`

```
Read docs/bombista-serve-spec.md §8.3 and CLAUDE.md first.

Bombista's confidence signals are printed as bare tokens — `lead-fallback`, `gap-outlier`,
`uncorroborated`, `ambiguous`, `no-anchor`, `clean-anchor`, `override` — in the markdown QA
report, in the report JSON, and on B16's HTML review page. A user who has not read
anchoring.py cannot act on them. B20 page 2 needs a plain-language sentence per signal, and
it must be the same sentence everywhere, so it belongs beside the signal names rather than in
any one writer.

Task, strict red → green → refactor:

1. Add `SIGNAL_GLOSSES: dict[str, str]` to bombista/anchoring.py, next to the tuning
   constants, mapping every signal name anchor_lines can emit to one plain sentence written
   for someone who has never read the source. Use §8.3's wording for `lead-fallback` verbatim;
   write the rest in the same register — what the tool observed and where to listen, not what
   the code did.

2. Write the failing tests first, in tests/:
   - every signal name that anchor_lines can emit has a KEY in SIGNAL_GLOSSES (derive the set
     from the code, do not hardcode a literal list that can drift);
   - every signal that indicates a PROBLEM has a non-empty sentence. `clean-anchor` and
     `override` are not problems and map to "" — they are the two exceptions and the test should
     name them explicitly rather than allowing any empty value through;
   - no gloss names a function, a module, or a threshold constant;
   - the markdown QA report renders the gloss for each flagged line;
   - B16's HTML review page renders the gloss for each flagged line;
   - the report JSON carries the gloss per line alongside the signal.

3. Make them pass. report.py and writers.py import SIGNAL_GLOSSES from anchoring; neither
   defines its own copy.

Note for later, do not act on it here: B20 page 2 will SUPPRESS `clean-anchor` on screen
entirely (§8.3) because 18 of 19 rows carry it and repeating it is noise. The markdown report
and the report JSON keep printing every signal — they are audit documents with different
duties. That asymmetry is deliberate; this PR just makes the vocabulary shared.

Do not change any band, threshold, or signal name. This PR adds words, nothing else.
The existing 263 tests must stay green.

Commit as `feat(anchoring): name each confidence signal in plain language`, then
`gh pr create --base main`.
```

---

## PR 2 — the `serve` skeleton and the two routes page 2 needs

**Branch:** `feat/b20-serve-routes`

```
Read docs/bombista-serve-spec.md — all of it, especially §1 (what this must never become),
§2 (step 0, already merged as PR #18), §4 (the invariants) and §6 (test obligations) — and
CLAUDE.md before touching anything.

This PR builds `bombista serve` as a process and the JSON routes page 2 talks to. It does NOT
build page 1, page 1.5, page 3, or page 2's HTML. Those are separate items; page 2's markup is
PR 3.

Build:

1. `bombista/server.py` — a ThreadingHTTPServer on 127.0.0.1 with an explicit host argument
   that is never 0.0.0.0 and never configurable to it (invariant 7). A `--port` option, default
   an ephemeral port, printed on start.

2. `bombista serve` in cli.py: wiring only, matching how align/promote/migrate are wired there
   today. It takes a staging directory (the output of a previous `align`) and boots a session
   from what is on disk: the song JSON or lyrics, asr-words.jsonl, the QA state. This is the
   development seam that lets page 2 be built against pimiento without page 1 existing.

3. Routes, JSON in and out:
   - `GET  /api/session` — the lines, their machine anchors, bands, signals, ASR context,
     leadIn, and the run's provenance.
   - `POST /api/reanchor` — body `{ "overrides": { "<line>": <seconds> } }`. Parses through
     anchoring.parse_anchor_overrides (which already exists for exactly this — read its
     docstring), then calls anchoring.anchor_lines and pipeline.build_timeline. Returns the
     full per-line result. It re-runs the anchoring; it never applies a delta to anything.
   - `POST /api/emit` — writes a NEW file via the extracted merge path in promotion.py /
     writers.merge_envelope. Never writes to an input path (invariant 6).

Tests, written first and failing for the right reason (§6):

- the server binds 127.0.0.1 and there is no code path to any other bind address;
- `/api/reanchor` DELEGATES — assert it calls the extracted anchoring and merge rather than
  reimplementing them. This is the drift risk the whole item is shaped around;
- an override re-anchors: with a synthetic Word list, lines after a correction take values
  derived from the word stream, not `original + delta`. Construct the fixture so those two
  answers differ, or the test proves nothing;
- line 0 cannot be moved through any route, and a lead offset lands in `leadIn`;
- no route rounds coarser than 0.07 s, in either direction of the JSON round trip;
- the emitted file carries `linesHash` and the hand-set provenance (which lines, their machine
  values, when they were set);
- `/api/emit` refuses to write to any path that was an input.

Use synthetic Word lists throughout — never the whisper model (CLAUDE.md, Development Protocol).

Do not import anything from cli.py into server.py; both call the extracted modules
(invariant 1). The existing 263 tests must stay green.

Commit as `feat(serve): local HTTP server and the re-anchor/emit routes`, then
`gh pr create --base main`.
```

---

## PR 3 — page 2 — **UNBLOCKED, RUN THIS NEXT**

> **Unblocked 2026-08-16. Both open questions are answered — read §8.6 and §11.3 before starting.**
>
> **§8.6 — line 0 is NOT special.** Jorge's decision: *"line timestamps can change independently
> without any ripple effect. Line 0 should be the same. The first value should not be considered
> anything special. It is Pregonero that will make a distinction between lead-in and line 0 — it is
> a performance-time topic, not a timeline-extractor one."*
>
> **This REVERSES what PR 2 built.** PR 2 refuses line 0 on every route, faithfully implementing
> the old §3 rule. This PR must:
> - remove that refusal and allow line 0 through `/api/reanchor`, bounds `[0, line 1's onset)`;
> - **invert the §6 test** — it currently asserts line 0 cannot be moved; it must assert line 0
>   moves like any other line, that its onset lands in `leadIn.durationSec`, and that entry 0 is
>   still written `0.00`;
> - render line 0 with **no special colour, no `lead-in` row label, no popup caption**. Item 4 of
>   the prompt below is void — build line 0 as an ordinary row.
>
> Invariant 3 is untouched and is not at risk: the v2 normaliser banks line 0's onset into `leadIn`
> at emit no matter how the value got there. It was being defended at the wrong layer.
>
> Verified in the mockup: moving line 0 from 8.92 to 9.32 leaves line 1's RAW onset at 18.44
> (no ripple), sets `leadIn.durationSec` to 9.32 with `source: "manual"` — the v2 contract takes
> `"measured" | "manual" | "none"` and has no `hand-set`, see §11.11 — keeps entry 0 at 0.00,
> and shifts every cue-relative value by −0.40. Reproduce that as a test.
>
> **§11.3 the fixture — settled: two tiers.** A synthetic fixture, committed, runs in CI and proves
> the mechanism. The pimiento canary is an opt-in acceptance run pointed at the private vault by an
> env var, skipped with a clear message when absent. **No song lyrics, no real asr-words.jsonl and
> no audio ever enter this repository** — build the synthetic fixture BY HAND, do not trim the real
> one, because a trimmed ASR stream still contains the sung words.
>
> Also read §11.5–§11.9 (what PR 4 found), and §11.8 in particular: tests must never touch a real
> user path. An autouse fixture redirects the staging root at `tmp_path` — keep using it.

**Branch:** `feat/b20-page2`

```
Read docs/bombista-serve-spec.md §3 (page 2), §4, §6 and §8 (the whole design), then open
docs/mockups/bombista-serve-mockup.html in a browser and use it. That mockup is the
reference implementation: pimiento's real 19 lines, with every re-anchor outcome taken from
anchoring.py run against the real asr-words.jsonl. Match its behaviour; you may improve its
code.

Build page 2 as the HTML `serve` returns for `/`, driven by the routes from PR 2.

Stack, and do not exceed it (§8.1): stdlib only. One page, inline CSS and JS, built by string
composition the way writers.write_html_review already does it. Vanilla JS, no framework, no
build step, no npm. `fetch` to the PR 2 routes is correct here — B16's zero-external-reference
assertion is scoped to write_html_review's output file and MUST NOT be extended to this page.
Serve the audio bytes from a loopback route rather than a relative src (§8.9).

**The page is deliberately spare, and that is the design, not an unfinished state.** It is:
an OPEN but quiet provenance block (two dim columns — collapsed, its summary line was an
unreadable run-on; the fix was to make it recede, not to hide it), a sticky player with the three
band counts, ONE line of instruction
immediately above the table ("Click a START time to adjust it. Press and hold to move fast — a
whole missed word is about a second."), the 19-line list, and one Confirm button. There is no lead-in panel, no "needs attention" card, no editor pane, no
re-anchor banner, no JSON preview, no acknowledgement checkbox. Do not add explanatory text,
help copy, status messages, or summary panels. If something needs explaining, it is in the
spec, not on the page.

The five things most likely to be got wrong:

1. **The start time IS the control.** Clicking it opens a popup containing one stepper and
   nothing else — no bounds text, no delta readout, no buttons. Bounds are the neighbouring
   lines, enforced by silently clamping. Escape or click-outside closes; arrow keys nudge.

2. **Press and hold auto-repeats** (380 ms, then 45 ms). This is load-bearing, not a nicety:
   line 3's error is 1.22 s, which is 24 separate presses. Two implementation consequences,
   both found while building the mockup — the struck-through previous value must have its line
   reserved always, or the row grows mid-press and the button moves out from under the cursor;
   and the popup must not be repositioned while a button is held.

3. **A band that changed shows its before and its after**, on the row: old chip faded, arrow,
   new chip, RE-ANCHORED badge, previous value struck through. Not a silent repaint. The
   whole-song announcement is the HIGH/REVIEW/FAIL counts in the sticky bar — no banner.

4. ~~**Line 0's number is the lead-in control.**~~ **VOID — §8.6 settled the other way on
   2026-08-16. Line 0 is an ordinary row.** The original clause, kept only so the reversal is
   legible: line 0 was to be underlined in clay, row labelled
   `line 0 / lead-in`, popup captioned "lead-in · moves the whole song". It shifts every line
   together and re-anchors nothing. Invariant 3 is untouched: line 0 is still 0.00 in the
   emitted timeline. **Confirm this with Jorge before building it** — it is the one place §8
   departs from §3's prose.

5. **Debounce the re-anchor at 250 ms** after the last press. Not per press, not behind a
   button.

Tests:
- every row carries its line's TEXT and not only its index (§6 — the requirement the CLI
  failed);
- the popup contains exactly one stepper and no other control;
- the stepper step and every serialisation are 0.05/0.07 s or finer (invariant 2);
- moving line 0 changes no band and re-anchors nothing;
- an end-to-end test over the pimiento fixture, driving the routes rather than the DOM:
  setting line 3 to 36.32 leaves all 15 lines below unchanged and all 19 HIGH; setting it to
  40.00 returns line 4 as REVIEW/gap-outlier. Both are measured, not invented — §8.8.

The acceptance case is §6's: a user who has never read the CLI docs can resolve line 3 of
pimiento and reach a correct output file. Build to that, not to a feature list.

Page 2's skin is retrofitted in PR 4 (§10.3). Build it here against the mockup's current CSS,
which is already the ink-predominant brutalist one — do not reintroduce radii, easing, a light
palette, or the blue edit colour.

Commit as `feat(serve): page 2 — review`, then `gh pr create --base main`.
```

---

## PR 4 — pages 1, 1.5 and 3 — **RUN THIS NEXT, BEFORE PR 3**

> **Reordered 2026-08-16.** PR 3 is blocked on two of Jorge's decisions; this one is blocked on
> nothing. The order is also simply better: this PR establishes the masthead, the step bar and the
> shared stylesheet, so page 2 **inherits** the skin instead of being retrofitted with it. Every
> "retrofit page 2" clause below therefore does not apply yet — build the shared chrome once, here,
> and PR 3 picks it up.
>
> **Expect to add one route.** PR 2 built `/api/session`, `/api/reanchor` and `/api/emit`. Page 1 →
> page 1.5 needs a way to *start* a run (transcribe, then anchor, with a working cancel). If it
> does not exist, add it here — it belongs with the pages that use it. Same rules as PR 2: bind
> loopback only, delegate to the extracted modules, never reimplement anchoring.

**Branch:** `feat/b20-pages-1-and-3`

```
Read docs/bombista-serve-spec.md §3, §5 (the plain-text branch), §4 (invariants), §9 (the
design for these three pages) and §10 (vocabulary, format and skin — §10.1 governs every user-facing
string), then open docs/mockups/bombista-serve-mockup.html and click through steps
1 → 1.5 → 2 → 3. Same stack rules as PR 3 (§8.1): stdlib, one page per step, inline CSS/JS,
vanilla JS, no build step, no webfont.

Build the remaining three states, plus the step bar that goes on all of them.

1. **The step bar** (§9.2) — `1 Input · 2 Review · 3 Output`, on every page including page 2
   (retrofit it there). One hard-bordered strip divided by 3px rules, not free-floating pills.
   Every step clickable, including backwards; nothing is destroyed by navigating. Page 1.5 is a
   state of step 1 and gets no segment of its own; its heading is "Processing".

2. **Page 1** (§9.3) — heading "Input song". EXACTLY FOUR ROWS: Lyrics, Media source, Language,
   Model. Each row is a label, one control, and one mono caption underneath. There is NO output
   folder picker and NO "also write" checkbox group — both were cut on 2026-08-15 and must not
   come back; step 3 offers downloads and the app does not choose where they land.

   - The picker shows THE FILE NAME ALONE, never the path.
   - There is no "as JSON / as plain text" dropdown. The branch is read off the extension.
   - The Language dropdown is CONSTRAINED BY THE FILE: an SP JSON declares the languages it
     carries and undeclared ones render disabled. This is a real rule — a language with no lines
     has nothing to anchor — but the caption does NOT explain it. The caption is exactly "The
     language on the recording and the lyrics file." and nothing more. Note that real Chango
     Pepper song files carry es/en/fr/nl, so on the pimiento fixture nothing is disabled; the
     guard is for .txt-derived and partial files.
   - The Model caption must say it RUNS ON YOUR LOCAL MACHINE AND NOTHING IS UPLOADED (that
     wording — "this machine" is ambiguous about whose), as well as the quality/time trade-off.
     §1 says this tool must never become a hosted service; say so where the user is choosing the
     thing that would otherwise have been the API call.
   - One primary button: `Process song →`. Ink fill, clay shadow, the only filled button on the
     page.
   - The plain-text branch (§5) grows the same form in place: slug read-only from the filename,
     title (the one free-text field in the whole flow), tempo as a dropdown starting at
     "— not set —" beside a warning that tempo is NEVER measured (rules 4 and 5 — B14 was
     dropped for this), and the stripped-line report shown BEFORE the run, never after.

3. **Page 1.5** (§9.4) — two phase rows with a blinking dot and an elapsed readout, a Cancel
   that actually cancels, and the one line about the transcription cache. Not a spinner. The
   dot blinks on steps(2), it does not fade — see §10.3.

4. **Page 3** (§9.5) — heading "Output", read-only. In order: one mono caption, a filename plate
   with a fold control, the FULL SP JSON in a bordered code window, three downloads, a back link.

   - Serialise the REAL song-file key order (§10.2): title, artist, notes, title_translations,
     tempo, intro, lyrics, linesHash, timelineSignedOff, timelineVersion, leadIn, timeline.
     Verify the passed-through part against songs/pimiento.json — do not take the order from this
     prompt if the file disagrees.
   - Render the FULL JSON. NO fold, NO expand control, no truncation. The window scrolls; the
     caption tells the user which five keys Bombista wrote. An earlier pass added a fold and
     Jorge cut it.
   - The three buttons are `Download JSON file` (primary — the whole file), `Download timeline
     only` (the FOUR TIMING KEYS: linesHash, timelineVersion, leadIn, timeline — never a bare
     timeline array, which would hand over the unguarded artifact B4 exists to prevent),
     `Download report` (bands, signals, provenance, hand-set lines, as markdown). One mono line
     under each saying which is which.
   - B19's surviving clause: EITHER JSON DOWNLOAD MUST BE PRESSABLE WHEN NOTHING WAS FLAGGED,
     and pressing either records the sign-off. THE REPORT DOES NOT COUNT AS SIGN-OFF — it
     certifies nothing. The buttons do NOT disable after the press.
   - There is NO "ready to write <name> into <folder>" line and NO file list. Both were cut on
     2026-08-15: they described a write to a folder the app no longer chooses.
   - `timelineSignedOff` is SETTLED (Jorge, 2026-08-15): an ISO timestamp beside `linesHash`,
     written when a JSON download is pressed. It is the whole of §3's provenance clause in one
     scalar; all the detail stays in the report.

5. **The masthead** (§9.1) — on every page, above the step bar: the "Bombista" wordmark, the
   tagline "Forced-alignment triage", and right-aligned "v0.9.0 / A TRAMOYA tool / by CHANGO
   PEPPER" with Tramoya in clay. Without it, page 1's "the format Tramoya promotes" has no
   context on the page.

6. **The skin** (§10.3) — brutalist, INK GROUND, QUIET REGISTER. Read §10.3's table of what
   changed and why before writing CSS; Jorge rejected a louder first pass with "things compete
   with your attention which are not relevant for the main flow", and that is the governing
   constraint, not a preference.

   Tokens: bg #121211, surface #1a1a18, surface-2 #232320, paper #e6dfd1 (body type), dim
   #8b8478 (captions/labels), dimmer #635d54 (provenance, table heads, indices), line #2c2a26,
   line-2 #423e37, clay #d98b7a (the accent), clay-dim #8f5a4e.

   1px borders for structure. NO border radius anywhere. NO shadows except the popup's drop.
   No transitions — removed, not eased. Mono uppercase labels at .13em tracking. Headings are
   800-weight uppercase but SMALL: clamp(1.35rem, 2.2vw, 1.7rem). `color-scheme: dark` on :root.
   The primary button is CLAY-FILLED with near-black text; secondary buttons are a hairline that
   brightens on hover. NO WEBFONT — a local-first tool does not phone a font CDN; system sans and
   mono stacks. ONE PALETTE ONLY: no light mode, no prefers-color-scheme block. No blue anywhere.

   Bands, re-tuned for the quiet register: HIGH #4f7d63 (DELIBERATELY MUTED — 18 of 19 rows are
   HIGH and none of them need attention), REVIEW #e0a437, FAIL #ef7a70, tints #241d11 / #251715.

   The native <audio> element renders light regardless of color-scheme in Chromium. Invert it
   back down (filter: invert(.92) hue-rotate(180deg); opacity: .72; full opacity on hover) or
   build a custom transport. Do not leave a light slab as the brightest object on page 2.

   Retrofit page 2 to match, including: provenance OPEN by default in two dim columns, and
   `clean-anchor` NOT PRINTED in the why column (§8.3).

Resolve before writing page 1: `serve` runs on the user's machine and needs a real filesystem
PATH, but a browser <input type="file"> hands you a File object with no path. Either add a
small loopback route that browses the filesystem, or accept the upload and stage it. Pick one
and say why in the PR description — §9.6. Cutting the output-folder picker reduced this to two
controls.

Tests:
- page 1 renders exactly four rows and contains no free-text input except the title, and the
  title only on the .txt branch;
- the round trip is lossless for every key Bombista does not own: load songs/pimiento.json,
  emit, and assert title/artist/notes/title_translations/tempo/intro/lyrics are byte-identical,
  INCLUDING all four languages on every lyrics entry;
- page 1 has no output-directory control and no emit-format checkboxes;
- selecting a language an SP JSON does not declare is impossible through the rendered page;
- the stripped-line report is rendered before the run is startable, from the reader's
  strippedLines, not recomputed;
- tempo is never derived from anything — assert there is no code path from audio or lyrics to a
  tempo value (rules 4 and 5);
- page 3 serialises the real song-file key order and entry 0 is 0.00 with the offset in leadIn;
- the .txt branch emits the from-scratch shape of §10.2.1: artist and notes are "", intro is
  absent, title_translations and lyrics are keyed by the chosen language;
- NO emitted file ever contains a tempo key with a null or invented bpm — assert it is either
  absent or fully real (songs@c5adf65);
- page 3 renders the whole JSON with no fold or truncation control;
- "download timeline only" yields all five timing keys, never a bare timeline array;
- an emitted file carries `timelineSignedOff`, and a file emitted without a JSON download being
  pressed does not exist (there is no path to one);
- page 3's two JSON downloads are enabled when bands are all HIGH (B19's clause), the report
  download does NOT record sign-off, and no download overwrites an input path (invariant 6);
- no user-facing string in any page contains "emit", "align", "alignment" or "CP JSON";
- the why column is empty on every clean-anchor row, and the markdown report still prints every
  signal (the two have different duties);
- no emitted song file contains a `format`, `review` or `provenance` key — QA data is in the
  report only;
- the served pages reference no external URL of any kind (no font CDN, no CSS host) — this is
  narrower than B16's assertion, which forbids fetch too, and both must keep their own scope;
- the step bar renders on all four states and every step is reachable from every other.

Commit as `feat(serve): pages 1, 1.5 and 3, and the step bar`, then `gh pr create --base main`.
```

---

## After the last PR

`v1.0.0` is gated on `serve` shipping **and** line 3 of pimiento being fixable through it (§7).
PR 3 closes the second half — which is why it runs last now, not first: the gate is an acceptance
run Jorge does by hand on the real canary, and it wants the whole flow standing.

---

## PR 5 — cleanup: tempo out, `extractedAt` honest, provenance quiet, audio findable

> **Built 2026-08-16 on `chore/b20-cleanup`, 454 → 479 tests.** Two clauses below did not survive
> contact and are corrected in **§11.13**, not here, so the prompt stays readable as what was
> asked: §9.3's note wording used *"emitted"*, which §10.1 forbids on a page; and *"no emitted
> file on either branch contains a `tempo` key"* had to become *Bombista never **constructs** one*,
> because §10.2 passes an existing `tempo` through untouched.

**Branch:** `chore/b20-cleanup` · **Run after #26 merges.** Four unrelated-looking changes that
are one idea: *the page shows what helps you judge a line; the report records what an audit needs;
nothing anywhere states a fact it did not establish.* Items 2 and 4 write the same file — do them
in one pass.

```
Read docs/bombista-serve-spec.md §8.2, §9.3, §11.5 and §11.10 first, plus CLAUDE.md.
All four are decisions already taken — this PR implements them, it does not reopen them.

1. REMOVE the tempo control from page 1 (§9.3, §11.5).

   - bombista/pages.py: delete the `<input type="number" id="tempo">` row and the JS that
     reads it into the request body.
   - bombista/server.py: delete the tempo_bpm parameter and `out["tempo"] = {"bpm": tempo_bpm}`.
     Bombista now emits NO tempo key on either branch, ever.
   - Replace the control with the note in §9.3, which must name ALL FOUR keys — bpm,
     numerator, denominator, countInBars. "Add the tempo by hand" is bad advice on its own,
     because it leads to exactly the bpm-only block this PR is deleting.

   WHY, so it does not come back: tempo.bpm is both Pregonero's scaling denominator
   (performedTempo.ts) and the driver of its visual pulse (beatScheduler.ts). SongTempo declares
   numerator and denominator as REQUIRED; getBeatsPerBar does `numerator % 3`, so a bpm-only
   block returns NaN and the pulse and count-in break while the scaling keeps working. That is
   the same split-brain songs@c5adf65 deleted the placeholder blocks to avoid, one key deeper.

   Tests: assert no emitted file on either branch contains a `tempo` key; assert page 1 has no
   tempo input; assert nothing in the emit path can construct a partial tempo block.

2. STOP `extractedAt` LYING on a --words re-run (§11.10).

   Today it is stamped when the report is written, so on any --words run — which §9.4 makes THE
   correction loop, so most runs — it claims the machine listened at a time when transcription
   was skipped.

   - save_words writes a sibling `asr-words.meta.json`: extractedAt, model, device, lang, and
     the audio sha256.
   - --words reads it back and carries those values forward instead of stamping fresh.
   - If the sibling is missing (an older staging dir), OMIT extractedAt entirely and set
     `wordsReused: true`. Do not invent a time and do not fall back to an mtime — an mtime does
     not survive the staging directory being copied.

   Tests: a --words run carries the ORIGINAL extractedAt, not the run time; a --words run
   against a staging dir with no sibling omits the field rather than inventing one; a normal
   run writes both the words and the sibling.

3. REDUCE page 2's provenance to one line (§8.2).

   Exactly: `Pimiento · pimiento.m4a · faster-whisper medium (es) · measured lead-in 8.92 s`
   Quiet mono, dim, one hairline under it. No <details>, no table, no columns.

   Everything removed — sha256, device, toolVersion, extractedAt, audio duration — STAYS in
   <stem>-report.json. It is filed, not lost. The page is for judging lines by ear; the report
   is the audit artifact and may be as technical as it likes.

   Test: page 2 contains no sha256, no toolVersion and no ISO timestamp; the report JSON still
   contains all three.

4. LET A STAGING DIRECTORY NAME ITS OWN AUDIO (§11.11, decided 2026-08-16).

   Page 2's audio route needs the take, and `serve <staging> <lyrics>` has no audio argument,
   so it falls back to the path the run recorded. `align` stores that AS IT WAS GIVEN, so
   staging/pimiento holds `../../songs/audio/pimiento.m4a`, which resolves only from the
   directory that run happened in. Copy the staging dir and the player has nothing.

   Same problem as item 2 and the same fix, so do them together:

   - Add the audio path to `asr-words.meta.json` as an ABSOLUTE path (item 2 writes that
     file already — this is one more key, not another file).
   - Add a `--audio <path>` option to `serve`. This is not a new concept: page 1 already
     collects lyrics, media and language as three pickers.
   - Resolution order, and TEST IT AS AN ORDER — each step reached only when the one above
     it yields nothing:
       1. `--audio` if given
       2. the absolute path in `asr-words.meta.json`
       3. the run's recorded relative path, resolved against the staging directory's parent
       4. fail loudly — the route says the take is not where the run recorded it
   - NEVER substitute another file, and never fall back to "the only audio file nearby".
     An audio route that silently plays the wrong take makes every judgement the user made
     against it wrong, and they will not know. A player that says it cannot find the take is
     strictly better than one that finds the wrong one.

   Tests: a staging dir with a meta sibling resolves after being MOVED to a new parent; an
   explicit --audio beats the sibling; an old staging dir with neither still resolves through
   the relative path when it is run from the original parent; a staging dir whose audio is
   genuinely gone returns a loud error and not some other file on disk.

Do not change any band, threshold, signal name, or the anchoring itself. Tests must never touch
a real user path — keep the autouse fixture that redirects the staging root at tmp_path (§11.8).

Commit as `chore(serve): drop the tempo control, and stop the report and the player guessing`,
then `gh pr create --base main`.
```
