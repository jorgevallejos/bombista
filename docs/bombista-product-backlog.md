# Bombista — product backlog

**Status:** drafted 2026-08-13, revised same day after Jorge's input on the input adapter.

**Repo state — 2026-08-15 (verified, not assumed).** Bombista is **public** and **MIT**, tagged **`v0.9.0`**; 263 tests green. Its sibling **Pregonero is also public and MIT, tagged `v0.10.0`** — the two ship as a pair, and the timeline v2 contract is shared. B18 is closed as a decision record: go public, **history deliberately left untouched**, master excerpt reachable as an accepted outcome. **B20's step 0 is merged** (PR #18) — the pure refactor that lifted `promote`'s merge and the anchor-override parsing out of `cli.py` into `promotion.py` / `songfile.py` / `anchoring.py`; it added no tests by design, because `promote`'s existing ones are the proof.

**B19 and B20 are both logged below** (PR #17, merged) — B20 is `bombista serve`, and B19 is absorbed into it as page 2 of that flow rather than built separately. `docs/output-contract.md` is retired in the same change; `docs/timeline-v2-contract.md` is the live contract.

**Codename:** Bombista (the bombo legüero player — the one who sets the pace for the ensemble). Part of the **Tramoya** suite.

---

## 1. Positioning (generic — no Chango Pepper in it)

> **You have a recording, and you have the text of what's said or sung in it. Bombista works out when each line happens — and tells you which lines it isn't sure about, so you check three instead of proofing forty.**

Bombista is **not** an automation tool. It is a **triage** tool. Forced aligners already exist (aeneas, Montreal Forced Aligner, whisperX) and they all hand you timings with no opinion about them — so you either trust the lot or re-check the lot, and on a deadline you re-check the lot.

What Bombista adds is the **review loop**:

1. Per-line confidence bands (`HIGH` / `REVIEW` / `FAIL`) with *named reasons* — `clean-anchor`, `ambiguous`, `lead-fallback`, `uncorroborated`, `gap-outlier`, `no-anchor`, `override`.
2. A report that says which lines to check **and why**.
3. A correction pass that re-runs in **0.07 s**, because the transcription is cached (`--words`).

Claim that survives contact with a real show: *timings, plus triage, plus instant correction.*

**Who it serves** (none of it artist-specific): anyone subtitling video; lyric-video and karaoke makers; accessibility captioning; educators building synced read-along texts; audiobook↔ebook sync; and — fittingly for the suite name — **theatre surtitles**, which is this exact job done by opera houses with worse tools.

**Runs offline.** No API keys, no GPU, no network. faster-whisper `medium` (~1.4 GB), CPU int8, ~50 s per song. **This is a property worth protecting** — see the note on translation in §3.

### The design property worth naming

Bombista's native artifact is a **timeline**: an ordered list of `{start, end}` spans, matched to lines by position, containing no words.

That separation is a feature — **the timeline is language-independent**. Retranslate every line into Dutch and the timings still hold. The words change; when they land does not. This is precisely why it feeds a *translation* tool well.

Its cost is positional fragility: insert one line into the lyrics and every timestamp after it is silently wrong. Nothing currently detects this (see **B4**).

---

## 2. Architecture — normalise at the boundary

**Decision (Jorge, 2026-08-13):** rather than teaching the core pipeline to read several input shapes, Bombista **normalises every input into the CP song JSON format as step zero**, then runs the existing pipeline unchanged. An anti-corruption layer, not a rewrite.

```
                ┌─ CP song JSON ──────────────→ (pass through)
  INPUT  ───────┤                                      │
                └─ plain text ──→ NORMALISE ───────────┤
                                  (structural,         │
                                   no LLM)             ▼
                                              CP song JSON (canonical internal form)
                                                       │
                                                       ▼
                                            align(audio, lines)
                                       → [{text, start, end, band, signals}]
                                                       │
        ┌──────────────┬─────────────┬─────────────────┼──────────────┐
        ▼              ▼             ▼                 ▼              ▼
   song.json      timeline.json   report.md       report.json     .srt / .lrc
   (CP format,     (native,        (today)                        (per language)
    always)        unchanged)
```

Three consequences, all good:

1. **The core never changes.** Additive by construction — no regression risk to the existing align→promote flow.
2. **One canonical internal format.** Every writer reads CP song JSON, so writers stay simple and consistent.
3. **CP song JSON is always available as an output**, whatever went in.

### Structural conversion vs linguistic translation — do not conflate these

| | What it is | Needs an LLM? | Whose job |
|---|---|---|---|
| **Structural** | plain text → `{"en": "line"}` objects in a CP-shaped file | **No.** ~30 lines of deterministic, testable Python. | **Bombista (B5)** |
| **Linguistic** | filling `fr`/`nl`/`en` from the `es` lines | Yes | **Not Bombista.** Document the format; the user runs their own LLM over it. |

Keeping linguistic translation out is what preserves the offline, no-API-key property. Bombista times; it does not translate.

### Timing model — lead-in separated from line timings

**Decision (Jorge, 2026-08-13).** The timeline is **relative to a start cue**, not to the beginning of an audio file. Line 0 always starts at `0.000`. The seconds of music before the first sung word are pulled out into a separate `leadIn` field.

```json
"timelineVersion": 2,
"leadIn": { "durationSec": 7.26, "source": "measured", "confidence": "low", "apply": false },
"timeline": [
  { "start": 0.00,  "end": 5.84 },
  { "start": 5.84,  "end": 9.64 },
  { "start": 76.64, "end": 98.84 }
]
```

Note `leadIn` — **not** `intro`. `intro` already exists in the CP format and holds the spoken introduction text.

**Why this is a correctness fix, not just ergonomics.** The measured lead-in is the single least reliable number Bombista produces: faster-whisper has a known quirk that clamps the first sung word toward 0.0 s (Tragedia line 0 came back `HIGH` and still had to be hand-corrected to 0.96 s). In the old model that one bad number contaminated **every** timestamp in the song. Isolating it means the unreliable value sits in one hand-editable field — and for Auto-mode songs it is not used at all, so the quirk stops mattering for 11 of 13 songs.

**What provides the cue differs by mode — same mechanism either way:**

| mode | cue | `leadIn.apply` |
|------|-----|----------------|
| **Auto** (no animation) | the performer's first pedal press | `false` — Jorge starts the lyrics himself, so a live intro of any length is fine |
| **Video** (animation is the clock) | video start **+** `leadIn.durationSec` | `true` — the lead-in is a fixed property of the media, not a live decision |

**Bombista is never told which case it is.** It always measures, always normalises, always records `leadIn`. Whether to *apply* it is a playback decision. One behaviour, one recorded number, one consumer-side switch — no modes, because modes are where bugs live.

`timelineVersion: 2` exists so a v1 (raw-offset) file loaded by a v2 Pregonero fails loudly instead of firing every line 7 seconds early.

### Lyrics arrays contain lyrics only

**Decision (Jorge, 2026-08-13).** The CP format carries **only sung lines** — no section labels, no meta entries. This *deletes* code rather than adding it: the zero-length `{0,0}` marker exemption goes out of `serializer.py::validate_timeline`, and Pregonero never needs the matching exemption. Verified 2026-08-13: no song currently has a marker, so nothing breaks.

Door left open: if section labels are ever wanted in the performer view, they belong in a **separate `sections` array keyed by line index** — never inline in `lyrics`.

### Partial CP song JSON is still CP song JSON

Plain text in → a **valid but incomplete** CP song file. Only the `--lang` key is filled per line; `title` comes from the filename; fields that cannot be inferred are simply absent.

```json
{
  "title": "Río de Sal",
  "lyrics": [
    { "en": "I keep the salt in my pockets," },
    { "en": "counting the lighthouses as they pass." }
  ],
  "timeline": [
    { "start": 5.40, "end": 11.02 },
    { "start": 11.02, "end": 15.18 }
  ],
  "_bombista": { "completeness": "partial", "filledLang": "en",
                 "missing": ["artist","tempo","media","title_translations","intro","translations"] }
}
```

The `_bombista` block tells a downstream tool (or a human, or an LLM asked to finish the job) exactly what is missing. `promote` refuses to overwrite a complete song file with a partial one.

---

## 3. Worked example — illustrative, *Río de Sal*

> **The song, and every number below, is invented.** This section previously
> reproduced a real run against a Chango Pepper master recording; it was
> replaced when the repo went public (B18), because a repo whose worked
> example is one artist's own song reads as that artist's private tool, and
> §1 positions Bombista at theatre surtitles and captioning. The shapes,
> field names, signal vocabulary and orders of magnitude are faithful to
> what the tool actually emits — the measurements are not measurements.

### 3.1 Input A — the audio

`songs/audio/rio-de-sal.m4a`

> ⚠ A timeline is only meaningful relative to the exact audio fed in. Auto-mode songs use the master recording; Video-mode songs must use audio extracted from the linked animation:
> `ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav`
> Getting this wrong is what put an early shipped timeline ~17 s off, silently, with clean confidence bands. **B1 makes this failure visible.**

### 3.2 Input B — the lines, as plain text (target, B5)

```text
Guardo la sal en los bolsillos,
cuento los faros al pasar.
El muelle duerme boca arriba
y el agua aprende a esperar.
…
Vuelvo a empezar.
```

Blank lines and `[Bracketed]` lines are **stripped**, not turned into markers — and what was stripped is listed in the QA report and the `_bombista` block, so the removal is visible rather than silent.

### 3.3 Command

```bash
bombista align songs/audio/rio-de-sal.m4a songs/rio-de-sal.json \
  -o staging/rio-de-sal --lang es --model-size medium
```

51.5 s. Console prints one line:

```
HIGH 18 / REVIEW 2 / FAIL 0 — timeline: … — report: … — words: …
```

### 3.4 Output 1 — native timeline, normalised (v2)

What the alignment measured (raw, against the audio file):

```
line 0: 5.40 → 11.02    line 12: 61.35 → 64.88    line 19: 92.40 → 111.75
```

What Bombista now emits — every value shifted by `−5.40`, the offset banked in `leadIn`:

```json
{
  "timelineVersion": 2,
  "leadIn": { "durationSec": 5.40, "source": "measured", "confidence": "low", "apply": false },
  "timeline": [
    { "start": 0.00,  "end": 5.62 },
    { "start": 55.95, "end": 59.48 },
    { "start": 87.00, "end": 106.35 }
  ]
}
```

Lossless and reversible: `normalised[i] = raw[i] − raw[0].start`, `leadIn = raw[0].start`. Nothing is thrown away — the same information is just stored where a human can edit the uncertain part without touching the reliable parts.

*(20 entries in full; three shown. The last line spans 19 s because `end` falls back to the last transcribed word — see B7.)*

### 3.5 Output 2 — CP song JSON, complete (B2)

Input was a CP song file, so everything is preserved and `timeline` is merged in:

```json
{
  "title": "Río de Sal",
  "artist": "Puerto Nueve",
  "notes": "Capo 3, acordes de Mim",
  "tempo": { "bpm": 92, "numerator": 4, "denominator": 4, "countInBars": 1 },
  "title_translations": { "en": "River of Salt", "fr": "Rivière de sel", "nl": "Rivier van zout" },
  "intro": { "es": "Una canción para los que vuelven tarde…", "en": "A song for those who come home late…" },
  "lyrics": [
    { "es": "Guardo la sal en los bolsillos,", "en": "I keep the salt in my pockets,",
      "fr": "Je garde le sel dans mes poches,", "nl": "Ik bewaar het zout in mijn zakken," }
  ],
  "timeline": [ { "start": 5.40, "end": 11.02 } ],
  "_bombista": { "completeness": "complete" }
}
```

### 3.6 Output 3 — rich JSON with confidence (B1 + B2)

Already computed in `anchoring.py`; currently discarded at serialisation.

```json
{
  "source": {
    "audio": "songs/audio/rio-de-sal.m4a",
    "sha256": "4f2a9c…", "durationSec": 180.6,
    "model": "faster-whisper:medium", "device": "cpu/int8", "lang": "es",
    "extractedAt": "2026-08-11T16:45:34+02:00", "toolVersion": "bombista 1.1.0"
  },
  "linesHash": "sha256:9d41b…",
  "summary": { "high": 18, "review": 2, "fail": 0 },
  "lines": [
    { "i": 0,  "text": "Guardo la sal en los bolsillos,", "start": 5.40,  "end": 11.02,
      "band": "HIGH",   "signals": ["clean-anchor"] },
    { "i": 12, "text": "No soy la orilla, soy la sed,",   "start": 61.35, "end": 64.88,
      "band": "REVIEW", "signals": ["ambiguous"],
      "asrContext": "No soy la orilla soy la se No soy el mar que" },
    { "i": 19, "text": "Vuelvo a empezar.",               "start": 92.40, "end": 111.75,
      "band": "HIGH",   "signals": ["override"], "previousSignals": ["lead-fallback"] }
  ]
}
```

### 3.7 Output 4 — SRT / LRC (B2)

One file per language key present. This is what makes reel and YouTube subtitles fall out of work already being done.

```srt
1
00:00:05,400 --> 00:00:11,020
Guardo la sal en los bolsillos,

2
00:00:11,020 --> 00:00:15,180
cuento los faros al pasar.
```

### 3.8 Output 5 — the QA report (the shape shipping today)

```markdown
# QA report — Río de Sal

- Song file: `songs/rio-de-sal.json`
- Audio file: `songs/audio/rio-de-sal.m4a`
- Model: faster-whisper `medium` (lang `es`)
- Generated: 2026-08-11T16:45:34
- Bands: HIGH 18 / REVIEW 2 / FAIL 0

## Needs attention

| line | band | canonical text | ASR context | start | end | dur | signals |
|------|------|----------------|-------------|-------|-----|-----|---------|
| 12 | REVIEW | No soy la orilla, soy la sed, | No soy la orilla soy la se No soy el mar que | 61.35 | 64.88 | 3.53 | ambiguous |
| 19 | REVIEW | Vuelvo a empezar. | Vuelvo a empezar Contando faros en la niebla | 92.40 | 111.75 | 19.35 | lead-fallback |

- Line 12: re-run with `--anchor 12=<seconds>` and `--words …` (candidate start was 61.35 s).
- Line 19: re-run with `--anchor 19=<seconds>` and `--words …` (candidate start was 92.40 s).

## All lines
… 20 rows …
```

**This report is the product.** It is currently a markdown file that dies in a staging folder.

### 3.9 Correction + promote

```bash
bombista align songs/audio/rio-de-sal.m4a songs/rio-de-sal.json \
  -o staging/rio-de-sal-anchored --lang es \
  --words staging/rio-de-sal/asr-words.jsonl --anchor 19=91.2   # 0.07 s

bombista promote staging/rio-de-sal-anchored/rio-de-sal-timeline.json songs/rio-de-sal.json
```

`promote` backs up, refuses on count mismatch, replaces only `timeline`, prints a per-line diff.

**≈ 4 minutes, of which ~90 s is human attention on 2 lines out of 20.**

---

## 4. Backlog

Because normalisation happens at the boundary (§2), **every item below is additive**. The existing flow cannot regress.

| ID | Item | Why | Size |
|----|------|-----|------|
| **B1** | **Provenance block** — audio path + sha256 + duration, model, device, lang, tool version, timestamp | The 17 s Tragedia error was silent because nothing recorded *which audio* a timeline belonged to. Turns a silent failure into a visible one. **Highest value item here.** | S |
| **B5** | **Input normaliser** — detect CP song JSON vs plain text; convert plain text to a partial CP song file, then run the existing pipeline. Structural only, no LLM. | Makes "give it your lyrics" true, and makes the tool's story generic. Now safe to do first, because it sits *before* the core. | M |
| **B2** | `--emit` (repeatable): `timeline` (default) · `songjson` · `report-json` · `srt` · `lrc` | Writers read the canonical CP form. Reuse `promote`'s merge as a shared function so there is one merge path. | M |
| **B4** | **Lines-hash guard** — store `linesHash`; `promote` warns loudly if the lyrics changed since extraction | Positional coupling is silent; one inserted line misaligns everything after it. | S |
| **B12** | **Normalise to line 0 = 0, bank the offset in `leadIn`** (§2). Add `timelineVersion: 2`. | Isolates the least reliable number Bombista produces into one editable field instead of contaminating all 20 timestamps. Gives the performer control of the start on Auto-mode songs. | M |
| **B13** | ~~**Migrate the two existing timelines**~~ — **DONE 2026-08-14.** `bombista migrate <song.json>`; both songs migrated and committed in `songs/`. Libertad reproduces the contract's golden envelope entry for entry. | Two files. Reversible; `.backup-*` already exists for both. Must ship in the same pass as B12. | S |
| **B3** | **Remove section-marker support** — delete the `{0,0}` exemption from `serializer.py::validate_timeline`; normaliser strips and reports meta lines | Jorge's ruling: CP format carries sung lines only. **Deletes code.** Verified: no song has a marker, so nothing breaks. | S |
| **B7** | Last-line `end` heuristic | Libertad line 19 runs 83.9 → 106.1 (22 s) because `end` falls back to the last transcribed word. Cap at max duration or audio end. | S |
| **B6** | `--lead` global offset knob | Whole-timeline nudge without re-anchoring line by line. | S |
| **B8** | Batch mode — N songs, one summary table | Ergonomics once the catalogue is >2 songs. Relevant as soon as the audio exists. | M |
| **B9** | Decide the canonical import path | `promote` writes `songs/*.json`; the A+ button patches the app's localStorage snapshot. Two destinations, nothing reconciles them. | S (decision) |
| ~~**B10**~~ | **README with §1 positioning** — **DONE 2026-08-14**, after the rename, so it is written in the new vocabulary from line one. MIT `LICENSE`, `.github/ISSUE_TEMPLATE/bug_report.md` and a `pytest` CI workflow landed with it. **"Repo public" is now executed too** — the repo is public as of 2026-08-14; see B18. | The `/tramoya` page needs somewhere to point. | S |
| ~~**B18**~~ | ~~**Decide what to do about lyrics in the repo before going public**~~ — **DONE 2026-08-14. Decision: go public. `gh repo edit --visibility public` has run; the repo is PUBLIC.** See the decision record below the table. | **History was deliberately left untouched** — no rewrite, no force-push. **Original:** going public was decided (both tool repos, MIT — Jorge, 2026-08-14) and then blocked on inspection: `staging/` is clean and always was (never committed, already gitignored), but the repo carried the full lyrics of Libertad and Tragedia in `tests/fixtures/`, in `docs/acceptance-tragedia-qa-report.md`, and quoted as the worked example in §3. Options were (a) accept it, (b) swap fixtures and docs, (c) stay private. | S (decision) |
| ~~**B11**~~ | ~~`align` as primary verb, `extract` kept as alias~~ — **DONE 2026-08-14**, with the rename. `extract` is a registered alias of the same Command object, so the two cannot drift. | S |
| ~~**B17**~~ | **The markdown QA report's re-run command is not shell-quoted** — **DONE 2026-08-14.** Every interpolated path goes through `shlex.quote`; four tests round-trip the printed commands through `shlex.split` rather than looking for quote characters. **Original:** — `report.py` builds it by raw f-string interpolation (no `shlex.quote`) | Same defect B16 fixed in the HTML page, still live in the markdown report. The real audio path is `~/Chango Pepper/songs/audio/libertad.m4a` — the filename is space-free under the `songs/audio/<slug>.<ext>` convention, but the `Chango Pepper` vault directory above it is not, and **one space is enough** for the printed command to split into the wrong arguments and fail on paste. (When B17 was spotted the filename carried a space too — `Song Libertad.m4a`, two spaces in all. The 2026-08-14 rename removed that one; the defect and its fix are unchanged, because the directory space remains.) A copyable command that is broken is worse than no command. Spotted by the B16 agent 2026-08-14; deliberately left untouched as out of scope. | S |
| ~~**B15**~~ | **`songs/_template.json` does not parse as JSON** — **DONE 2026-08-14** in the `songs` repo (`b55d359`); placeholders are neutral empty strings, and the reader was verified to take the CP path. **Original:** — fails at line 28, col 8 (presumably placeholders). Make it valid JSON, or rename it out of `*.json`. | Harmless today: nothing points at it. But B5's reader would fall through to the plain-text path and treat the whole template as lyrics. Spotted while verifying B13, 2026-08-14. | S |
| ~~**B14**~~ | ~~Derive and propose the BPM from the aligned onsets~~ — **DROPPED 2026-08-14.** See "Why B14 was dropped" below. The tempo comes from the Ableton project that produced the audio, where it is exact. | — |
| ~~**B19**~~ | ~~**Editable review page**~~ — **ABSORBED INTO B20 2026-08-14, before it was ever built.** It is **page 2 of the `serve` flow, not a separate item** — see `docs/bombista-serve-spec.md` §3. Its three constraints survive intact and are carried there: emit a timeline rather than a finished song JSON so B4's guard is not bypassed, record which lines were hand-set, and never round coarser than 0.07 s. **Its load-bearing clause survives too** — the download button must be pressed *even when no line was flagged*, which is what converts review from skippable into structurally required. **Original:** make B16's page editable, with a button that generates and downloads the timeline JSON. Jorge's design, 2026-08-14, proposed after the pimiento canary; never logged here as its own row. | Absorbed rather than dropped: a standalone editable page and a three-page `serve` flow would be two implementations of the same correction loop, and the drift between them is exactly what invariant 1 of the spec forbids. | — |
| **B20** | **`bombista serve` — a local web interface.** Full spec: **`docs/bombista-serve-spec.md`** (read it; the table row is a pointer, not a summary). Binds `127.0.0.1` only, runs the existing pipeline in-process, three pages plus the run state: parameters → review and correct → emit. **Absorbs B19.** **Step 0 is a refactor with no feature in it** (§2): `promote`'s merge and the anchor-override parsing live inside `cli.py` as a Click command plus private helpers, so B2's one-merge-path rule is not satisfied and `serve` would have nowhere to import from. Extract first, build second; `promote`'s existing tests are the proof. **Not a hosted service, not a second aligner, not Electron, and not a place tempo gets derived** (rules 4 and 5). | The interface decision below stands as written — this is not its reversal. That decision declined a **GUI** (Electron, a second app, packaging) and pointed at B16 as the cheap capture of most of the value; `serve` is a flag on the existing CLI serving stdlib HTTP, which is the same shape as B16 one step further on. What it adds over B16 is the thing B16 cannot do: the correction loop closes **in the page**, so a REVIEW line is judged and fixed in one place instead of judged in the browser and fixed by retyping a shell command. | L |
| **B21** | **A typed start time on page 2 — kept alongside the arrows, with the bound made visible.** The stepper is calibrated on pimiento's 1.22 s error (24 presses); Luz y Sal produced a **47 s** one — ~940 presses, ~42 s of continuous hold. **Settled 2026-08-16: both controls, not either.** §8.4's popup keeps its stepper and its number becomes a field — *type to arrive, nudge to land*. The typed value clamps to the neighbouring lines and rounds to the grid (never coarser than 0.07 s), **and the bound must be stated**: you feel a stepper stop, you do not feel a text field clamp. Full reasoning: `docs/bombista-serve-spec.md` §12.1. | Found by using it, not by building it — and Jorge corrected the premise: this is **not** the rare case. An unrecognised phrase leaves a line with nothing to anchor to, so where it lands is unbounded by construction, and he expects it *more often than not*. The first pass called it rare on the sole evidence that the fixture did not contain one. **What a fixture contains is not a frequency** — nineteen lines of one song cannot tell you how often a failure happens. | S |
| **B22** | **Drop the `.sp` from the download's file extension — and nothing else.** `serve` writes `<stem>.sp.json`; the vault stores `luz-y-sal.json`. §10.2 already settled that the SP JSON **is** the `songs/*.json` format, so a distinct extension reintroduces the distinction that correction removed. **`SP JSON` stays the name of the format (§10.1); the extension goes.** ⛔ **Withdrawn 2026-08-16 by Jorge:** the promote-from-page-3 and the second key set both proposed here first. §12.2. | Jorge: *"Bombista doesn't change state of a file, it receives one and returns another. It is cleaner in the end this way."* That rule dissolves the `linesHash` / `timelineSignedOff` loss rather than patching it — the returned file already carries all five keys and every original field untouched, so **the vault file *is* the returned file** and nothing needs merging. The keys only ever went missing on a path that took the returned file apart. And the extension was the whole reason the step looked missing: called `luz-y-sal.json` the download is plainly the song file, and *replace the old one with it* is the entire procedure. **`bombista promote` stays for bare timeline envelopes** — not a song file, cannot replace one — and is the one exception if this rule is ever written into §4. | S |
| ~~**B16**~~ | **`--emit html` — a self-contained review page** — **DONE 2026-08-14** (`feat/b16-html-review`, `4b25878`). Provenance header, sticky player, per-line seek, row highlight as the audio passes, `--anchor` command shell-quoted and click-to-copy. Offline guard is an **assertion** over every external-reference form, not a convention — independently verified: zero matches for `http://`, `https://`, `@import`, `<link`, `fetch(`, `src="//` in both the generated page and `writers.py`. Times on the page are **raw audio-clock seconds** (matching the QA report and `--anchor`), not cue-relative — cue-relative would seek every line short by the lead-in. | Chosen 2026-08-14 over building a Bombista GUI (see the interface decision below). The CLI is not the friction; the friction is that judging a `REVIEW` line means *hearing* the audio at 55.88 s, which today means opening the m4a elsewhere and scrubbing. One page, audio embedded, a seek-and-play button per line, REVIEW lines highlighted, the `--anchor` command pre-written beside each. Slots in beside `srt`/`lrc` as another writer in B2's architecture — no Electron, no second app, no packaging. **Worth doing before the 8-song batch** — it pays for itself over 8 reviews. | M |

### B18 — decision record, 2026-08-14: the repo is public

**Decision: go public.** `gh repo edit --visibility public` ran on 2026-08-14; `github.com/jorgevallejos/bombista` is now a public, MIT-licensed repo with `main` as its default branch.

**History was left untouched — deliberately.** No rewrite, no force-push, no orphaned branches. Everything ever committed is now public, including the two commits' worth of prior state described below. This was weighed and accepted rather than overlooked: the rights framing is weaker than it looks, because author rights are established by registration rather than by secrecy, and the Spanish and English lyrics are **already published on changopepper.com by Jorge's own choice**.

**What was swapped before publishing, and why.** The reason was **positioning, not rights** — §1 places Bombista at theatre surtitles and captioning, and a repo whose fixtures and worked example are one artist's own songs reads as that artist's private tool. Both swaps stand on their own merits regardless of the visibility decision:

| what | from | to | commit |
|---|---|---|---|
| audio fixture | `tests/fixtures/tragedia-opening-12s.wav` — 12 s of the actual Tragedia master recording | `tests/fixtures/synthetic-es-12s.wav` — **synthesised Spanish speech** (`say -v Mónica`), invented text, cut to exactly 12.000 s so the provenance duration assertion is untouched; `EXPECTED_OPENING_WORDS` reset | `255f7a1` |
| worked example (§3) | "Worked example — **real data**, Libertad, run of 2026-08-11", with genuine measured timestamps and band counts | "Worked example — **illustrative**, *Río de Sal*" — an invented song with representative numbers, shapes and field names faithful, measurements explicitly not measurements | `5056fa4` |

Two things about the fixture swap are recorded rather than left implicit. `test_aligner.py` runs the real `tiny` model and asserts ≥3 transcribed words overlap the expected lyric; tone or noise would have collapsed that to `len(words) > 0`, a genuine weakening, so synthesised *speech* was the only substitution that kept the assertion's shape. And **the softening is real**: synthesised speech is easier for Whisper than sung audio. That is written into the test's own docstring, and the test's stated purpose is wiring, so it stays within scope.

The §3 heading was relabelled, not just repointed. Invented data cannot sit under a heading that says "real data" — swapping the numbers silently would have left a lie in the heading.

**`docs/acceptance-tragedia-qa-report.md` stays**, with all 34 rows of Tragedia lines, by the same reasoning that kept the lyric fixtures in `tests/fixtures/`: it is the same already-published lyric text, so removing it buys nothing. Removing it would also destroy a real acceptance record for no gain.

**The one genuinely new exposure was the 12 s master excerpt** — neighbouring-rights material (SIMIM), where registration is not yet filed. It is off `main` as of `255f7a1`, but it remains reachable in history at `6829c2d`, which is what "history untouched" means here.

**That it stays publicly reachable is a reviewed and accepted outcome, not an oversight.** It was put to the visibility decision on 2026-08-14 and left in place. Three things carried that call:

- The lyrics the excerpt accompanies are **already published on changopepper.com by Jorge's own choice**. The excerpt is not the first public disclosure of the work.
- **Neighbouring rights are established by registration, not by secrecy.** Keeping a file unreachable creates no right; filing does.
- The mitigation is therefore **filing with SIMIM** — tracked in `projects/song-registration`, not here — rather than deleting the commit.

**Reversal remains possible, and its cost rises with time.** A history rewrite plus force-push would remove the excerpt from this repo, but it cannot recall clones or forks, and every fork that appears raises the cost and lowers the completeness of any later removal. Nothing currently schedules a rewrite; if one is ever wanted, sooner is cheaper than later.

### Pregonero (live-lyric-translator) — implied by B12/B3

Separate repo, separate submodule. These must land **before** a v2 timeline is loaded into the app.

| ID | Item | Why |
|----|------|-----|
| **P1** | **Start-on-cue for Auto mode** — the first pedal press starts the timeline at line 0; from there it runs automatically | This is the whole point of normalising. A live intro can run any length; Jorge triggers the words when he actually sings them. |
| **P2** | **Apply `leadIn` in Video mode** — timeline offset by `leadIn.durationSec` from video start | The animation is the clock; the lead-in is fixed. |
| **P3** | **Reject/warn on missing or v1 `timelineVersion`** | Prevents a v1 file firing every line 7 s early with no error — exactly the silent-failure class B1 exists to kill. |
| **P4** | **Drop the marker exemption need** in `validateTimeline` / `parseTimelineFromJsonText` | Falls out of B3. Simplification, not a fix. |

**P1–P4 built and tested. Gate 4 PASSED on real hardware with the pedal, 2026-08-14.** Cue-start confirmed: armed shows no Play button, time passing changes nothing, the first pedal press reveals line 0, and the song then advances on its own.

Findings from that test session, none of them blocking the merge. **P10 is a
deferred feature idea, not a defect** — read its row before treating the beat
pulse as broken:

| ID | Item | Why |
|----|------|-----|
| **P5** | **Beat pulse runs from Arm, and the cue must NOT re-phase it** | Jorge's real scenario: he talks to the audience while arming, the pulse starts, he picks the tempo up on guitar and plays a 2-bar intro *to* the pulse, then cues the lyrics when he's settled. The pulse is **the beat he plays to**, not a drift reference — so starting it at the cue is too late. And because "the lyrics don't always start on the first pulse of a bar", the performer owns the relationship between beat and first word. **`startAtCue` currently calls `setPhase(getBeatPhase(tempo, 0))`, forcing the pedal press to become a downbeat — that line must go.** Run the phase from Arm while idle; the cue starts `songElapsedMs` only. **Acceptance is visual: the circle must not shift.** Earlier drafts wrote "audibly or visually" — see P10; there is no audio to shift, so that phrasing described a permanently unverifiable condition rather than a real gap. |
| **P6** | **Next/Previous are dead during Auto playback — fix or remove** | The auto-advance effect recomputes the index from elapsed time every tick and snaps to it, so a manual Next reverts within a tick. The buttons *look* like a safety net and aren't one. This bites exactly when drift shows up mid-song and the instinct is to tap Next. **Preferred fix: pressing Next drops the song into Manual for the rest of the song** — one press to take the wheel, predictable under pressure, no new concepts. |
| **P7** | **The `A✓` badge should mean "v2 timeline", not "has a timeline"** | A stale v1 song shows a green `A✓` and looks fully configured while silently taking the legacy path. |
| **P8** | **Warn when importing a song whose title already exists** | Cost Jorge a debugging round on 2026-08-14: removing Libertad from the *setlist* left the v1 copy in the *library*, the import added a second, and the setlist kept pointing at the old one. Two identically-titled songs are indistinguishable in the UI. Related to **B9**. |
| **P10** | **Audible click for the beat pulse** — **DEFERRED FEATURE IDEA, not a defect.** | The pulse is **visual only, by design and always has been**: `BeatCircle` renders it, and there is no `AudioContext` anywhere in Pregonero's `src/`. **Jorge confirmed 2026-08-14 that there is no click and never has been — he plays to the visual pulse.** The "click track" wording that appears in earlier notes was loose shorthand for "the beat he plays to", not a description of something broken. Nothing is missing; this is a *new capability* that could be built if a future scenario wants one — a performer who cannot see the screen, or in-ear monitoring. It would cost nothing in design terms, because it would derive from the same `phase`/epoch the circle already uses and would inherit P5's fix for free. **Not scheduled. Do not log it as a bug, and do not "fix" the docs by implying a gap.** Written up at `live-lyric-translator/docs/pregonero-p5-p6-p9-kickoff.md` (`d355604`). |

**Priority call, 2026-08-14: P5 and P6 are pulled forward, ahead of the rename and the site work.** Jorge is playing to the pulse for the 21 Aug solo-ready date. P5 is therefore not polish — `startAtCue` re-phasing the pulse means the click jumps under his fingers at the exact moment he starts singing, which is a live failure. P6 is the escape hatch when drift shows up mid-song. P7 and P8 stay lower. Kickoff: `projects/live-lyric-translator/docs/pregonero-p5-p6-p9-kickoff.md`.

### P9 — performed-tempo scaling (added 2026-08-14)

**Question (Jorge):** if he decides to play a song at a different tempo, should Bombista rewrite the timestamps, or should Pregonero scale them on the fly?

**Answer: Pregonero, live. Never Bombista.**

The timeline is a **measurement of the recording** — a true statement about that audio file, and it stays true however the song is played on a given night. A performed tempo is a fact about *the performance*. Rewriting the file to match it would put a value in the timeline that no longer corresponds to the audio it was measured from — the exact silent-failure class **B1** exists to kill.

This is the same shape as `leadIn`, and that is the argument: **Bombista always measures and records; the consumer decides whether and how to apply.** `leadIn.apply` is a playback switch; performed tempo is a playback switch. One rule, applied twice — no new concepts, and modes are where bugs live.

```
scale        = tempo.bpm (declared, from the recording) / performedBpm
cueTime[i]   = timeline[i].start × scale
```

**Why linear scaling is sound here, when normally it would not be.** The standard objection is that humans do not slow down uniformly — they stretch verses, hold the last chord, keep the bridge — so the error accumulates and the last lines land seconds out. That objection does not apply **because of P5**: the pulse runs at the performed tempo and Jorge plays to it, so he is metronomically uniform at that tempo *by construction*. The click enforces the thing that would otherwise be an unsafe assumption. And because the pulse and the scaled timeline both derive from the same number, they cannot drift apart — satisfying rule 2 below by construction.

**Honest limit:** this holds while he is on the click. Off it, linear scaling degrades like any other approach would. **P6 is the escape hatch** — a second reason it belongs before 21 Aug.

**The trap — never overwrite `tempo.bpm`.** That field is the recording's tempo and the anchor the whole scale depends on. Overwrite it once and the scaling silently becomes relative to a past gig, with nothing to detect it. If the performed tempo persists at all it persists as a **separate key, `performedBpm`**, with `tempo.bpm` untouched.

**Live safety:** adjustable while idle, **frozen once armed.** Changing the scale mid-song would jump the current line under the performer.

### Why B14 was dropped (2026-08-14, Jorge's call — read this before proposing anything like it again)

B14 proposed that Bombista fit a BPM from the aligned onsets. Jorge rejected it, and the reasoning generalises well beyond this item.

**Bombista answers "when," not "in which beat."** A timestamp is a fact about time: phrase 1 at 0:00, phrase 2 at 0:23. That is the whole output. Tempo and meter are a *musical interpretation layered on top* of time, owned by the performer — and pulling them back down into the timing tool mixes two levels of abstraction that the suite otherwise keeps clean.

**The tell:** the design work needed to make B14 safe was all about defending against problems the feature invented — octave ambiguity (a grid fit lands on double or half time because lyric lines do not start on every beat), and the meter question (Libertad is 6/8 on a dotted quarter, which is a musical judgment no signal-processing result can supply). None of those problems exist if the tool does not attempt the inference. **Elaborate guardrails around a derived value are evidence the value should not be derived here.**

**The premise also failed numerically** (Claude Code, 2026-08-14, before writing any code). The onset fit does not hold: it would hit the decline-to-propose path on **every song in the catalogue, Libertad included**. Audio autocorrelation, the obvious fallback, lands at **±2–3% — 1.5–4.4 s of drift across a song**, which fails rule 2's rate-match requirement outright. So the earlier backlog line *"Method verified 2026-08-14: fitting Libertad's onsets gives 66.68 bpm against 66.67 declared, 0.02% rate error"* **did not survive contact and is withdrawn.** Two independent reasons to drop it: the abstraction is wrong, and the measurement does not work.

**⚠ Where the tempo number comes from — read this precisely.** Jorge knows his own songs' tempi and **types the number in by hand**. That is the entire mechanism.

**This is NOT an input to Bombista, and no reader for it may be built.** Bombista's inputs are **the audio recordings and the lyrics JSON, and nothing else.** In particular: **no Ableton `.als` parsing, in any form.** (Proposed by an agent on 2026-08-14 after an ambiguous phrase in an earlier draft of this section, and rejected by Jorge the same day.) A DAW-format reader would bolt a proprietary, version-fragile dependency onto a tool whose whole claim is audio-in/timings-out, would be meaningless for the generic §1 audiences — theatre surtitles and captioning have no `.als` files — and would automate typing ten numbers exactly once.

*(PM note: the choice was framed to Jorge as "build B14 vs. type them by hand," which was a false pair and steered the decision; and the phrase "the Ableton project is its primary source" was then read by an agent as naming a source *for the tool* rather than *for Jorge*. Both were Cowork-side wording defects. Jorge corrected both.)*

**Consequence:** filling the missing `tempo` blocks is a **data-entry task on Jorge's side**, not a build. No code, no fitting, no readers, no confidence bands.

**Explicitly out of scope for this version:** validating the performer's tempo against the timeline. If the performer enters a wrong BPM, the pulse and the P9 scaling will be wrong, and **that is the performer's problem, not the tools'** (Jorge, 2026-08-14). A consistency check may be worth revisiting later; it is not wanted now, and it is not a blocker.

### Rules established 2026-08-14

1. **No `tempo` block → no Auto mode.** Tempo is a prerequisite, not a nicety. Only 3 of 13 songs have one — filled by hand from the Ableton projects, not derived.
2. **The pulse and the timeline are separate clocks.** A constant offset between them is fine; what must match is the *rate*, so any shift stays consistent instead of accumulating. Verified on Libertad: 0.02 s across the whole song.
3. **The timeline measures the recording; the performance is a playback-side transform.** Anything describing how a song is played on a given night — lead-in application, performed tempo — is applied by Pregonero at playback and never written back over the measured values. Bombista measures and records; the consumer decides. (Established via P9.)
4. **Bombista answers "when," not "in which beat."** Its output is time: line *i* happens at *t*. Tempo, meter and any other musical structure are **performer-owned metadata**, entered by a human and consumed by Pregonero — never inferred from the timings. Timestamps and pulses are different levels of abstraction; keeping them apart is what makes the timeline language-independent, tool-independent and cheap to reason about. (Established by dropping B14.)
5. **Bombista's inputs are the audio recordings and the lyrics JSON. Nothing else.** No DAW project files, no `.als`, no session metadata, no third source of truth. If a fact is not in the audio or the lyrics, it is not Bombista's to know — a human supplies it. This is what keeps the tool generic, offline and portable to the §1 audiences, and it is the boundary the anti-corruption layer in §2 exists to defend. (Established 2026-08-14 after an agent proposed an Ableton tempo reader.)

### Interface decision, 2026-08-14: no Bombista GUI

Considered and declined for now. Bombista runs ~8 times over the next two weeks and then goes quiet; building an interface for a tool about to go idle is premature. A real GUI only pays off if the generic positioning in §1 (theatre surtitles, captioning, karaoke) is a bet actually being placed — which is not a bet to make three weeks before a new job starts.

The friction is not the CLI. It is that judging a `REVIEW` line requires *hearing* the audio at a candidate timestamp. **B16 (`--emit html`) captures most of that value at a fraction of the cost.** Revisit the GUI question after the 8-song batch, with real data on how many minutes review actually took.

A third option was named and deliberately rejected: putting the timing UI *inside* Pregonero, which already has the library, the audio and an Electron shell. It is the cheapest path to a real GUI, but it fuses two stations the Tramoya framing says should stay separable, and drags Bombista's language-independence into an app that is entirely about language.

**Sequel, same day: B20 (`bombista serve`).** This decision is unchanged, not reversed — every option it rejected is still rejected, and `docs/bombista-serve-spec.md` §1 restates the refusals in its own words. What B20 proposes is none of them: a flag on the existing CLI that serves stdlib HTTP on `127.0.0.1`, which is the B16 shape (one offline page, no packaging) carried one step further so the correction can be *applied* in the page rather than retyped as a shell command. B19 was folded into it rather than built beside it.

---

## 5. Catalogue state — verified 2026-08-13

| song | lines | mode | timeline | master project | audio bounced |
|------|------:|------|----------|----------------|---------------|
| libertad | 20 | auto | ✅ | ✅ | ✅ |
| tragedia-de-cerdo-asado | 29 | **video** | ✅ | ✅ | ✅ |
| pimiento | 19 | auto | — | ✅ | ✅ (ref + test) |
| duelo | 21 | auto | — | ✅ | ❌ |
| hasta-calmar-el-alma | 18 | auto | — | ✅ | ❌ |
| luz-y-sal | 18 | auto | — | ✅ | ❌ |
| no-te-voy-a-odiar | 30 | auto | — | ✅ | ❌ |
| paso | 19 | auto | — | ✅ | ❌ |
| soy-una-puerta | 24 | auto | — | ✅ | ❌ |
| vidas | 7 | auto | — | ✅ | ❌ |
| **don-bonifacio** | 24 | auto | — | ❌ | ❌ |
| **la-pajita** | 11 | auto | — | ❌ | ❌ |
| **quien-fuera** | 28 | auto | — | ❌ | ❌ |

**Section markers: none, in any song.** B3 is therefore not a blocker.
**Video mode: Tragedia only**, and it already has a timeline. The audio-provenance trap does not bite the remaining batch.

**The actual blocker was audio.** As verified above on 2026-08-13, `songs/masters/` held **Ableton projects (`.als`)**, not bounced files, and only Libertad, Tragedia and Pimiento had audio in `songs/audio/`.

### ✅ Update 2026-08-14 — the audio bottleneck is cleared

Jorge bounced and reorganised `songs/`. **All 10 recordable songs now have audio directly in `songs/audio/`**, so the "audio bounced ❌" column above is stale for duelo, hasta-calmar-el-alma, luz-y-sal, no-te-voy-a-odiar, paso, soy-una-puerta and vidas. `songs/masters/` is gone — the Ableton projects were removed deliberately. The older fixture-ish audio moved to `songs/audio/test/`.

**The naming convention is now binding and consistent: `songs/audio/<slug>.<ext>`, where `<slug>` is the song JSON's basename exactly** — `libertad.m4a`, `pimiento.m4a`, `tragedia-de-cerdo-asado.mp3`. Lowercase, hyphenated, no `Song-` prefix, no spaces, no capitals. Extensions are left as-is (`.mp3` / `.m4a`) because they reflect real format differences; nothing re-encodes to force uniformity. This makes the audio↔JSON pairing mechanical: given any song JSON, its audio is the same basename in `audio/`. **Every earlier spelling in every doc is dead** and will fail on paste.

**Video has the same rule, added 2026-08-15: `songs/video/<slug>.<ext>`.** Video had no convention until now, which is why `tragedia-de-cerdo-asado.json` carried a `media.src` pointing at a file that existed nowhere. `songs/video/` is the **delivery** copy; `animations/<slug>/` remains the authoring home and is not moved. Copy the clean H.264 master across — **never** a ProRes `.mov` (mastering format, tens of GB), and **never** a "Big Screen" or "Small Screen" cut: those carry **burned-in EN subtitles** that would fight Pregonero's own surtitles.

**This matters to Bombista because of the audio-clock rule.** For a Video-mode song the timeline must be aligned against the *animation's* audio, not the master recording. `songs/video/<slug>.<ext>` now gives that file a predictable home, so the extraction is `ffmpeg -i songs/video/<slug>.mp4 -vn -ac 1 -ar 16000 <slug>-video.wav` and no longer a hunt through `animations/`. Tragedia is the only Video-mode song, and its stored timeline is the known ~17 s-late one precisely because it was aligned against the wrong take.

### ⚠ Update 2026-08-15 — the ten placeholder tempo blocks are gone

The `tempo` column is not in the table above, but it gates as much as audio does: **no tempo means no Auto mode and no P9 scaling.** Until today ten songs *appeared* to have one and did not.

don-bonifacio, duelo, hasta-calmar-el-alma, la-pajita, no-te-voy-a-odiar, paso, pimiento, quien-fuera, soy-una-puerta and vidas all carried a byte-identical **invented** block — `bpm 100, 4/4, countInBars 1`. All ten are removed, and deliberately **not** replaced with a flag, a null, or a "provisional" marker.

**Why there is no marked-as-invented value to fall back on.** `tempo.bpm` has two consumers that need opposite things from a fake number: it is the **scaling denominator** in Pregonero's `performedTempo.ts`, and it also drives the **visual pulse**. A placeholder chosen to keep the pulse looking plausible is the wrong denominator for scaling; a value chosen to make scaling behave is the wrong pulse. No single number satisfies both, so no live setting can correct for it — the block is only ever correct when the number is real. Pregonero already degrades safely on absence: **no pulse, no count-in, scale pinned to 1.**

This is **not** a reopening of B14, and nothing here licenses deriving the tempo. Rule 5 stands: Bombista's inputs are the audio and the lyrics JSON, nothing else — no `.als` parsing in any form. The tempo is data entry from the Ableton projects, where it is exact.

Real measured tempos survive untouched: **libertad** (66.67, 6/8), **luz-y-sal** (140, 3/4), **tragedia-de-cerdo-asado** (128, 4/4, countInBars 2). All 13 song files re-parse; the change was 60 deletions, zero insertions.

Note the asymmetry this exposes: **`luz-y-sal` has a real tempo but no timeline**, while **tragedia has a timeline but a known-bad one**. **Libertad remains the only song with both.**

Also verified the same day, against every file in `songs/`: **no song carries the dead bare-timeline shape** (a `timeline` with no `timelineVersion: 2` and no `leadIn`) that the old Pregonero README documented and that P3 has rejected since. Only libertad and tragedia have a timeline at all, both correct v2; the other eleven have no `timeline` key, which the loader skips as a normal un-timed song. No song data was changed to make this true.

Remaining sequence:

1. Run Bombista on pimiento first — the canary — then the other 7. Find a writer bug on one song, not eight.
2. **Not Tragedia from its master.** It is the one Video-mode song: its timeline must come from the *animation video's* audio, never from the master recording. Its `media.src` also points at a `tragedia-de-cerdo-asado.mp4` that does not exist in the vault — a pre-existing broken link.
3. don-bonifacio, la-pajita, quien-fuera have no audio at all — they cannot be timed until something is recorded.

---

## 6. Claude Code kickoff

> Work in `projects/bombista`. Implement **B12, B13, B3, B1, B5, B2, B4** from `docs/bombista-product-backlog.md` — read that file first, especially §2 (architecture and timing model).
>
> **Architecture constraint:** normalise at the boundary. Plain-text input is converted to a CP-shaped song dict *before* the existing pipeline runs; the core alignment code is not modified. Default behaviour with no new flags must be byte-identical to today apart from the new provenance block — add a regression test asserting the existing `{"timeline":[…]}` output for the Libertad fixture is unchanged.
>
> - **B12** — normalise the emitted timeline so line 0 starts at `0.000`; subtract `raw[0].start` from every entry and record it as `leadIn: {durationSec, source: "measured", confidence: "low", apply: <bool>}`. Default `apply` to `true` when the song has `media.type == "video"`, else `false`. Stamp `timelineVersion: 2`. Bombista takes **no flag** for this — it always measures, always normalises, always records. Assert losslessness in a test: re-adding `leadIn.durationSec` reproduces the raw values exactly.
> - **B13** — one-shot migration script for `songs/libertad.json` and `songs/tragedia-de-cerdo-asado.json`: subtract `raw[0].start`, write `leadIn` and `timelineVersion: 2`. Back up first. Verify libertad line 0 becomes `{0.00, 5.84}` with `leadIn.durationSec == 7.26`.
> - **B3** — delete the zero-length `{0,0}` marker exemption from `serializer.py::validate_timeline` and its tests. Lyrics arrays carry sung lines only.
> - **B5** — new `readers.py`. Detect input: valid JSON with a `lyrics` array → CP path (unchanged). Anything else → plain-text path: one line per lyric line; blank lines and `[Bracketed]` lines are **stripped and reported**, not converted to markers; each surviving line wrapped as `{"<lang>": text}` with `--lang` (default `es`), `title` from the filename stem. Emit a `_bombista` block with `completeness`, `filledLang`, `missing`, `strippedLines`. **Structural only — no translation, no network, no LLM.** The offline property is a feature.
> - **B1** — provenance block (audio path, sha256, durationSec, model, device, lang, extractedAt, toolVersion) in the rich JSON, the CP song JSON `_bombista` block, and the report header. **Not** in the native `timeline.json` envelope, which the translator parses strictly.
> - **B2** — `--emit` repeatable click option: `timeline` (default), `songjson`, `report-json`, `srt`, `lrc`. Writers in `serializer.py`, all reading the canonical CP form. Extract `promote`'s merge into a shared function used by both `promote` and the `songjson` writer. `--emit srt|lrc` writes one file per language key present. `promote` refuses to overwrite a `completeness: complete` song file with a partial one.
> - **B4** — `linesHash` = sha256 over the ordered canonical line texts, stored in the rich JSON and `_bombista`; `promote` recomputes from the target and prints a loud warning (not an error) on mismatch.
>
> `pytest` green before commit. Separate commit per item.
>
> **Out of scope here:** the Pregonero items P1–P4 (separate repo, `projects/live-lyric-translator`). They must land before any v2 timeline is loaded into the app — do not promote a migrated song into a running setlist until P3 exists, or it will fail silently.
