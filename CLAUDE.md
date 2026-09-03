# CLAUDE.md — bombista

This file provides guidance to Claude Code when working in this repository.

## What This Tool Does

`bombista` (renamed from `timeline-extractor` on 2026-08-14) is a Python CLI that
derives a lyric/subtitle timeline for a song by
**forced-aligning its audio** (faster-whisper word timestamps + fuzzy line-anchoring) against
the song's ordered lyric lines, and writes the result as a JSON file consumed by the
**Live Lyric Translator**'s timeline-import surface. The tool **only defines the timeline** —
it never edits lyric text.

The live output contract is `docs/timeline-v2-contract.md` — shared with Pregonero, and
carrying the golden fixture both sides test against. Do not change the interchange format
without coordinating with the translator side. An earlier v1 spec covered the type derivation
and the `videoCueLookup` / `media.offset` background; it is superseded and removed — those
facts now live in this file (see "Relationship to Live Lyric Translator" below) and in
`timeline-v2-contract.md`, never in a separate v1 document.

> **The audio-clock rule (critical):** timeline times are only meaningful relative to the
> audio you feed in. For **Video-mode** songs, extract the audio from the linked animation
> video (`ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav`); for **Auto-mode** songs
> (no video), use the master recording. Feeding the wrong take produces a timeline that
> matches nothing — this is exactly the bug the 2026-07 ASR spike caught in the shipped
> Tragedia timeline.

## Commands

```bash
pip install -e ".[dev]"     # Install in editable mode with dev deps
python -m pytest            # Run all tests (includes one tiny-whisper integration test)
bombista --help             # CLI entry point
bombista --version          # `bombista <version>` — the SAME string that lands in
                            # a run's `toolVersion`, so a version quoted out of a
                            # song file and one read off the terminal compare directly

# The flow, front door to gate (round A closed both ends of it):
bombista new <song-id> [-o <song.json>] [--lang es] [--title TEXT]
#   ... an LLM session (or a human) writes the words into the skeleton ...
#   NOTE: `serve` no longer needs this door. Page 1 collects the general
#   information a `.txt` cannot carry (§11.15), so the browser flow goes
#   straight from words + recording to a complete song file.
bombista align <audio.wav> <song.json|lyrics.txt> -o <staging-dir> \
    [--model-size medium] [--lang es] [--anchor LINE=SECONDS] [--words <staging>/asr-words.jsonl] \
    [--emit timeline|songjson|report-json|srt|lrc|html]
bombista promote <staging>/<song>-timeline.json <song.json>
bombista validate <song.json> [--for-performance] [--lang es] [--media-dir DIR]...

# The three-step interface in a browser, on this machine only (B20):
bombista serve                                        # start at step 1
bombista serve <staging-dir> <song.json|lyrics.txt> [--audio <take>]  # boot into the review
#   Four options shape the run and the page without Bombista learning who
#   is calling — a directory, a file, a boolean, and nothing about a caller:
#     --staging DIR      where a page-1 run works, for a caller that will
#                        read the emitted <stem>.json back out
#     --browse-from DIR  where the file pickers open (default: home)
#     --song FILE        page 1 starts prefilled from it — what makes an
#                        edit an edit rather than a second new song
#     --no-header        do not draw the product header. The version goes
#                        with it (2026-09-03) and survives where Bombista
#                        is the whole window: the masthead, and --version

# One-off, for songs timed before timeline v2 (B13) — not part of the loop:
bombista migrate <song.json> [--dry-run]
```

The lyrics input may be a **CP song JSON or a plain text file** (one lyric line per line;
blank and `[Bracketed]` lines are stripped and reported). Either is normalised to a CP-shaped
song dict at the boundary before the pipeline runs — see `readers.py`.

`align` always writes `asr-words.jsonl` and `<song>-qa-report.md` into staging and **never
touches the song JSON**. `--emit` (repeatable, default `timeline`) picks which outputs join
them; passing it **replaces** the default set rather than adding to it. `--emit html` (B16)
writes `<song>-review.html` — the QA report as a self-contained offline page with a play
button per line that seeks the audio to that line's onset, so a REVIEW line can be judged by
ear instead of by scrubbing the m4a in another app. Review the QA report;
hand-fix REVIEW/FAIL lines by re-running with `--anchor <line>=<seconds>` (add `--words` to
skip re-transcription — it's near-instant). `promote` validates the candidate against the
timeline v2 contract, backs up the song JSON next to itself, and writes only
`timelineVersion`, `leadIn` and `timeline`.

`new` is the **front door**: it writes a canonical SP JSON skeleton that `validate` already
passes, so the step that used to be folklore — *a file appears, and that is the whole process* —
has a tool. **`tempo` and the timing keys are absent, not scaffolded**: a missing tempo is a real
state and a fake one is a bug that reaches a stage (`songs@c5adf65`), and a human starting a song
does not write timings.

**A RECORDING IS OPTIONAL** (§11.18, 2026-09-02). A song with words and no recording is a
legitimate song — it is performed by advancing the lines by hand — so `serve`'s page 1 lets you
through with the lyrics alone, there is nothing to align, step 2 is skipped and the flow lands on
step 3. Such a file carries **none of the five timing keys**, and `--for-performance` reports
`manual only: no timeline` and exits 0 rather than refusing it.

**A HALF-TYPED TEMPO REFUSES THE FILE, NOT THE RUN** (§11.22). Whole-or-nothing is unchanged, but
nothing in transcription or anchoring reads a tempo, so the run goes and every door that produces
the song file — `Save to the catalogue` and both JSON downloads — refuses. Page 1 says it at the
field, live, so nobody reaches the refusal.

`validate` is the **gate, and it asks two different questions**. The default asks *is this file
sane* and tolerates work in progress — a song fresh from `new` has no timeline and must still be
savable. `--for-performance` asks *which performance is this song ready for*: a timeline present and consistent with
the lyrics, and a declared `media` that resolves. **A missing `tempo` is a warning there, not a
failure** (pedal-driven mode works without one); a *partial* tempo block is a failure at both
levels. Every problem is listed, never just the first. **Playability is checked here and not in
Pregonero** — every rule lives inside one song file and needs no gig, and a second implementation
would be a second understanding of SP JSON.

`media.src` is a logical filename (Pregonero resolves it through a per-machine map), so
`--media-dir` is how `validate` is told where the file actually lives; the song file's own
directory is tried last, and a failure names every directory it looked in. **That makes the media
check necessarily partial and it must not be read as a guarantee:** *the media resolves* is a fact
about the machine the gate ran on and the directories it was handed, not about the song file. It
earns its keep because the machine that runs the gate is the machine that runs the gig — but a
pass says the file was found *here*, and nothing about anywhere else.

**Three things warn rather than fail at `--for-performance`**, and none of them is a fault: an
absent `tempo` (pedal-driven mode works without one), a `linesHash` that no longer matches the
lyrics (usually a corrected translation — `promote` warns rather than blocks and this keeps that
stance), and an absent `intro` (whatever projects it stands dark, which is correct behaviour).
All three are things to learn before a gig rather than at one. **`intro` is still not a required
field** at either level: `serve`'s from-scratch branch has no source for one, so requiring it
would make Bombista's own output fail Bombista's own gate.

`migrate` is the **one-off** for songs timed before v2 (B13): it rebases a *stored* v1
timeline in place, applying exactly what `align` applies to a fresh run. Both shipped
songs were migrated on 2026-08-14, so it should have nothing left to do — it refuses an
already-v2 song rather than subtracting the lead-in twice.

**Report times are raw audio-clock seconds; emitted timelines are cue-relative.** That is the
clock `--anchor LINE=SECONDS` is given in, and normalising the report would break the hand-fix
loop. SRT/LRC are absolute against their media, so they add the lead-in back when
`leadIn.apply` is true.

The faster-whisper `medium` model (~1.4 GB) is cached under `~/.cache/huggingface`; a full
song transcribes in ~50 s on this Mac (CPU int8).

## Architecture

```
bombista/
  models.py      — Word (ASR word + times), TimelineEntry (mirrors songState.ts)
  readers.py     — the boundary: CP song JSON or plain text → canonical CP song dict
                   + a _bombista block (completeness, filledLang, missing, strippedLines).
                   Structural only — stdlib, no network, no LLM. Bombista times; it
                   does not translate.
  aligner.py     — faster-whisper transcription → list[Word]; JSONL save/load, plus
                   the sibling `asr-words.meta.json` (B20 §11.10/§11.11): when the
                   machine listened, with which model, the ABSOLUTE path of the
                   take, and WHICH SONG it was made for (`song`, 2026-09-02).
                   Without that last one the sibling can only answer questions
                   about a folder, and it was asked one about a song — see
                   §11.19. The JSONL is bare records with no header and adding one
                   would break every reader, so the facts go beside it — in a file,
                   not an mtime, because an mtime does not survive a copy. This
                   module builds neither dict; provenance.py does
  anchoring.py   — pure, stdlib-only: fuzzy line-onset anchoring (forward-only) +
                   named-signal confidence bands (HIGH/REVIEW/FAIL); --anchor overrides,
                   including parse_anchor_overrides (LINE=SECONDS text -> the mapping
                   anchor_lines takes) — an anchoring concept, not a CLI one
  pipeline.py    — pure timeline building: anchors → TimelineEntry[] (end_i = next lyric
                   start, last line = last word end + 1.0 s pad, FAIL lines interpolated
                   so the candidate stays emittable) + normalize_to_lead_in
  provenance.py  — per-run audio identity (path, streamed sha256, duration, model, device,
                   lang, extractedAt, toolVersion) + linesHash over the canonical lines.
                   `tool_version()` is public because `--version` answers with it:
                   one resolution, one spelling, and the flag inherits the
                   pyproject fallback for a checkout never installed as a dist.
                   `extractedAt` is a claim about WHEN THE MACHINE LISTENED, so a
                   `--words` run — which §9.4 makes the correction loop, i.e. most
                   runs — carries it forward from the sibling instead of stamping
                   fresh, and OMITS it (with `wordsReused: true`) when there is no
                   sibling to read. Never an invented time, never an mtime.
                   `sha256`/`durationSec`/`audio` stay this run's own: it did hash
                   the file it was given, and those three describe one file
  report.py      — markdown QA report (per-line band, ASR context, signals, fix hints)
  serializer.py  — the frozen timeline v2 envelope, and nothing else
  skeleton.py    — round A: the canonical SP JSON skeleton `new` writes, in the
                   catalogue's key order (§10.2). `tempo` and the timing keys are
                   ABSENT, not scaffolded. The title is seeded from the song id and
                   is a seed — unlike a tempo, a wrong one is visible on sight
  validation.py  — round A: THE gate. Two levels (sane / finished), and it returns a
                   list of Findings rather than raising, because raising is a
                   first-failure interface and a person fixing a file wants all of it.
                   `validate_tempo` is the ONE understanding of a valid tempo block in
                   this repo — `bombista validate`, `POST /api/tempo` and the run route
                   all call it, so a partial block cannot get in through one door and
                   not the other. **Every tempo rule here is READ OFF THE RECEIVING
                   SIDE** (`pregonero/src/songState.ts` `validateTempo`) and not
                   reasoned about: `bpm` > 0, `numerator`/`denominator` WHOLE and > 0,
                   `countInBars` OPTIONAL and > 0 when present. `without_zero_count_in`
                   lives here too — `0` and absent both mean no count-in, so there is
                   ONE representation and it is absence, because the receiver refuses
                   a zero. tests/test_validation.py carries the receiver's accept/refuse
                   table; a divergence is a failing test rather than a walk.
                   THREE severities since 2026-09-02: ERROR, WARNING and MODE.
                   A MODE is a PROPERTY of the song, not a problem — `manual
                   only: no timeline` — so it never fails a gate and it joins
                   the HEADLINE rather than the list, because it says which
                   performance the verdict is about. A song with no timeline
                   is performed by hand, which is a normal night; refusing it
                   was the gate answering a question nobody asked.
                   Pure, stdlib-only, prints nothing
  writers.py     — everything downstream of the canonical CP form: songjson, report-json,
                   srt, lrc, html — plus merge_envelope, THE one merge path (shared with
                   promote). The html writer (B16) is the offline review page: inline CSS/JS
                   only, audio by relative path, play buttons in RAW audio-clock seconds
  migrate.py     — B13: rebase a stored v1 timeline onto the v2 start cue. Adds no rules
                   of its own (it composes normalize_to_lead_in / to_dict / merge_envelope)
                   — what it owns is the refusal set. Idempotent by refusal, not no-op.
  songfile.py    — back_up_and_replace (THE one song-write path: backup, scratch file,
                   os.replace — never a half-stamped song on disk) + timeline_diff.
                   Shared by promote and migrate; returns its lines, prints nothing
  promotion.py   — promote_candidate: the whole promote flow as a callable.
                   **A CANDIDATE WITH NO TIMELINE IS ACCEPTED** (§11.21,
                   2026-09-02) and creates the song without one: a manual song
                   is a complete song. `carries_a_timeline` is the rule —
                   NONE of the three envelope keys is a manual song, ANY of
                   them demands all three and a valid v2 envelope. Absence is
                   a state; incompleteness is a fault. The one refusal it adds
                   is a candidate with no timeline over a song that HAS one:
                   writing nothing leaves timings the person thinks they
                   removed, writing an empty envelope destroys a measured
                   timeline, and neither is what the candidate said — load the
                   candidate, extract + validate the v2 envelope, run B4's linesHash
                   guard, refuse a partial candidate over a complete target, merge,
                   write. Raises ValueError; `note` is a callback so a warning is
                   delivered before any refusal that follows it. B20 §2: `serve` must
                   promote what `promote` promotes, so there is one flow, not two
  pages.py       — B20: the HTML `serve` returns — pages 1 (input), 1.5 (processing),
                   2 (review) and 3 (output), the masthead and the step bar. Page 2's
                   ROWS are rendered here too, not in the page's JavaScript: one
                   template, which the page fetches back after a re-anchor rather than
                   keeping a second copy of. Line 0 is an ordinary row — no special
                   colour, no lead-in label, no popup caption, and no lead-in control
                   anywhere (§8.6). Page 2's provenance is ONE QUIET LINE — song,
                   media file NAME (never the path), model, lead-in — and nothing
                   else; sha256, device, toolVersion, extractedAt and duration are
                   filed in <stem>-report.json, which is the audit artifact (§8.2).
                   Page 1 carries the SONG BLOCK (§11.15, step 6): title,
                   artist, notes and the tempo, hidden until a lyrics file is
                   chosen and prefilled from an SP JSON. It is the metadata a
                   `.txt` cannot carry. NO TITLE TRANSLATIONS (§11.16):
                   translation is not Bombista's concern — the file already
                   carries it and nothing here asks. The tempo control lives
                   HERE and nowhere else, and it is THREE controls, not four
                   number fields (§11.16): a felt pulse in bpm, a time
                   signature from TIME_SIGNATURES, and bars before the first
                   line, with a TAP button beside the pulse and the chosen take
                   playable, because nobody counts beats for a minute and tapping
                   is the only method that yields the FELT pulse. TAPPING SETTLES
                   ON HALVES and a TYPED value stays free: a hand cannot resolve
                   a hundredth of a bpm, but `66.67` typed from the source is
                   exact and rounding it to `67` is drift a long song will show.
                   Page 2 ROUNDS THE DISPLAY AND NEVER THE VALUE — a tenth in the
                   list, hundredths in the popup, which is the instrument. The
                   0.05 stepper is unchanged: invariant 2 forbids a control
                   coarser than the 0.07 s correction loop.
                   `numerator`/`denominator` are the format's business,
                   split at the boundary, never a question put to a musician.
                   NO Set button: the block travels with `Process song →` and
                   the run route refuses the whole run. Nothing derives,
                   measures or guesses; the one proposed value is 0 bars, and
                   it never makes a block alone. Page 3 carries `Save to the
                   catalogue` ABOVE the three downloads — it is the ending of
                   the flow and they are an escape hatch — the one control
                   here that writes a file, with the path it will write
                   printed under it.
                   THE FILE PICKER IS THE ONE SURFACE WITH NO VOICE (§11.16):
                   a plain dialog — path, list, Cancel and Choose — because a
                   file dialog is where a person expects their system's own
                   furniture. It is the only place the skin's no-radius rule
                   is relaxed, and a test scopes the exception to `.picker`.
                   EVERY CLASS IT APPLIES IS PREFIXED (`pickgo`, not `go`) and
                   a test enforces it: the dialog is built in JavaScript, where
                   nothing shows you the page's other class names, and
                   `class="go"` silently inherited page 1's `margin: 1.5rem 0 0`.
                   A PAGE'S SCRIPT AND ITS MARKUP ARE ONE ARTIFACT: a test
                   fails when a script reaches for an id the page does not
                   render. That is what `v1.2.0` broke — moving the tempo
                   control off page 2 left its wiring, the script threw, and
                   `Confirm timeline` never got its listener.
                   THE STEP BAR IS PINNED AND NOTHING ELSE IS (§11.24): a
                   full-width `.stepband` sticks at top 0 — the BAND, because
                   `.steps` is `width: max-content` and the page would scroll
                   through the gap beside it. The masthead scrolls away, so
                   standalone ends with the same single fixed band the
                   embedded case has. Page 2's player docks at `--stepband`,
                   which is DERIVED from the band's own declarations rather
                   than copied. A test asserts the complete set of sticky
                   rules, not just the one added.
                   String composition,
                   stdlib only, inline CSS/JS, no build step, NO WEBFONT. STYLESHEET is
                   the whole of §10.3's skin and is defined ONCE — page 2 inherits it
                   rather than being retrofitted. §10.1's vocabulary is enforced by
                   tests: no "align"/"alignment"/"emit"/"CP JSON" in a user-facing
                   string, the masthead's own tagline excepted
  server.py      — B20: `serve`'s process, the pages, and the JSON routes.
                   ThreadingHTTPServer on 127.0.0.1 ONLY (invariant 7 — the host is
                   an explicit argument that refuses every other value). Holds one
                   Session (lines, words, QA state of a previous `align`) and answers
                   GET /api/session, POST /api/reanchor, POST /api/emit, POST
                   /api/tempo. The tempo route and the run route both defer
                   entirely to validation.validate_tempo through
                   `normalise_tempo` — server.py must never judge a bpm,
                   numerator, denominator or countInBars itself, and a test pins
                   that by AST rather than by grep. `/api/run` also carries page
                   1's `info` (title, artist, notes, title_translations), which
                   `_place_info` applies: absent means the song was never asked
                   and passes through byte for byte, a posted empty field clears
                   the key, and a language the page did not offer is left alone.
                   `answers_so_far` is what makes THE STEP BAR NAVIGATION
                   RATHER THAN A RESET (§11.23): page 1 rendered empty
                   whatever the session held, which discarded everything
                   typed and made the tempo backstop a wall — the refusal
                   says to finish the tempo on page 1 and page 1 threw the
                   half-typed one away. Nothing new is stored; the session
                   already held all of it and the page never asked.
                   `previous_take` answers WHICH RECORDING THIS SONG was
                   aligned against, and the emphasis is the bug (§11.19): it
                   read the staging directory's meta with no reference to the
                   song, so a shared staging directory handed every song the
                   last one's take — a `.txt` arrived with a recording, the
                   consent popup was skipped and one song's words were
                   anchored against another's audio. A `.txt` now gets
                   nothing, `media.src` comes first, and the meta records
                   `song` so it can be asked about a song rather than a
                   folder. The transcription cache is checked the same way:
                   reused only when the meta names THIS run's take.
                   `default_out_path` is THE answer to where a write with no path
                   of its own lands — page 3 names it and /api/emit writes it, so
                   the promise and the write cannot disagree. Imports
                   NOTHING from cli.py (invariant 1): it calls the same extracted
                   anchoring/pipeline/merge the CLI calls, so the two cannot drift.
                   An override RE-ANCHORS — there is no code here that adds an offset
                   to anything. Also owns the run (transcribe -> anchor, cancellable),
                   the loopback file-browse route (the server needs a real path; a
                   browser File object has none), the three downloads, which hand
                   over bytes and write nothing, and the audio route page 2 plays
                   from (ranges honoured — a transport that cannot seek cannot judge
                   a line by ear). The take is resolved in a FIXED ORDER, each step
                   reached only when the one above yields nothing: --audio, the
                   absolute path in asr-words.meta.json, the run's recorded relative
                   path, then a loud failure. NEVER another file — a player that
                   silently plays the wrong take makes every judgement made against
                   it wrong (§11.11). NO line is refused: line 0 moves like any other
                   and `leadIn.source` says `manual` when a human set it (§8.6)
  cli.py         — click CLI: new / align / promote / validate / migrate / serve, and
                   nothing else. Wiring only:
                   options, help text, and translating ValueError into ClickException /
                   BadParameter. `extract` is a registered alias of `align` (B11) — the
                   same Command object, so the two cannot drift
tests/           — all fast except one tiny-model integration test on a
                   committed 12 s fixture (tests/fixtures/). The `serve` acceptance
                   case runs in two tiers (B20 §11.3): a committed synthetic 19-line
                   fixture in CI, and the pimiento canary opt-in behind
                   BOMBISTA_CANARY_SONG / BOMBISTA_CANARY_STAGING, which skip with
                   those names in the message. NO song lyrics, no real
                   asr-words.jsonl and no audio are committed here — this repo ships
                   as `pipx install bombista`
docs/
  timeline-v2-contract.md           — THE live contract with the translator (Pregonero).
                                      Shared, amended by either side; do not diverge from it.
  acceptance-tragedia-2026-07-03.md — v1 acceptance record (calibration + promote diff)
  bombista-product-backlog.md       — the v2 spec (§2 is the architecture and timing model)
  bombista-serve-spec.md            — B20: `bombista serve`, the local web interface.
                                      Absorbs B19. §2 is the step-0 extraction that must
                                      land before any of it is built
  assignment-qa-design.md           — SUPERSEDED video-OCR design (banner explains what carried over)
```

The parked video-OCR track lives on origin branches `feat/lift-spike` and `feat/dp-alignment`
(unmerged, do not delete, do not merge).

## Development Protocol (TDD)

Strict **Red → Green → Refactor** for every change:

1. **Restate** the expected behavior in testable form.
2. **Write failing tests** (don't touch production code until tests fail for the right reason).
3. **Make the smallest implementation change** to turn tests green.
4. **Only then refactor** — must not change behavior.
5. **Commit only when tests are green.**

Prefer behavior tests over implementation-detail tests. Anchoring/pipeline logic is pure and
stdlib-only by design — test it with synthetic `Word` lists, never with the whisper model.

## Commit / PR Flow

- **Conventional Commits**: `<type>(<scope>): <subject>` — types: `feat`, `fix`, `refactor`,
  `docs`, `test`, `chore`.
- Feature branches only — never commit directly to `main`. **Always pass `--base main` to
  `gh pr create`** (a PR without it once merged into the wrong branch; the GitHub default
  branch is now `main`, but be explicit).
- Use `/release` to package and ship validated work.
- Each PR covers one logical change; merge and pull `main` before starting the next.

## Output Contract (summary — timeline v2)

- The emitted envelope has **exactly three top-level keys**:
  `{ "timelineVersion": 2, "leadIn": {…}, "timeline": [{start, end}] }`.
  Provenance, confidence bands and `_bombista` live in the rich JSON and the report —
  **never** in this envelope.
- `TimelineEntry = { start: float, end: float }` — half-open `[start, end)`, rounded to
  2 decimals. Entry *i* corresponds to `lyrics[i]`; **entry 0 always starts at `0.00`**.
- Times are **relative to a start cue**, not to the audio file. `raw[0].start` is banked in
  `leadIn: { durationSec, source, confidence, apply }`. Bombista always measures, always
  normalises, always records — **it is never told whether to apply the lead-in.** That is a
  playback decision: video start + lead-in for Video mode, the performer's pedal press for
  Auto mode.
- `leadIn.apply` defaults to `true` when the song has `media.type == "video"`, else `false`.
- Lyrics arrays carry **sung lines only** — no section markers, no meta entries. A non-lyric
  entry fails loudly, naming its index. `bombista validate` is where that is checked before a
  run rather than during one.
- **`tempo` is written whole — `bpm`, `numerator`, `denominator`, `countInBars` — or not at
  all** (serve-spec §11.5, checked against Pregonero: `beatScheduler.ts` needs `numerator` and
  `denominator` and does `numerator % 3`, so a bpm-only block gives a broken pulse and correct
  scaling with no error anywhere). Absence is safe — no pulse, no count-in, scale pinned to 1 —
  which is why a missing block is a warning and a partial one is a failure.
- Rounding matters: assert losslessness with a **tolerance** (`< 0.005`), not equality —
  `13.1 - 7.26 == 5.840000000000001` in IEEE floats.
- Alignment knobs (`offset`, `trimStart`) live on the song's `media` block — not here.
- **`docs/timeline-v2-contract.md` is the live contract** and carries the golden fixture both
  sides test against — the only interface spec in this repo.

## Relationship to Live Lyric Translator

- Consumer: `projects/pregonero/` — `TimelineEntry` type lives in
  `src/songState.ts`; cue lookup is `videoCueLookup` in `src/videoCueLookup.ts`.
- Song JSONs live in `~/Chango Pepper/songs/`; linked animation videos in
  `~/Chango Pepper/animations/<song-id>/`.
- Do not import or duplicate translator code here; `docs/timeline-v2-contract.md` is the bridge.
