# Claude Code prompt — E2E extractor test on Libertad (2026-08-11)

**Paste to Claude Code at the vault root (`~/Chango Pepper`).** First real end-to-end
run of the `bombista` → app pipeline on one Auto-mode song, Libertad.
Jorge tests the result in the app afterward.

## Role & objective

You are the **coordinator**. Take Libertad's master recording, run the forced-alignment
extractor to produce a candidate timeline, gate the QA with Jorge, promote the approved
timeline into `songs/libertad.json`, and commit. The goal is to validate the whole
pipeline on one song before doing the other ten.

## Model & delegation policy

This is a **sequential pipeline**, not parallelizable work — the coordinator runs it
directly. The one heavy step (`extract`, faster-whisper `medium`) is CPU-bound on a
single file; spreading it across workers buys nothing. Delegate to a low-cost worker
(Sonnet) only the **read-only QA-report summary** for Jorge if you want. `extract`,
`promote`, and all git steps stay on the coordinator. Never let a cheap model run
`promote` or the commits.

## Ground facts (verify, don't trust blindly)

- `songs/` is now a **private submodule**; edits to `songs/libertad.json` commit **inside**
  it, then the umbrella pointer is bumped.
- Audio: `songs/audio/libertad.m4a` (~105 s). Gitignored inside the submodule — never commit it.
- `songs/libertad.json`: **20 lyric lines**, all real lines (no section markers), `lang` key `es`.
  It already has a `tempo` block (`bpm 200, 3/4, countInBars 1`) — see the tempo note below.
- Extractor package: `projects/bombista/` (CLI `bombista`, commands
  `extract` and `promote`). Reuse its existing `.venv` if present; else create one and
  `pip install -e projects/bombista`. Confirm `ffmpeg` is available for m4a decode.

## Steps

**1. Environment.** Activate/create the extractor venv, install the package, confirm
`bombista --help` works and `ffmpeg -version` succeeds.

**2. Extract** (writes to a staging dir; never touches the song JSON):
```
bombista extract songs/audio/libertad.m4a songs/libertad.json \
  -o projects/bombista/staging/libertad --lang es --model-size medium
```
This writes `libertad-timeline.json`, `libertad-qa-report.md`, and `asr-words.jsonl`,
and prints a `HIGH / REVIEW / FAIL` line-band summary.

**⛔ CHECKPOINT 1 — QA gate.** Show Jorge the band counts + the QA report (a Sonnet
worker may summarize it). For any REVIEW/FAIL line, hand-correct by re-running with an
anchor — reuse the saved words to skip re-transcription (fast):
```
bombista extract songs/audio/libertad.m4a songs/libertad.json \
  -o projects/bombista/staging/libertad --lang es \
  --words projects/bombista/staging/libertad/asr-words.jsonl \
  --anchor 0=SECONDS --anchor 7=SECONDS
```
Expected: 20 timeline entries (must equal the lyric-item count or `promote` refuses).
If the recording opens with an instrumental intro, line 0's onset sitting a few seconds
in is **correct**, not an error. Wait for Jorge's go before promoting.

**3. Promote** the approved timeline into the song JSON (auto-backs-up, replaces only the
`timeline` key):
```
bombista promote projects/bombista/staging/libertad/libertad-timeline.json \
  songs/libertad.json
```

**4. Tempo-block note (flag, don't fix silently).** The timeline is independent of BPM.
But the recording reads **~99 BPM**, while the block says **200** — likely the same
tempo felt in half, or a genuinely slower take. The block only drives the **count-in /
beat indicator**, so tell Jorge and let him decide whether to change `bpm` to ~100 for
Libertad. Do not change it without his call. If he says yes, set `tempo.bpm` and note it.

**⛔ CHECKPOINT 2 — show the diff** (`songs/libertad.json`: `timeline` added, ± tempo)
before committing.

**5. Commit** inside the submodule, then bump the umbrella pointer:
```
git -C songs add libertad.json
git -C songs commit -m "Libertad: add extractor-derived timeline (E2E test)"
git -C songs push
git add songs && git commit -m "Bump songs: Libertad timeline" && git push
```
Handle the `libertad.json.backup-*` file `promote` creates: either delete it or add
`*.backup-*` to the submodule `.gitignore` — don't commit it.

## Report back
Band counts (HIGH/REVIEW/FAIL), any anchors used, the final 20-entry timeline range
(first onset, last end vs the 105 s length), and confirmation of the commits.

## Then — Jorge tests (not you)
Load Libertad in the app in **Auto mode**. Auto runs the app's own clock (count-in →
timeline in seconds), it does **not** play the recording. To check alignment, play
`songs/audio/libertad.m4a` alongside and confirm each line flips as that line is sung. Note
that a live performance must track the recording's timing for the lines to land — tempo
drift is the known limitation (Manual + pedal stays the fallback).
