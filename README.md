# Bombista

**You have a recording, and you have the text of what's said or sung in it. Bombista works out when each line happens — and tells you which lines it isn't sure about, so you check three instead of proofing forty.**

Bombista is not an automation tool. It is a **triage** tool.

Forced aligners already exist — [aeneas](https://github.com/readbeyond/aeneas), the [Montreal Forced Aligner](https://montreal-forced-aligner.readthedocs.io/), [whisperX](https://github.com/m-bain/whisperX) — and they all hand you timings with no opinion about them. So you either trust the lot or re-check the lot, and on a deadline you re-check the lot.

What Bombista adds is the **review loop**:

1. **Per-line confidence bands** — `HIGH` / `REVIEW` / `FAIL`, each with a *named reason*: `clean-anchor`, `ambiguous`, `lead-fallback`, `uncorroborated`, `gap-outlier`, `no-anchor`, `override`.
2. **A report that says which lines to check and why** — as markdown, as JSON, or as a self-contained HTML page with a play button per line that seeks the audio to that line's onset.
3. **A correction pass that re-runs in well under a second**, because the transcription is cached.

The claim that survives contact with a real deadline: *timings, plus triage, plus instant correction.*

## Who it's for

Nothing here is music-specific:

- anyone subtitling video
- lyric-video and karaoke makers
- accessibility captioning
- educators building synced read-along texts
- audiobook ↔ ebook sync
- **theatre surtitles** — this exact job, done today by opera houses with worse tools

## Runs offline

No API keys, no GPU, no network. [faster-whisper](https://github.com/SYSTRAN/faster-whisper) `medium` (~1.4 GB, cached locally on first use), CPU int8, roughly 50 s for a three-minute song on an M-series Mac.

This is a property worth protecting, and it is why **Bombista times but does not translate**. Turning one language into another needs a model with opinions about meaning; working out *when* a line happens does not. Structural conversion — plain text into the canonical JSON shape — is deterministic and stays in the tool. Linguistic translation is your business, with your own tools.

---

## Install

Bombista needs **Python 3.11 or newer** and expects to live in a virtual environment.

```bash
git clone https://github.com/jorgevallejos/bombista.git
cd bombista
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**The venv is not optional, and it is not relocatable.** Console-script shebangs bake in an absolute interpreter path, so moving or renaming the checkout after installing will break the `bombista` command with a bare `exit 127`. If that happens, delete `.venv` and repeat the three commands above — nothing else is lost.

Verify:

```bash
bombista --help
python -m pytest
```

If `bombista` is not on your PATH — an unactivated venv, a `pip install --user` — every command below also works as `python -m bombista.cli`.

---

## A worked example

You have a recording and its lyrics. You want to know when each line lands.

The song below — *Río de Sal*, twenty lines — is invented, and so are its
numbers; they are representative of a real run, not a transcript of one.

### 1. Align

```bash
bombista align audio/rio-de-sal.m4a lyrics/rio-de-sal.json -o staging/rio-de-sal --lang es
```

The lyrics input can be a **CP song JSON** or a **plain text file**, one line per line. In a text file, blank lines and `[Bracketed]` section labels are stripped — and *reported*, so the removal is visible rather than silent.

About 50 seconds later, one line of output:

```
HIGH 18 / REVIEW 2 / FAIL 0 — timeline: staging/rio-de-sal/rio-de-sal-timeline.json — report: staging/rio-de-sal/rio-de-sal-qa-report.md — words: staging/rio-de-sal/asr-words.jsonl
```

Eighteen lines Bombista is confident about. **Two to look at.** That number is the product.

### 2. Read the report

The QA report opens with the provenance of the run — which audio file, its sha256, the model, the language — then gets to the point:

```markdown
## Needs attention

| line | band | canonical text | ASR context | start | end | dur | signals |
|------|------|----------------|-------------|-------|-----|-----|---------|
| 12 | REVIEW | No soy la orilla, soy la sed, | No soy la orilla soy la se No soy el mar que | 61.35 | 64.88 | 3.53 | ambiguous |
| 19 | REVIEW | Vuelvo a empezar. | Vuelvo a empezar Contando faros en la niebla | 92.40 | 111.75 | 19.35 | lead-fallback |

- Line 12: re-run `align` with `--anchor 12=<seconds>` and `--words staging/rio-de-sal/asr-words.jsonl` to skip re-transcription (candidate start was 61.35 s).
```

`ambiguous` means the transcription heard something close to two different places. `lead-fallback` means the line's end had to fall back to the last transcribed word — which is why line 19 claims to run for 19 seconds.

To judge those two lines you need to *hear* them. Add `--emit html`:

```bash
bombista align audio/rio-de-sal.m4a lyrics/rio-de-sal.json -o staging/rio-de-sal \
  --lang es --emit html --words staging/rio-de-sal/asr-words.jsonl
```

That writes `rio-de-sal-review.html` — the same report as a page you open in a browser, with a play button on every row that seeks the audio to that line's onset, the `REVIEW` rows highlighted, and the fix command pre-written beside each one, click to copy. No server, no network, no build step.

### 3. Correct

Line 19 actually starts at 91.2 s. Pass it in, and reuse the cached transcription:

```bash
bombista align audio/rio-de-sal.m4a lyrics/rio-de-sal.json -o staging/rio-de-sal-fixed \
  --lang es --words staging/rio-de-sal/asr-words.jsonl --anchor 19=91.2
```

**0.07 seconds.** The expensive part was the transcription, and that is on disk. Correcting is free, so you correct until it is right instead of settling.

### 4. Apply

```bash
bombista promote staging/rio-de-sal-fixed/rio-de-sal-timeline.json lyrics/rio-de-sal.json
```

`promote` backs the file up next to itself, refuses on a line-count mismatch, warns loudly if the lyrics have changed since alignment, replaces **only** the timeline, and prints a per-line diff.

**Total: about four minutes, of which roughly ninety seconds is human attention on two lines out of twenty.**

---

## Other outputs

`--emit` is repeatable, and passing it **replaces** the default rather than adding to it:

| `--emit` | what you get |
|---|---|
| `timeline` *(default)* | the native envelope: `{ timelineVersion, leadIn, timeline }` |
| `songjson` | the full canonical song JSON with the timeline merged in |
| `report-json` | the QA report as data — bands, signals, provenance, per-line |
| `srt` | one subtitle file per language present |
| `lrc` | one lyric file per language present |
| `html` | the offline review page described above |

`asr-words.jsonl` and the markdown QA report are always written, whatever you ask for.

## The timeline

Bombista's native artifact is a **timeline**: an ordered list of `{start, end}` spans, matched to lines by position, containing no words.

```json
{
  "timelineVersion": 2,
  "leadIn": { "durationSec": 7.26, "source": "measured", "confidence": "low", "apply": false },
  "timeline": [
    { "start": 0.00,  "end": 5.84 },
    { "start": 5.84,  "end": 9.64 }
  ]
}
```

Two properties are worth knowing about.

**It is language-independent.** Retranslate every line into Dutch and the timings still hold. The words change; when they land does not.

**Entry 0 always starts at `0.00`.** The silence before the first word is banked separately in `leadIn` rather than folded into every timestamp. This is a correctness measure, not tidiness: the measured lead-in is the single least reliable number the tool produces — ASR has a known habit of clamping the first word toward zero — and isolating it keeps one uncertain value in one hand-editable field instead of contaminating all twenty.

Whether to *apply* the lead-in is the consumer's decision, never Bombista's. Bombista always measures, always normalises, always records.

The cost of matching lines by position is positional fragility: insert one line into the lyrics and every timestamp after it is silently wrong. `promote` guards against this with a hash over the lines, and warns when they no longer match.

## Commands

```
bombista align AUDIO SONG_JSON_OR_LYRICS_TXT -o STAGING_DIR
    [--lang es] [--model-size medium] [--anchor LINE=SECONDS]
    [--words STAGING/asr-words.jsonl] [--emit timeline|songjson|report-json|srt|lrc|html]

bombista promote STAGING/SONG-timeline.json SONG.json

bombista migrate SONG.json [--dry-run]
```

`extract` is a working alias for `align` — the original verb, kept so old commands still paste. `migrate` is a one-off for timelines produced before the `leadIn` model existed.

## Development

Strict red → green → refactor; tests green before every commit.

```bash
python -m pytest
```

All fast except one integration test that runs the tiny Whisper model against a committed 12-second fixture.

## License

MIT — see [LICENSE](LICENSE).

---

*Bombista is part of **Tramoya**, the stage machinery behind [Chango Pepper](https://changopepper.com). A bombista is the player of the bombo legüero, the drum that sets the pace for the ensemble. The repository was called `timeline-extractor` until August 2026.*
