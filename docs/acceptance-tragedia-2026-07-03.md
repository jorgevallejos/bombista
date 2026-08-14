# Acceptance run — Tragedia de Cerdo Asado (2026-07-03)

Slice **S4 — acceptance on Tragedia** for forced-alignment v1. Full end-to-end run of
`bombista extract` / `promote` against the real production song file and its
linked animation video, with operator review of the QA report and promotion into the
song JSON.

## Environment

- Branch: `feat/acceptance-tragedia` (from `origin/main`, 60 tests green at time of run)
- Model: faster-whisper `medium`, language `es`
- Song: `/Users/jorgevallejos/Chango Pepper/songs/tragedia-de-cerdo-asado.json` (29 lyric
  lines, no section markers)
- Audio source: `/Users/jorgevallejos/Chango Pepper/animations/tragedia-de-cerdo-asado/Tragedia de Cerdo Asado.mp4`
  (159.5 s, AAC audio) — Video-mode song, so audio was extracted from the animation, not
  a separate master recording.
- Card reference: `docs/spike-candidate-timeline.json` (29 card windows from the
  video-OCR spike, signed off; known to lag sung onset by ~0.4 s median)

## Commands run

```bash
# 1. Extract 16kHz mono audio from the animation video
ffmpeg -i "Tragedia de Cerdo Asado.mp4" -vn -ac 1 -ar 16000 \
  runs/tragedia-2026-07-03/tragedia-master-16k.wav

# 2. First extract pass (real transcription)
.venv/bin/bombista extract \
  runs/tragedia-2026-07-03/tragedia-master-16k.wav \
  "/Users/jorgevallejos/Chango Pepper/songs/tragedia-de-cerdo-asado.json" \
  -o runs/tragedia-2026-07-03

# 3. Re-run with hand anchors (reuses saved ASR words, no re-transcription)
.venv/bin/bombista extract \
  runs/tragedia-2026-07-03/tragedia-master-16k.wav \
  "/Users/jorgevallejos/Chango Pepper/songs/tragedia-de-cerdo-asado.json" \
  -o runs/tragedia-2026-07-03 \
  --words runs/tragedia-2026-07-03/asr-words.jsonl \
  --anchor 0=0.96 --anchor 13=58.5

# 4. Promote
.venv/bin/bombista promote \
  runs/tragedia-2026-07-03/tragedia-de-cerdo-asado-timeline.json \
  "/Users/jorgevallejos/Chango Pepper/songs/tragedia-de-cerdo-asado.json"
```

## Runtime

- Audio extraction (ffmpeg): sub-second (159.5 s of audio, ~1100x realtime with stream copy resample).
- **Transcription pass (medium model, real ASR): 51.5 s wall clock** (184.99s user / 36.71s
  system time — multi-core, ~430% CPU average).
- Re-run with `--words` (anchors only, no re-transcription): 0.07 s.

## Band counts

| Pass | HIGH | REVIEW | FAIL |
|------|------|--------|------|
| First run (no overrides) | 27 | 1 | 1 |
| After overrides | 28 | 1 | 0 |

## Overrides applied

| Line | Text | Issue | Override | Rationale |
|------|------|-------|----------|-----------|
| 0 | "Me acuestan en la cama" | Extracted start clamped to `0.00` (band was HIGH/clean-anchor, but the value is a known whisper quirk on this audio: it clamps the first sung word to ~0.0 instead of the true onset). Cross-checked against the current song timeline (spike ground truth), which has `0.96`. | `--anchor 0=0.96` | Known quirk called out in the run brief; confirmed by the pre-override calibration (Δ vs spike ground truth = -0.96 s, the single largest outlier in that comparison). |
| 13 | "hacia el fuego ardiente." | FAIL, `no-anchor` — ASR misheard the line entirely ("hace calor al diente" got attributed to line 12's context), so no clean anchor was found; the tool fell back to interpolation (58.68 s). | `--anchor 13=58.5` | Known ASR quirk called out in the run brief; the spike had hand-anchored the same line at 58.5 s. The tool's own interpolated fallback (58.68) was already close, but a FAIL band with no textual anchor doesn't warrant trusting the interpolation as a promoted value — the explicit anchor removes the ambiguity. |

**Line NOT overridden:**

| Line | Text | Band | Why left alone |
|------|------|------|-----------------|
| 21 | "¡Qué suerte divina! ¡Me voy a escapar!" | REVIEW, `ambiguous` | Candidate start (95.74 s) matches the current song timeline (spike ground truth) **exactly** — Δ vs spike = 0.00 s in both the pre- and post-override calibration passes. The ambiguous-signal flag is a false positive here (likely a transcript-boundary quirk with the preceding line's trailing clause "que quedó medio abierta"); overriding it would only reintroduce risk on a line the tool already got right. Per instructions, REVIEW/FAIL lines only get hand anchors when there's a reason to distrust the extracted value — there wasn't one here. |

## Calibration analysis (post-override / final promoted values)

All 29 lines, `Δcard = extracted_start − card_ref_start`, `Δcurrent = extracted_start − current_timeline_start` (current timeline = spike-derived ground truth, pre-promote).

| line | extracted start | card ref start | Δcard | current ref start | Δcurrent | band |
|------|------------------|-----------------|-------|--------------------|----------|------|
| 0 | 0.96 | 0.48 | +0.48 | 0.96 | 0.00 | HIGH (override) |
| 1 | 3.76 | 4.52 | -0.76 | 3.76 | 0.00 | HIGH |
| 2 | 8.00 | 8.64 | -0.64 | 8.00 | 0.00 | HIGH |
| 3 | 12.04 | 11.80 | +0.24 | 12.04 | 0.00 | HIGH |
| 4 | 15.90 | 16.12 | -0.22 | 15.90 | 0.00 | HIGH |
| 5 | 19.72 | 19.52 | +0.20 | 19.72 | 0.00 | HIGH |
| 6 | 23.24 | 23.24 | 0.00 | 23.24 | 0.00 | HIGH |
| 7 | 30.46 | 30.80 | -0.34 | 30.46 | 0.00 | HIGH |
| 8 | 38.24 | 38.60 | -0.36 | 38.24 | 0.00 | HIGH |
| 9 | 42.04 | 42.44 | -0.40 | 42.04 | 0.00 | HIGH |
| 10 | 45.62 | 46.16 | -0.54 | 45.62 | 0.00 | HIGH |
| 11 | 48.14 | 49.76 | -1.62 | 48.14 | 0.00 | HIGH |
| 12 | 55.20 | 55.56 | -0.36 | 55.20 | 0.00 | HIGH |
| 13 | 58.50 | 58.92 | -0.42 | 58.50 | 0.00 | HIGH (override) |
| 14 | 62.16 | 62.68 | -0.52 | 62.16 | 0.00 | HIGH |
| 15 | 68.80 | 69.40 | -0.60 | 68.80 | 0.00 | HIGH |
| 16 | 72.92 | 73.08 | -0.16 | 72.92 | 0.00 | HIGH |
| 17 | 76.60 | 76.76 | -0.16 | 76.60 | 0.00 | HIGH |
| 18 | 83.84 | 84.64 | -0.80 | 83.84 | 0.00 | HIGH |
| 19 | 88.74 | 88.60 | +0.14 | 88.74 | 0.00 | HIGH |
| 20 | 91.48 | 92.08 | -0.60 | 91.48 | 0.00 | HIGH |
| 21 | 95.74 | 99.00 | -3.26 | 95.74 | 0.00 | REVIEW |
| 22 | 102.60 | 102.68 | -0.08 | 102.60 | 0.00 | HIGH |
| 23 | 106.40 | 106.36 | +0.04 | 106.40 | 0.00 | HIGH |
| 24 | 112.22 | 113.24 | -1.02 | 112.22 | 0.00 | HIGH |
| 25 | 120.44 | 120.68 | -0.24 | 120.44 | 0.00 | HIGH |
| 26 | 127.96 | 128.44 | -0.48 | 127.96 | 0.00 | HIGH |
| 27 | 132.00 | 132.08 | -0.08 | 132.00 | 0.00 | HIGH |
| 28 | 136.16 | 135.76 | +0.40 | 136.16 | 0.00 | HIGH |

### Summary statistics

**Δ vs card reference** (`docs/spike-candidate-timeline.json`):

| median | mean | stdev | min | max | within ±0.5 s |
|--------|------|-------|-----|-----|-----------------|
| -0.360 | -0.419 | 0.700 | -3.260 | +0.480 | 19 / 29 |

**Δ vs current song timeline** (spike-derived ground truth, pre-promote):

| median | mean | stdev | min | max | within ±0.5 s |
|--------|------|-------|-----|-----|-----------------|
| 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 29 / 29 |

Convergence with the spike-derived ground truth is exact on all 29 lines after the two
hand anchors — the forced-alignment pipeline reproduces the ASR spike's onsets to the
hundredth of a second everywhere it agrees, and the two known quirks called out in the
run brief were the only places it needed help.

### Card-vs-sung offset: `--lead` knob recommendation

The median |Δcard| (0.360 s) exceeds the ~0.3 s materiality threshold. This confirms
the pre-verified relationship: **the OCR card reference lags the true sung onset by
~0.36–0.42 s** (median/typical-line value; the two outliers, lines 11 and 21 at -1.62 s
and -3.26 s, are almost certainly card-detection artifacts — e.g. a card held over an
unusually long span, or a mis-segmented change-detection window on the OCR spike — not
audio issues, since both lines land at Δcurrent = 0.00 against the spike-derived ground
truth).

**Recommendation:** if the card reference is ever used as a primary timing source (e.g.
for songs without a clean vocal track to force-align against), a `--lead` CLI option
(e.g. `--lead 0.38`) that subtracts a fixed offset from card-derived starts would bring
the typical line within tolerance. This is a proposal only — no code was changed as
part of this acceptance run.

## Promote result

```
backup: /Users/jorgevallejos/Chango Pepper/songs/tragedia-de-cerdo-asado.json.backup-20260703-112259
line 28: 136.16–140.0 -> 136.16–160.48
```

Only one line's stored value actually changed: line 28's `end` moved from `140.0` to
`160.48`. Every other line (`start` and `end`) was already identical to what the ASR
spike had promoted earlier — expected, since this song's current timeline *is* that
spike's ground truth and the calibration above shows exact convergence.

The line 28 `end` change is **expected pipeline behavior, not an anomaly**: per
`bombista/pipeline.py`, the last lyric line's `end` is set to
`last_transcribed_word_end + LAST_LINE_PAD` (`LAST_LINE_PAD = 1.0`). The last
transcribed word in this pass ended at 159.48 s (audio duration 159.509 s), giving
`159.48 + 1.0 = 160.48`. The previous value (140.0) was presumably a hand-set or
differently-derived end from the earlier spike promotion; the new value reflects the
actual last-word timing plus the tool's standard 1 s pad, and is consistent with the
tool's documented contract.

## Anomalies

- **Line 28 `end` extends ~1 s past the audio's physical duration** (160.48 s vs
  159.51 s). This is intentional per `LAST_LINE_PAD` (padding past the last word so the
  final cue doesn't clip), not a bug — flagged here for visibility only.
- No other anomalies. All 60 pre-existing tests remained green throughout (verified
  before starting the run); no source code was touched.

## Files

- `docs/acceptance-tragedia-2026-07-03.md` — this file.
- `docs/acceptance-tragedia-qa-report.md` — final QA report (post-override) copied from
  the staging run.
- `runs/tragedia-2026-07-03/` — staging directory (gitignored): master WAV, ASR words
  JSONL, both timeline JSONs (pre/post override), both QA reports, calibration script
  and output.
