# CLAUDE.md — timeline-extractor

This file provides guidance to Claude Code when working in this repository.

## What This Tool Does

`timeline-extractor` is a Python CLI that derives a lyric/subtitle timeline for a song by
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
timeline-extractor --help   # CLI entry point

# The workflow (extract stages, promote applies):
timeline-extractor extract <audio.wav> <song.json> -o <staging-dir> \
    [--model-size medium] [--lang es] [--anchor LINE=SECONDS] [--words <staging>/asr-words.jsonl]
timeline-extractor promote <staging>/<song>-timeline.json <song.json>
```

`extract` writes `asr-words.jsonl`, `<song>-timeline.json`, and `<song>-qa-report.md` into
staging and **never touches the song JSON**. Review the QA report; hand-fix REVIEW/FAIL lines
by re-running with `--anchor <line>=<seconds>` (add `--words` to skip re-transcription — it's
near-instant). `promote` validates the candidate against the contract, backs up the song JSON
next to itself, and replaces **only** its `timeline` field.

The faster-whisper `medium` model (~1.4 GB) is cached under `~/.cache/huggingface`; a full
song transcribes in ~50 s on this Mac (CPU int8).

## Architecture

```
timeline_extractor/
  models.py      — Word (ASR word + times), TimelineEntry (mirrors songState.ts)
  aligner.py     — faster-whisper transcription → list[Word]; JSONL save/load
  anchoring.py   — pure, stdlib-only: fuzzy line-onset anchoring (forward-only) +
                   named-signal confidence bands (HIGH/REVIEW/FAIL); --anchor overrides
  pipeline.py    — pure timeline building: anchors → TimelineEntry[] (markers {0,0},
                   end_i = next lyric start, last line = last word end + 1.0 s pad,
                   FAIL lines interpolated so the candidate stays emittable)
  report.py      — markdown QA report (per-line band, ASR context, signals, fix hints)
  serializer.py  — validate + serialize to interchange JSON
  cli.py         — click CLI: extract / promote
tests/           — 60 tests; all fast except one tiny-model integration test on a
                   committed 12 s fixture (tests/fixtures/)
docs/
  output-contract.md                — frozen interface spec; do not modify unilaterally
  acceptance-tragedia-2026-07-03.md — v1 acceptance record (calibration + promote diff)
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

## Output Contract (summary)

- `TimelineEntry = { start: float, end: float }` — half-open `[start, end)` window.
- Timeline is **parallel to song items** (including section markers); length must match.
- Section-marker entries use `start == end == 0` (zero-length, never matched). This repo's
  validator exempts them from the monotonic chain; **the translator's `validateTimeline`
  does not** — a known contract wrinkle to resolve translator-side before any song with
  mid-song markers gets a timeline.
- Alignment knobs (`offset`, `trimStart`) live on the song's `media` block — not here.
- See `docs/output-contract.md` for the full spec and interchange format.

## Relationship to Live Lyric Translator

- Consumer: `projects/live-lyric-translator-dev/` — `TimelineEntry` type lives in
  `src/songState.ts`; cue lookup is `videoCueLookup` in `src/videoCueLookup.ts`.
- Song JSONs live in `~/Chango Pepper/songs/`; linked animation videos in
  `~/Chango Pepper/animations/<song-id>/`.
- Do not import or duplicate translator code here; `docs/output-contract.md` is the bridge.
