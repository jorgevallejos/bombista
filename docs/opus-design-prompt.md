# Opus design-pass prompt — assignment + QA architecture

Paste into a **fresh Cowork chat set to Opus**. This is a design/spec session (no
production code) — it ends by producing a spec doc to hand to Sonnet in Claude Code.

---

Working on the **bombista** project. Load context per the Chango Pepper
bootstrap (personal-context → current-priorities → projects/bombista/
project-context.md), and also read `projects/bombista/docs/output-contract.md`.
Acknowledge, then engage.

This is the **Opus design pass** (kickoff agenda #4 + #5). The change-detection spike
is done and verified — don't redo it. Your job is to **design the production
architecture for two things**, then write a spec, not code:

1. **Assignment** — reconciling detected display cards → canonical lyric lines.
2. **Human-QA loop** — how mismatches surface and get corrected before a timeline is
   written.

**What the spike proved (use as ground truth, don't relitigate):**
- Working detection primitive on a clean lyrics-only video: crop the subtitle band →
  `signalstats` YAVG per frame → threshold against the blank baseline → rising/falling
  edges = card start/end. ffmpeg's whole-frame `scene` filter does NOT work (text is
  too few pixels).
- Brightness edges miss text→text changes with no dark gap; an intra-text pixel-diff
  splitter recovers them (worked on the one no-gap pair).
- Cards ≠ lyric lines 1:1. On Tragedia: 34 cards → 29 lines; 24 matched 1:1, 5 lyric
  lines (6, 14, 20, 24, 25) span two cards. Reconciliation was done by OCR fuzzy-match
  to the song JSON `.en` field, all 29 matched, 0 unmatched.
- OCR-verify correctly caught two cases where the **video text diverged from canonical
  lyrics** (source-video defects). The design lesson: OCR mismatch is a *human-QA flag*,
  not a hard failure.
- Output goes through the real `serializer.write_timeline` (frozen contract:
  `{ "timeline": [{start, end}] }`, half-open `[start, end)`, one entry per lyric line,
  monotonic). The signed-off reference is `docs/spike-candidate-timeline.json`.

**Design questions to resolve (this is the agenda):**
- **Assignment algorithm.** Tragedia was a friendly case (clean black bg, blank gaps,
  near-perfect OCR). Design the algorithm to generalize: how do cards map to lines when
  counts differ? What's the matching strategy (ordinal + OCR fuzzy-match + DP alignment
  over the full sequence)? How do you decide a merge vs a genuine extra/missing card?
  Specify the intra-text split trigger and threshold deliberately, not by the one value
  that happened to work.
- **Confidence + QA surface.** What per-line confidence signals exist (brightness
  cleanliness, OCR score, fuzzy-match score, monotonicity), and what's the
  human-review artifact + workflow when a line is low-confidence or unmatched? Keep it
  CLI/file-based (this is a batch tool), aligned with Jorge's markdown-deliverable bias.
- **Generalization + failure modes.** Non-black backgrounds, anti-aliased/animated
  text, no blank gaps anywhere, OCR in Spanish (`.es`) vs English (`.en`), section
  markers (`start == end == 0`), wrong card count, video offset/trim. Which does v1
  handle, which are explicitly out of scope?
- **Definition of done for v1** (agenda #5): one song end-to-end — video in → verified
  timeline in the song JSON → plays in Auto mode on the translator. State the acceptance
  test and the accuracy bar (tolerance in seconds vs the signed-off reference).

**Deliverable:** a design/architecture spec saved as `docs/assignment-qa-design.md`
(markdown, prose-first per my preferences) covering algorithm, data flow, confidence
model, QA loop, scope boundaries, and v1 definition of done — ending with a short,
ordered build plan I can hand to **Sonnet** in Claude Code. Do not write production
code in this session; pseudocode for the algorithm is fine.

---
