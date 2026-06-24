# Output Contract — Timeline Extractor → Live Lyric Translator

_Frozen 2026-06-24. Source of truth: `projects/live-lyric-translator-dev/src/songState.ts`
and `projects/live-lyric-translator-dev/src/videoCueLookup.ts`. Do not modify this file
without also updating the translator side._

---

## `TimelineEntry` type (from `songState.ts:130–133`)

```typescript
export interface TimelineEntry {
  start: number   // seconds (non-negative float)
  end:   number   // seconds (non-negative float)
}
```

### Validation rules (from `validateTimeline`, `songState.ts:182–212`)

| Rule | Detail |
|------|--------|
| Length | `timeline.length === items.length` — one entry **per song item**, including section markers |
| Types | Both `start` and `end` must be `number` |
| Non-negative | `start >= 0` and `end >= 0` |
| Monotonic | `start[i] >= end[i-1]` (non-overlapping; gaps are allowed) |
| Zero-length entries | `start === end` never match in the cue lookup (they are "off" placeholders for section markers) |

### Parallel-array contract

The timeline array is **parallel to `items`** — one entry per `SongItem` (both lyric lines and
section markers). Section-marker entries conventionally have `start === end === 0` (zero-length,
never matched). The translator enforces `timeline.length === items.length` at import.

---

## Cue lookup logic (from `videoCueLookup.ts:10–16`)

```typescript
export function videoCueLookup(timeline: TimelineEntry[], songTime: number): number {
  for (let i = 0; i < timeline.length; i++) {
    const { start, end } = timeline[i]
    if (songTime >= start && songTime < end) return i
  }
  return -1
}
```

- Window is **half-open `[start, end)`**.
- `songTime` = `video.currentTime + media.offset` — computed by the caller, not embedded here.
- Returns `-1` when `songTime` is before all entries, in a gap, or past the last entry.

---

## Alignment knobs (from `subtitle-format.md` and `songState.ts:136–141`)

These live on the song's `media` block — **not** in the timeline array:

```typescript
export interface MediaFile {
  type:       'video' | 'audio'
  src:        string
  trimStart?: number  // seconds to skip at the beginning (skips blank lead-in)
  offset?:    number  // whole-song subtitle shift in seconds (post-trimStart)
}
```

`songTime = video.currentTime + media.offset`. `trimStart` is where playback begins; it is
applied as the initial seek target before the `play` command is sent. Neither field belongs
in the timeline itself.

---

## Interchange format (what this tool emits)

**Format: standalone JSON file** — a plain object with a `timeline` key.

```json
{
  "timeline": [
    { "start": 0.0,  "end": 0.0  },
    { "start": 4.1,  "end": 8.3  },
    { "start": 8.3,  "end": 12.7 }
  ]
}
```

### Rationale

- **JSON, not SRT** — SRT's timestamp granularity is milliseconds (fine), but it carries no
  concept of section-marker placeholders and requires a lossless re-mapping. A JSON `timeline`
  array maps 1:1 to `TimelineEntry[]` and is the format the translator's song files already use.
- **Standalone envelope (`{ "timeline": [...] }`)** — the A+ import button (Prompt 16) reads
  this file, extracts the `timeline` array, validates it against the song's item count, and
  writes it into the song JSON. The translator's `parseSongFile` then validates it on load.

> **⚠ Confirm with Prompt 16 implementer before shipping.** Prompt 16 (translator side,
> `docs/d-wire-triage-and-prompts.md`) says the button imports "a timeline JSON or SRT" but
> its parser isn't implemented yet. This tool assumes the JSON envelope above. Align before
> both sides ship.

---

## Complete example (3-item song: section marker + 2 lyric lines)

Song items:
```json
[
  { "type": "section", "label": "Verse 1" },
  { "languages": { "es": "Aquí llegan los mariachis" } },
  { "languages": { "es": "con su música y su fe" } }
]
```

Produced timeline file:
```json
{
  "timeline": [
    { "start": 0.0, "end": 0.0  },
    { "start": 4.1, "end": 8.3  },
    { "start": 8.3, "end": 12.7 }
  ]
}
```

Entry 0 is the section marker placeholder (zero-length → never matched by `videoCueLookup`).
Entries 1–2 are the two lyric-line cues.
