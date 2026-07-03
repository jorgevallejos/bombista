# Claude Code prompt — production build (agenda #4 + #5 settled)

Paste the block below into **Claude Code in the `timeline-extractor` repo** (not the translator).
Model: **Sonnet** (build/iterate). The design is settled in `docs/assignment-qa-design.md` — that
file is the authority; this prompt just sequences the work.

---

You are working in the `timeline-extractor` repo, building the production assignment + QA pipeline
designed in `docs/assignment-qa-design.md`. Read that spec first — it is the source of truth for the
algorithm, the confidence model, the QA loop, scope, and the definition of done. Do **not** redesign;
implement it. The verified spike lives in `spike/change_detection.py` and is your starting reference
for the detection/OCR primitives (lift from it, don't re-derive). The frozen output shape is
`docs/output-contract.md`. The signed-off accuracy reference is `docs/spike-candidate-timeline.json`.

**STEP 0 — guards, before any code:**
1. Run `pwd && git remote -v && git status -sb`. Confirm the remote is `jorgevallejos/timeline-extractor`.
   If it is `live-lyric-translator-dev` or anything else, STOP and tell me — do not proceed.
2. Confirm `serializer.py`'s `to_dict` is implemented (not raising `NotImplementedError`). If it still
   raises, the `feat/green-serializer` PR isn't merged — merge it (or tell me), then
   `git checkout main && git pull` so main is green before building. Run the test suite; it must pass
   before you start.
3. Work the plan below as one feature branch per step, following the repo's `/release` flow (tests →
   lint → build → commit → PR via `gh`). TDD throughout: Red → Green → Refactor, small atomic commits,
   no mixing feature work with refactoring.

**Build order** (each step maps to the spec; section numbers in parentheses):
1. **Lift the spike into the package.** Split `spike/change_detection.py` into `timeline_extractor/`
   modules: `detect.py` (brightness edges), `split.py` (intra-text split), `ocr.py`, `align.py`,
   `confidence.py`, `report.py`. Keep behaviour identical first; unit-test each against small fixtures
   before changing anything. (§2)
2. **DP alignment** replacing the greedy reconcile (`align.py`, §3.3): MATCH / MERGE(≤3) / SKIP-CARD /
   SKIP-LINE / SPLIT with the cost function and penalties of §3.4. Unit-test on synthetic card/line
   sequences with known answers — clean 1:1, a two-card merge, an injected spurious card, an injected
   missing line — asserting the recovered operation sequence. Use the file's newline count as the
   expected-cards-per-line signal (§3.1, §4.5).
3. **Adaptive split** (`split.py`, §3.7): replace the 5-second gate and fixed 0.005 with per-video
   noise-floor calibration (`μ + k·σ` or Otsu), the `MIN_CARD_DURATION` guard, the lyric-count sanity
   rail, and frame-accurate boundary refinement.
4. **Confidence model** (`confidence.py`, §4.1–4.2): capture Tesseract per-word confidence, derive
   brightness-edge cleanliness and boundary provenance, implement the HIGH/REVIEW/FAIL band rule.
   Unit-test the band logic against crafted signal inputs.
5. **QA report** (`report.py`, §4.3): emit `<song>-qa-report.md` with the per-line table, summary
   stats, `qa-frames/` thumbnails for non-HIGH lines, and the **"Lyrics-file changes"** section.
6. **Language support** (§3.6): `--lang` selecting both the song-JSON field and the Tesseract pack;
   diacritic-stripping, punctuation/quote normalization, whitespace collapse in the fuzzy comparison.
7. **Item-sequence handling** (§2): read the full item list, place `{0,0}` for section markers, skip
   them in alignment, enforce `timeline.length === items.length`.
8. **Two-step CLI**: `extract` (auto-applies splits/adds per §1.1/§3.5 — backing up the lyrics file
   and writing a diff first — then writes staging candidate + QA report; never writes the song JSON)
   and `promote` (validates against the contract and writes the song JSON, refusing FAIL bands and
   pending removals without `--accept-fails`). Fixed bottom-band crop (`crop=1620:320:0:760`) as a
   config default (§5).
9. **Acceptance run** (§6): full pipeline on Tragedia, assert the candidate against
   `docs/spike-candidate-timeline.json` within tolerance in an automated test (start ±0.20 s, end
   ±0.30 s, mean abs start ≤ 0.10 s; 100% monotonic; 5 merges correct; lines 11 & 20 surface as REVIEW
   flags). Tune the DP penalties and split `k` against this reference and lock the values. Then I'll
   manually confirm Auto-mode playback in the translator.

**Explicitly deferred — do NOT build in this pass:** the LLM-assisted translation re-split step
(§1.1, §4.4). Tragedia has no structural divergences, so it is not on the acceptance path. For now,
when a split/add is auto-applied, fill only the English from OCR and leave the other-language variants
flagged in the report as "needs LLM re-split" — we wire the LLM step in a later pass once the
deterministic core is proven.

**Stop and check in** after step 2 (alignment) and step 9 (acceptance) so I can review before you
continue. Report test status at each PR.

---

## Side note — housekeeping in the OTHER repo (do NOT do this from the timeline-extractor window)

In the **translator** repo, a stray empty `feat/timeline-import-button` branch (zero commits, == main)
is still present from the 2026-06-24 misfire. Delete it there, in a translator-rooted window:
`git checkout main && git branch -d feat/timeline-import-button`. Keeping repo windows clearly
separated avoids a repeat of that incident.
