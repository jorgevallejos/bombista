"""
Tests for the pure timeline-building stage.

build_timeline turns per-line anchors + the word stream + the song's item
list into one TimelineEntry per item, per docs/output-contract.md. Every
item must be a lyric line (a dict carrying the chosen language key) —
section markers and meta entries are no longer supported and raise
ValueError naming the offending index. A lyric line runs from its anchor's
start to the NEXT lyric line's anchor start; the last lyric line ends at
the last transcribed word's end + LAST_LINE_PAD.
"""
import pytest

from bombista.anchoring import LineAnchor
from bombista.models import TimelineEntry, Word
from bombista.pipeline import (
    LAST_LINE_PAD,
    build_timeline,
    is_lyric_item,
    lyric_lines,
    normalize_to_lead_in,
)
from bombista.serializer import validate_timeline


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
    assert is_lyric_item("Chorus", "es") is False  # bare string


def test_lyric_lines_extracts_chosen_language_in_order():
    items = [
        {"es": "hola mundo", "en": "hello world"},
        {"es": "adios ya"},
    ]
    assert lyric_lines(items, "es") == ["hola mundo", "adios ya"]


def test_lyric_lines_raises_on_non_lyric_entry_naming_its_index():
    items = [
        {"es": "hola mundo"},
        {"type": "section", "label": "Bridge"},
        {"es": "adios ya"},
    ]
    with pytest.raises(ValueError, match=r"lyrics\[1\]"):
        lyric_lines(items, "es")


def test_lyric_lines_raises_on_bare_string_entry_naming_its_index():
    items = [{"es": "hola mundo"}, "Chorus"]
    with pytest.raises(ValueError, match=r"lyrics\[1\]"):
        lyric_lines(items, "es")


# ---------------------------------------------------------------------------
# build_timeline behaviors
# ---------------------------------------------------------------------------


def test_build_timeline_entries_are_one_to_one_with_items():
    items = [{"es": "hola mundo"}, {"es": "adios ya"}]
    anchors = [_anchor(0, 10.0), _anchor(1, 20.0)]
    words = _words_ending_at(22.0)

    entries = build_timeline(anchors, words, items, lang="es")

    assert len(entries) == len(items)
    assert entries[0].start == 10.0
    assert entries[0].end == entries[1].start == 20.0


def test_build_timeline_raises_on_non_lyric_entry_naming_its_index():
    items = [
        {"es": "hola mundo"},
        {"type": "section", "label": "Bridge"},
        {"es": "adios ya"},
    ]
    anchors = [_anchor(0, 10.0), _anchor(1, 20.0), _anchor(2, 25.0)]
    words = _words_ending_at(30.0)

    with pytest.raises(ValueError, match=r"lyrics\[1\]"):
        build_timeline(anchors, words, items, lang="es")


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


# ---------------------------------------------------------------------------
# normalize_to_lead_in (timeline v2, B12)
# ---------------------------------------------------------------------------


def test_normalize_to_lead_in_rebases_entry_zero_to_zero():
    raw = [TimelineEntry(7.26, 13.1), TimelineEntry(13.1, 16.9)]

    lead_in, normalized = normalize_to_lead_in(raw)

    assert lead_in == 7.26
    assert normalized[0].start == 0.0
    assert normalized[0].end == pytest.approx(5.84)
    assert normalized[1].start == pytest.approx(5.84)
    assert normalized[1].end == pytest.approx(9.64)


def test_normalize_to_lead_in_rounds_to_two_decimals():
    raw = [TimelineEntry(10.333333, 20.666666)]

    lead_in, normalized = normalize_to_lead_in(raw)

    assert lead_in == 10.33
    assert normalized[0] == TimelineEntry(0.0, round(20.666666 - 10.33, 2))


def test_normalize_to_lead_in_is_lossless_within_tolerance():
    """Re-adding lead_in to a normalised entry reproduces the raw value —
    within the contract's documented tolerance, not exact equality, since
    e.g. 13.1 - 7.26 == 5.840000000000001 in IEEE floats."""
    raw = [TimelineEntry(7.26, 13.1), TimelineEntry(13.1, 16.9)]

    lead_in, normalized = normalize_to_lead_in(raw)

    for raw_entry, norm_entry in zip(raw, normalized):
        assert abs((norm_entry.start + lead_in) - raw_entry.start) < 0.005
        assert abs((norm_entry.end + lead_in) - raw_entry.end) < 0.005


def test_normalize_to_lead_in_does_not_mutate_input():
    raw = [TimelineEntry(7.26, 13.1)]

    normalize_to_lead_in(raw)

    assert raw == [TimelineEntry(7.26, 13.1)]


def test_normalize_to_lead_in_empty_returns_zero_and_empty():
    lead_in, normalized = normalize_to_lead_in([])

    assert lead_in == 0.0
    assert normalized == []
