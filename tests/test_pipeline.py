"""
Tests for the pure timeline-building stage (slice S3).

build_timeline turns per-line anchors + the word stream + the song's full
item list into one TimelineEntry per item, per docs/output-contract.md:
markers get {0,0}; a lyric line runs from its anchor's start to the NEXT
lyric line's anchor start (display-card continuity — markers between
lyric lines don't break the chain); the last lyric line ends at the last
transcribed word's end + LAST_LINE_PAD.
"""
import pytest

from timeline_extractor.anchoring import LineAnchor
from timeline_extractor.models import TimelineEntry, Word
from timeline_extractor.pipeline import (
    LAST_LINE_PAD,
    build_timeline,
    is_lyric_item,
    lyric_lines,
)
from timeline_extractor.serializer import validate_timeline


def _anchor(i, start, band="HIGH", signals=("clean-anchor",)):
    lead = None if start is None else 0
    return LineAnchor(i, start, band, signals, "", lead)


def _words_ending_at(end):
    return [Word("fin", max(end - 0.3, 0.0), end)]


# ---------------------------------------------------------------------------
# Item classification
# ---------------------------------------------------------------------------


def test_is_lyric_item_requires_dict_with_chosen_language_key():
    assert is_lyric_item({"es": "hola mundo"}, "es") is True
    assert is_lyric_item({"en": "hello world"}, "es") is False  # wrong language
    assert is_lyric_item({"type": "section", "label": "Verse 1"}, "es") is False
    assert is_lyric_item("Chorus", "es") is False  # bare-string marker


def test_lyric_lines_extracts_chosen_language_in_order_skipping_markers():
    items = [
        {"type": "section", "label": "Verse 1"},
        {"es": "hola mundo", "en": "hello world"},
        "Chorus",
        {"es": "adios ya"},
    ]
    assert lyric_lines(items, "es") == ["hola mundo", "adios ya"]


# ---------------------------------------------------------------------------
# build_timeline behaviors
# ---------------------------------------------------------------------------


def test_markers_get_zero_length_placeholders():
    items = [
        {"type": "section", "label": "Verse 1"},
        {"es": "hola mundo"},
        "Chorus",
        {"es": "adios ya"},
    ]
    anchors = [_anchor(0, 10.0), _anchor(1, 20.0)]
    words = _words_ending_at(22.0)

    entries = build_timeline(anchors, words, items, lang="es")

    assert len(entries) == len(items)
    assert entries[0] == TimelineEntry(0.0, 0.0)
    assert entries[2] == TimelineEntry(0.0, 0.0)


def test_end_is_next_lyric_start_across_interleaved_marker():
    items = [
        {"es": "hola mundo"},
        {"type": "section", "label": "Bridge"},
        {"es": "adios ya"},
    ]
    anchors = [_anchor(0, 10.0), _anchor(1, 20.0)]
    words = _words_ending_at(22.0)

    entries = build_timeline(anchors, words, items, lang="es")

    # the marker between the two lyric lines does not break the chain
    assert entries[0].end == entries[2].start == 20.0


def test_last_line_end_is_last_word_end_plus_pad():
    items = [{"es": "hola mundo"}, {"es": "adios ya"}]
    anchors = [_anchor(0, 10.0), _anchor(1, 20.0)]
    words = _words_ending_at(23.5)

    entries = build_timeline(anchors, words, items, lang="es")

    assert entries[-1].end == pytest.approx(23.5 + LAST_LINE_PAD)


def test_fail_anchor_interpolates_between_anchored_neighbors():
    items = [{"es": "uno"}, {"es": "dos"}, {"es": "tres"}]
    anchors = [_anchor(0, 20.0), _anchor(1, None, band="FAIL", signals=("no-anchor",)), _anchor(2, 30.0)]
    words = _words_ending_at(32.0)

    entries = build_timeline(anchors, words, items, lang="es")

    assert entries[1].start == pytest.approx(25.0)
    assert entries[0].end == entries[1].start
    assert entries[1].end == entries[2].start == 30.0
    validate_timeline(entries)


def test_trailing_fail_anchor_stays_monotonic():
    items = [{"es": "uno"}, {"es": "dos"}, {"es": "tres"}]
    anchors = [_anchor(0, 10.0), _anchor(1, 20.0), _anchor(2, None, band="FAIL", signals=("no-anchor",))]
    words = _words_ending_at(28.0)

    entries = build_timeline(anchors, words, items, lang="es")

    assert 20.0 <= entries[2].start <= 28.0
    assert entries[2].end == pytest.approx(28.0 + LAST_LINE_PAD)
    validate_timeline(entries)


def test_leading_fail_anchor_stays_monotonic():
    items = [{"es": "uno"}, {"es": "dos"}]
    anchors = [_anchor(0, None, band="FAIL", signals=("no-anchor",)), _anchor(1, 10.0)]
    words = _words_ending_at(14.0)

    entries = build_timeline(anchors, words, items, lang="es")

    assert 0.0 <= entries[0].start <= 10.0
    assert entries[0].end == entries[1].start == 10.0
    validate_timeline(entries)


def test_output_passes_validate_timeline_with_mid_song_marker():
    items = [
        {"type": "section", "label": "Verse"},
        {"es": "uno"},
        {"type": "section", "label": "Chorus"},
        {"es": "dos"},
    ]
    anchors = [_anchor(0, 5.0), _anchor(1, 9.0)]
    words = _words_ending_at(12.0)

    entries = build_timeline(anchors, words, items, lang="es")

    validate_timeline(entries)  # must not raise despite the {0,0} at index 2


def test_embedded_newline_line_is_one_entry():
    items = [{"es": "gracias por venir\ny quedarse"}, {"es": "adios ya"}]
    anchors = [_anchor(0, 5.0), _anchor(1, 12.0)]
    words = _words_ending_at(14.0)

    entries = build_timeline(anchors, words, items, lang="es")

    assert len(entries) == 2
    assert entries[0] == TimelineEntry(5.0, 12.0)


def test_times_are_rounded_to_two_decimals():
    items = [{"es": "uno"}, {"es": "dos"}]
    anchors = [_anchor(0, 10.333333), _anchor(1, 20.666666)]
    words = _words_ending_at(22.111111)

    entries = build_timeline(anchors, words, items, lang="es")

    assert entries[0] == TimelineEntry(10.33, 20.67)
    assert entries[1].end == pytest.approx(round(22.111111 + LAST_LINE_PAD, 2))


def test_anchor_count_mismatch_raises():
    items = [{"es": "uno"}, {"es": "dos"}]
    anchors = [_anchor(0, 10.0)]

    with pytest.raises(ValueError):
        build_timeline(anchors, _words_ending_at(12.0), items, lang="es")
