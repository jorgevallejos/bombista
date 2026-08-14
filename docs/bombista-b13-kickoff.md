# Bombista — B13 kickoff (timeline v2 data migration)

**Written 2026-08-14 by the Cowork PM session, after verifying repo state.** This is **step 4** of the ordered plan in `context/current-priorities.md`. Steps 2 and 3 are done: Pregonero PR #56 (`76f7a0e`, P1–P4) is merged to `main`, Bombista v2 is merged (PR #13, `d81a72d`), and the vault-root submodule pointer records both. Vault, Bombista and Pregonero are all in sync with their origins. **The gate is met.**

Read `docs/bombista-product-backlog.md` §2 and `docs/timeline-v2-contract.md` before touching anything.

---

## The task

Migrate the two existing v1 timelines in the **`songs/` submodule** to timeline v2: subtract `raw[0].start` from every entry, bank it in `leadIn`, stamp `timelineVersion: 2`.

Both songs are still v1 on disk, verified today. **No migration script exists — you are writing it, not just running it.**

## Two repos, and this matters

| what | where | who commits |
|---|---|---|
| the migration script + its tests | `projects/timeline-extractor` (submodule) | you |
| the migrated song files | **`songs/`** (a separate private submodule) | you, inside `songs/` |
| the vault-root pointer bumps for **both** submodules | `~/Chango Pepper` | **Jorge, once, at the end — do not touch it** |

Open at the vault root so both are reachable, but commit inside each submodule separately.

## Ground truth, measured today — use these as your test assertions

**`songs/libertad.json`** — 20 lyric lines, 20 timeline entries, `tempo` present, **no `media` key** → Auto mode.

```
before: timeline[0] = { "start": 7.26, "end": 13.1 }
after:  timeline[0] = { "start": 0.00, "end": 5.84 }
        leadIn = { "durationSec": 7.26, "source": "measured", "confidence": "low", "apply": false }
        timelineVersion = 2
```

This must match the golden fixture in `docs/timeline-v2-contract.md` **entry for entry, all 20**. Assert that, not just line 0.

**`songs/tragedia-de-cerdo-asado.json`** — 29 lyric lines, 29 timeline entries, `tempo` present, **`media.type == "video"`** → Video mode.

```
before: timeline[0] = { "start": 0.96, "end": 3.76 }
after:  timeline[0] = { "start": 0.00, "end": 2.80 }
        leadIn = { "durationSec": 0.96, "source": "measured", "confidence": "low", "apply": true }
        timelineVersion = 2
```

Note `apply: true` here and `false` for libertad — driven by `media.type == "video"`, exactly as B12 does it. Reuse B12's logic rather than reimplementing the rule; if it isn't already an importable function, make it one.

## Rules

- **Back up before writing.** Both files already have older `.backup-*` siblings (`libertad.json.backup-20260811-164840`, `tragedia-de-cerdo-asado.json.backup-20260703-112259`) — write **new** timestamped ones, don't overwrite those.
- **Round to 2 decimals on write** (`round(raw - leadIn, 2)`). Per the contract this is not cosmetic: `13.1 - 7.26 == 5.840000000000001`.
- **Losslessness is a tolerance assertion, not equality**: `abs((normalised + leadIn.durationSec) - raw) < 0.005` per entry. Test both songs.
- **Preserve everything else byte-for-byte** — key order, indentation, trailing newline, unicode escaping. A diff of the migrated file must show only `timeline`, plus the two added keys. Check the actual `git diff` before committing; don't assume your JSON writer round-trips cleanly.
- **Idempotent or refusing** — running it on an already-v2 file must not subtract twice. Refuse loudly, don't silently no-op the wrong way.
- **Assert monotonicity** after migration: `start[i] >= end[i-1]`, and `timeline[0].start == 0.00`.
- **Entry count must equal lyric count** on both songs (20 and 29). Refuse on mismatch.

## Before you start

Establish the real test baseline from the parent commit before treating "tests green" as a gate. **Never weaken an assertion to hit a number** — if a test is wrong, say so and stop.

## Commits

One commit per work item, item ID in the message. Tests green before each. In `songs/`, one commit for the migrated data referencing B13.

## Explicitly out of scope

- **Do not re-extract Tragedia.** Its stored timeline is the known **~17 s-late** one, produced from the wrong audio source. Migration faithfully migrates a wrong timeline — that is expected and correct. The fix is step 6 (re-extract from the animation's audio via `ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav`), a separate job. Do not let a "the numbers look wrong" instinct pull you into it.
- **Do not bump the vault-root submodule pointer.**
- **Do not implement P5–P8** (Pregonero, step 10) or B14.
- **Do not start the rename** (step 11).

## Stop and report when

Both songs are migrated, tests green, committed in both submodules and pushed. Then tell Jorge the two pointer bumps are waiting for him, and that the app `.dmg` (still the **1 July** build, which rejects v2) must be rebuilt with `npm run pack` before any testing — step 5.

---

### Nit spotted while verifying, not part of B13

`songs/_template.json` does not parse as JSON (fails at line 28, col 8) — presumably placeholders. Harmless today, but B5's reader would treat it as plain text if ever pointed at it. Worth a line in the backlog, not a fix here.
