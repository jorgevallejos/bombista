# B20 — `bombista serve`: a local web interface

**Status:** specced, not built. Jorge's design, 2026-08-14. Supersedes and absorbs **B19** — the
editable review page is page 2 of this flow, not a separate item.

---

## 1. What it is, and what it is not

`bombista serve` starts an HTTP server **on the user's own machine**, binds to `127.0.0.1`, and
opens a browser at a three-page flow: parameters → review and correct → emit. The alignment runs
locally, in the same Python process that the CLI uses.

**It is:** a front end for the CLI that a non-technical person can drive.

**It is not, and must never become:**

| not | why |
|---|---|
| a hosted service on changopepper.com | Holding other people's audio is a legal posture Jorge does not want, and it would make him a data controller. Nothing leaves the machine, so GDPR does not arise rather than being answered. |
| a second aligner (WASM / transformers.js) | Two implementations of the confidence banding drift, and the report's trustworthiness is the entire product. Also: the real quality bar is `--model-size medium`, which does not fit in a browser or a serverless function. |
| Electron, a packaged app, a second codebase | The no-GUI decision stands. This is a flag on the existing CLI serving HTML, using the stdlib. |
| a place tempo gets derived | Rules 4 and 5, and B14 was dropped for this reason. See §5. |

**Bind to `127.0.0.1` explicitly, never `0.0.0.0`.** A dev server on the LAN is the one way this
design could accidentally become the thing it is avoiding.

---

## 2. Step 0 — a prerequisite that must land first

**`promote`'s merge does not currently exist as a reusable function.** It lives inside
`cli.py` as a Click command plus private helpers: `_load_promotable_candidate`,
`_extract_envelope`, `_find_candidate_lines_hash`, `_lines_hash_mismatch_warning`,
`_timeline_diff`, `_back_up_and_replace`. `_parse_anchor_overrides` is in the same position.

B2's rule — *one merge path* — is therefore not yet satisfied, and `serve` cannot honour it by
importing from `cli.py`.

**Extract first, build second.** Move the merge and the anchor-override parsing into modules that
both `promote` and `serve` import. `promote`'s behaviour must not change; its existing tests are
the proof. This is a refactor with no feature in it, and it is the first commit of B20.

---

## 3. The four states

Three pages, plus one that is easy to forget.

### Page 1 — parameters

**No free text anywhere.** Every field is a picker, a dropdown, a radio or a stepper.

| field | control | note |
|---|---|---|
| lyrics input | file picker, `.json` or `.txt` | Chooses the branch in §5. |
| audio | file picker | Filename convention is `songs/audio/<slug>.<ext>`, but the picker takes any path. |
| language | dropdown | Default `es`, matching the CLI. |
| model size | dropdown | Default `medium`, matching the CLI. Label the trade-off in the option text. |
| emit | checkboxes | `timeline` · `songjson` · `report-json` · `srt` · `lrc` (B2). |
| output directory | directory picker | Defaults to a staging dir. |

If the input is `.txt`, page 1 grows the fields in §5 and **shows what the normaliser stripped**
before running. B3 removes section markers; a silent line-count change surfaces much later as a
`promote` refusal, which is a bad place to learn it.

### Page 1.5 — the run

Alignment takes real time — `medium` on a full song is not instant. This is a state, not a spinner
between pages:

- Two visible phases: transcribe, then anchor.
- A working **cancel**.
- **Re-runs from page 2 skip transcription entirely**, reusing the saved `asr-words.jsonl`. Say so
  on screen — the difference between a 90-second wait and a 2-second one is the whole ergonomics of
  the correction loop.

### Page 2 — review and correct

This is B19, and the heart of it. It inherits B16's page: provenance header, sticky player,
per-line seek, band highlighting.

**Editing a timestamp re-anchors; it does not shift.**

`anchoring.py` is forward-only — the scan position only ever advances, and an override advances it
to the first word *after* the corrected time before anchoring the next line. So a correction
re-derives every following line **against the audio**. Subsequent values do change, which is the
behaviour Jorge asked for, but by re-matching rather than by arithmetic. A rigid delta shift would
displace lines that were measured correctly, destroying exactly the HIGH-confidence rows the report
exists to certify. **Never implement a ripple.**

Consequences the UI must show rather than hide:

- An edit **recomputes the bands below it**. A HIGH line may come back REVIEW. That is the most
  useful signal on the page — mark every band that changed, do not just repaint silently.
- Lines *above* the edit are untouched, by construction. Make that visible too.

Controls:

- **Stepper, ±0.05 s.** The differentiator is a 0.07 s correction loop, so the step must sit below
  it; neither the control nor the JSON round trip may round coarser.
- **Set from playhead.** A stepper alone cannot span a 1.2 s misdetection — that is 24 clicks. Play
  the audio, press a key at the moment the line starts, then use the stepper for the last hundred
  milliseconds. This is how a musician finds an onset.
- **Bounds come from the neighbouring lines**, recomputed live. That is the real allowed interval;
  a fixed range is not.
- **Line 0 has no stepper.** Timeline v2 normalises line 0 to zero and banks the offset in
  `leadIn`. A stepper on line 0 silently breaks the v2 contract. If the whole song sits late that is
  a `leadIn` control at the top of the page — which is also where B6's global nudge belongs. Local
  error and global drift are different problems and get different widgets.
- Every hand-set line is **recorded as hand-set**, with its original machine value and a timestamp.

### Page 3 — emit

- **Always a new file. Never edits the input.** This is Jorge's call, 2026-08-14, and it is the
  right one: it removes the file-changed-on-disk race entirely and keeps the merge a pure
  input → output function.
- Renders the resulting JSON **read-only**. No editing at this stage.
- A **download** button — and per B19's original clause, **it must be pressed even when no line was
  flagged**. That clause is the point of the whole design: it converts review from something
  skippable into something the pipeline structurally requires, so every timeline reaching a song
  JSON carries a conscious human sign-off.
- The emitted file carries **`linesHash`** (B4) and the **edit provenance** from page 2. Without the
  hash the download routes around B4's guard: you save the file, a line gets added to the canonical
  song JSON upstream, you copy yours over it, and everything after that line misaligns silently —
  the precise scenario B4 exists to prevent. Without the provenance, a machine timeline and a
  reviewed one are indistinguishable.
- The merge is the extracted one from §2. Page 3 does not hand-roll a write.

---

## 4. Invariants

1. `serve` imports no logic from `cli.py`; both call the same extracted modules.
2. No timestamp control or serialisation step rounds coarser than 0.07 s.
3. Line 0 is always 0 in a v2 timeline; any lead offset lives in `leadIn`.
4. Onsets are monotonic; a stepper's bounds are its neighbours.
5. A correction re-anchors. Nothing anywhere applies a blanket delta except the explicit global
   `leadIn` / `--lead` control.
6. The emitted file never overwrites an input path.
7. Bind `127.0.0.1` only.

---

## 5. The plain-text branch (B5)

A `.txt` carries lines and nothing else. CP format needs more, so page 1 asks for it — as controls,
not free text where avoidable:

- **slug** — derived from the filename, shown for confirmation.
- **title**, **language**.
- **tempo** — a **clearly marked placeholder**, never derived. Rules 4 and 5 stand, and B14 was
  dropped precisely because tempo comes from the Ableton project that produced the audio, where it
  is exact. The UI must make it obvious this is a value Jorge fills in by hand, not a measurement.
- **stripped meta lines** — shown before the run, not after.

---

## 6. Test obligations

- `promote`'s existing tests pass unchanged after the §2 extraction. That is the refactor's proof.
- A test asserts the `serve` layer **delegates** to the extracted anchoring and merge rather than
  reimplementing them — the drift risk is the whole reason this item is shaped this way.
- A test asserts an override re-anchors: lines after a correction take values derived from the word
  stream, not `original + delta`.
- A test asserts line 0 cannot be moved and that a lead offset lands in `leadIn`.
- A test asserts the emitted file carries `linesHash` and the hand-set provenance.

---

## 7. Open

- Does `serve` ship in `v1.0.0` or after? The pimiento canary gates 1.0.0; this is larger than the
  canary and probably wants its own version.
- Installation is still `pipx install bombista` — one line, but a line. A packaged binary is the
  answer if that ever needs to go, **not** a hosted service.
- `changopepper.com/tramoya/bombista` remains a shopfront: what it does, the *Río de Sal* worked
  example as a clickable page, install instructions. It is no longer a dependency of this item.
