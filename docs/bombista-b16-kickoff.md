# Bombista — B16 kickoff (`--emit html` review page)

**Written 2026-08-14 by the Cowork PM session. Revised the same day: B14 was dropped, this is now a single-item kickoff.**

Read `docs/bombista-product-backlog.md` first — §1 (positioning), the B16 row, the section **"Why B14 was dropped"**, and the four **Rules established 2026-08-14**. Rule 4 in particular: *Bombista answers "when," not "in which beat."*

## Context

- B13 is merged (PR #14); both shipped songs are v2. `migrate` exists.
- **B14 (fitting a BPM from the onsets) was dropped**, for two independent reasons: the abstraction is wrong (rule 4), and the measurement does not work (the onset fit declines on every song; autocorrelation is ±2–3%, failing rule 2). Do not implement it, and do not add tempo/BPM/meter inference to anything you build here.
- **The missing `tempo` blocks are typed in by hand by Jorge.** They are not an input to the tool. **Do not build a reader for them from any source** — in particular **no Ableton `.als` parsing, in any form** (proposed and rejected 2026-08-14). Per rule 5, Bombista's inputs are **the audio recordings and the lyrics JSON, and nothing else.**
- **Pregonero is being worked in parallel** in `projects/live-lyric-translator` (P5/P6/P9). Different repo, no shared files. **Commit and push inside this repo only. Do not bump the vault-root submodule pointer** — Jorge does that once.
- Jorge is bouncing 7 Ableton projects to `songs/audio/` meanwhile. When that lands, 8 songs get run through this tool in one sitting. **You are building the thing that makes that sitting short** — so this wants to be done before the batch.

---

# B16 — `--emit html`, a self-contained review page

**Chosen over building a Bombista GUI** (see the interface decision in the backlog). The CLI is not the friction. The friction is that judging a `REVIEW` line means *hearing* the audio at 55.88 s, which today means opening the m4a in something else and scrubbing.

Slots in beside `srt`/`lrc` as another writer in B2's architecture, reading the canonical CP form like the others. **No Electron, no second app, no packaging.**

## What the page has

- Every line, in order: index, canonical text, start/end, duration, band, signals.
- `REVIEW` and `FAIL` lines visually prominent — this is a **triage** view, not a table dump. The whole product claim in §1 is "check three lines instead of proofing forty"; the page should make those three obvious at a glance.
- **A play button per line that seeks the audio to that line's start.** This is the point of the item; everything else is decoration.
- The `--anchor` re-run command pre-written per flagged line, click-to-copy.
- The provenance block (B1) in the header: which audio file, which model, when. A review page that does not say what it reviewed is how the 17 s Tragedia error stayed invisible.

## Two hard constraints

**No network. No CDN.** Bombista running fully offline is a stated product property, protected deliberately in §1. A `<script src="https://...">` silently breaks it. **Vanilla HTML/CSS/JS, inline, no external anything.**

**Audio by relative path**, with the page written into the same staging directory as the rest of the run's output. Do not base64-embed by default — it bloats the file for no benefit when it lives next to the audio. If embedding is ever wanted for sharing, that is a later `--embed-audio` flag, not now.

## Out of scope — do not drift into these

- **Any tempo, BPM, beat or meter inference.** Dropped, deliberately. The page shows *times*.
- **A GUI.** Considered and declined; this page is the agreed answer.
- P5/P6/P9 — other repo, other agent.
- The rename (step 11), READMEs (B10), `_template.json` (B15).

## Acceptance

Run it on Libertad, open the file, click line 12's play button, hear the audio at 55.88 s. If that works the item is done.

## Standing constraints

- **Establish the real test baseline from the parent commit** before treating "tests green" as a gate.
- **Never weaken an assertion to hit a number.** If a test is wrong, say so and stop.
- Commit with the item ID (`B16`) in the message. Tests green before committing.
- Default behaviour with no new flags stays unchanged.

## Stop and report when

B16 is implemented, tested, committed and pushed on a branch, and you have opened the generated page on Libertad yourself and confirmed the per-line seek works.
