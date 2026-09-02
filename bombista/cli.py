"""
bombista CLI entrypoint — forced-alignment pipeline.

    bombista new <song-id>
    bombista align <audio> <song-json> -o <staging-dir>
    bombista promote <timeline-json> <song-json>
    bombista validate <song-json> [--for-performance]
    bombista migrate <song-json>

`new` writes the skeleton a song starts from — the front door of the flow,
and the step that used to be folklore. `align` transcribes the audio
(faster-whisper word timestamps), anchors each lyric line, and writes a
candidate timeline + QA report to a staging directory. It never writes to
the song JSON. `promote` copies an approved timeline into the song JSON
(backup + diff), touching nothing else. `validate` is the gate at both
ends: is this file sane, and is this song finished. `migrate` (B13)
rebases a stored v1 timeline onto the v2 start cue in place — a one-off
for songs timed before v2, not part of the loop.
"""
from __future__ import annotations

import json
import shutil
from copy import copy
from pathlib import Path

import click

from .aligner import (
    load_words,
    load_words_meta,
    save_words,
    save_words_meta,
    transcribe_words,
)
from .anchoring import anchor_lines, parse_anchor_overrides
from .migrate import migrate_song_to_v2
from .pipeline import build_timeline, lyric_lines, normalize_to_lead_in
from .promotion import promote_candidate
from .provenance import (
    build_provenance,
    compute_lines_hash,
    provenance_for_reused_words,
    tool_version,
    words_meta,
)
from .readers import read_lyrics_input
from .report import band_counts, render_qa_report
from .serializer import to_dict, write_timeline
from .server import LOOPBACK_HOST, create_server, load_session
from .skeleton import song_skeleton
from .songfile import back_up_and_replace, timeline_diff
from .validation import has_errors, load_and_validate, render_findings
from .writers import (
    build_bombista_block,
    write_html_review,
    write_lrc,
    write_report_json,
    write_songjson,
    write_srt,
)

_EMIT_CHOICES = ("timeline", "songjson", "report-json", "srt", "lrc", "html")

_ALIGN_EPILOG = """\
\b
IMPORTANT — pick the right audio:
Timeline times are only meaningful relative to the audio you feed in.
- Video-mode songs: extract the audio from the linked animation video:
    ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav
- Auto-mode songs (no video): use the master recording.
"""


_FLOW = """\
\b
A song's life, and Bombista owns both ends of the one un-tooled step:
    bombista new <song-id>     the skeleton — a legal song file with nothing in it
    (an LLM session, or you, writes the words into it)
    bombista align ...         the timeline, aligned against the audio
    bombista promote ...       the timeline, written into the song
    bombista validate ...      the gate — is it sane, and is it finished
"""


@click.group(epilog=_FLOW)
@click.version_option(
    version=tool_version(),
    message="%(version)s",
    help="Show the version and exit — the same string that lands in toolVersion.",
)
def main() -> None:
    """Derive a lyric timeline from audio via forced alignment."""


@main.command(name="new", epilog=_FLOW)
@click.argument("song_id")
@click.option(
    "-o",
    "--output",
    "out_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the skeleton here instead of to stdout. Never overwrites.",
)
@click.option("--lang", default="es", show_default=True, help="Language key the blocks are keyed by.")
@click.option(
    "--title",
    help="The song's title. Defaults to SONG_ID de-slugified, which is a seed to edit.",
)
def new(song_id: str, out_path: Path | None, lang: str, title: str | None) -> None:
    """Write a canonical Song Performance JSON skeleton for SONG_ID.

    **This is the front door of the flow above**, and the reason it exists
    is that the first step used to be folklore: a file appeared, and that
    was the whole process — which is why the pipeline had silent failures
    at the far end. What comes out here is already a legal song file, so
    `bombista validate` passes it on the way in as well as on the way out.

    Two absences are deliberate. **`tempo` is absent, not a placeholder** —
    a missing tempo is a real state and a fake one is a bug that reaches a
    stage; type it in on `bombista serve`'s review page, where the value is
    yours to supply. **The timing keys are absent** until `align` and
    `promote` write them: a human starting a song does not write timings.
    """
    try:
        skeleton = song_skeleton(song_id, lang=lang, title=title)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="SONG_ID")

    payload = json.dumps(skeleton, indent=2, ensure_ascii=False) + "\n"

    if out_path is None:
        click.echo(payload, nl=False)
        return

    if out_path.exists():
        raise click.ClickException(
            f"{out_path}: already exists — refusing to overwrite a song file "
            "with an empty skeleton"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload, encoding="utf-8")
    click.echo(f"wrote: {out_path}")


@main.command(epilog=_ALIGN_EPILOG)
@click.argument("audio", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument(
    "song_json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    metavar="SONG_JSON_OR_LYRICS_TXT",
)
@click.option(
    "-o",
    "--output",
    "staging_dir",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Staging directory for the candidate timeline, QA report, and ASR words.",
)
@click.option("--model-size", default="medium", show_default=True, help="faster-whisper model size.")
@click.option("--lang", default="es", show_default=True, help="Language: song-JSON lyric key and ASR language.")
@click.option(
    "--anchor",
    "anchor_opts",
    multiple=True,
    metavar="LINE=SECONDS",
    help="Hand-set a lyric line's onset (repeatable), e.g. --anchor 7=93.4.",
)
@click.option(
    "--words",
    "words_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Reuse a saved asr-words.jsonl and skip transcription (fast re-runs).",
)
@click.option(
    "--emit",
    "emit_targets",
    type=click.Choice(_EMIT_CHOICES),
    multiple=True,
    default=("timeline",),
    show_default=True,
    help=(
        "Output(s) to write into the staging directory (repeatable). "
        "Passing --emit at all REPLACES the default set — it does not add "
        "to it, so `--emit songjson` alone writes only the song JSON, not "
        "timeline.json too. asr-words.jsonl and the QA report are always "
        "written regardless of --emit."
    ),
)
def align(
    audio: Path,
    song_json: Path,
    staging_dir: Path,
    model_size: str,
    lang: str,
    anchor_opts: tuple[str, ...],
    words_path: Path | None,
    emit_targets: tuple[str, ...],
) -> None:
    """Align AUDIO against the lyric lines in SONG_JSON_OR_LYRICS_TXT and
    stage a candidate timeline.

    The lyrics input may be a CP song JSON (passed through unchanged) or
    a plain text file, one lyric line per line (blank lines and
    [Bracketed] lines are stripped and reported, never converted to
    markers) — either way it is normalised to a CP-shaped song dict
    before this pipeline runs (see readers.py).

    Writes asr-words.jsonl and <song>-qa-report.md into the staging
    directory unconditionally — those are part of the workflow, not an
    --emit output. --emit (repeatable) picks which of timeline / songjson
    / report-json / srt / lrc / html also get written there; default is
    `timeline` alone, matching today's behaviour. `html` is the offline
    review page (B16) — the QA report with a per-line play button that
    seeks the audio, so a REVIEW line can be judged by ear. Never writes to the song
    JSON — review the QA report, then apply with `bombista
    promote` (accepts either a bare timeline or an emitted songjson).

    Timeline times are only meaningful relative to the audio you feed in:
    for Video-mode songs extract the audio from the linked animation video
    (ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav); for Auto-mode
    songs use the master recording.
    """
    try:
        normalised = read_lyrics_input(song_json, lang=lang)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    song = normalised.song
    stripped_lines = normalised.bombista.get("strippedLines")
    items = song.get("lyrics")
    if not isinstance(items, list):
        raise click.ClickException(f'{song_json}: song JSON has no "lyrics" list')
    try:
        lines = lyric_lines(items, lang)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    if not lines:
        raise click.ClickException(
            f"{song_json}: no lyric lines carry the {lang!r} language key"
        )
    lines_hash = compute_lines_hash(lines)  # B4 — positional-fragility guard
    try:
        overrides = parse_anchor_overrides(anchor_opts, len(lines))
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--anchor")

    staging_dir.mkdir(parents=True, exist_ok=True)
    words_out = staging_dir / "asr-words.jsonl"

    # Built once per run, even when --words skips transcription — that's
    # exactly when the audio's sha256 earns its keep (B1). Built *before*
    # the branch below, because on the transcribing path it is also what
    # gets filed beside the word stream, and on the --words path it is
    # what the sibling corrects (B20 §11.10).
    provenance = build_provenance(audio, model_size=model_size, lang=lang)

    if words_path is not None:
        words = load_words(words_path)
        meta = load_words_meta(words_path)
        if words_path.resolve() != words_out.resolve():
            shutil.copyfile(words_path, words_out)
            # The facts travel with the stream, or the copy is the
            # older-staging-directory case one run later.
            if meta is not None:
                save_words_meta(meta, words_out)
        # faster-whisper never ran, so this run cannot say when the
        # machine listened, or with which model. The run that did says so.
        provenance = provenance_for_reused_words(provenance, meta)
    else:
        words = transcribe_words(audio, model_size=model_size, language=lang)
        save_words(words, words_out, meta=words_meta(provenance, audio))

    anchors = anchor_lines(words, lines, overrides=overrides or None)
    try:
        entries = build_timeline(anchors, words, items, lang=lang)
    except ValueError as exc:
        raise click.ClickException(str(exc))

    lead_in, normalized_entries = normalize_to_lead_in(entries)

    stem = song_json.stem
    emit_set = set(emit_targets)
    # Built once regardless of which --emit targets are requested: songjson,
    # srt, and lrc all need it, and it's cheap/pure.
    envelope = to_dict(lead_in, normalized_entries, song)

    produced: list[str] = []

    if "timeline" in emit_set:
        timeline_out = staging_dir / f"{stem}-timeline.json"
        write_timeline(lead_in, normalized_entries, song, timeline_out)
        produced.append(f"timeline: {timeline_out}")

    if "songjson" in emit_set:
        bombista = build_bombista_block(normalised.bombista, provenance, lines_hash)
        songjson_out = staging_dir / f"{stem}-song.json"
        write_songjson(song, envelope, bombista, songjson_out)
        produced.append(f"songjson: {songjson_out}")

    if "report-json" in emit_set:
        report_json_out = staging_dir / f"{stem}-report.json"
        write_report_json(
            provenance=provenance,
            lines_hash=lines_hash,
            lead_in_block=envelope["leadIn"],
            anchors=anchors,
            lines=lines,
            line_entries=entries,  # raw audio-clock — see writers.py docstring
            out_path=report_json_out,
        )
        produced.append(f"report-json: {report_json_out}")

    if "srt" in emit_set:
        srt_paths = write_srt(song, envelope, stem, staging_dir)
        produced.append("srt: " + ", ".join(str(p) for p in srt_paths))

    if "lrc" in emit_set:
        lrc_paths = write_lrc(song, envelope, stem, staging_dir)
        produced.append("lrc: " + ", ".join(str(p) for p in lrc_paths))

    if "html" in emit_set:
        html_out = staging_dir / f"{stem}-review.html"
        write_html_review(
            song_title=song.get("title", stem),
            song_path=song_json,
            audio_path=audio,
            staging_dir=staging_dir,
            words_path=words_out,
            lang=lang,
            provenance=provenance,
            lead_in=lead_in,
            anchors=anchors,
            lines=lines,
            line_entries=entries,  # raw audio-clock — the <audio> element's clock
            out_path=html_out,
        )
        produced.append(f"html: {html_out}")

    report_out = staging_dir / f"{stem}-qa-report.md"
    report = render_qa_report(
        anchors=anchors,
        lines=lines,
        line_entries=entries,  # raw audio-clock times — see report.py docstring
        lead_in=lead_in,
        song_title=song.get("title", stem),
        song_path=song_json,
        audio_path=audio,
        model_size=model_size,
        lang=lang,
        staging_dir=staging_dir,
        provenance=provenance,
        stripped_lines=stripped_lines,
    )
    report_out.write_text(report, encoding="utf-8")
    produced.append(f"report: {report_out}")
    produced.append(f"words: {words_out}")

    counts = band_counts(anchors)
    click.echo(
        f"HIGH {counts['HIGH']} / REVIEW {counts['REVIEW']} / FAIL {counts['FAIL']} "
        "— " + " — ".join(produced)
    )


# B11: `align` is the primary verb — "forced alignment" is the category
# word, and claiming the category is the point of the name. `extract` was
# the original verb and keeps working indefinitely: it is written into
# every QA report generated so far, into the acceptance records, and into
# the shell history of every run. Breaking a paste is the failure B17
# exists to prevent.
#
# A shallow copy of the same Command, not a second implementation — the
# two cannot drift, which is what tests/test_cli.py pins.
_extract_alias = copy(align)
_extract_alias.name = "extract"
_extract_alias.short_help = "Alias for `align`, the verb this command used to have."
main.add_command(_extract_alias)


@main.command()
@click.argument("timeline_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("song_json", type=click.Path(dir_okay=False, path_type=Path))
def promote(timeline_json: Path, song_json: Path) -> None:
    """Write the timeline v2 envelope from TIMELINE_JSON into SONG_JSON,
    creating SONG_JSON when it does not exist yet.

    TIMELINE_JSON may be either a bare timeline v2 envelope (`extract`'s
    default `--emit timeline` output) or a full `--emit songjson` output
    (the envelope plus every other song field and a `_bombista` block) —
    only the envelope keys are read out of it either way. A bare envelope
    carries no completeness information, so no refusal (below) is ever
    possible against one.

    Validates the envelope against the timeline v2 contract (rejecting a
    v1 candidate loudly) and the song's item count, backs the song file up
    next to itself, and writes `timelineVersion`, `leadIn` and `timeline`
    (via `writers.merge_envelope` — the one merge path shared with
    `--emit songjson`) — every other key is preserved untouched, in order.

    Refuses to overwrite a target song whose `readers.song_completeness`
    is `"complete"` with a candidate (only possible when TIMELINE_JSON is
    an emitted songjson) whose own completeness is `"partial"` — promoting
    a thin, plain-text-derived candidate over a song that already has full
    CP data is very likely a mistake, not an upgrade.

    \b
    CREATING a song, when SONG_JSON does not exist:
    This is the last step of making a song from a lyrics text file and a
    recording, and it is the only way that song ever reaches the
    catalogue. Two conditions, both refusals rather than judgement calls:
      - TIMELINE_JSON must be a full `--emit songjson` output. A bare
        timeline envelope is three keys; there is no song in it.
      - SONG_JSON must be the canonical name for it — `<stem>.json` for a
        candidate `<stem>-song.json`. A song's id IS its filename, so a
        free choice of name here is a free choice of id.
    The `_bombista` provenance block is not carried into the created song:
    it is about a run, it belongs beside the report in staging, and a
    catalogue where created songs carry a key hand-made ones do not is a
    catalogue with two kinds of song file in it.
    """
    try:
        outcome = promote_candidate(
            timeline_json,
            song_json,
            note=lambda message: click.echo(message, err=True),
        )
    except ValueError as exc:
        raise click.ClickException(str(exc))

    if outcome.backup is None:
        click.echo(f"created: {song_json}")
    else:
        click.echo(f"backup: {outcome.backup}")
    for line in outcome.diff:
        click.echo(line)


@main.command()
@click.argument("song_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--for-performance",
    is_flag=True,
    help="Ask the stricter question: is this song finished?",
)
@click.option("--lang", default="es", show_default=True, help="Song JSON lyric key.")
@click.option(
    "--media-dir",
    "media_dirs",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help=(
        "Where a relative media.src is looked for (repeatable). Tried before "
        "the song file's own directory."
    ),
)
def validate(
    song_json: Path, for_performance: bool, lang: str, media_dirs: tuple[Path, ...]
) -> None:
    """Check SONG_JSON, and say everything that is wrong with it.

    \b
    Two strictness levels, because there are two questions:
      (default)           is this file SANE? Tolerates work in progress — a
                          song fresh from `bombista new` has no timeline
                          yet and must still be savable.
      --for-performance   is this song FINISHED? The gate a song passes
                          before it can be put in a setlist.

    `--for-performance` additionally requires a timeline that is present
    and consistent with the lyrics, and a declared `media` that resolves —
    without either, nothing can be displayed. A **missing `tempo` is a
    warning there, not a failure**: pedal-driven mode works without one,
    and only the beat indicator, the count-in and clock-driven mode need
    it. A `tempo` that is present but partial is a failure at both levels.

    Every problem is listed, never just the first — a person fixing a file
    wants all of it at once. Exits non-zero if any of them is an error.
    """
    findings = load_and_validate(
        song_json,
        lang=lang,
        for_performance=for_performance,
        media_dirs=media_dirs,
    )

    for line in render_findings(song_json, findings):
        click.echo(line)

    if has_errors(findings):
        raise SystemExit(1)


@main.command()
@click.argument(
    "staging_dir",
    required=False,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.argument(
    "lyrics",
    required=False,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    metavar="[SONG_JSON_OR_LYRICS_TXT]",
)
@click.option("--lang", default="es", show_default=True, help="Song JSON lyric key.")
@click.option(
    "--audio",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=(
        "The take this staging directory was aligned against. Only needed "
        "when the run's own record of it no longer resolves — a staging "
        "directory that was moved, or one from before the record existed."
    ),
)
@click.option(
    "--staging",
    "staging_out",
    type=click.Path(file_okay=False, path_type=Path),
    help=(
        "Where a run started from page 1 does its work, instead of the "
        "cache under ~/.cache/bombista. For a caller that means to read "
        "the <stem>.json `Save to the catalogue` writes back out — a "
        "directory in, a file path out, and nothing else passes."
    ),
)
@click.option(
    "--browse-from",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help=(
        "The directory the file pickers open in. Defaults to your home "
        "folder, which is a poor answer on a screen whose job is to find "
        "a lyrics file and a recording that live beside each other — "
        "point it at wherever the songs are."
    ),
)
@click.option(
    "--song",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=(
        "A song file to start page 1 prefilled from, which is what makes "
        "an edit an edit rather than a second new song. Different from the "
        "positional argument, which boots straight into a review of a "
        "finished run: this one starts at step 1 with the file chosen."
    ),
)
@click.option(
    "--header/--no-header",
    default=True,
    help=(
        "Draw the product header — the name, the tagline, the version and "
        "who made it. Turn it off inside a window that already has a "
        "title of its own. The version still shows either way."
    ),
)
@click.option(
    "--port",
    default=0,
    show_default="an ephemeral port, printed on start",
    help=f"Port to bind on {LOOPBACK_HOST}.",
)
def serve(
    staging_dir: Path | None,
    lyrics: Path | None,
    lang: str,
    audio: Path | None,
    staging_out: Path | None,
    browse_from: Path | None,
    song: Path | None,
    header: bool,
    port: int,
) -> None:
    """Open the three-step interface in a browser, on this machine only.

    With no arguments it starts at step 1, where the song and its media
    source are chosen and the run is started.

    With STAGING_DIR it boots straight into the review of a previous
    `align`. The staging directory supplies the word stream and the QA
    state; the lyrics argument supplies the lines, because `align` never
    copies its lyrics input into staging — pass the same song JSON (or
    lyrics text) you aligned against. It may be omitted only when the
    staging directory holds an `--emit songjson` output to fall back on.

    --audio names the take the review plays. It is the third of the three
    things page 1 collects with pickers, and it is only needed when the
    run's own record of the take no longer resolves: `align` stores that
    path as it was given, so a staging directory that has been moved
    records a relative path that leads nowhere. The player says so rather
    than finding some other file — a timeline is only meaningful against
    the audio it was measured from.

    --staging says where a run started from page 1 should work. Without
    it that is a cache directory under ~/.cache/bombista, which is right
    for running Bombista on its own and wrong for a caller that means to
    read the `<stem>.json` `Save to the catalogue` writes back out: it
    would have to know this tool's cache layout to find the file. A
    directory in, a file path on the page, and nothing else passes.

    --browse-from, --song and --no-header are three answers about the page
    itself: where the file pickers open, a song file page 1 starts
    prefilled from, and whether to draw the product header. They exist
    because the defaults are right for running Bombista on its own and
    wrong inside a window that already has a title and already knows where
    the songs are. **None of them tells Bombista who is calling**, and none
    of them changes a byte of what it writes.

    Binds 127.0.0.1 and nothing else. The audio, the transcription and the
    anchoring all stay in this process on this machine — nothing is
    uploaded, and there is no configuration that would change that.
    """
    session = None
    if staging_dir is not None:
        if lyrics is None:
            lyrics = next(iter(sorted(staging_dir.glob("*-song.json"))), None)
            if lyrics is None:
                raise click.ClickException(
                    f"{staging_dir}: no lyrics argument, and no <stem>-song.json in "
                    "the staging directory to fall back on. Pass the song JSON or "
                    "lyrics text this run was aligned against."
                )
        try:
            session = load_session(staging_dir, lyrics, lang=lang, audio_path=audio)
        except ValueError as exc:
            raise click.ClickException(str(exc))

    try:
        httpd = create_server(
            session,
            port=port,
            staging=staging_out,
            browse_from=browse_from,
            song=song,
            header=header,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc))

    bound_port = httpd.server_address[1]
    click.echo(f"bombista serve — http://{LOOPBACK_HOST}:{bound_port}/ (ctrl-c to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive
        click.echo("")
    finally:
        httpd.server_close()


@main.command()
@click.argument("song_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--dry-run",
    is_flag=True,
    help="Report what would change and write nothing.",
)
def migrate(song_json: Path, dry_run: bool) -> None:
    """Rebase a **v1** SONG_JSON onto the timeline v2 start cue, in place.

    Subtracts `timeline[0].start` from every entry, banks it in `leadIn`
    (`apply` defaulting from `media.type`, as B12 does) and stamps
    `timelineVersion: 2` — the song's other keys are preserved untouched
    and in order. Backs the file up next to itself first, then replaces
    it atomically.

    Refuses, without writing anything, if the song is already v2, is
    half-stamped, has no timeline, or has an entry count that does not
    match its lyric count. It is **idempotent by refusal**: running it
    twice must not subtract the lead-in twice, and a silent no-op would
    look too much like success.
    """
    song = json.loads(song_json.read_text(encoding="utf-8"))
    old_timeline = song.get("timeline")

    try:
        migrated = migrate_song_to_v2(song)
    except ValueError as exc:
        raise click.ClickException(f"{song_json}: {exc}")

    lead_in = migrated["leadIn"]
    report = [
        f"leadIn: {lead_in['durationSec']}s "
        f"({lead_in['source']}, confidence {lead_in['confidence']}, "
        f"apply={str(lead_in['apply']).lower()})",
        *timeline_diff(old_timeline, migrated["timeline"]),
    ]

    if dry_run:
        click.echo(f"dry run — {song_json} not written")
        for line in report:
            click.echo(line)
        return

    backup = back_up_and_replace(song_json, migrated)

    click.echo(f"backup: {backup}")
    for line in report:
        click.echo(line)


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess
    # `python -m bombista.cli` is the documented fallback when the
    # console script is not on PATH (a venv that was not activated, a
    # `pip install --user`). Without this guard the module imports, defines
    # the group, and falls off the end — exit 0, no output. Silent success
    # is the worst failure mode a CLI has; tests/test_cli.py pins it.
    main()
