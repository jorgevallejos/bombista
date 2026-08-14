# Project Context — Timeline Extractor

_Project-specific Cowork context. Read this **after** `~/Chango Pepper/personal-context.md` (and any relevant `~/Chango Pepper/disciplines/<topic>.md`). Acknowledge briefly ("Context loaded. Ready.") and wait for Jorge to describe what's on his plate. At the end of the session, propose updates if anything important changed._

> **Stub created 2026-06-24**, spun out of the Live Lyric Translator D-wire round 3. The engineering counterpart for Claude Code lives in `CLAUDE.md` at the repo root (`projects/bombista/CLAUDE.md`). Stack, output contract, and interchange format are now decided (see Build state) — the sections below are kept as the method/contract record.

---

## Build state — v2 "Bombista" BUILT on `feat/bombista-v2` (2026-08-13), not yet merged

**Six of seven backlog items done, one gated.** Branch `feat/bombista-v2`, **196 tests green**
(verified baseline at the branch point was 60 green / 0 failing, checked in an isolated
worktree — the "60 tests" figure recorded below was accurate). Built in order, one commit per
item, per `docs/bombista-v2-kickoff.md`:

- **B3** — section-marker support deleted. Lyrics arrays carry sung lines only; a non-lyric
  entry fails loudly naming its index. This closes the "known contract wrinkle" flagged in the
  v1 build state below.
- **B12** — timelines are now **relative to a start cue**: entry 0 at `0.00`, `raw[0].start`
  banked in `leadIn {durationSec, source, confidence, apply}`, stamped `timelineVersion: 2`.
  Bombista never decides whether to apply it — that is a playback decision.
- **B1** — provenance: audio path + streamed sha256 + duration, model, device, lang,
  extractedAt, toolVersion, on every run. This is the item that would have caught the ~17 s
  Tragedia error.
- **B5** — `readers.py`: plain text or CP song JSON in, canonical CP song dict out, normalised
  at the boundary. The core pipeline is untouched. Structural only — no network, no LLM.
- **B2** — `--emit timeline|songjson|report-json|srt|lrc`, all reading the canonical CP form;
  one shared merge path with `promote`.
- **B4** — `linesHash` guard: `promote` warns loudly (never blocks) when the target's lyrics
  moved since extraction.
- **B13 (migration of the two live song files) — GATED**, deliberately not run. See below.

**The shared contract is `docs/timeline-v2-contract.md`**, co-owned with Pregonero
(live-lyric-translator) and amended by either side mid-flight. Bombista reproduces its golden
Libertad fixture exactly.

**Two things not to forget:**
1. **B13 waits on Pregonero P3.** Migrating the data before the app can reject a version it
   doesn't understand means a v1-aware app reads v2 files and fires every line ~7 s early with
   no error.
2. **Migrating Tragedia will not fix Tragedia.** Its stored timeline is the known ~17 s-late
   one, produced from the wrong audio source; migration faithfully migrates a wrong timeline.
   The fix is a **re-extraction** from audio pulled out of the animation video
   (`ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav`) — a post-merge data job.

## Build state — v1 SHIPPED (2026-07-03, forced-alignment pivot complete)

**v1 is built, accepted, and live.** The alignment-pivot run (`docs/alignment-pivot-kickoff-2026-07-03.md`, Block A) went end-to-end in one session: PRs #5–#9, #11 merged to `main`, 60 tests green. Pipeline: audio + song JSON → faster-whisper `medium` (word timestamps, ~50 s/song, model cached) → forward-only fuzzy anchoring of each line's opening tokens → `{"timeline": [...]}` per the frozen contract, with a per-line HIGH/REVIEW/FAIL markdown QA report and a `--anchor <line>=<seconds>` hand-fix loop (`--words` reuses the transcription, re-runs in <0.1 s). `extract` stages, `promote` applies (backup + diff, touches only `timeline`). **The audio-clock rule** is documented in the CLI help and repo CLAUDE.md: feed the linked video's audio for Video-mode songs, the master recording for Auto-mode songs.

**Acceptance (Tragedia, `docs/acceptance-tragedia-2026-07-03.md`):** exact convergence with the spike's derived ground truth (Δ = 0.000 on all 29 lines after two documented hand anchors: line 0 = 0.96 — whisper clamps the first word to 0.0; line 13 = 58.5 — the known misheard line, FAIL→override). vs the card reference: median −0.36 s / stdev 0.70 (cards lag sung onsets) → a **`--lead` knob is proposed, not built** — Jorge decides if cards-style timing is wanted. The regenerated timeline is **promoted into `songs/tragedia-de-cerdo-asado.json`** (backup: `tragedia-de-cerdo-asado.json.backup-20260703-112259`); only real change vs the spike-derived values: line 28's end now 160.48 (last word + 1.0 s pad). Jorge's in-app test (Auto + Video modes) closes v1.

**Re-run on new recordings:** `bombista align <audio.wav> <song.json> -o <staging>` then `promote` — no code changes needed; see repo CLAUDE.md.

**Known contract wrinkle (translator-side) — RESOLVED 2026-08-13 by B3; markers no longer exist on either side.** Original note: the translator's `validateTimeline` (`songState.ts`) has no exemption for zero-length `{0,0}` entries in its monotonic check, so any song with **mid-song section markers** would fail import. The extractor's validator exempts them (PR #9). Resolve translator-side before a marker-carrying song needs a timeline.

**Incident log (2026-07-03):** S4's PR #10 merged into `chore/scaffold-cli-and-output-contract` because that stale branch was still GitHub's **default branch** and the `gh pr create` omitted `--base`. Fixed: re-merged as PR #11 to `main`, default branch switched to `main`, scaffold branch force-reset to its pre-merge commit. Repo CLAUDE.md now mandates explicit `--base main`.

## Superseded build state (2026-06-25 — video-OCR track, parked)

**Spike RAN and PASSED — reference signed off (2026-06-25).** Claude Code ran the spike on a merged-green `main`; all 29 lyric lines got exactly one monotonic window, 0 unmatched, written through the real `serializer.write_timeline`. `docs/spike-candidate-timeline.json` is now the **signed-off reference** (Jorge + Cowork hand-verified lines 0, 11, 17, 20, 21, 28 against the video).

**Opus design pass DONE (2026-06-25) — `docs/assignment-qa-design.md`.** Architecture for assignment + human-QA settled with Jorge. Key decisions: (1) assignment is a **global DP alignment** (cards↔lines, monotonic, ops MATCH/MERGE≤3/SKIP-CARD/SKIP-LINE/SPLIT), replacing the spike's greedy walk; merge-vs-split decided by the file's **newline count = expected card count** vs cards the video shows. (2) **Video rules on structure, file rules on wording.** Splits + adds (video shows more phrasing) are **auto-applied and reported, no confirmation**; removals + hard FAILs still gate; wording mismatches (e.g. lines 11/20 defects) are flagged only, never auto-overwritten. (3) Auto-applied structural edits re-split the es/fr/nl variants via an **LLM-assisted apply step** kept separate from the deterministic core — **deferred** in the build (not on the Tragedia acceptance path); lyrics file is backed up + diffed so any auto-edit reverts. (4) Confidence = named signals → HIGH/REVIEW/FAIL bands; QA artifact = markdown report + `qa-frames/` thumbnails; CLI is two steps, `extract` (staging, never writes song JSON) → `promote`. (5) Fixed bottom-band crop (`crop=1620:320:0:760`) is the v1 standard (no position auto-detect). v1 DoD = Tragedia end-to-end, start ±0.20 s vs reference, plays in Auto mode.

**Resume at Sonnet build-out** — paste `docs/build-plan-prompt.md` into Claude Code (bombista repo). 9-step plan, TDD; check in after step 2 (alignment) and step 9 (acceptance).

**Spike result detail:** 24 lines matched 1:1; 5 two-card lyric lines (6, 14, 20, 24, 25) reconciled as merges; the intra-text pixel-diff splitter correctly split the no-gap pair at line 6 (~25.66s). End times = brightness falling edges (full card display duration).

**Source-video text defects found by OCR-verify (fix in the subtitle master, NOT the extractor — timeline carries timing only, so unaffected):**
- Line 11 displays a burned-in glitch `so I may seem deli, i, i, i, i, i, ighted.` (canonical: "so I may seem delighted.").
- Line 20 second card displays a duplicated fragment `and the oven door left hanging half open.` (canonical: "left hanging half open.").
- (Line 21 was a benign tesseract apostrophe quirk — video is correct; not a defect.)
- These may self-resolve when the master is regenerated after the producer re-record (see `animations/.../notes.md` provisional flag). **Lesson worth keeping: OCR-verify earns its place precisely by catching video↔canonical-lyric divergence — treat mismatches as human-QA flags, not failures.**

- **Stack: Python CLI (`click`)** — decided, no longer open. Output format kept language-agnostic so a later Node/in-app caller is unaffected.
- **Interchange format: JSON, locked 2026-06-24.** `{ "timeline": [...] }` envelope deserializing straight into the translator's `TimelineEntry[]`; parallel-array contract preserved (one entry per song item, section markers as `start == end == 0`). **SRT rejected** (carries cue text that duplicates the song JSON's source-of-truth lyric order, and can't represent section markers). An optional `.srt` export may be added later as a human-QA debug convenience only — never the canonical contract. This is mirrored in the translator's `project-context.md` so Prompt 16 (the A+ import button) conforms.
- **Scaffold shipped** (PR `chore/scaffold-cli-and-output-contract`, on `main`): `docs/output-contract.md` (frozen interface extracted from `songState.ts` — `TimelineEntry = {start, end}`, half-open `[start, end)`, parallel-array semantics, `videoCueLookup` quoted, `offset`/`trimStart` documented as living on `media`), `pyproject.toml`, `bombista/` package, `click` CLI entrypoint stub (`extract <video> <lyrics> -o <out>` — validates args only), `models.py` (frozen `TimelineEntry` dataclass, non-negative guard), `serializer.py` stubs, `tests/`, `CLAUDE.md`, `.gitignore`, `.claude/`.
- **Serializer greened** (PR branch `feat/green-serializer`, **pushed, open — merge next session**): `to_dict` / `write_timeline` implemented, round-trip tests pass.

**Git state (verified 2026-06-25 — both housekeeping items still OPEN):**
- `feat/green-serializer` is **NOT merged.** Local `main` is checked out and clean, but still carries the stub serializer (`to_dict` raises `NotImplementedError`); the green impl lives only on `feat/green-serializer` (2 commits ahead of `main`). After the PR merges: `git checkout main && git pull && git push && git branch -d feat/green-serializer`.
- `project-context.md` loose end **resolved** — committed to `main` (`50863cb docs: track project-context`), per the earlier recommendation. **But that commit is local-only (1 ahead of `origin/main`, unpushed)** — the `git push` above covers it.
- Stray `feat/timeline-import-button` in the **translator** repo is **still present** — delete it there: `git checkout main && git branch -d feat/timeline-import-button`.

**Spike findings (2026-06-25 — important, they correct the method):**
- Input is `animations/tragedia-de-cerdo-asado/Master Sequence only subtitles.mp4`: 1620×1080, 25fps, 160.32s, **white text on pure black, English (`.en`)**, bottom band (`crop=1620:320:0:760`).
- ffmpeg's whole-frame `scene` filter finds nothing (text too few pixels). **Working primitive = region brightness-edge:** crop band → `signalstats` YAVG → threshold (blank≈16, text≈18–19.5) → rising/falling edges. OCR (tesseract on `negate,format=gray`) is near-perfect.
- **Cards ≠ lyric lines 1:1 — the "assign N lines to N change-points in order" method is wrong for real data.** Brightness found **33 cards vs 29 lyric lines.** Two causes: (a) brightness misses text→text changes with no dark gap (consecutive cards merge — needs an intra-text signature/SSIM/hash split); (b) song `lyrics` entries 6, 14, 20, 24, 25 carry an embedded `\n` and display as two cards each. Assignment must **reconcile cards→lines via OCR fuzzy-match**, not blind ordinal mapping. → This is the genuine Opus design moment (assignment + QA loop, agenda #4/#5).
- **Reference now exists** (resolved 2026-06-25): the song JSON `timeline` was only an even-spaced scaffold; the spike's reconciled `docs/spike-candidate-timeline.json` is the hand-verified ground truth. (The scaffold in the song JSON can be replaced by this once v1 ships.)

**Workflow note (incident 2026-06-24):** the JSON-confirmation prompt was first pasted into the *translator* Claude Code by mistake, which spun up the stray empty `feat/timeline-import-button` branch (zero commits, == `main`, harmless). Lesson: keep two clearly-rooted VS Code windows (one per repo) and check the repo path Claude Code echoes before pasting.

---

## What this project is

A tool that **derives a lyric/subtitle timeline from a "lyrics-only" video** — a video that shows just the lyric phrases burned in at the correct times. Output: a `timeline` (cue start times mapped to lyric lines) that the **Live Lyric Translator** app imports per song.

It exists because lyric timing and animation should be **decoupled**: the translator's animation video is an optional visual; the timeline is independent song data. The translator's **A+ timeline-import button** (Prompt 16 in `projects/live-lyric-translator-dev/docs/d-wire-triage-and-prompts.md`) consumes the output of this tool. Until this project ships, timelines are authored offline by Cowork (the "#6 DATA task" path in that same doc) — this project automates that path.

## Why it's a separate project (not in the translator repo)

Deriving a timeline from video is a real subsystem (video decode, subtitle-region change detection, OCR verification, a progress/QA loop) with its own dependencies and failure modes. Bundling it into the Electron app would bloat the app and mix concerns. Keeping it standalone lets it run as a CLI/batch tool now and, later, be wrapped into the app (or invoked by it) once it's proven. Decided 2026-06-24.

## How it should work (method — from the #6 DATA-task approach)

1. **Input:** a lyrics-only video + the song's ordered lyric lines (the fixed phrase list).
2. **Change detection:** with `ffmpeg`, sample frames and detect the timestamps where the burned-in subtitle **region changes** (the moments a new phrase appears). This yields an ordered list of change-point timestamps.
3. **Assignment:** ~~because lyric order is fixed, assign the N lyric lines to the N change points in order (line *i* starts at change-point *i*).~~ **Revised 2026-06-25 — naive 1:1 doesn't hold.** Detected display cards ≠ lyric lines (Tragedia: 33 cards vs 29 lines): some lyric entries span two cards (embedded `\n`), and consecutive no-gap cards must be split. Assignment must **reconcile cards→lines by OCR fuzzy-match**, with a human-QA pass on splits/mismatches. (Design this at Opus level — see Build state findings.)
4. **OCR verification (only):** run OCR (e.g. Tesseract) on each region **just to verify** the assignment matched the expected line — not as the primary signal. Flag mismatches for human review.
5. **Output:** write the `timeline` in the translator's expected shape (see Output contract) — either a standalone timeline JSON/SRT the A+ button imports, or written directly into the song JSON.

## Output contract (what the translator expects)

- The translator stores a per-song `timeline: TimelineEntry[]`; the cue lookup logic is `videoCueLookup` and the type is `TimelineEntry` in `projects/live-lyric-translator-dev/src/songState.ts` — **that code is the source of truth for the exact shape.** Confirm fields there before building the writer.
- Alignment knobs live on the song's `media` block, not the timeline: `offset` (whole-song subtitle shift, seconds) and `trimStart` (skip blank lead-in). See `projects/live-lyric-translator-dev/docs/subtitle-format.md`.
- Import surface: the A+ button (Prompt 16) imports a timeline JSON or SRT and parses it to `TimelineEntry[]`. Decide the interchange format with that prompt so producer and consumer agree.

## Tech stack (DECIDED 2026-06-24 — Python CLI; see Build state)

~~Open: Python vs Node.~~ **Resolved: Python CLI (`click`).** Rationale retained below.
- **Python** is the natural fit for the CV/OCR pipeline (`ffmpeg`, OpenCV/Pillow for region diffing, `pytesseract` for OCR) and stays cleanly separate as a CLI.
- **Node/TypeScript** would ease a later in-app integration (Electron is Node; `ffmpeg-static` + `tesseract.js` exist) and shares language with the translator.
Recommendation to revisit at kickoff: start as a **Python CLI** for the pipeline, keep the output format language-agnostic (JSON/SRT) so an eventual Node/in-app caller is unaffected.

## Relationship to other projects

- **Consumer:** `projects/live-lyric-translator-dev/` — imports the timeline via the A+ button (Prompt 16). Don't duplicate the translator's schema here; reference `songState.ts`.
- **Shared data:** song lyric lines + JSON live in the root `songs/` library. This tool reads lyric order from there and may write the `timeline` back into a song JSON.

## Open questions / next steps (kickoff agenda)

All five kickoff items closed (contract, stack, prototype, QA loop, DoD) — v1 shipped 2026-07-03 via the forced-alignment pivot; see Build state. What remains is Jorge's in-app test and, per new-recording batch, a plain re-run of `extract`/`promote`. Open decisions parked for later: the proposed `--lead` knob (card-style visual lead vs sung onsets), and the translator-side marker-monotonicity wrinkle.

## Model picks

General rule in `personal-context.md`. For this project: **Opus** for the initial pipeline/architecture framing (CV + assignment + QA design), then **Sonnet** for build-out and iteration.
