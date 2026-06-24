# Project Context — Timeline Extractor

_Project-specific Cowork context. Read this **after** `~/Chango Pepper/personal-context.md` (and any relevant `~/Chango Pepper/disciplines/<topic>.md`). Acknowledge briefly ("Context loaded. Ready.") and wait for Jorge to describe what's on his plate. At the end of the session, propose updates if anything important changed._

> **Stub created 2026-06-24**, spun out of the Live Lyric Translator D-wire round 3. The engineering counterpart for Claude Code lives in `CLAUDE.md` at the repo root (`projects/timeline-extractor/CLAUDE.md`). Stack, output contract, and interchange format are now decided (see Build state) — the sections below are kept as the method/contract record.

---

## Build state — where to resume (updated 2026-06-24)

**Kickoff done in one Cowork session + two Claude Code PRs.** Decisions locked and the serializer foundation is green. Resume at the change-detection prototype.

- **Stack: Python CLI (`click`)** — decided, no longer open. Output format kept language-agnostic so a later Node/in-app caller is unaffected.
- **Interchange format: JSON, locked 2026-06-24.** `{ "timeline": [...] }` envelope deserializing straight into the translator's `TimelineEntry[]`; parallel-array contract preserved (one entry per song item, section markers as `start == end == 0`). **SRT rejected** (carries cue text that duplicates the song JSON's source-of-truth lyric order, and can't represent section markers). An optional `.srt` export may be added later as a human-QA debug convenience only — never the canonical contract. This is mirrored in the translator's `project-context.md` so Prompt 16 (the A+ import button) conforms.
- **Scaffold shipped** (PR `chore/scaffold-cli-and-output-contract`, on `main`): `docs/output-contract.md` (frozen interface extracted from `songState.ts` — `TimelineEntry = {start, end}`, half-open `[start, end)`, parallel-array semantics, `videoCueLookup` quoted, `offset`/`trimStart` documented as living on `media`), `pyproject.toml`, `timeline_extractor/` package, `click` CLI entrypoint stub (`extract <video> <lyrics> -o <out>` — validates args only), `models.py` (frozen `TimelineEntry` dataclass, non-negative guard), `serializer.py` stubs, `tests/`, `CLAUDE.md`, `.gitignore`, `.claude/`.
- **Serializer greened** (PR branch `feat/green-serializer`, **pushed, open — merge next session**): `to_dict` / `write_timeline` implemented, round-trip tests pass.

**Git state at wrap (2026-06-24):**
- Extractor repo is on `feat/green-serializer` (pushed to origin). **First action next session: review/merge that PR, then `git checkout main && git pull`.**
- **Loose end:** `project-context.md` (this file) is **untracked** in the extractor repo (`??`). In the translator repo the equivalent file *is* committed — decide whether to `git add` it here for consistency, or gitignore it. Recommend committing it.

**Resume here → kickoff agenda item #3:** prototype `ffmpeg` change-detection on the Tragedia lyrics-only video (29 lines) and measure timestamp accuracy vs a hand-checked reference. (Cowork still owes the paste-ready Claude Code prompt for this — ask for it at the start of next session.)

**Workflow note (incident 2026-06-24):** the JSON-confirmation prompt was first pasted into the *translator* Claude Code by mistake, which spun up a stray empty `feat/timeline-import-button` branch (zero commits, == `main`, harmless). Couldn't be deleted remotely due to an active git lock — **delete it in the translator Claude Code session: `git checkout main && git branch -d feat/timeline-import-button`.** Lesson: keep two clearly-rooted VS Code windows (one per repo) and check the repo path Claude Code echoes before pasting.

---

## What this project is

A tool that **derives a lyric/subtitle timeline from a "lyrics-only" video** — a video that shows just the lyric phrases burned in at the correct times. Output: a `timeline` (cue start times mapped to lyric lines) that the **Live Lyric Translator** app imports per song.

It exists because lyric timing and animation should be **decoupled**: the translator's animation video is an optional visual; the timeline is independent song data. The translator's **A+ timeline-import button** (Prompt 16 in `projects/live-lyric-translator-dev/docs/d-wire-triage-and-prompts.md`) consumes the output of this tool. Until this project ships, timelines are authored offline by Cowork (the "#6 DATA task" path in that same doc) — this project automates that path.

## Why it's a separate project (not in the translator repo)

Deriving a timeline from video is a real subsystem (video decode, subtitle-region change detection, OCR verification, a progress/QA loop) with its own dependencies and failure modes. Bundling it into the Electron app would bloat the app and mix concerns. Keeping it standalone lets it run as a CLI/batch tool now and, later, be wrapped into the app (or invoked by it) once it's proven. Decided 2026-06-24.

## How it should work (method — from the #6 DATA-task approach)

1. **Input:** a lyrics-only video + the song's ordered lyric lines (the fixed phrase list).
2. **Change detection:** with `ffmpeg`, sample frames and detect the timestamps where the burned-in subtitle **region changes** (the moments a new phrase appears). This yields an ordered list of change-point timestamps.
3. **Assignment:** because lyric order is fixed, assign the N lyric lines to the N change points in order (line *i* starts at change-point *i*).
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
4. Decide the human-QA loop: how mismatches surface and get corrected before writing the timeline.
5. Define done for v1: one song end-to-end (video in → verified timeline in the song JSON → plays in Auto mode on the translator).

## Model picks

General rule in `personal-context.md`. For this project: **Opus** for the initial pipeline/architecture framing (CV + assignment + QA design), then **Sonnet** for build-out and iteration.
