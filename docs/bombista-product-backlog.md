# Bombista — product backlog

**Status:** drafted 2026-08-13, revised same day after Jorge's input on the input adapter.
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

1. **The core never changes.** Additive by construction — no regression risk to the existing extract→promote flow.
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
  "title": "Libertad",
  "lyrics": [
    { "en": "I was a glowing ember in the dark," },
    { "en": "a spark longing to break free." }
  ],
  "timeline": [
    { "start": 7.26, "end": 13.10 },
    { "start": 13.10, "end": 16.90 }
  ],
  "_bombista": { "completeness": "partial", "filledLang": "en",
                 "missing": ["artist","tempo","media","title_translations","intro","translations"] }
}
```

The `_bombista` block tells a downstream tool (or a human, or an LLM asked to finish the job) exactly what is missing. `promote` refuses to overwrite a complete song file with a partial one.

---

## 3. Worked example — real data, Libertad, run of 2026-08-11

### 3.1 Input A — the audio

`songs/audio/Song Libertad.m4a`

> ⚠ A timeline is only meaningful relative to the exact audio fed in. Auto-mode songs use the master recording; Video-mode songs must use audio extracted from the linked animation:
> `ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav`
> Getting this wrong is what put the original Tragedia timeline ~17 s off, silently, with clean confidence bands. **B1 makes this failure visible.**

### 3.2 Input B — the lines, as plain text (target, B5)

```text
Fui brasa viva en la oscuridad,
Chispa que quiso brotar.
Tantas noches que pasé
soñando un nuevo lugar.
…
Elijo arder más.
```

Blank lines and `[Bracketed]` lines are **stripped**, not turned into markers — and what was stripped is listed in the QA report and the `_bombista` block, so the removal is visible rather than silent.

### 3.3 Command

```bash
timeline-extractor extract "songs/audio/Song Libertad.m4a" songs/libertad.json \
  -o staging/libertad --lang es --model-size medium
```

51.5 s. Console prints one line:

```
HIGH 18 / REVIEW 2 / FAIL 0 — timeline: … — report: … — words: …
```

### 3.4 Output 1 — native timeline, normalised (v2)

What the alignment measured (raw, against the audio file):

```
line 0: 7.26 → 13.10    line 12: 55.88 → 59.52    line 19: 83.90 → 106.10
```

What Bombista now emits — every value shifted by `−7.26`, the offset banked in `leadIn`:

```json
{
  "timelineVersion": 2,
  "leadIn": { "durationSec": 7.26, "source": "measured", "confidence": "low", "apply": false },
  "timeline": [
    { "start": 0.00,  "end": 5.84 },
    { "start": 48.62, "end": 52.26 },
    { "start": 76.64, "end": 98.84 }
  ]
}
```

Lossless and reversible: `normalised[i] = raw[i] − raw[0].start`, `leadIn = raw[0].start`. Nothing is thrown away — the same information is just stored where a human can edit the uncertain part without touching the reliable parts.

*(20 entries in reality. The last line spans 22 s because `end` falls back to the last transcribed word — see B7.)*

### 3.5 Output 2 — CP song JSON, complete (B2)

Input was a CP song file, so everything is preserved and `timeline` is merged in:

```json
{
  "title": "Libertad",
  "artist": "Chango Pepper",
  "notes": "Capo 5, Acordes de Lam",
  "tempo": { "bpm": 66.67, "numerator": 6, "denominator": 8, "countInBars": 1 },
  "title_translations": { "en": "Freedom", "fr": "Liberté", "nl": "Vrijheid" },
  "intro": { "es": "Ese pequeño grano de locura…", "en": "That small touch of madness…" },
  "lyrics": [
    { "es": "Fui brasa viva en la oscuridad,", "en": "I was a glowing ember in the dark,",
      "fr": "J'étais une braise vive dans l'ombre,", "nl": "Ik was een gloeiende sintel in het donker," }
  ],
  "timeline": [ { "start": 7.26, "end": 13.1 } ],
  "_bombista": { "completeness": "complete" }
}
```

### 3.6 Output 3 — rich JSON with confidence (B1 + B2)

Already computed in `anchoring.py`; currently discarded at serialisation.

```json
{
  "source": {
    "audio": "songs/audio/Song Libertad.m4a",
    "sha256": "4f2a9c…", "durationSec": 172.4,
    "model": "faster-whisper:medium", "device": "cpu/int8", "lang": "es",
    "extractedAt": "2026-08-11T16:45:34+02:00", "toolVersion": "bombista 1.1.0"
  },
  "linesHash": "sha256:9d41b…",
  "summary": { "high": 18, "review": 2, "fail": 0 },
  "lines": [
    { "i": 0,  "text": "Fui brasa viva en la oscuridad,", "start": 7.26,  "end": 13.10,
      "band": "HIGH",   "signals": ["clean-anchor"] },
    { "i": 12, "text": "Fui más impulso que voz,",        "start": 55.88, "end": 59.52,
      "band": "REVIEW", "signals": ["ambiguous"],
      "asrContext": "Fui más impulsó que vos Fui fuego que" },
    { "i": 19, "text": "Elijo arder más.",                "start": 83.90, "end": 106.10,
      "band": "HIGH",   "signals": ["override"], "previousSignals": ["lead-fallback"] }
  ]
}
```

### 3.7 Output 4 — SRT / LRC (B2)

One file per language key present. This is what makes reel and YouTube subtitles fall out of work already being done.

```srt
1
00:00:07,260 --> 00:00:13,100
Fui brasa viva en la oscuridad,

2
00:00:13,100 --> 00:00:16,900
Chispa que quiso brotar.
```

### 3.8 Output 5 — the QA report (today, real)

```markdown
# QA report — Libertad

- Song file: `songs/libertad.json`
- Audio file: `songs/audio/Song Libertad.m4a`
- Model: faster-whisper `medium` (lang `es`)
- Generated: 2026-08-11T16:45:34
- Bands: HIGH 18 / REVIEW 2 / FAIL 0

## Needs attention

| line | band | canonical text | ASR context | start | end | dur | signals |
|------|------|----------------|-------------|-------|-----|-----|---------|
| 12 | REVIEW | Fui más impulso que voz, | Fui más impulsó que vos Fui fuego que | 55.88 | 59.52 | 3.64 | ambiguous |
| 19 | REVIEW | Elijo arder más. | arder más Soñando mi sombra en llamas | 84.96 | 106.10 | 21.14 | lead-fallback |

- Line 12: re-run with `--anchor 12=<seconds>` and `--words …` (candidate start was 55.88 s).
- Line 19: re-run with `--anchor 19=<seconds>` and `--words …` (candidate start was 84.96 s).

## All lines
… 20 rows …
```

**This report is the product.** It is currently a markdown file that dies in a staging folder.

### 3.9 Correction + promote

```bash
timeline-extractor extract "songs/audio/Song Libertad.m4a" songs/libertad.json \
  -o staging/libertad-anchored --lang es \
  --words staging/libertad/asr-words.jsonl --anchor 19=83.9   # 0.07 s

timeline-extractor promote staging/libertad-anchored/libertad-timeline.json songs/libertad.json
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
| **B13** | **Migrate the two existing timelines** — subtract `raw[0].start` from libertad and tragedia, write `leadIn` + `timelineVersion: 2` | Two files. Reversible; `.backup-*` already exists for both. Must ship in the same pass as B12. | S |
| **B3** | **Remove section-marker support** — delete the `{0,0}` exemption from `serializer.py::validate_timeline`; normaliser strips and reports meta lines | Jorge's ruling: CP format carries sung lines only. **Deletes code.** Verified: no song has a marker, so nothing breaks. | S |
| **B7** | Last-line `end` heuristic | Libertad line 19 runs 83.9 → 106.1 (22 s) because `end` falls back to the last transcribed word. Cap at max duration or audio end. | S |
| **B6** | `--lead` global offset knob | Whole-timeline nudge without re-anchoring line by line. | S |
| **B8** | Batch mode — N songs, one summary table | Ergonomics once the catalogue is >2 songs. Relevant as soon as the audio exists. | M |
| **B9** | Decide the canonical import path | `promote` writes `songs/*.json`; the A+ button patches the app's localStorage snapshot. Two destinations, nothing reconciles them. | S (decision) |
| **B10** | README with §1 positioning; repo public | The `/tramoya` page needs somewhere to point. | S |
| **B11** | `align` as primary verb, `extract` kept as alias | "Forced alignment" is the category word. Cosmetic; last. | S |

### Pregonero (live-lyric-translator) — implied by B12/B3

Separate repo, separate submodule. These must land **before** a v2 timeline is loaded into the app.

| ID | Item | Why |
|----|------|-----|
| **P1** | **Start-on-cue for Auto mode** — the first pedal press starts the timeline at line 0; from there it runs automatically | This is the whole point of normalising. A live intro can run any length; Jorge triggers the words when he actually sings them. |
| **P2** | **Apply `leadIn` in Video mode** — timeline offset by `leadIn.durationSec` from video start | The animation is the clock; the lead-in is fixed. |
| **P3** | **Reject/warn on missing or v1 `timelineVersion`** | Prevents a v1 file firing every line 7 s early with no error — exactly the silent-failure class B1 exists to kill. |
| **P4** | **Drop the marker exemption need** in `validateTimeline` / `parseTimelineFromJsonText` | Falls out of B3. Simplification, not a fix. |

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

**The actual blocker is audio.** `songs/masters/` holds **Ableton projects (`.als`)**, not bounced files. Only Libertad, Tragedia and Pimiento have audio in `songs/audio/`.

Realistic sequence:

1. **Bounce 7 Ableton projects** to `songs/audio/<slug>.m4a` — duelo, hasta-calmar-el-alma, luz-y-sal, no-te-voy-a-odiar, paso, soy-una-puerta, vidas. *This is the bottleneck, not Bombista.*
2. Run Bombista on those 7 + pimiento (audio already staged) → **8 songs timed**.
3. don-bonifacio, la-pajita, quien-fuera have neither audio nor an Ableton project — they cannot be timed until something is recorded.
4. Follow `songs/audio/README.md` convention on the way in (`<slug>/` or `<slug>.m4a`) — current naming is inconsistent (`Song Libertad.m4a`).

---

## 6. Claude Code kickoff

> Work in `projects/timeline-extractor`. Implement **B12, B13, B3, B1, B5, B2, B4** from `docs/bombista-product-backlog.md` — read that file first, especially §2 (architecture and timing model).
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
