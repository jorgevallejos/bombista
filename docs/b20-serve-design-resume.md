# B20 `serve` — resume (2026-08-16, PRs 1/2/4 shipped, page 2 is all that is left)

**Written so this can continue on a fresh account/session with no context loss.** Everything
below is already on disk in this repo; nothing lives in Cowork memory.

## Where things stand

| file | what it is |
|---|---|
| `docs/bombista-serve-spec.md` | The spec. §1–§7 Jorge's original, amended for naming. **§8 = page 2's visual design.** **§9 = the masthead, the step bar and pages 1, 1.5 and 3.** **§10 = the vocabulary (10.1), the format (10.2) and the ink-predominant skin (10.3).** |
| `docs/mockups/bombista-serve-mockup.html` | Clickable mockup of the **whole three-step flow**, on pimiento's real 19 lines, in the ink-predominant brutalist skin, using the real metadata and four-language lyrics from `songs/pimiento.json`. Hash-routed: `#1` input, `#1.5` processing, `#2` review, `#3` output. Steps at the top are clickable. On step 1, **Choose file** swaps between the `.sp.json` and `.txt` fixtures. |
| `docs/b20-serve-code-prompts.md` | **Four** paste-ready Claude Code prompts, one PR each. PR 4 rewritten against the new design. |

## Where the build is

**PRs 1, 2 and 4 merged** (#22, #23, #24). `main` at `cf7961e`, **389 tests green**. The umbrella
pointer was bumped to match (`fc9d19e`). Docs merged as #21, so §8/§9/§10 are on `main` — **but
§11 and everything after it is still only in the working tree and needs a `docs(B20)` commit.**

**§11.2's action is done** (2026-08-15 19:07): the canary was re-run with `--emit report-json`,
reproduced **HIGH 18 / REVIEW 1 / FAIL 0**, and `staging/pimiento/pimiento-report.json` now carries
the provenance §8.2 renders.

**Page 2 is the only page left, and PR 3 is now unblocked.** Both of its questions are answered:
§8.6 (line 0 is not special) and §11.3 (the fixture, two tiers).

`serve` now has seven routes: `/api/session`, `/api/reanchor`, `/api/emit` (PR 2) and `/api/run`
(start/poll/cancel), `/api/lyrics`, `/api/browse`, `/api/download` (PR 4).

**§11 has grown to twelve findings.** Read it before touching anything — §11.5 in particular
(tempo is whole or absent, checked against Pregonero's `beatScheduler.ts`) and §11.8 (a test that
passed while proving nothing).

## Design is closed. Prompts in `b20-serve-code-prompts.md`.

**Settled last, 2026-08-15:**

- **`timelineSignedOff` is in** — an ISO timestamp beside `linesHash`, written when a JSON download
  is pressed. Bombista therefore owns **five** keys, not four. §10.2.
- **`songs/_template.json` was wrong and has been corrected** — `es` added to
  `title_translations` (the same file already carried `es` in `intro` and `lyrics`), and the
  **The catalogue was backfilled to match the same day** — all 13 `songs/*.json` now carry `es`
  first in `title_translations`. One line per file, 14 including the template, nothing else
  touched. **The commit is Jorge's**, in the `songs` submodule.
- ⚠ **`tempo` is omitted when unset, never a null scaffold.** A pass added a scaffold to the
  template, to three song files and to Bombista's from-scratch output; all three were reverted
  before committing. `songs@c5adf65` already settled this — placeholder tempo was removed
  "outright — not replaced with a flag or a null", because `tempo.bpm` drives both Pregonero's
  scaling denominator and its visual pulse and an invented number cannot serve both. Pregonero
  degrades safely when the key is absent. **Do not reintroduce it.**
- **§8.6 settled 2026-08-16: line 0 is not special.** Jorge: *"the first value should not be
  considered anything special. It is Pregonero that will make a distinction between lead-in and
  line 0 — a performance-time topic, not a timeline-extractor one."* No lead-in widget anywhere.
  **This reverses what PR 2 built** — line 0 is refused on every route today and PR 3 must undo it,
  along with §6's test.
- **The fixture is settled (§11.3): two tiers.** Synthetic fixture in CI for the mechanism; the
  pimiento canary as an opt-in acceptance run against the private vault. No lyrics, no real
  `asr-words.jsonl`, no audio in the Bombista repo — it ships as `pipx install`.

## Settled in the fourth pass (Jorge on contrast, and the from-scratch JSON)

1. **Quiet register.** Jorge on the first ink pass: *"a lot of contrast… things compete with your
   attention which are not relevant for the main flow."* **Contrast is a budget** and it is spent on
   the one flagged line and the control the hand is going to. Structure dropped to 1px hairlines,
   shadows removed, the primary button became clay-filled, headings shrank to ~1.6rem, the step bar
   lost its filled numeral blocks. §10.3 has the full before/after table.
2. **HIGH is deliberately muted** (`#4f7d63`) and **`clean-anchor` is no longer printed.** Eighteen
   of nineteen rows are fine; a bright chip and a repeated token eighteen times outshout the one row
   that needs judging. The markdown report still prints every signal — different duty.
3. **Provenance is open by default**, in two dim columns. Collapsed, its summary was an unreadable
   run-on. The reason to hide it was that it was loud; the fix was to make it quiet. **Quiet, not
   hidden** is now the general rule.
4. **The `Expand lyrics` control on page 3 is cut.** The full JSON renders, the window scrolls.
5. **Two shapes, one format** (§10.2.1) — Jorge's pasted sketch is the contract for the from-scratch
   case. `.txt` in → a new file with `artist: ""`, `notes: ""`, `title_translations` keyed by the
   chosen language, `tempo` **omitted unless real**, no `intro`, `lyrics` in one language. `.sp.json` in
   → pass-through, five keys written, nothing else touched. The mockup demonstrates both: toggling
   the fixture on step 1 changes what step 3 emits.
6. **The native `<audio>` element** ignores `color-scheme` in Chromium and rendered as the brightest
   object on page 2. Inverted back down; noted as a candidate for a custom transport later.

## Settled in the third pass (Jorge's review of the skin, the copy and the payload)

1. **Ink-predominant, not paper.** Jorge: black should dominate. Same Chango Pepper vocabulary,
   inverted ground; clay `#d98b7a` the only accent. **One palette; no light mode.** §10.3.
   *Tokens were re-tuned again in the fourth pass — take them from §10.3, not from here.*
2. **A masthead on every page** — `Bombista` / *Forced-alignment triage*, and right-aligned
   *v0.9.0 · A **Tramoya** tool · by **Chango Pepper***. Jorge's note: without it, page 1's "the
   format Tramoya promotes" had no context to attach to. §9.1.
3. **The SP JSON *is* the `songs/*.json` format.** This was the big correction. A first pass
   invented a shape and flattened `lyrics` to strings, which would have destroyed every
   translation. There is no new schema: *Song Performance JSON* is the **name** for the format
   that already exists. Bombista owns five keys — `linesHash`, `timelineSignedOff`,
   `timelineVersion`, `leadIn`, `timeline` — and passes `title`, `artist`, `notes`, `title_translations`, `tempo`, `intro`,
   `lyrics` through untouched. §10.2.
4. **`linesHash` stays in the song file** (Jorge asked for the judgement). It guards the
   lyrics↔timeline correspondence *in that file*; in a report it is decorative. It should also
   appear in the report for the audit trail.
5. **Bands, signals, ASR provenance and the hand-set record move to the report.** ⚠ **One open
   question for Jorge:** whether a single `timelineSignedOff` timestamp stays in the song file. If
   not, §3's edit-provenance clause has to be struck rather than left unsatisfied. §10.2.
6. ~~Page 3 folds `lyrics` by default.~~ **Reversed in the fourth pass** — the fold control was cut.
7. **`Download timeline only` yields all five timing keys**, never a bare `timeline` array — a
   timeline without `linesHash` is exactly the unguarded artifact B4 exists to prevent.
8. **Copy fixes:** *"The language on the recording and the lyrics file"* (the rule is enforced, not
   explained); *"Runs on your local machine"*; page 2's *"Click a START time to adjust it"* moved
   out of the lede to sit directly above the table.

## Settled in the second pass (Jorge's review of pages 1 and 3)

1. **Step names: `1 Input · 2 Review · 3 Output`.** *Set up*, *alignment* and *emit* are retired
   from the interface. §10.1.
2. **The format is the Song Performance JSON — `SP JSON`, `.sp.json`.** It is the **whole
   document**: lyrics, metadata, the timeline as one section, and everything Jorge later adds for
   performance support (translations, projection cues, animation triggers). It replaces both "CP
   song JSON" and the ambiguous bare "song JSON". Documentation home: likely a section on the
   **Tramoya tab of changopepper.com** — tracked in §9.6, not blocking B20. *Superseded in the
   third pass: it is not a new format, it is the name for `songs/*.json`.*
3. **Page 1 is four rows**: Lyrics · Media source · Language · Model. The output-folder picker and
   the *Also write* checkboxes are **cut**. File name only, never the path. No branch dropdown —
   the extension answers it. The Language dropdown is **constrained by the languages the SP JSON
   declares**. The Model caption must say it runs locally and nothing is uploaded. Button is
   **`Process song →`**, primary weight.
4. **Page 3 is a caption, the JSON, and three downloads**: `Download JSON file` ·
   `Download timeline only` · `Download report`. The *ready to write into `staging/`* line and the
   file list are **cut** — they described a write to a folder the app no longer chooses. **Either
   JSON download records the sign-off; the report does not.** *The key-order fix here was
   superseded in the third pass by the fold, once the payload became the real song file.*
5. **Brutalist skin, borrowed from changopepper.com** — 3px borders, no radii, hard offset shadows,
   no easing, mono uppercase labels, **no webfont**. The blue edit colour is gone; clay took its
   jobs. **The bands keep their hue** — the one deliberate exception, because 19 rows must be
   scannable in half a second. §10.3. *The paper ground was inverted to ink in the third pass.*

## Settled in the first pass (still standing)

1. **Stack:** stdlib `http.server.ThreadingHTTPServer`, one page, inline CSS/JS, vanilla JS, no
   build step. `fetch` to loopback routes. B16's zero-external-reference assertion does **not**
   extend to `serve`'s page — keep it scoped to `write_html_review`.
2. **Page 2's governing rule, Jorge's call:** the list of lines *is* the interface. A lead-in panel,
   a needs-attention card, an editor pane, a re-anchor banner and a JSON preview were all cut.
3. **The start time is the control.** One stepper in a popup, bounds clamp silently,
   **press-and-hold auto-repeats** (380 ms then 45 ms) — load-bearing, because line 3's error is
   1.22 s = 24 separate presses.
4. **Line 0's number is the lead-in control** (§8.6). ⚠ **Still needs Jorge's confirmation.**
5. **Signal glosses** move into `anchoring.py` beside the signal names — PR 1.
6. **`Confirm timeline →` on page 2 goes to page 3.**

## The fixture — measured, not estimated

Run of the real `anchoring.py` against the real `staging/pimiento/asr-words.jsonl`:

- **Line 3's true onset is 36.32 s.** The ASR heard *"Este"* for *"desde"* at 36.32; anchoring fell
  back to the second token *"niño"* at 37.54. The error is exactly one word: **1.22 s**.
- Any override in **`[29.47, 39.86]`** leaves all 15 lines below identical — including 36.32.
- At **≥ 39.88 s** line 4 flips **HIGH → REVIEW (`gap-outlier`)** — the gap to line 4 drops below a
  third of the song's median gap. Real threshold, inside the allowed range.
- ≥ 43.36 line 4 also moves to 44.28 (`lead-fallback, gap-outlier`); ≥ 44.30 it `no-anchor`s. Both
  unreachable from the page because the neighbour bounds stop short.

To regenerate: the sweep script loads `anchoring.py` + `models.py` directly, reads
`staging/pimiento/asr-words.jsonl` and `songs/pimiento.json`, and calls
`anchor_lines(words, lines, overrides={3: v})` across the range. The mockup's baked lookup table
lives in the `DATA` object at the bottom of the mockup HTML.

## Still open

- **Line 0 as the lead-in control** — Jorge to confirm (§8.6).
- **One correction at a time?** The mockup carries one; `anchor_lines` already takes a mapping. The
  rail and the divider would have to key off the *earliest* edited line. Decide before PR 3.
- **Page 1's file pickers** (§9.6). `serve` needs a real filesystem path; a browser
  `<input type="file">` gives a File object with none. Either a loopback filesystem-browse route or
  accept-and-stage. Cutting the output-folder picker reduced this from three controls to two.
  Must be resolved before PR 4.
- **Where the SP JSON format is documented** — a Tramoya-tab section on the website is the
  candidate, and page 1's *See an example* link points there. Not a B20 dependency.
- **`intro`** — it exists in the song format, it is translated like a line, but it is not in
  `lyrics`, so it has no timeline entry and `linesHash` does not cover it. Passed through and
  ignored. If it is ever projected, that is a B4 problem.
- **The quiet ink skin has had one round of Jorge's direction; the result is unreviewed** (§10.3).
- Nothing has been committed to git. The three doc files and the mockup are **untracked working-tree
  files**; they belong on the B20 branch, and that is Jorge's to do (repo rule: branch + PR, never
  straight to main; submodule pointer bumps are his).

## Next actions

1. Run **PR 1** (signal glosses) — smallest, independent, unblocks the rest. Nothing gates it.
2. **PR 2** (server + routes). Nothing gates it either.
3. **PR 4** (masthead, pages 1, 1.5, 3, the step bar, the shared skin) — unblocked, run it next.
4. Answer §8.6 (line 0), then **PR 3** (page 2).
5. `v1.0.0` ships when `serve` exists **and** line 3 of pimiento is fixable through it (§7).
