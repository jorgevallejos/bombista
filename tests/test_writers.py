"""
Tests for the `--emit` writers — B2 (docs/bombista-product-backlog.md §4,
§3.5-§3.7). Every writer reads the canonical CP form produced by
`readers.py`; these tests exercise `writers.py` directly with small,
synthetic inputs (no whisper model, no audio decoding) so they stay fast.
"""
from __future__ import annotations

import json
import re
import shlex
from html import unescape
from pathlib import Path

import pytest

from bombista.anchoring import LineAnchor
from bombista.models import TimelineEntry
from bombista.writers import (
    build_bombista_block,
    merge_envelope,
    write_html_review,
    write_lrc,
    write_report_json,
    write_songjson,
    write_srt,
)

FIXTURES = Path(__file__).parent / "fixtures"
LIBERTAD_SONG = FIXTURES / "libertad-song.json"


# ---------------------------------------------------------------------------
# merge_envelope — the one merge path
# ---------------------------------------------------------------------------

ENVELOPE = {
    "timelineVersion": 2,
    "leadIn": {"durationSec": 1.0, "source": "measured", "confidence": "low", "apply": False},
    "timeline": [{"start": 0.0, "end": 1.0}, {"start": 1.0, "end": 2.0}],
}


def test_merge_envelope_inserts_new_keys_at_first_existing_occurrence():
    song = {"title": "T", "lyrics": [1, 2], "timeline": "old", "notes": "keep"}

    merged = merge_envelope(song, ENVELOPE)

    assert list(merged.keys()) == [
        "title",
        "lyrics",
        "timelineVersion",
        "leadIn",
        "timeline",
        "notes",
    ]
    assert merged["timelineVersion"] == 2
    assert merged["leadIn"] == ENVELOPE["leadIn"]
    assert merged["timeline"] == ENVELOPE["timeline"]
    assert merged["notes"] == "keep"


def test_merge_envelope_appends_new_keys_when_none_existed():
    song = {"title": "T", "lyrics": [1, 2]}

    merged = merge_envelope(song, ENVELOPE)

    assert list(merged.keys()) == ["title", "lyrics", "timelineVersion", "leadIn", "timeline"]


@pytest.mark.parametrize("dropped", ["timelineVersion", "leadIn", "timeline"])
def test_merge_envelope_refuses_a_partial_envelope(dropped):
    """The three keys go in as a unit or not at all. A song with normalised
    timings but no version stamp would be rejected by the translator; one
    with a stamp but no leadIn would lose the offset that reconstructs the
    raw times."""
    partial = {k: v for k, v in ENVELOPE.items() if k != dropped}
    song = {"title": "T", "lyrics": [1, 2]}

    with pytest.raises(ValueError, match="partial envelope"):
        merge_envelope(song, partial)


@pytest.mark.parametrize("dropped", ["timelineVersion", "leadIn", "timeline"])
def test_merge_envelope_writes_nothing_when_the_envelope_is_partial(dropped):
    """Not merely 'raises' — the song must come back untouched, with none of
    the three keys half-applied."""
    partial = {k: v for k, v in ENVELOPE.items() if k != dropped}
    song = {"title": "T", "lyrics": [1, 2]}
    before = json.dumps(song)

    with pytest.raises(ValueError):
        merge_envelope(song, partial)

    assert json.dumps(song) == before


def test_merge_envelope_does_not_mutate_the_input_song():
    song = {"title": "T", "lyrics": [1, 2]}
    merge_envelope(song, ENVELOPE)
    assert song == {"title": "T", "lyrics": [1, 2]}


# ---------------------------------------------------------------------------
# build_bombista_block
# ---------------------------------------------------------------------------

PROVENANCE = {
    "audio": "songs/audio/x.wav",
    "sha256": "deadbeef",
    "durationSec": 120.0,
    "model": "faster-whisper:medium",
    "device": "cpu/int8",
    "lang": "es",
    "extractedAt": "2026-08-13T10:00:00+02:00",
    "toolVersion": "bombista 0.9.0",
}


def test_build_bombista_block_combines_reader_block_with_provenance_under_source():
    reader_bombista = {"completeness": "complete"}

    block = build_bombista_block(reader_bombista, PROVENANCE, "sha256:abc123")

    assert block == {
        "completeness": "complete",
        "source": PROVENANCE,
        "linesHash": "sha256:abc123",
    }


def test_build_bombista_block_preserves_partial_fields():
    reader_bombista = {
        "completeness": "partial",
        "filledLang": "es",
        "missing": ["artist", "tempo"],
        "strippedLines": [{"line": 1, "text": "", "reason": "blank"}],
    }

    block = build_bombista_block(reader_bombista, PROVENANCE, "sha256:abc123")

    assert block["completeness"] == "partial"
    assert block["filledLang"] == "es"
    assert block["missing"] == ["artist", "tempo"]
    assert block["strippedLines"] == reader_bombista["strippedLines"]
    assert block["source"] == PROVENANCE
    assert block["linesHash"] == "sha256:abc123"


# ---------------------------------------------------------------------------
# write_songjson
# ---------------------------------------------------------------------------


def test_write_songjson_merges_envelope_and_appends_bombista(tmp_path):
    song = {"title": "T", "lyrics": [{"es": "uno"}, {"es": "dos"}]}
    bombista = build_bombista_block({"completeness": "complete"}, PROVENANCE, "sha256:abc123")
    out = tmp_path / "song.json"

    result = write_songjson(song, ENVELOPE, bombista, out)

    assert list(result.keys()) == ["title", "lyrics", "timelineVersion", "leadIn", "timeline", "_bombista"]
    assert result["_bombista"] == bombista
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == result


def test_write_songjson_round_trips_libertad_fixture_non_timeline_fields_byte_identically(tmp_path):
    """Acceptance #1: every key other than timelineVersion/leadIn/timeline/
    _bombista keeps its value AND position; re-serialising them is
    identical text to the original fixture's own serialisation of those
    keys."""
    song = json.loads(LIBERTAD_SONG.read_text(encoding="utf-8"))
    bombista = build_bombista_block({"completeness": "complete"}, PROVENANCE, "sha256:abc123")
    out = tmp_path / "libertad-song.json"

    result = write_songjson(song, ENVELOPE, bombista, out)

    reserved = {"timelineVersion", "leadIn", "timeline", "_bombista"}
    original_keys = [k for k in song.keys() if k not in reserved]
    result_non_timeline_keys = [k for k in result.keys() if k not in reserved]
    assert result_non_timeline_keys == original_keys

    for key in original_keys:
        assert result[key] == song[key]
        assert json.dumps(result[key], ensure_ascii=False) == json.dumps(
            song[key], ensure_ascii=False
        )


# ---------------------------------------------------------------------------
# write_report_json
# ---------------------------------------------------------------------------

ANCHORS = [
    LineAnchor(0, 10.0, "HIGH", ("clean-anchor",), "hola mundo bonito", 0),
    LineAnchor(1, 55.88, "REVIEW", ("ambiguous",), "fui mas impulso que voz", 0),
    LineAnchor(2, None, "FAIL", ("no-anchor",), "", None),
]
LINES = ["hola mundo", "fui mas impulso que voz", "no encontrado"]
ENTRIES = [
    TimelineEntry(10.0, 20.0),
    TimelineEntry(55.88, 59.52),
    TimelineEntry(59.52, 60.52),
]
LEAD_IN_BLOCK = {"durationSec": 10.0, "source": "measured", "confidence": "low", "apply": False}


def test_write_report_json_shape(tmp_path):
    out = tmp_path / "report.json"

    result = write_report_json(
        provenance=PROVENANCE,
        lines_hash="sha256:abc123",
        lead_in_block=LEAD_IN_BLOCK,
        anchors=ANCHORS,
        lines=LINES,
        line_entries=ENTRIES,
        out_path=out,
    )

    assert result["source"] == PROVENANCE
    assert result["linesHash"] == "sha256:abc123"  # B4
    assert result["leadIn"] == LEAD_IN_BLOCK
    assert result["summary"] == {"high": 1, "review": 1, "fail": 1}
    assert len(result["lines"]) == 3

    line0 = result["lines"][0]
    assert line0["i"] == 0
    assert line0["text"] == "hola mundo"
    assert line0["start"] == 10.0
    assert line0["end"] == 20.0
    assert line0["band"] == "HIGH"
    assert line0["signals"] == ["clean-anchor"]

    line1 = result["lines"][1]
    assert line1["band"] == "REVIEW"
    assert line1["signals"] == ["ambiguous"]
    assert line1["asrContext"] == "fui mas impulso que voz"

    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == result


def test_write_report_json_omits_asr_context_when_empty(tmp_path):
    out = tmp_path / "report.json"

    result = write_report_json(
        provenance=PROVENANCE,
        lines_hash="sha256:abc123",
        lead_in_block=LEAD_IN_BLOCK,
        anchors=ANCHORS,
        lines=LINES,
        line_entries=ENTRIES,
        out_path=out,
    )

    line2 = result["lines"][2]
    assert "asrContext" not in line2


def test_write_report_json_uses_raw_audio_clock_times_not_normalised(tmp_path):
    """Times here match the markdown QA report's clock (raw, pre-leadIn
    subtraction), not the emitted timeline's clock."""
    out = tmp_path / "report.json"

    result = write_report_json(
        provenance=PROVENANCE,
        lines_hash="sha256:abc123",
        lead_in_block=LEAD_IN_BLOCK,
        anchors=ANCHORS,
        lines=LINES,
        line_entries=ENTRIES,
        out_path=out,
    )

    assert result["lines"][0]["start"] == 10.0  # raw, not 0.0


# ---------------------------------------------------------------------------
# write_srt / write_lrc
# ---------------------------------------------------------------------------

SUBTITLE_SONG = {
    "title": "Cancion",
    "artist": "Chango Pepper",
    "lyrics": [
        {"es": "hola mundo bonito", "en": "hello beautiful world"},
        {"es": "vamos a bailar\nahora", "en": "let's dance\nnow"},
    ],
}

SUBTITLE_ENVELOPE_APPLY_TRUE = {
    "timelineVersion": 2,
    "leadIn": {"durationSec": 7.0, "source": "measured", "confidence": "low", "apply": True},
    "timeline": [{"start": 0.0, "end": 10.0}, {"start": 10.0, "end": 15.5}],
}

SUBTITLE_ENVELOPE_APPLY_FALSE = {
    "timelineVersion": 2,
    "leadIn": {"durationSec": 7.0, "source": "measured", "confidence": "low", "apply": False},
    "timeline": [{"start": 0.0, "end": 10.0}, {"start": 10.0, "end": 15.5}],
}


def test_write_srt_one_file_per_language_key(tmp_path):
    paths = write_srt(SUBTITLE_SONG, SUBTITLE_ENVELOPE_APPLY_FALSE, "cancion", tmp_path)

    names = sorted(p.name for p in paths)
    assert names == ["cancion-en.srt", "cancion-es.srt"]
    for p in paths:
        assert p.exists()


def test_write_srt_cue_format_and_content(tmp_path):
    paths = write_srt(SUBTITLE_SONG, SUBTITLE_ENVELOPE_APPLY_FALSE, "cancion", tmp_path)
    es_path = next(p for p in paths if p.name == "cancion-es.srt")
    content = es_path.read_text(encoding="utf-8")

    assert content == (
        "1\n"
        "00:00:00,000 --> 00:00:10,000\n"
        "hola mundo bonito\n"
        "\n"
        "2\n"
        "00:00:10,000 --> 00:00:15,500\n"
        "vamos a bailar\nahora\n"
        "\n"
    )


def test_write_srt_excludes_lead_in_when_apply_false(tmp_path):
    paths = write_srt(SUBTITLE_SONG, SUBTITLE_ENVELOPE_APPLY_FALSE, "cancion", tmp_path)
    es_path = next(p for p in paths if p.name == "cancion-es.srt")
    assert "00:00:00,000 --> 00:00:10,000" in es_path.read_text(encoding="utf-8")


def test_write_srt_includes_lead_in_when_apply_true(tmp_path):
    paths = write_srt(SUBTITLE_SONG, SUBTITLE_ENVELOPE_APPLY_TRUE, "cancion", tmp_path)
    es_path = next(p for p in paths if p.name == "cancion-es.srt")
    # 0.0 + 7.0 leadIn -> 00:00:07,000
    assert "00:00:07,000 --> 00:00:17,000" in es_path.read_text(encoding="utf-8")


def test_write_lrc_one_file_per_language_with_tags(tmp_path):
    paths = write_lrc(SUBTITLE_SONG, SUBTITLE_ENVELOPE_APPLY_FALSE, "cancion", tmp_path)

    names = sorted(p.name for p in paths)
    assert names == ["cancion-en.lrc", "cancion-es.lrc"]

    es_path = next(p for p in paths if p.name == "cancion-es.lrc")
    content = es_path.read_text(encoding="utf-8")
    assert "[ti:Cancion]" in content
    assert "[ar:Chango Pepper]" in content
    assert "[00:00.00]hola mundo bonito" in content


def test_write_lrc_includes_lead_in_when_apply_true(tmp_path):
    paths = write_lrc(SUBTITLE_SONG, SUBTITLE_ENVELOPE_APPLY_TRUE, "cancion", tmp_path)
    es_path = next(p for p in paths if p.name == "cancion-es.lrc")
    assert "[00:07.00]hola mundo bonito" in es_path.read_text(encoding="utf-8")


def test_write_lrc_omits_tags_when_song_has_no_title_or_artist(tmp_path):
    song = {"lyrics": [{"es": "una linea"}]}
    envelope = {
        "timelineVersion": 2,
        "leadIn": {"durationSec": 0.0, "source": "measured", "confidence": "low", "apply": False},
        "timeline": [{"start": 0.0, "end": 1.0}],
    }

    paths = write_lrc(song, envelope, "sinatitulo", tmp_path)

    content = paths[0].read_text(encoding="utf-8")
    assert "[ti:" not in content
    assert "[ar:" not in content


# ---------------------------------------------------------------------------
# write_html_review — B16, the self-contained review page
# ---------------------------------------------------------------------------

HTML_ANCHORS = [
    LineAnchor(0, 10.0, "HIGH", ("clean-anchor",), "hola mundo bonito", 0),
    LineAnchor(1, 55.88, "REVIEW", ("ambiguous",), "fui mas impulso que voz", 0),
    LineAnchor(2, None, "FAIL", ("no-anchor",), "", None),
]
HTML_LINES = ["hola mundo", "fui mas impulso que voz", "no encontrado"]
HTML_ENTRIES = [
    TimelineEntry(10.0, 20.0),
    TimelineEntry(55.88, 59.52),
    TimelineEntry(59.52, 60.52),
]


def render_html(tmp_path, **overrides):
    """Render a review page into a staging dir with the audio sitting in a
    sibling directory — the real layout, where the relative path has to
    climb out of staging."""
    staging = overrides.pop("staging_dir", None) or tmp_path / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    audio = overrides.pop("audio_path", None) or audio_dir / "Song Libertad.m4a"
    audio.write_bytes(b"")
    out = staging / "cancion-review.html"

    kwargs = {
        "song_title": "Libertad",
        "song_path": tmp_path / "libertad.json",
        "audio_path": audio,
        "staging_dir": staging,
        "words_path": staging / "asr-words.jsonl",
        "lang": "es",
        "provenance": PROVENANCE,
        "lead_in": 10.0,
        "anchors": HTML_ANCHORS,
        "lines": HTML_LINES,
        "line_entries": HTML_ENTRIES,
        "out_path": out,
    }
    kwargs.update(overrides)
    write_html_review(**kwargs)
    return out.read_text(encoding="utf-8")


def test_write_html_review_renders_title_and_every_line(tmp_path):
    html = render_html(tmp_path)

    assert "Libertad" in html
    for line in HTML_LINES:
        assert line in html


def test_write_html_review_makes_no_network_requests(tmp_path):
    """Bombista running fully offline is a stated product property
    (backlog §1). A single external reference silently breaks it, and it
    breaks *quietly* — the page still renders, just unstyled or inert. No
    CDN, no webfont, no XHR: this assertion is the guard."""
    html = render_html(tmp_path)

    for forbidden in (
        "http://",
        "https://",
        'src="//',
        "@import",
        "fetch(",
        "XMLHttpRequest",
        "<link",
        "cdn.",
    ):
        assert forbidden not in html, f"external reference in the page: {forbidden!r}"


def test_write_html_review_references_audio_by_relative_url_encoded_path(tmp_path):
    """The page lives beside the run's other output, so the audio is
    reachable relatively — and must stay reachable when the staging dir is
    moved or copied. Spaces in the filename have to be percent-encoded or
    the browser will not resolve the href."""
    html = render_html(tmp_path)
    audio = tmp_path / "audio" / "Song Libertad.m4a"

    assert 'src="../audio/Song%20Libertad.m4a"' in html
    assert f'src="{audio}"' not in html  # the media reference is never absolute


def test_write_html_review_play_controls_carry_raw_audio_clock_starts(tmp_path):
    """The play button seeks the AUDIO, so its time must be the raw
    audio-clock second — the same clock as the QA report and `--anchor`,
    NOT the lead-in-normalised clock of the emitted timeline. Line 0 here
    starts at 10.00 s of audio, not 0.00."""
    html = render_html(tmp_path)

    assert 'data-start="10.00"' in html
    assert 'data-start="55.88"' in html
    assert 'data-start="59.52"' in html


def test_write_html_review_puts_flagged_lines_in_a_needs_attention_section(tmp_path):
    """A triage view, not a table dump: REVIEW and FAIL lines are lifted
    out where they cannot be scrolled past."""
    html = render_html(tmp_path)

    assert 'id="needs-attention"' in html
    section = html.split('id="needs-attention"', 1)[1].split("</section>", 1)[0]
    assert "fui mas impulso que voz" in section  # REVIEW
    assert "no encontrado" in section  # FAIL
    assert "hola mundo" not in section  # HIGH stays in the full table


def test_write_html_review_says_so_when_nothing_is_flagged(tmp_path):
    html = render_html(
        tmp_path,
        anchors=[LineAnchor(0, 10.0, "HIGH", ("clean-anchor",), "hola", 0)],
        lines=["hola mundo"],
        line_entries=[TimelineEntry(10.0, 20.0)],
    )

    section = html.split('id="needs-attention"', 1)[1].split("</section>", 1)[0]
    assert "None" in section


def test_write_html_review_pre_writes_the_anchor_rerun_command_per_flagged_line(tmp_path):
    html = render_html(tmp_path)

    assert "--anchor 1=" in html
    assert "--anchor 2=" in html
    assert "--words" in html
    assert "--lang es" in html
    assert "--anchor 0=" not in html  # line 0 anchored HIGH


def test_write_html_review_header_carries_the_provenance_block(tmp_path):
    """A review page that does not say what it reviewed is how the 17 s
    Tragedia error stayed invisible (B1)."""
    html = render_html(tmp_path)

    assert PROVENANCE["sha256"] in html
    assert PROVENANCE["model"] in html
    assert PROVENANCE["extractedAt"] in html
    assert PROVENANCE["toolVersion"] in html
    assert "120.00 s" in html  # durationSec, rendered


def test_write_html_review_renders_unknown_duration_when_the_container_was_unreadable(tmp_path):
    html = render_html(tmp_path, provenance={**PROVENANCE, "durationSec": None})

    assert "unknown" in html
    assert "None" not in html.split('id="needs-attention"')[0]


def test_write_html_review_escapes_lyric_text(tmp_path):
    """Lyrics are arbitrary text and go straight into the markup."""
    html = render_html(
        tmp_path,
        anchors=[LineAnchor(0, 1.0, "HIGH", ("clean-anchor",), "", 0)],
        lines=['<script>alert("x")</script> & co'],
        line_entries=[TimelineEntry(1.0, 2.0)],
    )

    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "&amp; co" in html


def test_write_html_review_shows_band_signals_and_durations(tmp_path):
    html = render_html(tmp_path)

    assert "clean-anchor" in html
    assert "ambiguous" in html
    assert "no-anchor" in html
    assert "REVIEW" in html
    assert "FAIL" in html


def test_write_html_review_returns_the_path_it_wrote(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    out = staging / "cancion-review.html"

    result = write_html_review(
        song_title="T",
        song_path=tmp_path / "t.json",
        audio_path=audio,
        staging_dir=staging,
        words_path=staging / "asr-words.jsonl",
        lang="es",
        provenance=PROVENANCE,
        lead_in=0.0,
        anchors=[LineAnchor(0, 0.0, "HIGH", ("clean-anchor",), "x", 0)],
        lines=["x"],
        line_entries=[TimelineEntry(0.0, 1.0)],
        out_path=out,
    )

    assert result == out
    assert out.exists()


def test_write_html_review_shell_quotes_paths_in_the_anchor_command(tmp_path):
    """Click-to-copy is only worth having if the pasted command actually
    runs. Real audio filenames have spaces in them — "Song Libertad.m4a" —
    and an unquoted path silently becomes two arguments."""
    page = render_html(tmp_path)
    audio = tmp_path / "audio" / "Song Libertad.m4a"

    # what click-to-copy puts on the clipboard is the element's textContent,
    # i.e. the markup-unescaped command
    raw = re.search(r'<code class="cmd">(.*?)</code>', page, re.S).group(1)
    command = unescape(raw)

    argv = shlex.split(command)
    assert str(audio) in argv  # one argument, not two
    assert argv[:2] == ["bombista", "align"]  # B11: the primary verb
    assert "--anchor" in argv
