# Project Context — Timeline Extractor

_Project-specific Cowork context. Read this **after** `~/Chango Pepper/personal-context.md` (and any relevant `~/Chango Pepper/disciplines/<topic>.md`). Acknowledge briefly ("Context loaded. Ready.") and wait for Jorge to describe what's on his plate. At the end of the session, propose updates if anything important changed._

> **Stub created 2026-06-24**, spun out of the Live Lyric Translator D-wire round 3. The engineering counterpart for Claude Code lives in `CLAUDE.md` at the repo root (`projects/timeline-extractor/CLAUDE.md`). Stack, output contract, and interchange format are now decided (see Build state) — the sections below are kept as the method/contract record.

---

## Build state — where to resume (updated 2026-07-03)

**PIVOT (2026-07-03): core mechanism is now audio forced alignment, not video change-detection + OCR.** The translator's ASR spike (branch `spike/asr-following` there, report `docs/asr-spike-report-2026-07.md`) proved faster-whisper `medium` batch-aligns a full song near-verbatim in 46 s — strictly better than the video pipeline for deriving timings, and it works for songs with no video at all (this week's new recordings). Scope sharpened with Jorge: **the tool only defines the timeline** — it never edits lyric text; wording/defect QA on videos is out of scope. The video-OCR work (branches `feat/lift-spike`, `feat/dp-alignment`, both pushed) is **parked unmerged** — preserved on origin, not deleted. The design doc's QA concepts (confidence bands, `extract`→`promote`, markdown report) carry over to the alignment pipeline. The spike also exposed that the translator's shipped Tragedia timeline is misaligned scaffolding (~17 s late vs its linked video) — regenerating it is this project's **acceptance test**, regardless of when new recordings land.

**Resume:** paste `docs/alignment-pivot-kickoff-2026-07-03.md` into Claude Code at the extractor repo (Fable/Opus coordinator + Sonnet slices). Part B of the same doc is translator-repo housekeeping.

## Superseded build state (2026-06-25 — video-OCR track, parked)

**Spike RAN and PASSED — reference signed off (2026-06-25).** Claude Code ran the spike on a merged-green `main`; all 29 lyric lines got exactly one monotonic window, 0 unmatched, written through the real `serializer.write_timeline`. `docs/spike-candidate-timeline.json` is now the **signed-off reference** (Jorge + Cowork hand-verified lines 0, 11, 17, 20, 21, 28 against the video).

**Opus design pass DONE (2026-06-25) — `docs/assignment-qa-design.md`.** Architecture for assignment + human-QA settled with Jorge. Key decisions: (1) assignment is a **global DP alignment** (cards↔lines, monotonic, ops MATCH/MERGE≤3/SKIP-CARD/SKIP-LINE/SPLIT), replacing the spike's greedy walk; merge-vs-split decided by the file's **newline count = expected card count** vs cards the video shows. (2) **Video rules on structure, file rules on wording.** Splits + adds (video shows more phrasing) are **auto-applied and reported, no confirmation**; removals + hard FAILs still gate; wording mismatches (e.g. lines 11/20 defects) are flagged only, never auto-overwritten. (3) Auto-applied structural edits re-split the es/fr/nl variants via an **LLM-assisted apply step** kept separate from the deterministic core — **deferred** in the build (not on the Tragedia acceptance path); lyrics file is backed up + diffed so any auto-edit reverts. (4) Confidence = named signals → HIGH/REVIEW/FAIL bands; QA artifact = markdown report + `qa-frames/` thumbnails; CLI is two steps, `extract` (staging, never writes song JSON) → `promote`. (5) Fixed bottom-band crop (`crop=1620:320:0:760`) is the v1 standard (no position auto-detect). v1 DoD = Tragedia end-to-end, start ±0.20 s vs reference, plays in Auto mode.

**Resume at Sonnet build-out** — paste `docs/build-plan-prompt.md` into Claude Code (timeline-extractor repo). 9-step plan, TDD; check in after step 2 (alignment) and step 9 (acceptance).

**Spike result detail:** 24 lines matched 1:1; 5 two-card lyric lines (6, 14, 20, 24, 25) reconciled as merges; the intra-text pixel-diff splitter correctly split the no-gap pair at line 6 (~25.66s). End times = brightness falling edges (full card display duration).

**Source-video text defects found by OCR-verify (fix in the subtitle master, NOT the extractor — timeline carries timing only, so unaffected):**
- Line 11 displays a burned-in glitch `so I may seem deli, i, i, i, i, i, ighted.` (canonical: "so I may seem delighted.").
- Line 20 second card displays a duplicated fragment `and the oven door left hanging half open.` (canonical: "left hanging half open.").
- (Line 21 was a benign tesseract apostrophe quirk — video is correct; not a defect.)
- These may self-resolve when the master is regenerated after the producer re-record (see `animations/.../notes.md` provisional flag). **Lesson worth keeping: OCR-verify earns its place precisely by catching video↔canonical-lyric divergence — treat mismatches as human-QA flags, not failures.**

- **Stack: Python CLI (`click`)** — decided, no longer open. Output format kept language-agnostic so a later Node/in-app caller is unaffected.
- **Interchange format: JSON, locked 2026-06-24.** `{ "timeline": [...] }` envelope deserializing straight into the translator's `TimelineEntry[]`; parallel-array contract preserved (one entry per song item, section markers as `start == end == 0`). **SRT rejected** (carries cue text that duplicates the song JSON's source-of-truth lyric order, and can't represent section markers). An optional `.srt` export may be added later as a human-QA debug convenience only — never the canonical contract. This is mirrored in the translator's `project-context.md` so Prompt 16 (the A+ import button) conforms.
- **Scaffold shipped** (PR `chore/scaffold-cli-and-output-contract`, on `main`): `docs/output-contract.md` (frozen interface extracted from `songState.ts` — `TimelineEntry = {start, end}`, half-open `[start, end)`, parallel-array semantics, `videoCueLookup` quoted, `offset`/`trimStart` documented as living on `media`), `pyproject.toml`, `timeline_extractor/` package, `click` CLI entrypoint stub (`extract <video> <lyrics> -o <out>` — validates args only), `models.py` (frozen `TimelineEntry` dataclass, non-negative guard), `serializer.py` stubs, `tests/`, `CLAUDE.md`, `.gitignore`, `.claude/`.
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

1. ✅ **Done** — `TimelineEntry` shape confirmed (`docs/output-contract.md`) and import format locked to **JSON** (coordinated with Prompt 16; see Build state).
2. ✅ **Done** — stack picked (**Python CLI**), repo + `CLAUDE.md` stood up, scaffold + serializer shipped.
3. ▶️ **NEXT** — prototype change-detection on the Tragedia lyrics-only video (29 lines) and measure timestamp accuracy vs a hand-checked reference. (After merging the `feat/green-serializer` PR.)
4. ✅ **Done** — human-QA loop designed (`docs/assignment-qa-design.md` §4): named-signal confidence → HIGH/REVIEW/FAIL, markdown report + thumbnails, `extract`→`promote` with splits/adds auto-applied and only removals/FAILs gating.
5. ✅ **Done** — v1 DoD defined (`docs/assignment-qa-design.md` §6): Tragedia end-to-end, start ±0.20 s / end ±0.30 s vs `spike-candidate-timeline.json`, plays in Auto mode. Build sequenced in `docs/build-plan-prompt.md`.

## Model picks

General rule in `personal-context.md`. For this project: **Opus** for the initial pipeline/architecture framing (CV + assignment + QA design), then **Sonnet** for build-out and iteration.
