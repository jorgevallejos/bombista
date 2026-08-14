# Timeline v2 — the contract between Bombista and Pregonero

**Created 2026-08-13.** Canonical copy lives in `projects/bombista/docs/`; an identical copy sits in `projects/live-lyric-translator/docs/`. Spec rationale is in `projects/bombista/docs/bombista-product-backlog.md` §2.

Bombista and Pregonero are being built **in parallel, in separate sessions**. Neither may wait on the other. This file is the single shared truth: Bombista asserts it **produces** the fixture below; Pregonero asserts it **consumes** it. Do not invent your own shape — if something here is wrong or insufficient, stop and raise it with Jorge rather than diverging.

## Envelope

```json
{
  "timelineVersion": 2,
  "leadIn": { "durationSec": 7.26, "source": "measured", "confidence": "low", "apply": false },
  "timeline": [ { "start": 0.00, "end": 5.84 } ]
}
```

Exactly these three top-level keys. Nothing else goes in this envelope — provenance, confidence bands and the `_bombista` block live in the *rich* JSON and the report, never here.

### Producer vs consumer strictness (amended 2026-08-13, after Pregonero P3)

The producer rule and the consumer rule are deliberately different.

- **Bombista (producer) writes exactly these three keys.** Nothing more.
- **Pregonero (consumer) must IGNORE unknown top-level keys, not reject them.** This is a guarantee, not an accident: it means a future Bombista can add a field to the envelope without every older build of the app refusing the file. Be liberal in what you accept.
- **But a file that declares `timelineVersion: 2` and has no usable `timeline` array MUST be rejected**, not treated as a no-op. A file claiming to be a timeline while carrying no timeline is malformed — most likely truncated or half-written. Silently loading it makes the song look like it simply has no timings, which is precisely the silent-failure class this whole format exists to eliminate. Message: *"This timeline file is incomplete — it declares version 2 but contains no timeline."*

**Not the same case:** a song file with no `timeline` key **and** no `timelineVersion` is a perfectly normal un-timed song. It must keep loading untouched. That is the 11-song regression case.

| field | type | meaning |
|---|---|---|
| `timelineVersion` | `2` | Absent or any other value → **reject loudly.** Never coerce. |
| `leadIn.durationSec` | float ≥ 0 | Seconds of audio before the first sung word. |
| `leadIn.source` | `"measured"` \| `"manual"` \| `"none"` | `measured` = Bombista computed it; `manual` = a human overrode it. |
| `leadIn.confidence` | `"low"` \| `"high"` | Always `low` when `measured` — faster-whisper clamps the first sung word toward 0. |
| `leadIn.apply` | bool | `true` when the song has `media.type == "video"`, else `false`. Bombista sets the default; a human may flip it. |
| `timeline[]` | `{start, end}` | Entry *i* corresponds to `lyrics[i]`. **Entry 0 always starts at `0.00`.** Monotonic: `start[i] >= end[i-1]`. |

Lyrics arrays contain **sung lines only** — no section markers, no meta entries. Both tools reject anything else, naming the offending index.

## Rounding — read this before writing the losslessness test

All emitted values are **rounded to 2 decimals**. This is not cosmetic: `13.1 - 7.26 == 5.840000000000001` in IEEE floats, so a naive round-trip assertion fails.

- Bombista: `round(raw - leadIn, 2)` on write.
- The losslessness test asserts `abs((normalised + leadIn) - raw) < 0.005` per entry — **tolerance, not equality**.

## Playback semantics

The timeline is relative to a **start cue**. What provides the cue depends on the song; the file is identical either way.

| mode | cue | `leadIn.apply` |
|---|---|---|
| **Auto** (no animation) | the performer's first pedal press | `false` — a live intro can run any length |
| **Video** (animation is the clock) | video start **+** `leadIn.durationSec` | `true` — the lead-in is fixed by the media |

## Golden fixture — Libertad, 20 lines

Derived from the real accepted run of 2026-08-11 (`leadIn` 7.26 subtracted from every entry). **Bombista must produce exactly this; Pregonero must accept exactly this.** Copy it into each repo's fixture directory under your own naming conventions.

```json
{
  "timelineVersion": 2,
  "leadIn": { "durationSec": 7.26, "source": "measured", "confidence": "low", "apply": false },
  "timeline": [
    { "start": 0.00,  "end": 5.84 },
    { "start": 5.84,  "end": 9.64 },
    { "start": 9.64,  "end": 13.32 },
    { "start": 13.32, "end": 17.00 },
    { "start": 17.00, "end": 20.72 },
    { "start": 20.72, "end": 24.66 },
    { "start": 24.66, "end": 28.22 },
    { "start": 28.22, "end": 32.88 },
    { "start": 32.88, "end": 37.50 },
    { "start": 37.50, "end": 39.58 },
    { "start": 39.58, "end": 44.00 },
    { "start": 44.00, "end": 48.62 },
    { "start": 48.62, "end": 52.26 },
    { "start": 52.26, "end": 56.12 },
    { "start": 56.12, "end": 59.82 },
    { "start": 59.82, "end": 63.62 },
    { "start": 63.62, "end": 67.26 },
    { "start": 67.26, "end": 72.66 },
    { "start": 72.66, "end": 76.64 },
    { "start": 76.64, "end": 98.84 }
  ]
}
```

Raw values before normalisation, for the round-trip test: `7.26, 13.1, 16.9, 20.58, 24.26, 27.98, 31.92, 35.48, 40.14, 44.76, 46.84, 51.26, 55.88, 59.52, 63.38, 67.08, 70.88, 74.52, 79.92, 83.9, 106.1` (21 boundaries, 20 spans).

Line 19 spanning 22 s is real, not a bug — `end` falls back to the last transcribed word. Backlog item B7.

## Proving the round-trip — corrected 2026-08-13

An earlier acceptance criterion said *"after migration, Tragedia must behave on screen exactly as it does today."* **That was wrong and is withdrawn.** Tragedia's stored timeline is the known ~17 s-late one, produced from the wrong audio source. "Nothing moved" would only prove it is still wrong.

Two separate things were being conflated:

1. **Is the representation change lossless?** A maths property. Prove it against the golden fixture below, in unit tests, on both sides — no song playback involved. Bombista: `round(raw − leadIn, 2)` reproduces `raw` within 0.005 when the lead-in is added back. Pregonero: with `leadIn.apply == true`, the cue time for every line equals `normalised + leadIn.durationSec` within the same tolerance.
2. **Is Tragedia's data correct?** A separate, pre-existing defect. It is fixed by Bombista **re-extracting** Tragedia from audio pulled out of the animation video (`ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav`), not by anything Pregonero does. That is a later gate, after the parallel streams merge.

Do not block P2 on Tragedia. Prove (1) now; (2) is a data job for the Bombista stream.

## Rules while both streams are in flight

1. **Test against this fixture, not against the real song files.** `songs/libertad.json` and `songs/tragedia-de-cerdo-asado.json` are still v1 on disk and stay that way until the migration runs.
2. **Bombista stops before B13** (the data migration). Jorge runs it once both streams are merged and green.
3. **Neither session bumps the vault-root submodule pointer.** Commit and push inside your own repo only; Jorge bumps the umbrella once.
