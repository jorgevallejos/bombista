# CLAUDE.md — timeline-extractor

This file provides guidance to Claude Code when working in this repository.

## What This Tool Does

`timeline-extractor` is a Python CLI that derives a lyric/subtitle timeline from a
"lyrics-only" video (ffmpeg change-detection + OCR verification) and writes the result
as a JSON file consumed by the **Live Lyric Translator**'s A+ timeline-import button.

The output contract is **frozen** in `docs/output-contract.md`. Do not change the
interchange format without coordinating with the translator side.

## Commands

```bash
pip install -e ".[dev]"     # Install in editable mode with dev deps
python -m pytest            # Run all tests
python -m pytest -x         # Stop on first failure
timeline-extractor --help   # CLI entry point
```

## Architecture

```
timeline_extractor/
  models.py      — TimelineEntry dataclass (mirrors songState.ts)
  serializer.py  — validate + serialize to interchange JSON
  cli.py         — click CLI: `timeline-extractor extract <video> <lyrics> -o <out>`
tests/
  test_serializer.py — round-trip tests (one intentional RED until serializer implemented)
docs/
  output-contract.md — frozen interface spec; do not modify unilaterally
```

## Development Protocol (TDD)

Strict **Red → Green → Refactor** for every change:

1. **Restate** the expected behavior in testable form.
2. **Write failing tests** (don't touch production code until tests fail for the right reason).
3. **Make the smallest implementation change** to turn tests green.
4. **Only then refactor** — must not change behavior.
5. **Commit only when tests are green** (the scaffold's intentional red test is the exception).

Prefer behavior tests over implementation-detail tests. Extract pure functions when logic
is too coupled to test. Do not mix feature work, bug fixing, and refactoring in the same step.

## Commit / PR Flow

- **Conventional Commits**: `<type>(<scope>): <subject>` — types: `feat`, `fix`, `refactor`,
  `docs`, `test`, `chore`.
- Feature branches only — never commit directly to `main`.
- Use `/release` to package and ship validated work.
- Each PR covers one logical change; merge and pull `main` before starting the next.

## Output Contract (summary)

- `TimelineEntry = { start: float, end: float }` — half-open `[start, end)` window.
- Timeline is **parallel to song items** (including section markers); length must match.
- Section-marker entries use `start == end == 0` (zero-length, never matched).
- Alignment knobs (`offset`, `trimStart`) live on the song's `media` block — not here.
- See `docs/output-contract.md` for the full spec and interchange format.

## Relationship to Live Lyric Translator

- Consumer: `projects/live-lyric-translator-dev/` — `TimelineEntry` type lives in
  `src/songState.ts`; cue lookup is `videoCueLookup` in `src/videoCueLookup.ts`.
- Import surface: A+ button (Prompt 16 in `docs/d-wire-triage-and-prompts.md`).
- Do not import or duplicate translator code here; `docs/output-contract.md` is the bridge.
