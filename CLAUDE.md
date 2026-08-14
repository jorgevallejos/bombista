# CLAUDE.md — bombista

This file provides guidance to Claude Code when working in this repository.

## What This Tool Does

`bombista` (renamed from `timeline-extractor` on 2026-08-14) is a Python CLI that
derives a lyric/subtitle timeline for a song by
**forced-aligning its audio** (faster-whisper word timestamps + fuzzy line-anchoring) against
the song's ordered lyric lines, and writes the result as a JSON file consumed by the
**Live Lyric Translator**'s timeline-import surface. The tool **only defines the timeline** —
it never edits lyric text.

The output contract is **frozen** in `docs/output-contract.md`. Do not change the
interchange format without coordinating with the translator side.

> **The audio-clock rule (critical):** timeline times are only meaningful relative to the
> audio you feed in. For **Video-mode** songs, extract the audio from the linked animation
> video (`ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav`); for **Auto-mode** songs
> (no video), use the master recording. Feeding the wrong take produces a timeline that
> matches nothing — this is exactly the bug the 2026-07 ASR spike caught in the shipped
> Tragedia timeline.

## Commands

```bash
pip install -e ".[dev]"     # Install in editable mode with dev deps
python -m pytest            # Run all tests (includes one tiny-whisper integration test)
bombista --help   # CLI entry point

# The workflow (align stages, promote applies):
bombista align <audio.wav> <song.json|lyrics.txt> -o <staging-dir> \
    [--model-size medium] [--lang es] [--anchor LINE=SECONDS] [--words <staging>/asr-words.jsonl] \
    [--emit timeline|songjson|report-json|srt|lrc|html]
bombista promote <staging>/<song>-timeline.json <song.json>

# One-off, for songs timed before timeline v2 (B13) — not part of the loop:
bombista migrate <song.json> [--dry-run]
```

The lyrics input may be a **CP song JSON or a plain text file** (one lyric line per line;
blank and `[Bracketed]` lines are stripped and reported). Either is normalised to a CP-shaped
song dict at the boundary before the pipeline runs — see `readers.py`.

`align` always writes `asr-words.jsonl` and `<song>-qa-report.md` into staging and **never
touches the song JSON**. `--emit` (repeatable, default `timeline`) picks which outputs join
them; passing it **replaces** the default set rather than adding to it. `--emit html` (B16)
writes `<song>-review.html` — the QA report as a self-contained offline page with a play
button per line that seeks the audio to that line's onset, so a REVIEW line can be judged by
ear instead of by scrubbing the m4a in another app. Review the QA report;
hand-fix REVIEW/FAIL lines by re-running with `--anchor <line>=<seconds>` (add `--words` to
skip re-transcription — it's near-instant). `promote` validates the candidate against the
timeline v2 contract, backs up the song JSON next to itself, and writes only
`timelineVersion`, `leadIn` and `timeline`.

`migrate` is the **one-off** for songs timed before v2 (B13): it rebases a *stored* v1
timeline in place, applying exactly what `align` applies to a fresh run. Both shipped
songs were migrated on 2026-08-14, so it should have nothing left to do — it refuses an
already-v2 song rather than subtracting the lead-in twice.

**Report times are raw audio-clock seconds; emitted timelines are cue-relative.** That is the
clock `--anchor LINE=SECONDS` is given in, and normalising the report would break the hand-fix
loop. SRT/LRC are absolute against their media, so they add the lead-in back when
`leadIn.apply` is true.

The faster-whisper `medium` model (~1.4 GB) is cached under `~/.cache/huggingface`; a full
song transcribes in ~50 s on this Mac (CPU int8).

## Architecture

```
bombista/
  models.py      — Word (ASR word + times), TimelineEntry (mirrors songState.ts)
  readers.py     — the boundary: CP song JSON or plain text → canonical CP song dict
                   + a _bombista block (completeness, filledLang, missing, strippedLines).
                   Structural only — stdlib, no network, no LLM. Bombista times; it
                   does not translate.
  aligner.py     — faster-whisper transcription → list[Word]; JSONL save/load
  anchoring.py   — pure, stdlib-only: fuzzy line-onset anchoring (forward-only) +
                   named-signal confidence bands (HIGH/REVIEW/FAIL); --anchor overrides,
                   including parse_anchor_overrides (LINE=SECONDS text -> the mapping
                   anchor_lines takes) — an anchoring concept, not a CLI one
  pipeline.py    — pure timeline building: anchors → TimelineEntry[] (end_i = next lyric
                   start, last line = last word end + 1.0 s pad, FAIL lines interpolated
                   so the candidate stays emittable) + normalize_to_lead_in
  provenance.py  — per-run audio identity (path, streamed sha256, duration, model, device,
                   lang, extractedAt, toolVersion) + linesHash over the canonical lines
  report.py      — markdown QA report (per-line band, ASR context, signals, fix hints)
  serializer.py  — the frozen timeline v2 envelope, and nothing else
  writers.py     — everything downstream of the canonical CP form: songjson, report-json,
                   srt, lrc, html — plus merge_envelope, THE one merge path (shared with
                   promote). The html writer (B16) is the offline review page: inline CSS/JS
                   only, audio by relative path, play buttons in RAW audio-clock seconds
  migrate.py     — B13: rebase a stored v1 timeline onto the v2 start cue. Adds no rules
                   of its own (it composes normalize_to_lead_in / to_dict / merge_envelope)
                   — what it owns is the refusal set. Idempotent by refusal, not no-op.
  songfile.py    — back_up_and_replace (THE one song-write path: backup, scratch file,
                   os.replace — never a half-stamped song on disk) + timeline_diff.
                   Shared by promote and migrate; returns its lines, prints nothing
  promotion.py   — promote_candidate: the whole promote flow as a callable — load the
                   candidate, extract + validate the v2 envelope, run B4's linesHash
                   guard, refuse a partial candidate over a complete target, merge,
                   write. Raises ValueError; `note` is a callback so a warning is
                   delivered before any refusal that follows it. B20 §2: `serve` must
                   promote what `promote` promotes, so there is one flow, not two
  cli.py         — click CLI: align / promote / migrate, and nothing else. Wiring only:
                   options, help text, and translating ValueError into ClickException /
                   BadParameter. `extract` is a registered alias of `align` (B11) — the
                   same Command object, so the two cannot drift
tests/           — 263 tests; all fast except one tiny-model integration test on a
                   committed 12 s fixture (tests/fixtures/)
docs/
  timeline-v2-contract.md           — THE live contract with the translator (Pregonero).
                                      Shared, amended by either side; do not diverge from it.
  output-contract.md                — v1 interface spec; superseded by timeline-v2-contract.md
  acceptance-tragedia-2026-07-03.md — v1 acceptance record (calibration + promote diff)
  bombista-product-backlog.md       — the v2 spec (§2 is the architecture and timing model)
  assignment-qa-design.md           — SUPERSEDED video-OCR design (banner explains what carried over)
```

The parked video-OCR track lives on origin branches `feat/lift-spike` and `feat/dp-alignment`
(unmerged, do not delete, do not merge).

## Development Protocol (TDD)

Strict **Red → Green → Refactor** for every change:

1. **Restate** the expected behavior in testable form.
2. **Write failing tests** (don't touch production code until tests fail for the right reason).
3. **Make the smallest implementation change** to turn tests green.
4. **Only then refactor** — must not change behavior.
5. **Commit only when tests are green.**

Prefer behavior tests over implementation-detail tests. Anchoring/pipeline logic is pure and
stdlib-only by design — test it with synthetic `Word` lists, never with the whisper model.

## Commit / PR Flow

- **Conventional Commits**: `<type>(<scope>): <subject>` — types: `feat`, `fix`, `refactor`,
  `docs`, `test`, `chore`.
- Feature branches only — never commit directly to `main`. **Always pass `--base main` to
  `gh pr create`** (a PR without it once merged into the wrong branch; the GitHub default
  branch is now `main`, but be explicit).
- Use `/release` to package and ship validated work.
- Each PR covers one logical change; merge and pull `main` before starting the next.

## Output Contract (summary — timeline v2)

- The emitted envelope has **exactly three top-level keys**:
  `{ "timelineVersion": 2, "leadIn": {…}, "timeline": [{start, end}] }`.
  Provenance, confidence bands and `_bombista` live in the rich JSON and the report —
  **never** in this envelope.
- `TimelineEntry = { start: float, end: float }` — half-open `[start, end)`, rounded to
  2 decimals. Entry *i* corresponds to `lyrics[i]`; **entry 0 always starts at `0.00`**.
- Times are **relative to a start cue**, not to the audio file. `raw[0].start` is banked in
  `leadIn: { durationSec, source, confidence, apply }`. Bombista always measures, always
  normalises, always records — **it is never told whether to apply the lead-in.** That is a
  playback decision: video start + lead-in for Video mode, the performer's pedal press for
  Auto mode.
- `leadIn.apply` defaults to `true` when the song has `media.type == "video"`, else `false`.
- Lyrics arrays carry **sung lines only** — no section markers, no meta entries. A non-lyric
  entry fails loudly, naming its index.
- Rounding matters: assert losslessness with a **tolerance** (`< 0.005`), not equality —
  `13.1 - 7.26 == 5.840000000000001` in IEEE floats.
- Alignment knobs (`offset`, `trimStart`) live on the song's `media` block — not here.
- **`docs/timeline-v2-contract.md` is the live contract** and carries the golden fixture both
  sides test against. `docs/output-contract.md` is the superseded v1 spec.

## Relationship to Live Lyric Translator

- Consumer: `projects/live-lyric-translator-dev/` — `TimelineEntry` type lives in
  `src/songState.ts`; cue lookup is `videoCueLookup` in `src/videoCueLookup.ts`.
- Song JSONs live in `~/Chango Pepper/songs/`; linked animation videos in
  `~/Chango Pepper/animations/<song-id>/`.
- Do not import or duplicate translator code here; `docs/output-contract.md` is the bridge.
