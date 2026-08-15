# B20 `serve` — HANDOFF (2026-08-16)

> **Start here.** This file is the entry point for a fresh session, on any account. Everything
> needed is on disk in this repo — **nothing essential lives in Cowork memory**, which does not
> travel between accounts.

## How to work on this (carry these over — they are not in the repo anywhere else)

- **Jorge works at PM level.** Handle the file edits and supply exact, paste-ready Claude Code
  prompts. Do not walk him through steps he did not ask for.
- **Decide, don't escalate.** Only bring him things with a **visible effect** that need his input —
  a control appearing or disappearing, wording he will read, an irreversible or expensive choice.
  Internal correctness (timestamps, key names, test structure) gets decided, recorded in the spec,
  and made reversible. His words: *"unless there is a visible effect that requires my input, you
  propose a solution and solve it accordingly."*
- **Read `git log` before "fixing" a missing or inconsistent field.** Several apparent gaps in this
  repo are decisions with written reasoning — `songs@c5adf65` is the canonical example.
- **Cowork cannot commit or push** (git over the device bridge is inspect-only and leaves a stuck
  `.git/index.lock`). Write files, then hand Jorge exact commands. **`#` is not a comment in his
  interactive zsh** — never put inline comments in shell commands for him.
- **Repo rule:** branch + PR, never straight to `main`; submodule pointer bumps are his.
- Deliverables are `.md`; every project lives in `projects/<name>/`.

## Where things stand

| file | what it is |
|---|---|
| `docs/bombista-serve-spec.md` | The spec. §1–§7 Jorge's original, amended for naming. **§8 = page 2's visual design.** **§9 = the masthead, the step bar and pages 1, 1.5 and 3.** **§10 = the vocabulary (10.1), the format (10.2) and the ink-predominant skin (10.3).** |
| `docs/mockups/bombista-serve-mockup.html` | Clickable mockup of the **whole three-step flow**, on pimiento's real 19 lines, in the ink-predominant brutalist skin, using the real metadata and four-language lyrics from `songs/pimiento.json`. Hash-routed: `#1` input, `#1.5` processing, `#2` review, `#3` output. Steps at the top are clickable. On step 1, **Choose file** swaps between the `.json` and `.txt` fixtures. |
| `docs/b20-serve-code-prompts.md` | **Five** paste-ready Claude Code prompts, one PR each. **All five are run and merged** — the file is now a record of how B20 was built, not a queue. |

## Where the build is (2026-08-16)

**B20 is built. All five PRs are merged** — #22, #23, #24, #26 and #27 — and `main` carries
**479 tests green**. The 3 skips are the opt-in pimiento canary; all three pass against the vault.
Code drove page 2 in a real browser on the real canary: the stepper, the press-and-hold, the
debounced re-anchor, the before/after bands and the line-0 move all behave.

**Nothing is left to build. What is left is one acceptance run** — §7's gate, below.

`serve` has eight routes: `/api/session`, `/api/reanchor`, `/api/emit` (PR 2), `/api/run`
(start/poll/cancel), `/api/lyrics`, `/api/browse`, `/api/download` (PR 4) and `/api/audio` with
ranges, plus `GET /review/rows` (PR 3). `serve` takes `[STAGING_DIR] [SONG_JSON_OR_LYRICS_TXT]`
and `--audio`, `--lang`, `--port`.

**§11 has grown to twenty-four findings across §11.1–§11.13.** Read it before touching anything —
§11.5 (tempo is whole or absent, checked against Pregonero's `beatScheduler.ts`), §11.8 (a test that
passed while proving nothing), **§11.11** (what page 2 found), **§11.13** (what the cleanup found)
and **§11.12** (how the docs nearly lost half of themselves — a process rule, not a code one).

**The docs are all on GitHub.** §11.1–§11.10 as #25, §11.11–§11.12 on #26, §11.13 on #27.

## What page 2 settled (§11.11, 2026-08-16)

1. **`leadIn.source` is `manual`, never `hand-set`.** `docs/timeline-v2-contract.md` is frozen at
   `"measured" | "manual" | "none"` and Pregonero validates against exactly those; `manual` is the
   contract's own word for *a human overrode it*. `to_dict` now refuses `hand-set` outright. **This
   is the one thing §8.6's reversal needed that was written down nowhere** — before it, every
   lead-in was measured by definition, so `source` had nothing to distinguish. **The mockup and the
   prompts have been corrected to say `manual`.**
2. **The debounce fired in the gap before the auto-repeat started.** `HOLD_DELAY` 380 ms,
   `DEBOUNCE` 250 ms — so a plain debounce commits at t=250 and re-renders the list out from under
   a cursor still holding the button. §8.5's finding a third time. **The mockup could not have found
   it**: it re-rendered locally and instantly, with no round trip to land mid-press. Expect more of
   that class from anything built against the mockup — *its fidelity ends where the network begins.*
3. **Line 0 is not named in the help copy either.** The mockup said *"…line 0 included"*; §8.2's
   wording was built instead, and **the mockup now matches**. §8.6 lists three ways line 0 must not
   be marked; the one sentence of help copy was a fourth it did not think to name.
4. **Page 2's rows render in `pages.py`, not in the page's JS** — the one deliberate departure from
   the mockup, so §6's *every row carries its line's text* can be asserted about rows rather than
   about the spelling of a JS template. The page fetches the same markup back from
   `GET /review/rows`. One template, not two.
5. **Many corrections at once, not one.** `anchor_lines` takes a mapping and PR 2's routes already
   accepted one; limiting the page to a single edit would have been a new restriction. The rail and
   the divider key off the **earliest** edited line, exactly as §8.9 predicted.
6. **§6's old clause did not survive the inversion in letter.** Moving line 0 *does* re-anchor — it
   goes through `anchor_lines` like any other override. What is true and now tested: **no raw onset
   below it moves, and no band changes.**

## What the cleanup settled (§11.13, 2026-08-16)

1. **A section quoting page copy is not exempt from §10.1.** §9.3's replacement note said *"so the
   emitted file carries no `tempo` block"* — and *emit* is a retired word that PR 4's own test bans
   from every page. Built as *"so the file it writes carries…"*. **Second time**: §11.11 found the
   first, in the line-0 instruction. §10.1 governs the page no matter which section wrote the words.
2. **`tempo` passes through; Bombista never *constructs* one.** The prompt asked for a test that no
   emitted file contains a `tempo` key, which contradicts §10.2's pass-through — libertad and
   pimiento both carry a real block. §11.5's own wording is the rule that holds both. Asserted
   structurally over the AST, not by grep, so `server.py` keeps the docstrings explaining why there
   is no bpm.
3. **A `--words` run carries forward some provenance and not the rest.** Carried: `extractedAt`,
   `model`, `device`, `lang` — facts about *when and how the machine listened*, which a run that
   skipped transcription did not establish. Still its own: `sha256`, `durationSec`, `audio` — that
   run did hash the file it was pointed at, and the three are one coherent description of one file.
4. **The sibling is a *partial* provenance carrier**, and the poorest of the three `_find_provenance`
   reads — but the only one a page-1 run leaves behind. It gave the report header a shape that had
   never existed and raised `KeyError` on download. Fixed by laying unknowns down first and recorded
   facts over them: a report that says `unknown` tells the truth; one that cannot render says nothing.
5. **A decision is not landed until the mockup agrees with it** — now three for three. The mockup
   still had the tempo dropdown, an `out.tempo` inventing pimiento's real 6/8, and the full
   provenance table. All corrected, with the reasoning left as a comment where each used to be.

## Next actions

**Only one thing is left, and it is not a build.**

1. **The §7 acceptance run — the `v1.0.0` gate.** `v1.0.0` is gated on `serve` existing **and line 3
   of pimiento being fixable through it**. `serve` exists. So: boot the real canary into the review,
   move line 3 from **37.54 → 36.32** with the stepper, confirm all 19 lines read HIGH and the 15
   below line 3 are unchanged, and download the JSON. It is a thing Jorge does once, by hand — CI
   asserts the mechanism on the synthetic fixture, not this.
2. **Then tag `v1.0.0`** and bump the umbrella pointer a last time.
3. **After that, the skin review.** §10.3 has had one round of Jorge's direction as a mockup and has
   never been reviewed on the built pages. The acceptance run is the first time he sees the real
   thing in a browser — worth looking with both hats on.

## The stale docs commit (2026-08-16) — what happened and how it was fixed

On 2026-08-15 the spec was edited from two directions in the same hour. Cowork wrote the design
decisions (§8.2, §9.3, §11.5, §11.9, §11.10) into the working tree; Claude Code wrote §11.11 and the
§6/§8.6/§8.9 closures on `feat/b20-page2`. Both were newer than `main`; **neither contained the
other.** `2cb5af2` (20:49) wrote its whole file over `886bfa8` (20:42) and reverted §11.11, plus it
resurrected `docs/_to_delete/`. It survived only because `886bfa8` had already been pushed to #26.

**Reconstructed by three-way merge against `0d4b999`** — one conflict, in a single sentence. The
spec on disk now carries both halves. Recorded as **§11.12**, with the three rules it earns; the
first is *a whole-file write is not an edit — diff before writing a doc the branch may have moved.*

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
   chosen language, `tempo` **omitted unless real**, no `intro`, `lyrics` in one language. A song `.json` in
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
5. **Bands, signals, ASR provenance and the hand-set record move to the report.** ~~⚠ One open
   question for Jorge: whether a single `timelineSignedOff` timestamp stays in the song file.~~
   **Answered 2026-08-15: it stays** — see *Settled last* above. §3's edit-provenance clause is
   satisfied by that one scalar. §10.2.
6. ~~Page 3 folds `lyrics` by default.~~ **Reversed in the fourth pass** — the fold control was cut.
7. **`Download timeline only` yields all five timing keys**, never a bare `timeline` array — a
   timeline without `linesHash` is exactly the unguarded artifact B4 exists to prevent.
8. **Copy fixes:** *"The language on the recording and the lyrics file"* (the rule is enforced, not
   explained); *"Runs on your local machine"*; page 2's *"Click a START time to adjust it"* moved
   out of the lede to sit directly above the table.

## Settled in the second pass (Jorge's review of pages 1 and 3)

1. **Step names: `1 Input · 2 Review · 3 Output`.** *Set up*, *alignment* and *emit* are retired
   from the interface. §10.1.
2. **The format is the Song Performance JSON — `SP JSON`, extension `.json`.** It is the **whole
   document**: lyrics, metadata, the timeline as one section, and everything Jorge later adds for
   performance support (translations, projection cues, animation triggers). It replaces both "CP
   song JSON" and the ambiguous bare "song JSON". Documentation home: likely a section on the
   **Tramoya tab of changopepper.com** — tracked in §9.6, not blocking B20. *Superseded in the
   third pass: it is not a new format, it is the name for `songs/*.json`. The `.sp.json` extension
   this pass gave it was dropped by §12.2 for the same reason — a distinct extension reintroduces
   the distinction that correction removed.*
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
4. ~~**Line 0's number is the lead-in control** (§8.6).~~ **Confirmed and then inverted,
   2026-08-16: line 0 is not special at all** — same stepper as any other line, no lead-in control
   anywhere. Built in #26. §8.6.
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

Everything that gated a PR is now closed. What is left is genuinely open, and none of it blocks
`v1.0.0`:

- **A staging directory made before PR 5 has no `asr-words.meta.json`.** `staging/pimiento` is one:
  `extractedAt` is omitted and `wordsReused: true` rather than invented, and the audio resolves by
  the recorded relative path — which works from `projects/bombista` and nowhere else. `--audio`
  names it explicitly if that ever fails. Not a bug; the honest behaviour of an old directory.
- **"This is not the audio that was transcribed."** The sibling records the `sha256`, so the warning
  is now *possible* — it is not built. §11.13.
- **Killing the transcription outright** (§11.6). Cancel currently abandons the worker rather than
  killing it — the user's experience is correct and the cost is a thread finishing work nobody
  reads. Not worth a subprocess boundary yet.
- **Where the SP JSON format is documented** — a Tramoya-tab section on the website is the
  candidate, and page 1's *See an example* link points there. Not a B20 dependency.
- **`intro`** — it exists in the song format, it is translated like a line, but it is not in
  `lyrics`, so it has no timeline entry and `linesHash` does not cover it. Passed through and
  ignored. If it is ever projected, that is a B4 problem.
- **The quiet ink skin was designed but never reviewed on the built pages** (§10.3). It has had one
  round of Jorge's direction as a mockup; page 2 is now standing in a real browser, so the review
  can finally be of the thing rather than of a drawing of it.

**Closed since this list was written:** line 0 (§8.6, not special), one-correction-at-a-time (§8.9,
many), page 1's file pickers (§9.6, `/api/browse`), the audio path (§11.11, four-step resolution in
#27), and *nothing has been committed to git* — the docs are on GitHub as #21, #25, #26 and #27.
