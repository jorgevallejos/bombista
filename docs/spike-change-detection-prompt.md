# Claude Code prompt — change-detection spike (agenda item #3)

Paste the block below into **Claude Code in the `bombista` repo** (not the translator).
It includes a repo guard as the first step. Model: **Sonnet** (build/iterate spike).

---

You are working in the `bombista` repo.

**STEP 0 — guard, do this before anything else:**
Run `pwd && git remote -v && git status -sb`. Confirm the remote is
`jorgevallejos/bombista` — if it is `live-lyric-translator-dev` or anything
else, STOP and tell me, do not proceed. Also confirm `serializer.py`'s `to_dict` is
implemented (not raising `NotImplementedError`); if it still raises, the
`feat/green-serializer` PR isn't merged — STOP and tell me before continuing.

**Goal (throwaway measurement spike):** prototype ffmpeg change-detection on the
Tragedia "lyrics-only" video and measure timestamp accuracy. Work on a
`spike/change-detection` branch in a `spike/` or `scripts/` directory. This is
exploratory — do NOT wire it into the `click` CLI or the production package.

**Inputs (absolute paths):**
- Video: `/Users/jorgevallejos/Chango Pepper/animations/tragedia-de-cerdo-asado/Master Sequence only subtitles.mp4`
- Lyrics + scaffold: `/Users/jorgevallejos/Chango Pepper/songs/tragedia-de-cerdo-asado.json`
  (29 lines. `.en` is the language burned into THIS video; `.es` is the canonical
  lyric. The `timeline` field is an EVEN-SPACED SCAFFOLD — not ground truth, ignore
  it for accuracy.)

**Already probed — build on these, don't rediscover:**
- 1620×1080, 25 fps, 160.32 s. White text on PURE BLACK, in the bottom band.
  `crop=1620:320:0:760` isolates the subtitle region.
- ffmpeg's whole-frame `scene` filter finds nothing (text is too few pixels). The
  working primitive is REGION brightness: crop the band → `signalstats` YAVG per
  frame. Blank baseline YAVG ≈ 16; text plateaus ≈ 18–19.5. Rising edge
  (blank→text) = cue start, falling edge = cue end.
- A brightness-edge pass finds **33 cue starts**, but the song has **29 lyric lines**.
  Two distinct causes, both of which the spike must handle:
  1. **Brightness misses text→text changes with no dark gap** — consecutive cards get
     merged into one window. Example: ~23–30 s shows `"You will be exquisite," he sighs,`
     then `while I dream of my muddy childhood pond.` back-to-back with no blank
     between → detected as a single window. Add a content-signature diff WITHIN
     text frames (scene/SSIM/perceptual-hash on the contrast-boosted crop) to split
     these.
  2. **Cards ≠ lyric lines 1:1** — song `lyrics` entries 6, 14, 20, 24, 25 contain an
     embedded `\n` and display as TWO cards each. So blind ordinal assignment is
     wrong; reconcile via OCR.

**Tasks:**
1. Region brightness-edge detection (crop band → YAVG per frame → threshold →
   rising/falling edges) → list of `(start, end)` cue windows.
2. Intra-text splitting to catch no-gap card changes (signature diff on the cropped,
   thresholded band).
3. OCR each window (tesseract, `negate,format=gray`, `--psm 6` or `7`) → text per
   card. OCR is near-perfect on this source.
4. Reconcile detected cards → 29 lyric lines by fuzzy-matching OCR text to `.en`
   (handle the embedded-newline two-card lines). Report unmatched/ambiguous.
5. Emit a candidate timeline in the FROZEN output contract (`docs/output-contract.md`:
   `{ "timeline": [{start, end}, ...] }`, half-open `[start, end)`, one entry per
   lyric line, monotonic).
6. QA output (no hand-checked reference exists yet): a table —
   `lyric line | detected start | detected end | OCR text | match status` — plus
   summary stats (matched 1:1, merges split, unmatched). Jorge hand-verifies a sample
   + the splits against the video; that reconciled file becomes the reference.

**Stop after reporting** — don't commit to `main`, don't touch the CLI. Report: did
every lyric line get exactly one monotonic window? Where was the intra-text split
needed? Any OCR/match failures?

---
