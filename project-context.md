# Project Context — Bombista

_Project-specific Cowork context. Read this **after** `~/Chango Pepper/personal-context.md` (and any relevant `~/Chango Pepper/disciplines/<topic>.md`). Acknowledge briefly ("Context loaded. Ready.") and wait for Jorge to describe what's on his plate. At the end of the session, propose updates if anything important changed._

> Spun out of the Live Lyric Translator (now Pregonero) D-wire round in June 2026. The engineering counterpart for Claude Code lives in `CLAUDE.md` at the repo root (`projects/bombista/CLAUDE.md`). This file is the reasoning record; `docs/bombista-product-backlog.md` and `docs/bombista-serve-spec.md` hold the detailed specs.

---

## What this project is

**Bombista** is a **forced-alignment triage tool**, part of the **Tramoya** suite: give it a recording and the text of what's sung in it, and it works out when each line happens — and tells you which lines it isn't sure about, so you check three instead of proofing forty.

It is deliberately **not** an automation tool. Forced aligners already exist (aeneas, Montreal Forced Aligner, whisperX) and hand back timings with no opinion about them, so on a deadline you either trust the lot or re-check the lot. What Bombista adds is the review loop: per-line confidence bands (`HIGH` / `REVIEW` / `FAIL`) with named reasons (`clean-anchor`, `ambiguous`, `lead-fallback`, `uncorroborated`, `gap-outlier`, `no-anchor`, `override`); a report that says which lines to check and why; and a correction pass that re-runs in about 0.07 s because the transcription is cached.

Runs entirely **offline** — no API keys, no GPU, no network — via faster-whisper `medium` (~1.4 GB, CPU int8, ~50 s per song). This is a property worth protecting; see "Design boundaries" below.

**Positioned generically** (no Chango Pepper specifics in the tool itself): subtitling video, lyric-video and karaoke makers, accessibility captioning, educators building synced read-along texts, audiobook↔ebook sync, and — fittingly for the suite name — theatre surtitles, which is this exact job done by opera houses with worse tools. Output feeds **Pregonero**'s timeline import.

**The design property worth naming: the timeline is language-independent.** Bombista's native artifact is an ordered list of `{start, end}` spans, matched to lines by position, containing no words. Retranslate every line into Dutch and the timings still hold — the words change, when they land does not. This is precisely why it feeds a translation-aware performance tool well. Its cost is positional fragility: insert one line into the lyrics and every timestamp after it is silently wrong — this is exactly what the `linesHash` guard (B4) exists to catch.

## Why it's a separate project (not in the translator repo)

Deriving a timeline from a recording is a real subsystem (transcription, alignment, confidence scoring, a review/QA loop) with its own dependencies and failure modes. Bundling it into the Electron app would bloat the app and mix concerns. Keeping it standalone lets it run as a CLI/local-web tool and be wrapped into the app later (or invoked by it) once it's proven. Decided 2026-06-24.

## Design boundaries — what Bombista will not do

These were tested against real proposals and hold as rules, established 2026-08-14:

1. **No `tempo` block → no Auto mode.** Tempo is a prerequisite in Pregonero, not a nicety, and it is never derived. It is **supplied by the performer** (for the Chango Pepper catalogue, by Jorge, who is the source of record) and typed in by hand. *Amended in round A of the Tramoya integration, and again at step 6:* the typing now happens **in Bombista**, on `serve`'s page 1, with the rest of the song's general information — see "Bombista became the place a tempo is typed" below. Never derived is unchanged; where a human types it is what moved.
2. **The pulse and the timeline are separate clocks.** A constant offset between them is fine; what must match is the *rate*, so any shift stays consistent instead of accumulating.
3. **The timeline measures the recording; the performance is a playback-side transform.** Anything describing how a song is played on a given night — lead-in application, performed tempo — is applied by Pregonero at playback and never written back over the measured values. Bombista measures and records; the consumer decides.
4. **Bombista answers "when," not "in which beat."** Its output is time: line *i* happens at *t*. Tempo, meter and any other musical structure are performer-owned metadata, entered by a human and consumed by Pregonero — never inferred from the timings.
5. **Bombista's inputs are the audio recordings and the lyrics JSON. Nothing else.** No DAW project files of any kind, no session metadata, no third source of truth. If a fact is not in the audio or the lyrics, it is not Bombista's to know — a human supplies it.

**Why B14 (derive BPM from the aligned onsets) was rejected, 2026-08-14 — read before proposing anything like it again.** A timestamp is a fact about time; tempo and meter are a musical interpretation layered on top of time, owned by the performer, and pulling them back down into the timing tool mixes two levels of abstraction the suite otherwise keeps clean. The tell: making the feature safe would have required guarding against problems it invented (octave ambiguity, meter judgment calls no signal-processing result can supply) — elaborate guardrails around a derived value are evidence the value should not be derived here. The premise also failed numerically: an onset fit would decline to propose on every song in the catalogue, and the obvious fallback (audio autocorrelation) lands at ±2–3%, 1.5–4.4 s of drift across a song. Two independent reasons to drop it, and neither is "not built yet." **Tempo is data Jorge supplies and types in by hand** — a data-entry task, not a build, and explicitly **no DAW project reader, ever.**

## Proposed direction (unbuilt, undecided) — an orchestrator over Bombista's confidence output

*Folded in 2026-08-20 from a retired separate project. Working name during that project was
**Apuntador** — a candidate never confirmed, not a name of record. This section is durable design
thinking only: nothing below is decided, scheduled, or built, and no dates here mark progress.*

**The core idea.** A second tool, separate from Bombista and calling it rather than modifying it,
that does the judgment work Bombista deliberately refuses: reads a confidence report, decides which
flagged lines are actually wrong, and proposes a correction. It would never write to a song file and
would never produce the sign-off — the human still presses Bombista's own download, which is the
structural moment that certifies a timeline. Its entire action surface, as proposed, is expressible
as a list of `--anchor LINE=SECONDS` flags plus a reason in prose: nothing it produces could not
already be typed by hand.

**Why this stayed a separate tool rather than a Bombista feature.** Bombista's own boundaries (above)
already settle this: it is a triage tool, not an automation tool, and "receives a file, returns a
file, does not change the state of one" is the property the whole suite rests on. Deciding which
flagged line is actually wrong is judgment, not measurement — the same category of thing rule 4
("Bombista answers 'when,' not 'in which beat'") and the B14 rejection (tempo is a musical
interpretation layered on top of a timestamp, not a fact recoverable from one) already refuse to pull
into Bombista itself. An orchestrator that did this work would sit in its own tool, call Bombista's
existing CLI/flags, and leave Bombista's own repo at zero commits from the work — consistent with,
not an exception to, the design boundaries above.

**Also proposed to double as a rehearsal for Corilus.** The autonomy ladder, the proposes-never-
decides rule, confidence as a first-class output, and evals as the thing that decides whether it
works all have a direct twin in `projects/corilus-onboarding/strategic-brief.md`. The rationale for
doing this here first, if it is ever done: solo, reversible, with a real corpus and no regulator,
before arriving at Corilus having only read about these mechanisms rather than built one.

**Seven open questions — none decided.** These were the deliverables of a design session that never
produced them:
1. Name — "Apuntador" was the leading candidate, never confirmed; alternatives raised were
   Traspunte and Utilero.
2. The one-sentence purpose.
3. The autonomy ceiling, with reasoning — the proposed answer, to argue with rather than accept, was
   rung 2 ("draft — prepares, you approve") and never higher, on the reasoning that Bombista's own
   download is the sign-off and the agent must be structurally unable to press it.
4. The "must never" list — candidates raised: never writes to a song file (inherited), never
   produces the sign-off, never re-implements alignment or confidence banding, never proposes
   anything not expressible as an existing Bombista flag, never derives tempo, never translates.
5. The proposal object — its fields, what evidence it may read (word-level timings, the six
   signals and their glosses, full lyric text, neighbour spacing; whether it may hear the audio at
   all was left open), and what makes a reason legitimate (must point at evidence, not intuition).
6. The eval — three candidate metrics (accuracy, harm rate, calibration), explicitly not
   band-improvement (rejected as trivially gameable), plus a candidate acceptance canary on the
   Luz y Sal 47-second line.
7. Local model or hosted API — flagged as the same data-residency question Corilus will ask, at a
   fraction of the stakes, with the added concern that a hosted call would cost the Tramoya suite its
   "offline" property.

**Status: proposed only.** No code exists, no session has produced answers to the seven questions
above, and nothing here is a plan of record. If this is ever picked up, `context/current-priorities.md`
gets a row and this section stops being the only place it's described.

## How it works (method)

The shipped method (forced alignment, adopted 2026-07-03 — see "History" below for how it got here):

1. **Input:** an audio recording (or a video's audio track) + the song's ordered lyric lines.
2. **Transcription:** faster-whisper `medium` transcribes the whole recording with word-level timestamps.
3. **Anchoring:** a forward-only fuzzy match anchors each line's opening tokens against the word stream — the scan position only ever advances, so a hand correction re-derives every following line by re-matching against the audio rather than by a rigid arithmetic shift. This is deliberate: a ripple/delta shift would displace lines that were measured correctly. **Never implement a ripple.**
4. **Confidence banding:** each line gets `HIGH` / `REVIEW` / `FAIL` with a named signal, plus a QA report that says which lines to check and why.
5. **Correction:** `--anchor <line>=<seconds>` (CLI) re-anchors from that point using the cached transcription (`--words`), so a fix costs ~0.07 s, not another 50-second run. `bombista serve` (below) puts this loop in a page instead of a shell command.
6. **Output:** `align` stages a timeline (never writing the input); `promote` merges it into the target song JSON (backup + diff, touches only the timing keys).

**Time cost of filling in a missing timeline, as observed:** roughly fifteen minutes per song, start
to finish through align, review and promote. This is the number behind "missing timelines are work,
not a blocker" (Jorge).

## The review loop, and why `bombista serve` exists

**Interface decision, 2026-08-14 — no dedicated Bombista GUI, at first.** Considered and declined: Bombista was expected to run only a handful of times over a couple of weeks and then go quiet, and a real GUI only pays off if the generic positioning above (theatre surtitles, captioning, karaoke) is a bet actually being placed. The friction was never the CLI — it's that judging a `REVIEW` line means *hearing* the audio at a candidate timestamp, which meant opening the file elsewhere and scrubbing. **`--emit html` (B16)** captured most of that value cheaply: one offline, self-contained review page with the audio embedded, a seek-and-play button per line, and the `--anchor` command pre-written beside each flagged line — no Electron, no packaging, no second app. A third option — building the timing UI *inside* Pregonero, which already has the library, the audio and an Electron shell — was named and rejected: it fuses two stations the Tramoya framing keeps separable, and drags Bombista's language-independence into an app that is entirely about language.

**The pimiento canary is what closed the gap B16 left open.** Jorge ran Bombista by hand on the real `pimiento.json` + its audio, 2026-08-15: alignment was fine (18 of 19 lines `HIGH`, none failed), but he had no way to *act* on the one flagged line — the report told him which line and why, not how to judge and fix it in the same place. He promoted the timeline with that line still unresolved. **That gap — a correction loop that identifies but cannot resolve — is the entire reason `bombista serve` (B20) exists.** It is not a reversal of the no-GUI decision; every option that decision rejected (a hosted service, a second aligner, Electron/packaging) is still rejected. What B20 adds is the B16 shape carried one step further: a flag on the existing CLI serving stdlib HTTP on `127.0.0.1`, so a correction can be *applied* in the page instead of judged in a browser and retyped as a shell command. The first public release ended up gated on two things: `serve` shipping, and pimiento's flagged line being fixable through it, not merely identifiable.

**What `serve` is not, and must never become** (bound to `127.0.0.1` explicitly, never `0.0.0.0`):
- **Not a hosted service on changopepper.com.** Holding other people's audio is a legal posture Jorge doesn't want, and it would make him a data controller — nothing leaves the machine, so the question doesn't arise rather than being answered.
- **Not a second aligner** (no WASM/transformers.js reimplementation). Two implementations of the confidence banding would drift, and the report's trustworthiness is the entire product; the real quality bar (`--model-size medium`) doesn't fit in a browser anyway.
- **Not Electron, not a packaged app, not a second codebase.** It's a flag on the existing CLI serving HTML with the stdlib.
- **Not a place tempo gets derived** — design boundary rules 4 and 5 stand inside `serve` exactly as they do in the CLI.

**Design decisions worth carrying forward:**
- **A correction re-anchors; it never ripples.** Same rule as the CLI's `--anchor` (see "How it works" above) — edits below a correction re-derive against the audio, lines above stay untouched.
- **Line 0 is not special, settled 2026-08-16.** It gets the same control as any other line. The normaliser banks its onset into `leadIn` and writes entry 0 as `0.00` at emit time regardless of how the value got there — the v2 contract is enforced by the normaliser, not by refusing the edit. *Lead-in* is a performance concept, meaningful the moment someone counts a band in; that distinction belongs to Pregonero at performance time, not to a timing tool.
- **The Song Performance JSON (SP JSON) is not a new format — it is `songs/*.json`, named.** An early pass invented a shape from scratch; Jorge caught it ("not connected at all") and the fix wasn't a tweak, it was recognising the existing Chango Pepper song format already carried everything needed. Bombista owns five keys and passes everything else through byte-for-byte: `linesHash`, `timelineSignedOff`, `timelineVersion`, `leadIn`, `timeline`. **`tempo` is a sixth, and it is different in kind:** the other five are measurements, and `tempo` is the one value Bombista takes *from the performer* rather than from the audio (round A — see below). Never computed, never guessed, and **omitted rather than null-scaffolded** when not given (a null is not neutral once a consumer reads it — Pregonero already degrades safely on absence: no pulse, no count-in, scale pinned to 1).
- **B21 — both the stepper and a typed value, not either.** The stepper alone doesn't scale: pimiento's error was 1.22 s (24 presses), but Luz y Sal produced a 47 s one (~940 presses). Found by using the tool, not by building it — an unrecognised phrase leaves a line with nothing to anchor to, so an unbounded landing is not the rare case it first looked like.
- **B22 — withdrawn.** A plan to drop the `.sp` suffix from the download's filename was superseded by a cleaner rule, Jorge's: *"Bombista doesn't change the state of a file, it receives one and returns another."* The returned file already carries every original field plus the five timing keys, so the vault file **is** the returned file — replacing the old one with the download is the entire procedure, and the extension question dissolves rather than needing a decision.

## Bombista became the place a tempo is typed (round A, 2026-08-24)

**What changed, and it is narrow.** A tempo control existed on `serve`'s page 1 and was removed on
2026-08-16 (serve-spec §11.5), leaving the note *"Tempo is not Bombista's business."* Round A of the
Tramoya integration puts a control back — on **page 2, the review** — because Pregonero loses tempo
ownership later in that integration, so Bombista becomes the only remaining home for typing one in.

**Step 6 moved it to page 1 (2026-09-02) and that is where it lives.** Round A's argument for page 2
was that the timeline is visible there while it is being changed. It does not survive contact with
what a tempo is in this tool: it changes no timing, is never read against the audio, and is never
derived from anything, so **nothing about typing one waits on having heard the take**. It belongs
with the rest of the song's general information, which page 1 now collects. Page 1's old objection —
*four rows total* — was answered by the same change: the song block is a second half of the page,
below the four rows and hidden until there is a song to describe.

**What did not change, and this is the part §11.5 exists for.** `tempo` is written **whole** —
`bpm`, `numerator`, `denominator`, `countInBars` — or not written at all. There is no valid partial
block, proved against Pregonero rather than asserted: `performedTempo.ts` degrades perfectly when
the block is unusable, but `beatScheduler.ts` declares `numerator` and `denominator` as required and
`getBeatsPerBar` does `numerator % 3`, so a bpm-only block yields NaN beats, bars and count-in. The
result is **correct scaling and a broken pulse, with no error anywhere** — the same split brain
`songs@c5adf65` deleted the ten placeholder blocks to avoid, one key deeper. Design boundary rules 4
and 5 also stand in full: Bombista still never derives, measures or guesses a tempo, and B14 stays
dropped.

**The one rule, in one place.** `validation.validate_tempo` is the whole definition of a valid tempo
block, and `bombista validate`, `POST /api/tempo` and the run route all call it. Two front ends with
two opinions about a valid block is how a partial one gets in through the door the other one closed.

**What the move cost, recorded rather than papered over.** A tempo typed wrong on page 1 can only be
corrected by going back to step 1 and running again, and a re-run discards the line corrections made
on page 2 — which the page-2 control could fix in place. `POST /api/tempo` survives and still can,
so the capability is in the tool and only the surface is gone. Whether page 2 should offer it again
is Jorge's call; two controls writing one fact is not the way to settle it.

**The move also broke `Confirm timeline` for a day** — the control left page 2 and its wiring did
not, so the page's script threw before reaching the one listener registered after it. Recorded here
rather than only in the fix, because the lesson is not about tempo: a control that moves takes its
wiring with it, and the test that now enforces that is the durable half of the repair.

## The song's general information is collected on page 1 (step 6, 2026-09-02)

**What a `.txt` cannot carry has to be asked for somewhere, and page 1 is that place.** Title,
artist, notes and title translations, in a block below the four rows, revealed once a lyrics file is
chosen. An SP JSON prefills every field from itself, because this flow is **also how an existing
song is edited** — which is why page 3's new control reads `Save to the catalogue` rather than *Add
to the library*.

**This is what closes the skeleton's reason for existing on the `serve` path.** `bombista new` was
kept because it supplies `artist`, `notes` and `title_translations`, which a plain text cannot and
`bombista validate` wants; creating a skeleton up front is also what forecloses `promote`'s create
path. With page 1 asking for them, the browser flow goes straight from words plus a recording to a
complete song file, and nothing in it calls `new`. **The `new` command is unchanged and still the
CLI's front door** — see the finding below.

**`Save to the catalogue` writes through `POST /api/emit`**, which signs off exactly as pressing a
download does. Emit refuses every path the session read as an input, so it cannot land on `align`'s
`<stem>-song.json`; it writes `<stem>.json` beside it and **reports the path**, which is printed on
the page before the button is pressed and replaced by what was actually written after it. Bombista
has no idea where a catalogue is and must not acquire one: the button carries the name and the line
carries the fact.

## What the first walk of the embedded flow found (2026-09-02)

The first time the seam between Bombista and Pregonero was operated by a person. Five findings, all
of them Bombista's, and none of them teaches this repo who is calling it.

- **`Confirm timeline` did nothing, and the cause was `v1.2.0`'s own.** Moving the tempo control off
  page 2 left its wiring behind; the script threw on `getElementById("t-set")` and stopped one
  statement short of `Confirm`'s listener. Everything registered earlier still worked, so the page
  looked alive. **It failed standalone, not only in a frame.** The guard is a test that fails when
  any page's script reaches for an id its markup does not carry — a page's script and its markup are
  one artifact, and nothing but a test keeps them that way.
- **The tempo block could not be answered by the person who has to answer it.** Four bare numbers
  became three controls: a felt pulse, a time signature, and bars before the first line. **The bpm
  caption was actively harmful**: it sent the reader to the source that produced the audio, where a
  `6/8` song counted in two reads `100` against a felt pulse of `66.67`, and Jorge typed `100`. A
  1.5x error the screen invited. Whole-or-nothing is unchanged.
- **Title translations came off page 1**, on the principle now written into tramoya-integration's
  `project-context.md`: translation happens outside the suite and no tool asks for one. What a file
  carries still passes through untouched — dropping the key from `INFO_KEYS` is the whole change,
  because that list is only what page 1 may *replace*.
- **The file picker is the one surface in the suite with no voice.** It sits beside Pregonero's real
  macOS dialogs, which cannot be styled, so what matches is the behaviour and the vocabulary rather
  than the pixels: `Choose`, path on top, plain list, confirm bottom-right. It stays in-page because
  a web page cannot hand back a file path, and one implementation serves both contexts.
- **Four options now shape the run and the page**, and every one is a directory, a file or a
  boolean: `--staging`, `--browse-from`, `--song`, `--no-header`. **The version survives
  `--no-header`** — two builds calling themselves the same number is the trap that has already cost
  this project a day.

## The tempo contract, and the habit that kept breaking it (2026-09-02)

**Three contract mismatches in two days, all the same mistake**: a value one tool offered as its
default, checked against nothing on the receiving side. The third one was walked — `Save to the
catalogue` wrote a song Pregonero refused with *`tempo.countInBars` must be a positive integer when
present*, and the song was dropped from the list it had just joined.

**The repair is a contract decision, not a bug fix.** `0` and absent both mean no count-in, so there
is one representation and it is absence. Bombista omits the key; Pregonero's rule stands. Teaching
the receiver to accept `0` would have left two ways to say nothing.

**The habit is the actual finding.** Reading `pregonero/src/songState.ts` `validateTempo` — instead
of reasoning about what looked reasonable — turned up two more divergences in the same block:
`numerator` and `denominator` were checked for *positive* here and for *whole* there, so `4.5`
passed this gate and would have been refused; and `countInBars` was *required* here and optional
there, which would have broken the fix on its own the moment a zero stopped being written.

**Bombista's tests now carry the receiver's accept/refuse table**, transcribed from that file and
verified by running its own `validateTempo` over each block. A divergence is a failing test rather
than a walk. **This is the pattern to repeat**: when this suite's tools disagree, the answer is in
the consumer's source, and it is cheap to read.

## A song with no recording is a whole song (2026-09-02)

**The rule that a song could not leave step 1 without audio was written when a timeline was assumed,
and it was wrong.** A song with words and no recording is performed by advancing the lines by hand,
which is a normal night — `libertad` was chosen as the case for it on 26/08. Page 1 now lets the
lyrics alone through, there is nothing to align, step 2 is skipped, and the flow lands on step 3.

**The file such a flow writes carries none of the five timing keys** — not `linesHash`, which guards
a timeline that is not there, and not `timelineSignedOff`, which would claim a human reviewed one.

**The gate names the mode instead of refusing the song.** `--for-performance` reports
`manual only: no timeline` and exits zero. A third severity, `MODE`, exists for it: a property of the
song rather than a problem, so it never fails a gate and it qualifies the verdict in the headline.
*Not ready* was the gate answering a question nobody asked — ready for **which** night?

**One deviation from what was asked, recorded rather than taken silently.** The round also asked for
the timestamp stepper to nudge in tenths. A `0.1` step is coarser than the 0.07 s correction loop the
stepper exists to land inside, which is invariant 2 by number and has its own test. The display
rounds to a tenth and the stepper does not: the list is a readout, the popup is the instrument.

## A prefill that answered the wrong question (2026-09-02)

**`v1.6.0` reported the no-recording path as built and tested, and it did not take.** The cause was
the feature shipped beside it: the media prefill read the take out of the staging directory's
`asr-words.meta.json` **with no reference to which song was being described**. A staging directory is
not necessarily one song's — `serve --staging` takes one directory and a caller may open every song
in it — so picking any lyrics file, including a `.txt` that had never been aligned against anything,
set a media source. From there the consent popup was skipped by design, the review was not skipped
because the run was not manual, and one song's words were anchored against another song's recording.

**The lesson, and it is the third time in this shape.** A per-song question was answered from
per-run state. The guard written for it is the class rather than the instance: *what page 1 says
about a file must not depend on what the server did before it*, checked over the whole payload and
against an empty staging directory, because pointed at one that already held a take both answers
would be equally wrong.

**A second wrong-take path was found while fixing it**: the transcription cache was reused whenever
`asr-words.jsonl` existed, without checking it was made from this run's recording. Re-transcribing
costs ninety seconds; using the wrong words costs a timeline nobody can tell is wrong.

## The fifth mismatch, and what finally caught it (2026-09-02)

**`promote` refused the manual song the flow produces.** `v1.6.0` omits the five timing keys for a
song with no recording on purpose; nothing checked what `promote` does with such a candidate, and
`Save to the catalogue` failed on the file its own flow had just written. Fifth in two days, same
shape every time: one side produces a value deliberately, the other refuses it, a walk finds it.

**Tracing the whole contract rather than the reported error is what made this one different.** The
manual candidate would have hit three refusals in a row — the absent version, then `len(None)`, then
an envelope of three `None`s — and fixing only the first would have moved the failure one line down
and cost another walk. The accept/refuse table is now in the spec (§11.21) and pinned by tests.

**And there is a test that runs the real flow's output through the real `promote`**, which is the
check all five mismatches lacked. Each of them lived in the gap between two components that were
individually well tested.

**Found and not fixed:** `promote` writes only the timeline envelope, so editing a title in the flow
and saving over a song that already exists changes nothing, silently. Not new and not the manual
path's fault, but it is what the flow now implies and does not do. Widening `promote` past the
timeline is a contract change, and how an edit lands is Pregonero's decision.

## Going back was a reset, and it made the backstop a wall (2026-09-02)

Page 1 rendered empty whatever the session held, so pressing `1 Input` discarded the files, the
language, the model and everything typed. **The consequence was worse than the inconvenience**: the
refusal at `Save to the catalogue` tells the person to finish the tempo on page 1, and the only way
to page 1 threw away the answers the refusal was about. A backstop that cannot be acted on is a
wall.

**The fix stores nothing new.** The session has held every one of those answers since the run; page
1 simply never asked for them. What was genuinely lost was the model, and not by the page — the
manual run path never passed it to `load_session`, so a song with no recording fell back to
`medium`. Nothing transcribes on that path and the value is unused, but the person chose it.

**Where a run has happened the page says what running again costs** — step 2's corrections are
re-anchored away — rather than discarding them in silence. With no recording there is nothing to
redo and nothing is said.

**Leaving by `Back` is a different problem and none of this survives it.** Pregonero kills the
`serve` process, and the session is in that process's memory. Reported for Jorge to decide; the two
ways to close it are keeping the process alive across `Back`, or having `serve` persist page 1's
answers into the staging directory — the second changes what Bombista writes and was not made on
speculation.

## The step bar is pinned, and the check came first (2026-09-02)

The rule is the integration's, in its own `project-context.md`. What is worth keeping here is that
**the receiving-side check it demands was done before building and it passed**: Pregonero gives the
frame `flex: 1; min-height: 0` in a bounded flex column, so the embedded page scrolls inside its own
frame and sticky works. Measured in a reproduction of that arrangement — a 793px frame box against
a 1169px document — rather than reasoned about, which is the lesson this project has now paid for
five times.

**One thing the rule could not have known.** Page 2's player was already sticky at `top: 0`, so
pinning the band put two sticky things in the same place. The player docks under the band now, at an
offset derived from the band's own declarations; a first pass guessed it and was nine pixels wrong,
which is invisible except on a scrolled page.

**Open, found while building this and not fixed here.** `skeleton.py` writes
`lyrics: [{"<lang>": ""}]` — one empty lyric entry, deliberately, so the entry *shape* is visible to
whoever writes the words in. Pregonero refuses that file: an empty lyric string is not a lyric line.
Under this design nothing on the `serve` path calls `bombista new`, so it is off the walk, but
`bombista new` is still the CLI's front door and still hands a file to a tool that rejects it.
Named here, not resolved.

## Round A also gave the pipeline a front door and a gate (2026-08-24)

`bombista new` and `bombista validate`. The reasoning is one sentence: a song's life is
**`new` → the words get written in → `align` → `promote` → `validate`**, and until this round the
first and last steps had no tool. A file appeared, and that was the whole process; nothing checked
a hand-edited song file until Pregonero rejected it on a stage.

- **`new` writes a skeleton `validate` already passes** — the catalogue's key order, lyric entries
  as objects keyed by language (flattening them to strings destroyed every translation once), and
  **`tempo` and the timing keys absent** rather than scaffolded.
- **`validate` asks two questions.** The default asks *is this file sane* and tolerates work in
  progress, or the front door would write files the gate rejects. `--for-performance` asks *is this
  song finished* and is what a song passes before entering a setlist.
- **Playability is checked in Bombista and not in Pregonero.** Every rule lives inside a single song
  file and needs no gig. A first draft of the design put these checks in Pregonero; two
  implementations would be two understandings of SP JSON, and the second would go stale the moment
  the first changed.
- **On its first run over the real catalogue it found a live defect**: `libertad.json` carries 24
  lyric lines and a 20-entry timeline (`songs@93e729c` added four verses on purpose and left the
  timeline behind). That is exactly the positional failure the tool exists to make loud.

**What the media check can and cannot promise — recorded because it is easy to over-read.**
`media.src` is a *logical* filename: Pregonero resolves it through a per-machine map
(`mediaPathStore.ts`), because the delivery video lives wherever that machine keeps it. There is no
canonical location, so `validate` is told where to look with `--media-dir` rather than guessing.
**The consequence is that "the media resolves" is machine-dependent, and the check is necessarily
partial.** That is acceptable — the machine that runs the gate is the machine that runs the gig —
but it is not a guarantee, and a pass means the file was found *on that machine, in those
directories*, not that the song is portable.

**Three warnings, and the reason there are warnings at all.** `--for-performance` fails on what
makes a song undisplayable and *warns* on what is correct but worth knowing: an absent `tempo`
(pedal-driven mode works without one), a `linesHash` that no longer matches the lyrics — the common
cause is a corrected translation, so blocking would punish the ordinary case — and an absent
`intro`, which means whatever projects the intro stands dark. None is a fault; each is better
learned before a gig than at one.

## Going public (B18) — the decision, not just the fact

Bombista and Pregonero are both public, MIT-licensed repos. The decision (2026-08-14) was weighed, not automatic: going public meant Bombista's fixtures and worked example would expose real Chango Pepper lyrics and a real master-recording excerpt. Two things were swapped before publishing — not for rights reasons, but for **positioning**: a repo whose fixtures and worked example are one artist's own songs reads as that artist's private tool, which undercuts the generic captioning/surtitles positioning above. The test audio fixture became synthesised speech; the worked example became an invented song (*Río de Sal*), faithful in shape and field names but explicitly not real measurements.

**History was left untouched — deliberately.** No rewrite, no force-push; the pre-swap commits are still reachable. That was accepted rather than overlooked: author rights are established by registration, not by secrecy, and the lyrics involved are already published on changopepper.com by Jorge's own choice, so the repo isn't the first disclosure of the work. The one genuinely new exposure — a 12 s master-recording excerpt (neighbouring rights, SIMIM territory) — stays reachable in history as a reviewed, accepted trade-off; the mitigation is filing with SIMIM (tracked in `projects/song-registration/`), not deleting the commit. A history rewrite remains possible if ever wanted, and gets costlier with every fork that appears.

## On PyPI (2026-08-21)

Published as **`bombista`** at https://pypi.org/project/bombista/, MIT, alongside the public GitHub
repo. Install is now `pip install bombista` rather than a clone.

**What this was for, so it is not mistaken for a launch.** Three things, in order: it **claims the
name** permanently, which was free and is not free later; it **removes a contradiction in the
positioning**, because a tool sold as generic captioning and surtitles infrastructure whose only
install path is "clone this musician's repo" reads as a private script; and it is a **portfolio
artifact** with Jorge's name on it. What it is explicitly **not** is distribution. Nobody browses
PyPI for a forced-alignment triage tool, and the measured lesson from the Instagram work applies
unchanged: the direct, hand-sent channel beat the passive one roughly 30 to 1. If Bombista is ever
meant to be *used*, that comes from posting it where subtitlers and surtitle operators actually
talk, not from the index. Expect zero installs and treat any as a surprise.

**Two irreversible properties of the index, worth remembering before the next release.** A version
number is spent the moment it is uploaded, even if the release is later deleted or yanked, and the
metadata of an uploaded version can never be edited. This is why `1.0.1` exists as a git tag and was
never published: its classifiers understated the supported Python versions, and correcting them
before uploading cost one small PR, where correcting them afterwards would have been impossible.
The tag list therefore shows a gap that the PyPI page does not.

### Round A's upload found a dead token (2026-08-24)

The `bombista`-scoped PyPI token created the previous Sunday no longer authenticated, and its value
was unrecoverable (PyPI never lets you read a token back after creation), so shipping round A's
release meant creating a fresh token and deleting the dead one first. **Claude Code refused to
handle the token itself, and that refusal is now a standing rule**: Claude Code builds the package
and runs `twine check`, but a human uploads it. There is still no `~/.pypirc` and nothing in the
keyring, so the next release will prompt for a token again unless that changes.

## Output contract (what the translator expects)

- The translator (Pregonero) stores a per-song `timeline: TimelineEntry[]`; the cue lookup logic is `videoCueLookup` and the type is `TimelineEntry` in `projects/pregonero/src/songState.ts` — **that code is the source of truth for the exact shape.**
- **The shared contract is `docs/timeline-v2-contract.md`**, co-owned with Pregonero and amended by either side mid-flight. A timeline is relative to a start cue (line 0 at `0.00`, the lead-in banked separately) rather than absolute against the audio file — see "Design decisions" above for why.
- **Interchange format: JSON, locked 2026-06-24.** A `{ "timeline": [...] }` envelope deserializing straight into `TimelineEntry[]`, parallel-array contract preserved. **SRT was rejected**: it carries cue text that duplicates the song JSON's source-of-truth lyric order, and can't represent section markers (which the format no longer carries anyway, per B3). An optional `.srt` export exists as a human-QA debug convenience only — never the canonical contract.

## Tech stack (decided 2026-06-24)

**Python CLI (`click`).** The natural fit for the alignment pipeline (`faster-whisper`, audio handling) and stays cleanly separate. Node/TypeScript would have eased a later in-app integration and shared language with Pregonero, but the output format is language-agnostic (JSON) so an eventual Node/in-app caller is unaffected either way.

## Relationship to other projects

- **Consumer:** `projects/pregonero/` — imports the timeline via the timeline-v2 contract. Don't duplicate the translator's schema here; reference `songState.ts`.
- **Shared data:** song lyric lines + JSON live in the root `songs/` library. This tool reads lyric order from there and writes the timing keys back into a song JSON via `promote` (CLI) or the `serve` download.

## History — how the method got here

Bombista shipped its forced-alignment method (above) on 2026-07-03, but it started as a different tool entirely.

**Video-OCR change-detection (parked 2026-06-25) — the original method.** The plan was to derive a timeline from a "lyrics-only" video: `ffmpeg` region-brightness-edge detection to find subtitle-card change points, OCR to verify each card against the expected line, and a DP-alignment reconciliation step (cards ↔ lyric lines don't map 1:1 — Tragedia showed 33 cards vs 29 lyric lines, because some lines span two cards and consecutive no-gap cards need splitting). A spike ran and passed on Tragedia — 24 of 29 lines matched 1:1, the rest resolved as merges/splits, OCR near-perfect — and an Opus design pass settled the assignment architecture (global DP alignment, video rules on structure / file rules on wording, confidence bands, a two-step `extract`/`promote` CLI). **Superseded, not because it failed its own spike, but because it depended on an input most songs don't have** — a specially prepared lyrics-only subtitle video — where forced alignment needs only an audio recording and the lyrics text, which every song already has. This is also why design boundary rule 5 above (audio + lyrics JSON, nothing else) reads as a hard-won constraint rather than an arbitrary one: the OCR approach's dependency on video was exactly the kind of extra input source the current method refuses to reintroduce.

**The pivot (2026-07-03).** Dispatched from an ASR-following spike run in Pregonero's repo: that spike found live streaming ASR too slow for driving a lyric pointer in real time, but its side finding — faster-whisper `medium` batch-aligning a whole song near-verbatim in under a minute — became Bombista's core mechanism. `align` (the CLI verb; `extract` is a kept alias of the same command so the two cannot drift) replaced the OCR pipeline in one session, green end to end; the acceptance run against Tragedia converged exactly with the spike's hand-verified ground truth after two documented hand anchors.

**Timeline v2 (B12, 2026-08-13–14).** The timeline moved from absolute-against-audio to relative-against-a-start-cue: line 0 always at `0.00`, the seconds before the first sung word banked in `leadIn {durationSec, source, confidence, apply}`, stamped `timelineVersion: 2`. Bombista never decides whether to apply the lead-in — Auto mode defaults `apply: false` (the performer starts the lyrics live, so any intro length is fine) and Video mode defaults `apply: true` (the video is the fixed clock). This is the fix for the single least reliable number Bombista produces: faster-whisper has a known quirk that clamps the first sung word toward `0.0`, and isolating it means that one bad number no longer contaminates every timestamp in the song. `timelineVersion: 2` exists so a v1-aware app reading a v2 file fails loudly rather than firing every line early with no error. **B13 (migrating Libertad and Tragedia's stored timelines to v2) is done** — both migrated and committed, Libertad reproduces the contract's golden fixture exactly. Migrating Tragedia's timeline did not fix Tragedia: its stored timeline was measured from the wrong audio source (the master, not the linked animation's own audio) and stayed ~17 s late until re-extracted from the correct source — a reminder that a timeline is only meaningful relative to the exact audio it was measured from (this is what the provenance block, B1, exists to make visible).

**Lyrics arrays carry sung lines only (B3).** Section markers were deleted from the contract entirely rather than kept as a `{0,0}` exemption — no song ever used one, so nothing broke, and Pregonero doesn't need the matching exemption either.

## Open questions

- **The proposed `--lead` knob** (a card-style visual-lead offset vs. sung onsets) is parked, not built. Jorge decides if cards-style timing is ever wanted; the acceptance run's Tragedia comparison found a median −0.36 s / stdev 0.70 gap between forced-alignment onsets and the card reference.
- **Re-running on new recordings** is a plain `bombista align <audio.wav> <song.json> -o <staging>` then `promote` — no code changes needed; see the repo `CLAUDE.md`.

## Model picks

General rule in `personal-context.md`. For this project: **Opus** for the initial pipeline/architecture framing (alignment + confidence-band + review-loop design), then **Sonnet** for build-out and iteration.
