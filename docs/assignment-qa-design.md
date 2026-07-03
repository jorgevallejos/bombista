# Assignment & Human-QA Design — Timeline Extractor v1

> **⚠️ SUPERSEDED (2026-07-03) — video-OCR track parked.** The core mechanism pivoted to
> **audio forced alignment** (faster-whisper `medium` + fuzzy line-anchoring) after the
> translator's ASR spike proved it near-verbatim at 46 s/song; see
> `docs/alignment-pivot-kickoff-2026-07-03.md` and the shipped v1
> (`timeline_extractor/aligner.py`, `anchoring.py`, `pipeline.py`).
> §4 (named-signal confidence bands, `extract`→`promote`, markdown QA report) and the
> §5 contract posture **carried over** into the alignment pipeline, adapted from OCR to
> ASR signals. The change-detection/DP/OCR machinery (§2–§3, §5 video cases) and the
> §6 video-based DoD did **not** ship — kept here as the record of that track
> (branches `feat/lift-spike`, `feat/dp-alignment`, parked on origin).
> Acceptance record for the shipped v1: `docs/acceptance-tragedia-2026-07-03.md`.

_Opus design pass, 2026-06-25 (kickoff agenda #4 + #5). This is an architecture spec, not code — pseudocode for the algorithm only. It builds on the verified change-detection spike; it does not relitigate it. Ground truth for accuracy is `docs/spike-candidate-timeline.json` (signed off 2026-06-25). The frozen output shape is `docs/output-contract.md`. Hand this to Sonnet in Claude Code via the build plan at the end._

---

## 1. What the spike settled, and what this design changes

The spike proved a detection primitive and a reconciliation primitive on one friendly song (Tragedia: clean white-on-black, blank gaps between most cards, near-perfect OCR). Crop the subtitle band, take `signalstats` YAVG per frame, threshold against the blank baseline, and the rising/falling edges give card start/end. Where two cards run back-to-back with no dark gap, a pixel-diff within the text region recovers the hidden boundary. OCR each card and fuzzy-match the text to the canonical lyric line to decide which detected card belongs to which line. On Tragedia this produced 33–34 detected cards reconciling cleanly to 29 lyric lines — 24 matched one-to-one, 5 lines (indices 6, 14, 20, 24, 25) spanning two cards each — with zero unmatched, all monotonic, written through the real serializer.

Two things in the spike are deliberately *not* production-ready, and this document replaces them. First, reconciliation was a **greedy left-to-right walk** that consumes one or two cards per line and, when nothing matches, swallows a card "to stay aligned." That works when detection is nearly perfect but cascades badly the moment a single card is spurious, missing, or badly OCR'd — one local mistake shifts every subsequent line. Second, the **intra-text split** was gated on an arbitrary "window longer than five seconds" rule with a fixed pixel-diff threshold of 0.005 — the one value that happened to work on this source. Both are generalized here: greedy reconciliation becomes a global DP alignment, and the split trigger becomes an adaptively-calibrated signal with a duration guard.

The organizing principle for the whole design is a clean separation of two concerns that the spike entangled: **timing** comes from card boundaries (brightness edges and intra-text splits), and **identity** comes from OCR content matched against canonical lyrics. Detection answers "when did a card appear and disappear"; assignment answers "which lyric line is this card." Keeping them separate is what lets confidence signals from each side combine into a single per-line judgement, and lets a video defect (wrong burned-in text) surface as an identity flag without corrupting the timing.

### 1.1 Source of truth: the video leads on structure, the human decides on text

A decision that shapes the whole tool (Jorge, 2026-06-25): **the video is the source of truth for structure.** The lyrics-only video is a later iteration of how lyrics are split and presented, so when the video and the song JSON disagree on *segmentation* (how a line is split) or *presence* (which lines appear at all), the JSON should be brought into line with the video — not the other way around. The tool therefore emits, alongside the timeline, a set of **proposed updates to the lyrics JSON** (split this line, add this line, remove that one) that converge the file to the video. The timeline is always built to match the video.

Text content is the exception. When the on-screen text *disagrees in wording* with the canonical lyric — Tragedia line 11 (the burned-in `deli, i, i… ighted` glitch) and line 20 (the duplicated `and the oven door` fragment) — the video is sometimes the defective party, so text mismatches are **never auto-applied**. They surface as REVIEW flags for the human to resolve, with the JSON treated as canonical for wording. In short: structure follows the video; wording disagreements are always a human call.

Two refinements on how structure is applied (Jorge, 2026-06-25). Structural **splits and adds** — where the video shows more phrasing than the file (Examples 3–4) — are **applied automatically and reported afterward, with no per-edit confirmation**; the video is trusted. Only a structural **remove** (a file line the video never shows, Example 5) or a hard confidence failure still holds the write until the human resolves it, since a removal can be a detection miss rather than a real cut. When a split or add changes a line, the **other-language variants (Spanish/French/Dutch) are re-split automatically to mirror the video's phrasing**, using an LLM-assisted apply step (§4.4) rather than being left as a manual to-do — and that too is reported, not confirmed. Because these edits rewrite the canonical lyrics file without asking, the tool first copies the original and emits a diff of every structural change, so any bad auto-split is trivially reverted. This LLM-assisted path is designed here but not exercised by the v1 acceptance test (Tragedia has no structural divergences); it is built when the first divergent video appears.

---

## 2. Data flow

The pipeline is a linear batch with one human gate near the end:

```
lyrics-only video ─┐
                   ├─► detect ─► split ─► OCR ─► align ─► confidence ─► [extract] ─► staging:
song JSON (items) ─┘                                                                 candidate-timeline.json
                                                                                     qa-report.md + qa-frames/
                                                                                          │
                                                                                   human reviews qa-report.md
                                                                                          │
                                                                                   [promote] ─► song JSON.timeline
```

`detect` turns per-frame brightness into coarse card windows. `split` subdivides windows that contain more than one card with no dark gap between them. `OCR` reads the text of each resulting card. `align` is the new core: a global, monotonic alignment of the detected card sequence against the canonical item sequence. `confidence` attaches per-line signals and a coarse band. `extract` writes a candidate timeline plus a human-readable QA report to a staging area and stops — it never touches the song JSON. A human reads the report; `promote` then copies the approved timeline into the song JSON. Extraction is always safe to run; only `promote` mutates real song data.

The extractor reads the song's full **item** sequence, not just the lyric lines. Items include section markers (verse/chorus labels) that are never displayed in the video. Those must still receive a timeline entry — the contract requires `timeline.length === items.length` — so section-marker items get the `{start: 0, end: 0}` placeholder and are skipped during alignment (they consume no cards). For Tragedia the item list happens to be 29 displayable lyric lines with no markers, but the design treats markers as first-class so the tool generalizes to songs that have them.

---

## 3. Assignment algorithm

### 3.1 The matching problem, stated precisely

After detection and splitting we have an ordered list of **cards**, each a `(start, end, ocr_text)` triple. From the song JSON we have an ordered list of **lines** (the displayable items, markers excluded), each with canonical text in the chosen language. Both sequences are in the same order — the video shows lyrics in lyric order, and the song lists them in lyric order — so the mapping between them is **monotonic**: no card maps backwards, no line is revisited. What it is *not* is one-to-one. The real cardinalities we must support are:

- **1 card ↔ 1 line** — the common case (substitution / match).
- **2+ cards ↔ 1 line** — a lyric line with an embedded newline displays as two cards (Tragedia lines 6, 14, 20, 24, 25). Call this a **merge**. The newline count is also the file's *expectation* of how many cards a line should produce (`expected_cards = 1 + newline_count`); comparing that expectation against the cards the video actually shows is how the tool detects a structural disagreement (§4.5).
- **1 card ↔ 0 lines** — a spurious detection: an intro title, a section-transition flash, a sub-half-second flicker, or an OCR-noise card that corresponds to no lyric. Call this an **extra card** (skip-card).
- **0 cards ↔ 1 line** — a lyric line that was never displayed, or whose card detection failed entirely. Call this a **missing card** (skip-line). Rare, and usually a video defect, but the line still needs a timeline entry.
- **1 card ↔ 2 lines** — two short lyric lines shown on one card. Not seen in Tragedia; supported by the model but treated as low-confidence (see §3.4).

The greedy spike walk only models the first two and fakes its way past the rest. That is the weakness we are removing.

### 3.2 Why DP alignment, not greedy

Greedy commits to the locally-best card-to-line decision and never reconsiders. A single extra card early in the song pushes every later line off by one, and because each later match is then slightly wrong, the fuzzy scores degrade quietly rather than failing loudly — the worst kind of error for a batch tool. **Global alignment** instead chooses the assignment that minimizes total mismatch cost across the *entire* sequence, so a single anomaly is absorbed as one cheap skip rather than propagated. This is the same structure as Needleman–Wunsch sequence alignment, with the operation set extended to cover merges. The ordinal prior (cards and lines are co-ordered) is exactly what makes a DP over the two indices valid; the OCR fuzzy score is the cost function; the DP is the optimizer. That is the "ordinal + OCR fuzzy-match + DP alignment over the full sequence" stack, made concrete.

### 3.3 The DP

Let `C[0..m-1]` be cards and `L[0..n-1]` be lines. Define `cost(i, j)` for matching card `i` to line `j` as `1 - fuzzy(C[i].ocr, L[j].text)`, where `fuzzy` is a normalized token-aware ratio in `[0,1]` (see §3.6 for normalization). Let `D[i][j]` be the minimum total cost to align the first `i` cards with the first `j` lines. Transitions into `D[i][j]`:

```
D[i][j] = min(
    D[i-1][j-1] + cost(i-1, j-1),                     # MATCH   1 card  ↔ 1 line
    D[i-2][j-1] + merge_cost(i-2, i-1, j-1),          # MERGE   2 cards ↔ 1 line
    D[i-3][j-1] + merge_cost(i-3, i-1, j-1),          # MERGE   3 cards ↔ 1 line   (cap merges at 3)
    D[i-1][j]   + SKIP_CARD_PENALTY,                  # EXTRA   1 card  ↔ 0 lines
    D[i][j-1]   + SKIP_LINE_PENALTY,                  # MISSING 0 cards ↔ 1 line
    D[i-1][j-2] + split_cost(i-1, j-2, j-1),          # SPLIT   1 card  ↔ 2 lines  (rare)
)
```

where `merge_cost(a, b, j) = 1 - fuzzy(concat(C[a..b].ocr), L[j].text)` and `split_cost` is the symmetric version comparing one card's OCR against the concatenation of two lines. Backtracking from `D[m][n]` yields the operation sequence. Each MATCH or MERGE emits one timeline entry: `start` = first card's start, `end` = last card's end. A MISSING line emits a flagged entry (see §3.5 for what timing it gets). An EXTRA card emits nothing and is logged as a dropped card in the QA report.

The crucial property: **merge-versus-extra is now an outcome of cost minimization, not a local rule.** The DP picks MERGE when concatenating two cards matches one line better than matching them to two separate lines; it picks EXTRA-card when no concatenation helps and paying the skip penalty is cheaper than forcing a bad match. The greedy version had to guess this per-step; the DP decides it with global information.

### 3.4 Setting the penalties (not magic numbers)

The two penalties are the only free parameters, and they have a clear interpretation: a skip should cost *more than a plausible-but-imperfect match and less than a clearly-wrong one*. Concretely, with fuzzy in `[0,1]`, an OCR card that genuinely belongs to a line scores high (cost well below ~0.3 on this source); a card forced onto the wrong line scores low (cost above ~0.5). Set both penalties in that gap — start at **0.45** — so the DP prefers a real match when one exists and prefers to skip rather than fabricate a wrong one. `SKIP_CARD_PENALTY` (spurious detections) and `SKIP_LINE_PENALTY` (undisplayed lines) can differ: spurious cards are common and cheap (lower penalty, ~0.4), missing lines are rare and alarming (higher penalty, ~0.6, so the DP only invokes it when truly forced). These are starting values to calibrate against the Tragedia reference, not constants to hardcode — the build plan includes tuning them on synthetic sequences with known answers. The merge cap of three cards reflects that no single lyric line in the catalog wraps to more than two display cards today; three leaves headroom without letting the DP merge an entire verse.

**SPLIT needs a coverage correction (added during build, 2026-06-25).** The SPLIT operation (one card ↔ two lines) has a flaw the other operations don't: a token-aware fuzzy score gives a card *partial* credit for matching just one of the two concatenated lines (`token_sort_ratio` ≈ 0.6–0.7 when the card is really only the first line). That makes SPLIT look cheap enough to absorb a genuinely MISSING line instead of flagging it — the exact silent cascade the DP exists to prevent. Two acceptable fixes: (a) a flat **`SPLIT_SURCHARGE ≈ 0.35`** added to the SPLIT cost, calibrated so SPLIT only wins above fuzzy ≈ 0.75 (`1 − SKIP_LINE + surcharge`), which separates "card contains both lines" (>0.9) from "card contains one" (~0.5–0.7); or (b) the self-contained form that defines SPLIT similarity as `min(partial_ratio(card, L1), partial_ratio(card, L2))`, which only scores high when *both* lines are covered and needs no surcharge. The implementation took (a); either is fine, but note (a) couples to `SKIP_LINE`, so a regression test must pin the relationship (a one-line-covered card must lose to MISSING; a both-lines-covered card must win) so retuning `SKIP_LINE` can't silently break it. SPLIT does not occur in Tragedia, so this is a generalization concern, not on the v1 acceptance path.

### 3.5 Skips become structural lyric edits, not interpolated guesses

Under "the video leads on structure" (§1.1), the DP's two skip operations are not timeline problems to paper over — they are **structural disagreements**, and the tool turns them into edits of the lyrics JSON rather than fabricating timing. Whether an edit is auto-applied or held depends on its direction.

An **EXTRA card** (on-screen text matching no JSON line) means the video shows phrasing the file lacks. If its OCR reads like a real lyric, the tool **adds it as a new line automatically** (English from OCR, the other languages re-split to match per §4.4) and reports it; if it's noise (fails the fuzzy and minimum-duration tests, Example 7), it is dropped. No confirmation either way. A **MISSING line** (a JSON line the video never shows) is the opposite and the one case that still holds: the tool does not interpolate a fake window, and because a missing card can be a genuine detection failure rather than a real cut, it **flags the line for removal and waits** (band FAIL) for the human to confirm the cut or fix detection.

The order of operations keeps the contract intact. Auto-applied splits/adds change the item list, the timeline is built against that updated list, and `timeline.length === items.length` holds without ever inventing a window — the original lyrics file is backed up and a diff emitted first (§1.1). A pending removal blocks the write until resolved. (Section markers still get `{0,0}` and are skipped, exactly as before.)

### 3.6 Fuzzy matching and normalization

The match score must be robust to OCR quirks and language, not to lyric content. Normalize both sides before scoring: lowercase, strip surrounding punctuation and quote-mark variants, collapse whitespace (including the embedded `\n` in two-card lines), and **strip diacritics** (`ñ→n`, `é→e`) so Spanish accents don't penalize an otherwise-correct read. Use a token-sort ratio (order-insensitive within a line) as the spike did — it tolerates a transposed or dropped word. The normalization is symmetric and lossless to the decision; it only affects the cost, never the stored canonical text or the emitted timeline.

### 3.7 The intra-text split, specified deliberately

Splitting exists because brightness edges only fire on blank↔text transitions; two cards shown back-to-back with no dark frame between them register as one long window. The spike caught this with a binarized pixel-diff inside windows over five seconds, splitting where the diff exceeded 0.005. Three things make that fragile and are redesigned here.

**Trigger — when to attempt a split.** Drop the five-second gate; it conflates "long" with "multi-card" (a slow single card can run long; a fast no-gap pair can be short). Attempt a split on *every* brightness window, and let the signal plus a duration guard decide. The cheap protection against over-splitting a stable card is that a genuinely stable card produces near-zero internal diff, so the threshold — not the gate — does the gating.

**Signal.** Sample binarized crops of the subtitle band at a fixed cadence tied to frame rate (every ~4 frames ≈ 0.15 s at 25 fps), and compute frame-to-frame distance. The spike's mean-absolute-diff of the binarized mask is adequate; a perceptual/average hash Hamming distance on the contrast-boosted crop is a more stable alternative and either is acceptable. What matters is that a real card change moves a large fraction of the ink pixels at once, producing a distance spike one to two orders of magnitude above the within-card noise floor — so the two regimes are cleanly separable and the absolute number need not be guessed.

**Threshold — calibrated, not fixed.** Instead of a literal 0.005, measure the noise floor per video: take the frame-to-frame distance series *inside* a region known to be a single stable card (e.g. the middle 60% of a confirmed brightness window), and let `σ` be its standard deviation and `μ` its mean. Set the split threshold at `μ + k·σ` with `k ≈ 8`, or equivalently run a two-cluster split (Otsu / 1-D k-means) on the per-window distance series and place the boundary between the "noise" and "change" clusters. Either way the threshold adapts to the source's contrast and encoder noise rather than to Tragedia specifically.

**Guards.** Every resulting sub-card must exceed a minimum duration (`MIN_CARD_DURATION ≈ 0.4 s`, derived from the fastest plausible card given the song's line count over its runtime) — anything shorter is treated as a flicker, not a card, and folded back. As a global sanity rail, the total card count after splitting should be bounded by the number of lines plus the number of known two-card lines (the song JSON tells us which lines carry an embedded `\n`); if splitting produces dramatically more cards than that bound, the threshold is mis-calibrated and the run should warn loudly rather than feed a garbage card list into alignment. Finally, once a split point is located coarsely from the sampled cadence, refine it to frame accuracy by re-decoding densely (bisection) around the candidate so the emitted boundary is as sharp as a brightness edge.

A subtle but important point: a two-card embedded-`\n` line is *both* a split (detection must see two cards) *and* a merge (alignment puts them back into one line). These are not in tension — split operates on pixels during detection, merge operates on text during alignment, and Tragedia line 6 (~25.66 s split, reference window 23.24–30.44 as one merged entry) is exactly this round trip working correctly.

---

## 4. Confidence model and the human-QA loop

### 4.1 Per-line confidence signals

Rather than a single opaque number, v1 attaches a small set of **named signals** to each line and derives a coarse band from them. Named signals are more debuggable and map better to Jorge's markdown-deliverable bias — a reviewer can see *why* a line is flagged, not just that it scored 0.71. The signals:

- **Fuzzy-match score** — OCR text against canonical line, the primary identity signal. Low score = wrong card or video defect.
- **OCR confidence** — Tesseract's own mean per-word confidence (via `image_to_data` / TSV output). Low = the read itself is shaky, so the fuzzy score is untrustworthy in either direction.
- **Brightness-edge cleanliness** — was the card's window bounded by sharp YAVG step edges, or by a gradual ramp / unstable plateau? A noisy edge means the start/end timing is soft.
- **Boundary provenance** — was this card's boundary a clean brightness edge (trusted) or an inferred intra-text split (less trusted, especially if the split distance sat near the calibrated threshold)?
- **Alignment operation** — MATCH (trusted), MERGE (mostly trusted), SPLIT/EXTRA-adjacent or MISSING/interpolated (suspect).
- **Duration / gap sanity** — is the window duration a plausible outlier versus neighbours, and does it respect monotonicity without overlap?

### 4.2 Bands and the flag rule

Combine the signals into three bands, by rule rather than weighted sum:

- **HIGH** — clean 1:1 or merge, fuzzy and OCR confidence above threshold, brightness edges clean, duration sane. Ships without comment.
- **REVIEW** — any single soft signal trips: fuzzy below `T_fuzzy`, OCR confidence below `T_ocr`, boundary from a near-threshold split, or a duration outlier. The line is probably fine but a human should glance at it.
- **FAIL** — a hard problem: a MISSING/interpolated line, or fuzzy so low the identity is in doubt. Cannot be promoted without explicit human acceptance.

Critically, **a wording mismatch between OCR and canonical text is a REVIEW flag, not a failure and not an auto-edit.** The spike's two catches — line 11's burned-in glitch (`so I may seem deli, i, i, i, i, i, ighted.`) and line 20's duplicated fragment — were the video diverging from the canonical lyric, i.e. source-video defects the timeline correctly carries past (timing is unaffected; the timeline holds timing only). That is OCR-verify *earning its place*. Per §1.1 the video leads on *structure* but not on *wording*: the QA surface presents these as "the video text disagrees with the canonical lyric here — confirm it's a known video defect, not a timing error," and lets the human decide, never overwriting the JSON wording automatically.

### 4.3 The QA artifact

`extract` writes a markdown report, `<song>-qa-report.md`, to staging. Its core is one row per line:

| # | band | line text (canonical) | OCR text | start | end | dur | match | op | flags |
|---|------|-----------------------|----------|-------|-----|-----|-------|----|-------|

plus a summary header — counts of HIGH / REVIEW / FAIL, matched-1:1 / merges / proposed-adds / proposed-removes, total cards vs lines, and a single monotonic-OK line. REVIEW and FAIL rows are grouped or marked so they read first. For every non-HIGH line the tool also exports a thumbnail PNG of that card's mid-window frame into a `qa-frames/` folder beside the report, referenced inline from the markdown — so the reviewer sees the actual burned-in card next to the canonical text without opening the video. Because the workspace is also an Obsidian vault, those images render inline in the report, which makes the review a single-file read.

The report also carries a **"Lyrics-file changes"** section (§1.1, §3.5): every structural edit that converged the JSON to the video, each with before/after text in all four languages and a one-line reason. Splits and adds appear here as **already applied** (with the multilingual re-split shown), since they need no confirmation; a pending **remove** appears as the one item awaiting your decision. For a video that already agrees with its file (Tragedia), this section reads "none structural" and only the wording flags remain. The original lyrics file is backed up and the section links the diff, so any auto-applied edit can be reverted at a glance.

### 4.4 The loop: extract → review → promote

The workflow is `extract` then `promote`, with the human reviewing in between but only *gated* on the few things that genuinely need it. `extract <video> <song-json> --lang en` runs the whole pipeline: it detects and times cards, aligns them, **auto-applies any splits/adds** (backing up the original lyrics file and writing a diff first), runs the **LLM-assisted apply step** that re-splits the other-language variants to mirror the video's phrasing, and writes the candidate timeline, the updated lyrics, the QA report, and the frames to staging. Splits, adds, and wording flags need no sign-off — they are reported for after-the-fact review, and the diff makes a bad auto-edit easy to undo. The only things that hold are a pending **remove** (a line the video never showed) and any hard confidence **FAIL**. `promote <candidate-json> <song-json>` validates the timeline against the contract (length equals the item count, monotonic, types, non-negative) and writes it into the song JSON; it refuses while a FAIL or unresolved removal remains unless an explicit `--accept-fails` flag is passed. Corrections stay manual and file-based — edit the JSON or the diff and re-run — with no interactive fixer in v1.

The LLM-assisted apply step is deliberately separate from the deterministic core (ffmpeg, OCR, the DP). The Python pipeline detects the structural change and supplies the video's English phrasing; an LLM call performs the multilingual re-split. Keeping it a distinct stage means the timing/identity pipeline stays fully deterministic and testable, and the one stage that needs language judgement is isolated and easy to swap or review. It is not on the Tragedia acceptance path (no divergences there), so it can be built after v1's core lands.

---

### 4.5 Worked examples — every video↔file disagreement

These walk each case the tool must judge. The operating rule throughout: **the video rules on structure** (how lines split, which lines appear), surfaced as a proposed file edit the human approves; **the file rules on wording**, so a text difference is only ever a flag. The file's newline count is the expected card count per line, and the disagreement is detected by comparing it against the cards the video shows.

**Example 1 — Clean match (no disagreement).** File line 1 is `of shining silver.` (no newline → expects 1 card). The video shows one card, `of shining silver.`, at 4.52–7.4. → One timeline slot `{4.52, 7.4}`, band HIGH, no proposed edit, no flag.

**Example 2 — Two-card line the file already encodes (no disagreement).** File line 6 is `"You will be exquisite," he sighs,⏎while I dream of my muddy childhood pond.` (one newline → expects 2 cards). The video shows exactly two cards, back-to-back with no dark gap. → The two cards merge into one slot `{23.24, 30.44}`, band HIGH, no proposed edit. The file and video agree, so nothing changes.

**Example 3 — Video splits a line the file keeps whole (video rules → auto-split, no confirmation).** File line is `with fat, garlic and salt.` (no newline → expects 1 card), but a re-rendered video shows two cards: `with fat,` then `garlic and salt.`. The file expected 1, the video shows 2 → structural disagreement, video wins. → The tool **applies the split automatically**: it re-phrases the file line to match the video and uses the LLM-assisted step to re-split the Spanish/French/Dutch the same way (e.g. `con manteca,` / `ajo y sal.`), builds the matching slots, and reports the change with a before/after diff. No sign-off needed; the original is backed up so you can revert if a phrasing looks wrong.

**Example 4 — Video shows a line the file lacks (video rules → auto-add, no confirmation).** Between two known lines the video shows a card whose text matches no file line, and the OCR reads like real lyric (`and the night turns cold`). → The tool does **not** force it onto a neighbour. It **adds a new line automatically** at that position with the read English, fills the other languages via the LLM-assisted step, gives it its own slot, and reports it. (Contrast Example 7: if the card were noise, it would be dropped, not added.)

**Example 5 — File has a line the video never shows (video rules → propose remove).** The file carries a line, but the video shows nothing matching it anywhere in sequence. → No fabricated window. The tool proposes removing that line from the file (or, if it suspects a detection miss, asks you to confirm it's truly absent). Band FAIL until you resolve it, so it can't ship silently.

**Example 6 — Wording differs, video is the defective one (file rules → flag only).** File line 11 is `so I may seem delighted.` (expects 1 card); the video shows 1 card but its burned-in text reads `so I may seem deli, i, i, i, i, i, ighted.`. Structure agrees (1 = 1), so there's no structural edit — only the wording differs. → The slot uses the card's timing, the file's wording is kept, the line is flagged REVIEW with a thumbnail, and you confirm it's a known video defect. The file is never overwritten with the video's text. (Line 20's duplicated `and the oven door` fragment is the same case.)

**Example 7 — Detection noise / glitch card (propose drop).** A sub-second flash, a logo, or an encoder artifact gets detected as a card; its OCR is garbage or non-lyric text matching nothing. → Distinguished from Example 4 by failing the fuzzy and minimum-duration tests: the tool proposes dropping it rather than adding a line, and it gets no slot.

The throughline: Examples 3, 4, 7 are *structural and additive* (split, add, or drop noise), so the video leads and the tool **auto-applies and reports** with no confirmation; Example 5 is the *one structural case that gates* (a removal could be a detection miss); Example 6 is *wording*, so the file leads and the tool only flags. Examples 1–2 are agreement, and produce the Tragedia reference unchanged.

## 5. Generalization and failure modes

What v1 handles, and what it explicitly defers. The guiding fact is that Jorge generates these lyrics-only masters himself, so v1 can assume a cooperative source format and treat hostile formats as out of scope until a real song needs them. On **subtitle position**, v1 does not try to locate the text band — it reuses the fixed band Jorge already renders into (the current bottom-strip crop, `crop=1620:320:0:760`) as the v1 standard, exposed as a config value so a future song with a different layout can override it. No auto-detection in v1.

| Case | v1 | Notes |
|------|----|-------|
| White/bright text on near-constant dark background | **In** | The proven primitive. The production master format. |
| Non-black / textured / animated background | **Out** | YAVG-against-blank-baseline assumes text is the bright thing on a dark constant. Future path: per-video baseline calibration, or edge detection on a color-keyed/stroke-width text mask instead of raw brightness. |
| Anti-aliased text | **In** | Binarization and OCR both tolerate it. |
| Animated / fading text | **Out** | Fades turn brightness step-edges into ramps and make the intra-text diff fire on motion. v1 assumes hard cuts — which the master format controls. |
| Some no-gap (text→text) card pairs | **In** | The intra-text split's purpose; proven on Tragedia's one pair. |
| Fully gapless video (no blank frames anywhere) | **Stretch** | Brightness then finds one giant window and everything rests on the split threshold; expect more REVIEW lines. The lyric-count prior is the main rail. Handle-and-flag, don't guarantee. |
| OCR language `.en` vs `.es` | **In** | `--lang` selects both the song-JSON field to match and the Tesseract language pack; diacritic-stripping in normalization keeps Spanish accents from penalizing matches. |
| Section markers (`start==end==0`) | **In** | Read the full item sequence; markers get the zero-length placeholder and are skipped in alignment. Required by the contract. |
| Wrong / off-by-a-few card count | **In** | The DP absorbs extras (skip-card) and misses (skip-line) as local, flagged events instead of cascading. Gross miscount → many flags → human re-checks params; the tool surfaces the problem rather than hiding it. |
| Video offset / trim | **In (by staying out of it)** | The timeline is emitted in raw video time (video start = 0). `offset` and `trimStart` live on the song's `media` block and remain the translator's concern, per the output contract. The extractor never bakes them in. The one assumption to flag: the lyrics-only video and the playback video share a timebase; if they don't, that residual offset is resolved on the translator side, not here. |

---

## 6. Definition of done for v1

v1 is done when one song goes end-to-end with a human in the loop and the result plays correctly.

**Acceptance test (Tragedia).** Run `extract` on `Master Sequence only subtitles.mp4` plus `tragedia-de-cerdo-asado.json` with `--lang en`. The run must produce a candidate timeline in which every one of the 29 displayable lines gets exactly one monotonic window (markers, if any, get `{0,0}`), the 5 embedded-`\n` lines (6, 14, 20, 24, 25) are correctly merged, the no-gap split at line 6 (~25.66 s) is present, and zero of the 24 clean 1:1 lines are unmatched. The two known video-defect lines (11 and 20) **should** surface as REVIEW flags — that is the tool working, not failing. After human acceptance, `promote` writes the timeline into the song JSON, and the song plays correctly in the translator's **Auto mode**: subtitles track the audio with no perceptible drift.

**Accuracy bar (vs the signed-off reference `docs/spike-candidate-timeline.json`).** For every non-flagged line, `start` within **±0.20 s** and `end` within **±0.30 s** of the reference, with **mean absolute start error ≤ 0.10 s** across all lines. End times are allowed the looser bound because a card's clear-time matters less perceptually than its appear-time, and the next card's start usually dominates. The structural requirements are hard, not toleranced: 100% monotonic, exactly one window per displayable line, the 5 merges correct, no overlaps. The reference is frame-derived at 25 fps (0.04 s granularity) and was hand-verified on lines 0, 11, 17, 20, 21, 28, so these tolerances sit comfortably above its own resolution while staying well inside perceptual subtitle timing.

---

## 7. Build plan (ordered, for Sonnet in Claude Code)

Hand this list to Sonnet; each step is TDD-able and most map to one module. Work on a feature branch per the repo's release flow, not on `main`.

1. **Lift the spike into the package.** Split `spike/change_detection.py` into clean modules under `timeline_extractor/`: `detect.py` (brightness edges), `split.py` (intra-text split), `ocr.py`, `align.py`, `confidence.py`, `report.py`. Keep behaviour identical first; cover each with unit tests against small fixtures before changing anything.
2. **Replace greedy reconcile with the DP alignment** (`align.py`, §3.3). Implement MATCH / MERGE(≤3) / SKIP-CARD / SKIP-LINE / SPLIT with the cost function and penalties of §3.4. Unit-test on synthetic card/line sequences with known answers — clean 1:1, a two-card merge, an injected spurious card, an injected missing line — asserting the recovered operation sequence.
3. **Make the split adaptive** (`split.py`, §3.7). Replace the 5-second gate and fixed 0.005 with the per-video noise-floor calibration (`μ + k·σ` or Otsu), the `MIN_CARD_DURATION` guard, the lyric-count sanity rail, and frame-accurate boundary refinement.
4. **Build the confidence model** (`confidence.py`, §4.1–4.2). Capture Tesseract per-word confidence, derive brightness-edge cleanliness and boundary provenance, and implement the HIGH/REVIEW/FAIL band rule. Unit-test the band logic against crafted signal inputs.
5. **Build the QA report** (`report.py`, §4.3). Emit `<song>-qa-report.md` with the per-line table, summary stats, `qa-frames/` thumbnails for non-HIGH lines, and the **"Proposed updates to the lyrics file"** section (structural split/add/remove edits per §1.1/§3.5, each with a translations-need-resplitting note where relevant).
6. **Language support** (§3.6). Add `--lang` selecting both the song-JSON field and the Tesseract language pack; implement diacritic-stripping, punctuation/quote normalization, and whitespace collapse in the fuzzy comparison.
7. **Item-sequence handling** (§2). Read the full item list, place `{0,0}` for section markers, skip them in alignment, and enforce `timeline.length === items.length` before writing.
8. **Two-step CLI.** Wire `extract` (→ auto-applies splits/adds with a lyrics backup + diff, writes staging candidate + QA report, never writes the song JSON) and `promote` (→ validates against the contract and writes the song JSON, refusing FAIL bands and pending removals without `--accept-fails`). Use the fixed bottom-band crop as a config default per §5.
9. **Acceptance run** (§6). Run the full pipeline on Tragedia, assert the candidate against `docs/spike-candidate-timeline.json` within tolerance in an automated test, then manually confirm Auto-mode playback in the translator. Tune the DP penalties and split `k` against this reference; lock the values once the bar is met.
