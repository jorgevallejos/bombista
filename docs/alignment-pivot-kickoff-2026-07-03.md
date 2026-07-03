# Dispatch — Timeline Extractor v1 via Forced Alignment (pivot) + Translator Housekeeping

_2026-07-03. Two paste blocks for Claude Code (Fable/Opus coordinator + Sonnet crew). **Block A** goes in the **timeline-extractor** repo window; **Block B** goes in the **live-lyric-translator** repo window. Check the repo path Claude Code echoes before pasting (lesson from the 2026-06-24 wrong-repo incident)._

**Decision context:** the translator's ASR spike (2026-07-03, branch `spike/asr-following` there, report `docs/asr-spike-report-2026-07.md`) closed live-ASR following as NO-GO but proved **offline forced alignment** (faster-whisper `medium`, near-verbatim word timings, 46 s/song) is the right way to *author* timelines. This pivots the extractor's core from video change-detection + OCR to audio alignment, and finishes the project. Scope agreed with Jorge: **the tool only defines the timeline** — it never edits lyric text.

---

## Block A — paste into Claude Code at the **timeline-extractor** repo

You are the **coordinator** (PM role) for finishing this project. You frame, dispatch Sonnet subagents (worktree isolation) for build slices, integrate, and bring Jorge results + things to test. Follow the repo's `/release` flow (feature branches, TDD, PRs via `gh`); auto-merge on green is authorized as in the translator's recent batches, **end to end — including the final promote**. Jorge tests the finished result in the app afterwards.

### Step 0 — guards + housekeeping, before any building

1. `pwd && git remote -v && git status -sb` — confirm remote is `jorgevallejos/timeline-extractor`. If not, STOP.
2. Housekeeping: `main` is 1 commit ahead of origin (unpushed) and the design docs (`docs/assignment-qa-design.md`, `docs/build-plan-prompt.md`, `docs/opus-design-prompt.md`, `docs/spike-candidate-timeline.json`, `docs/spike-change-detection-prompt.md`, this file) are untracked. Commit the docs to `main`, push. Leave `feat/lift-spike` and `feat/dp-alignment` **parked as-is** (pushed, unmerged — the superseded video-OCR track; do not delete, do not merge). Checkout a clean, pushed `main` before building.
3. Read before framing: `docs/output-contract.md` (frozen output shape), `docs/assignment-qa-design.md` §4–§5 (confidence bands + `extract`→`promote` — the concepts carry over), and in the translator repo (`../live-lyric-translator-dev`, branch `spike/asr-following`): `spike/harness/derive_ground_truth.py` + `docs/asr-spike-report-2026-07.md` — the proven reference implementation to port, plus its known failure mode (a misheard anchor: "hacia el fuego ardiente" → REVIEW case).

### The design (settled — implement, don't redesign)

- **Pipeline:** audio file + song JSON → faster-whisper `medium` (batch, word timestamps, Spanish) → anchor each lyric line by fuzzy-matching its opening tokens (normalized), forward-only, exactly the spike's approach → `{ "timeline": [...] }` per `docs/output-contract.md`. One entry per song item in order; section markers as `start == end == 0`; embedded `\n` lines are still **one** timeline entry (no more card-splitting — that was a video-pipeline concern).
- **Inputs:** `extract <audio> <song-json> -o <staging-dir>`. The operator picks the audio to match the clock the timeline will run against: **extract audio from the linked animation video** (ffmpeg) for Video-mode songs; **the master recording** for songs without video (Auto mode). Document this rule prominently — timeline times are only meaningful relative to the audio fed in (the bug this spike caught: Tragedia's shipped timeline matches neither its video nor its master).
- **End times:** default `end_i = start_{i+1}` (display-card continuity, matching the signed-off reference's semantics); last line = its last word's end + 1.0 s pad. Half-open `[start, end)` per the contract.
- **QA report (markdown, per line):** canonical text vs ASR text at the anchor, match score, confidence band HIGH/REVIEW/FAIL (named signals, per the design doc's model — adapted from OCR to ASR signals). REVIEW lines get a one-line instruction for hand-anchoring (a `--anchor <line>=<seconds>` override flag). No thumbnails — there's no video in the loop.
- **`promote`** writes the timeline into the song JSON's `timeline` field (backup + diff shown), touching **nothing else**. `extract` never writes to the song JSON.

### Slices (dispatch to Sonnet; S1 ∥ S2, then S3, then S4)

- **S1 — aligner core:** port the spike's transcription + word-timestamp machinery into `timeline_extractor/aligner.py`; venv/model handling; tested against a short fixture.
- **S2 — anchoring + confidence:** pure functions, unit-tested (clean match, misheard anchor, repeated-chorus ambiguity, skipped line, `--anchor` override).
- **S3 — CLI + serializer + QA report:** wire `extract`/`promote` through the existing `serializer.py` and `models.py`; report generation.
- **S4 — acceptance on Tragedia** (see below).

### Acceptance (v1 DoD, revised for the pivot)

1. **Calibration run:** extract audio from `animations/tragedia-de-cerdo-asado/Master Sequence only subtitles.mp4` (the file `docs/spike-candidate-timeline.json` was derived from) and run `extract`. Report the per-line Δstart distribution vs that signed-off reference. Expect a small systematic offset (cards may appear slightly before/after the sung onset — the reference encodes card times, alignment yields sung times); report median and spread rather than forcing the old ±0.20 s rule. If the systematic card-vs-sung offset is material (> ~0.3 s), report it and propose a `--lead` knob — **don't** add it unilaterally.
2. **Production run:** extract audio from the song's **linked animation video** in the translator repo, generate the real replacement timeline for `tragedia-de-cerdo-asado.json`, and **promote it directly** (backup + diff included in the end report — no approval gate; Jorge decided 2026-07-03 that promote is auto-applied, no harm possible since the shipped timeline is already broken and the backup allows revert).
3. Merge everything on green, then hand Jorge a short test script: what to open, which modes to try (Auto and Video), what correct looks like. Jorge tests; that closes v1.

### End of run

Report: results per slice, calibration numbers, the QA report, and proposed memory edits (`CLAUDE.md` here, `project-context.md` here — mark the video-OCR track superseded in `docs/assignment-qa-design.md` with a banner note rather than rewriting it). The tool must be re-runnable as-is on this week's new recordings (new audio + same song JSONs).

---

## Block B — paste into Claude Code at the **live-lyric-translator** repo

Housekeeping only — no feature work. Guard first: `pwd && git remote -v` must show `jorgevallejos/live-lyric-translator`. If not, STOP.

1. Push the spike branch for preservation: `git push -u origin spike/asr-following`. No PR, no merge — the report and reusable scripts live there.
2. On a small docs branch off `main`: commit `docs/asr-following-spike-kickoff-2026-07-03.md` (currently untracked), and add this note to `CLAUDE.md`'s song-data section: *"`timeline` values are only meaningful relative to the linked video's own clock — generate/validate them against that video's audio (`media.offset` compensates). The 2026-07 ASR spike found the shipped Tragedia timeline ~17 s off. Forced alignment on the video's audio (timeline-extractor) is the sanctioned way to author timelines."* PR via `/release`, merge on green.
3. Delete the stray empty branch: `git branch -d feat/timeline-import-button` (verify it's still == `main` first).
4. Do **not** commit the untracked `spike/` directory sitting on the `main` working tree (venv + WAVs — it belongs to the spike branch); confirm `.gitignore` keeps it out or leave it untracked.
5. Report: confirm whether the A+ timeline-import button (Prompt 16) exists on `main`. If it doesn't, say so and stop — building it is a separate decision for Jorge (manual `promote` into the song JSON covers v1).
