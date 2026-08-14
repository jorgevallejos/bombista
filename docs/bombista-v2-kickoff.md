# Claude Code kickoff — Bombista v2 (timeline-extractor)

**Created:** 2026-08-13 · **Spec:** `docs/bombista-product-backlog.md`
**Paste everything below the line into a fresh Claude Code session opened at the vault root.**

---

You are the **coordinator** for this piece of work. Do not hand-execute the whole thing yourself: read and decide, then delegate each work item to a Sonnet subagent, review what comes back, and keep the test suite green. Escalate to me (Jorge) only at the gates marked below.

## Context — read before doing anything

1. `projects/timeline-extractor/docs/timeline-v2-contract.md` — **the shared contract with Pregonero, which is being built in a parallel session right now.** Read this first. It fixes the envelope, the rounding rule, and a golden fixture you must produce exactly. Do not invent your own shape; if something there is wrong or insufficient, stop and raise it with Jorge rather than diverging.
2. `projects/timeline-extractor/docs/bombista-product-backlog.md` — **the spec.** §2 (architecture and timing model) is the part that matters most; §4 is the item list.
3. `projects/timeline-extractor/CLAUDE.md` and `project-context.md` — house rules and current state.
4. `CLAUDE.md` at the vault root — standing rules.

Primary repo: `projects/timeline-extractor` (its own repo, a submodule of the vault).
**One item (B13) writes to the `songs` submodule** — a different repo. Treat that boundary carefully.

## Non-negotiable constraints

1. **Normalise at the boundary.** Plain-text input is converted into a CP-shaped song dict *before* the existing pipeline runs. The core alignment code in `pipeline.py` / `anchoring.py` / `aligner.py` is not restructured. This is an anti-corruption layer, not a rewrite.
2. **No network, no API keys, no LLM calls anywhere in the tool.** Running fully offline is a product property, not an implementation detail. Structural conversion only — Bombista times, it does not translate.
3. **Bombista is never told whether to apply the lead-in.** It always measures, always normalises, always records. Applying it is a playback decision made downstream.
4. **Tests green before every commit.** One commit per work item, with the item ID in the message.
5. **B13 is last and is gated** — see the gate note on it.
6. **Test against the golden fixture in the contract, not against the real song files.** `songs/*.json` are still v1 on disk and stay that way until the migration runs.
7. **Do not bump the vault-root submodule pointer.** Pregonero is being built in parallel; two sessions committing at the umbrella repo will collide. Commit and push inside `projects/timeline-extractor` only — Jorge bumps the umbrella once, at the end.

## Work items, in this order

### B3 — remove section-marker support
Lyrics arrays carry sung lines only.
- Delete the zero-length `{0,0}` exemption from `serializer.py::validate_timeline` and the tests that exercise it.
- `pipeline.py::lyric_lines()` must no longer silently treat non-language-keyed entries as markers. For **CP JSON input**, raise a clear error naming the offending index. (For plain-text input the rule differs — see B5.)
- *Acceptance:* a CP song file containing a non-lyric entry fails loudly with a message that names the index.

### B12 — normalise to line 0 = 0, bank the offset in `leadIn`
- Subtract `raw[0].start` from every emitted entry so line 0 starts at `0.000`.
- Record `leadIn: { durationSec, source: "measured", confidence: "low", apply: <bool> }`, where `apply` defaults to `true` if the song has `media.type == "video"`, else `false`.
- Stamp `timelineVersion: 2`.
- The **native timeline envelope** becomes `{ "timelineVersion": 2, "leadIn": {…}, "timeline": […] }`. These three keys are the contract Pregonero parses — nothing else goes in this envelope.
- *Acceptance:* a losslessness test — re-adding `leadIn.durationSec` to every normalised entry reproduces the raw measured values exactly.

### B1 — provenance
- Emit `{ audio path, sha256, durationSec, model, device, lang, extractedAt, toolVersion }`. `toolVersion` comes from `pyproject.toml`.
- Goes in: the rich JSON, the report header, and the `_bombista` block of an emitted song JSON.
- **Does not go in** the native timeline envelope (see B12 — that contract stays minimal).
- *Acceptance:* two runs against different audio files for the same song produce different `sha256` values, and the report header shows which audio was used.

### B5 — input normaliser (`readers.py`)
- Detect the input: valid JSON carrying a `lyrics` array → CP path, unchanged. Anything else → plain-text path.
- Plain text: one line per lyric line. Blank lines and `[Bracketed]` lines are **stripped and reported** — not converted to markers. Each surviving line is wrapped as `{"<lang>": text}` using `--lang` (default `es`). `title` comes from the filename stem.
- Emit a `_bombista` block: `completeness` (`partial` | `complete`), `filledLang`, `missing`, `strippedLines`.
- *Acceptance:* a plain `.txt` of Libertad's 20 Spanish lines produces a partial CP song dict whose `lyrics` match `songs/libertad.json`'s `es` values exactly, in order.

### B2 — `--emit` writers
- Repeatable click option: `timeline` (default), `songjson`, `report-json`, `srt`, `lrc`.
- All writers read the canonical CP form. Extract `promote`'s merge into a shared function used by both `promote` and the `songjson` writer — one merge code path only.
- `--emit srt|lrc` writes one file per language key present in the input. SRT timings must have the lead-in applied when `leadIn.apply` is true, since subtitle files are absolute by nature — note this divergence in a comment.
- `promote` refuses to overwrite a `completeness: complete` song file with a partial one.
- *Acceptance:* `--emit songjson` on `songs/libertad.json` round-trips every non-timeline field byte-identically.

### B4 — lines-hash guard
- `linesHash` = sha256 over the ordered canonical line texts. Stored in the rich JSON and the `_bombista` block.
- `promote` recomputes it from the target song and prints a **loud warning, not an error**, on mismatch.
- *Acceptance:* editing one lyric line in the target song then promoting an older timeline produces the warning.

### B13 — migrate the two existing timelines ⚠ GATED
Writes to the **`songs`** submodule, not this repo.
- One-shot script: for `songs/libertad.json` and `songs/tragedia-de-cerdo-asado.json`, subtract `raw[0].start` from every entry, write `leadIn` and `timelineVersion: 2`. Back up first.
- *Acceptance:* libertad line 0 becomes `{ "start": 0.00, "end": 5.84 }` with `leadIn.durationSec == 7.26`.

> **⚠ Gate — do not run B13 until Pregonero item P3 is merged.** P3 is what makes the app reject a version it doesn't understand. Migrating the data first means a v1-aware app reads v2 files and fires every line seconds early with no error. Stop and check with me.

## Out of scope
Pregonero items P1–P4 (`projects/live-lyric-translator`) — separate kickoff, separate session.
B6, B7, B8, B9, B10, B11 from the backlog — later.

## Gates for me
1. After B12 + B1: show me one full `extract` run on Libertad — the console summary, the report header, and the normalised envelope.
2. After B5: show me the plain-text round-trip result.
3. Before B13: confirm P3 has landed.

## Finishing
Commit inside `projects/timeline-extractor` and push. **Stop there** — do not touch the vault root or the `songs` submodule. Jorge bumps the umbrella pointer himself once both parallel streams are merged.
