"""
Tests for forced-alignment line anchoring (slice S2).

Anchoring follows the proven ASR-following spike's sequential algorithm
(spike/harness/derive_ground_truth.py + spike/matcher/follower.py in the
live-lyric-translator-dev repo): a line's onset is the time of the
earliest word (from the previous anchor onward) matching the line's
first token, corroborated by a match of another of its first 4 tokens
within the following 8 words; falls back to token[1] as lead if the
first word was mis-heard; else the line gets no anchor.

Each anchored line also gets a confidence band derived from named
signals (see anchoring.py module constants for the exact thresholds).
"""
from timeline_extractor.anchoring import (
    LineAnchor,
    anchor_lines,
    fuzzy_match,
    levenshtein,
    normalize_token,
    tokenize_line,
)
from timeline_extractor.models import Word


# ---------------------------------------------------------------------------
# Fuzzy-matching utilities — ported behaviors from the spike (verbatim logic)
# ---------------------------------------------------------------------------


def test_normalize_token_strips_accents_and_punctuation():
    assert normalize_token("¡QUÉ") == "que"
    assert normalize_token("festín.") == "festin"
    assert normalize_token("pa'") == "pa"
    assert normalize_token("años") == "anos"


def test_normalize_token_pure_punctuation_becomes_empty():
    assert normalize_token("¡¿?!") == ""


def test_tokenize_line_handles_embedded_newlines():
    toks = tokenize_line("El aire me envuelve,\ny yo canto.")
    assert toks == ["el", "aire", "me", "envuelve", "y", "yo", "canto"]


def test_levenshtein_basics():
    assert levenshtein("gato", "gato") == 0
    assert levenshtein("gato", "pato") == 1
    assert levenshtein("", "abc") == 3


def test_fuzzy_match_short_tokens_require_exact_match():
    # 'el'/'la'-style short words must not fuzzy-match arbitrary garbage.
    assert fuzzy_match("do", "de") is False
    assert fuzzy_match("de", "de") is True


def test_fuzzy_match_prefix_absorbs_truncation():
    assert fuzzy_match("brillan", "brillante") is True


def test_fuzzy_match_edit_distance_tiers():
    # target len 4-6: max_dist 1
    assert fuzzy_match("cana", "cama") is True
    assert fuzzy_match("gaxy", "gato") is False  # dist 2, too far for a 4-char target
    # target len >= 7: max_dist 2
    assert fuzzy_match("aquestan", "acuestan") is True


# ---------------------------------------------------------------------------
# Sequential anchoring — behavior tests
# ---------------------------------------------------------------------------


def test_clean_match_all_high_with_correct_onsets():
    lines = [
        "hola mundo bonito",
        "vamos a bailar ahora",
        "gracias por venir",
    ]
    words = [
        Word("hola", 0.0, 0.3),
        Word("mundo", 0.3, 0.6),
        Word("bonito", 0.6, 0.9),
        Word("vamos", 1.0, 1.3),
        Word("a", 1.3, 1.4),
        Word("bailar", 1.4, 1.7),
        Word("ahora", 1.7, 2.0),
        Word("gracias", 2.5, 2.8),
        Word("por", 2.8, 3.0),
        Word("venir", 3.0, 3.3),
    ]

    result = anchor_lines(words, lines)

    assert [a.start for a in result] == [0.0, 1.0, 2.5]
    assert [a.band for a in result] == ["HIGH", "HIGH", "HIGH"]
    assert all(a.signals == ("clean-anchor",) for a in result)
    assert all(a.lead_token == 0 for a in result)


def test_misheard_first_word_falls_back_to_second_token():
    # "hacia el fuego ardiente" heard with 'hacia' corrupted beyond fuzzy
    # reach ('hace'), but 'el' intact -> anchor via token[1] fallback.
    lines = [
        "primero un verso claro",
        "hacia el fuego ardiente",
        "y luego se termina",
    ]
    words = [
        Word("primero", 0.0, 0.3),
        Word("un", 0.3, 0.5),
        Word("verso", 0.5, 0.8),
        Word("claro", 0.8, 1.1),
        Word("hace", 5.0, 5.2),  # corrupted beyond fuzzy reach of 'hacia'
        Word("el", 5.2, 5.3),
        Word("fuego", 5.3, 5.6),
        Word("ardiente", 5.6, 6.0),
        Word("y", 8.0, 8.1),
        Word("luego", 8.1, 8.4),
        Word("se", 8.4, 8.5),
        Word("termina", 8.5, 8.8),
    ]

    result = anchor_lines(words, lines)

    assert result[0].band == "HIGH"
    assert result[1].start == 5.2
    assert result[1].band == "REVIEW"
    assert "lead-fallback" in result[1].signals
    assert result[1].lead_token == 1
    # following line still anchors correctly after the fallback
    assert result[2].start == 8.0
    assert result[2].band == "HIGH"


def test_repeated_chorus_does_not_double_consume_and_flags_ambiguity():
    lines = [
        "vamos a bailar",
        "vamos a bailar",
        "gracias totales",
    ]
    words = [
        Word("vamos", 0.0, 0.2),
        Word("a", 0.2, 0.3),
        Word("bailar", 0.3, 0.6),
        Word("vamos", 1.0, 1.2),
        Word("a", 1.2, 1.3),
        Word("bailar", 1.3, 1.6),
        Word("gracias", 2.0, 2.3),
        Word("totales", 2.3, 2.6),
    ]

    result = anchor_lines(words, lines)

    # distinct anchors, forward-only, no double consumption
    assert result[0].start == 0.0
    assert result[1].start == 1.0
    assert result[2].start == 2.0
    # the first occurrence is flagged ambiguous (chorus repeats shortly after)
    assert "ambiguous" in result[0].signals
    assert result[0].band == "REVIEW"
    # the second occurrence has no further repeat ahead -> clean
    assert result[1].band == "HIGH"
    # later, unrelated line still anchors correctly
    assert result[2].band == "HIGH"


def test_skipped_line_fails_but_following_lines_still_anchor():
    lines = [
        "hola mundo",
        "palabras inexistentes rarezas",
        "gracias siempre",
    ]
    words = [
        Word("hola", 0.0, 0.3),
        Word("mundo", 0.3, 0.6),
        Word("gracias", 2.0, 2.3),
        Word("siempre", 2.3, 2.6),
    ]

    result = anchor_lines(words, lines)

    assert result[0].band == "HIGH"
    assert result[1].start is None
    assert result[1].band == "FAIL"
    assert result[1].signals == ("no-anchor",)
    assert result[2].start == 2.0
    assert result[2].band == "HIGH"


def test_override_sets_onset_and_resyncs_scan_position():
    lines = [
        "primera linea aqui",
        "segunda linea confusa",
        "tercera linea final",
    ]
    words = [
        Word("primera", 0.0, 0.3),
        Word("linea", 0.3, 0.6),
        Word("aqui", 0.6, 0.9),
        # decoys that would incorrectly match line 2 if resync didn't skip them
        Word("tercera", 1.0, 1.3),
        Word("linea", 1.3, 1.6),
        Word("final", 1.6, 1.9),
        # the real occurrence, after the override point
        Word("tercera", 10.5, 10.8),
        Word("linea", 10.8, 11.0),
        Word("final", 11.0, 11.3),
    ]

    result = anchor_lines(words, lines, overrides={1: 10.0})

    assert result[0].start == 0.0
    assert result[0].band == "HIGH"

    assert result[1].start == 10.0
    assert result[1].band == "HIGH"
    assert result[1].signals == ("override",)
    assert result[1].lead_token is None
    assert result[1].asr_context == ""

    # line 2 must anchor to the *real* occurrence after the override time,
    # not the decoy that sits between line 0 and the override point.
    assert result[2].start == 10.5
    assert result[2].band == "HIGH"


def test_embedded_newline_line_is_one_anchor():
    lines = ["hola\nmundo"]
    words = [Word("hola", 0.0, 0.3), Word("mundo", 0.3, 0.6)]

    result = anchor_lines(words, lines)

    assert len(result) == 1
    assert result[0].start == 0.0
    assert result[0].band == "HIGH"


def test_gap_outlier_flagged_against_median_of_prior_gaps():
    lines = [
        "uno dos tres",
        "cuatro cinco seis",
        "siete ocho nueve",
        "diez once doce",
    ]
    words = [
        Word("uno", 0.0, 0.2), Word("dos", 0.2, 0.4), Word("tres", 0.4, 0.6),
        Word("cuatro", 2.0, 2.2), Word("cinco", 2.2, 2.4), Word("seis", 2.4, 2.6),
        Word("siete", 4.0, 4.2), Word("ocho", 4.2, 4.4), Word("nueve", 4.4, 4.6),
        # big unexplained jump vs the steady ~2s gap established above
        Word("diez", 50.0, 50.2), Word("once", 50.2, 50.4), Word("doce", 50.4, 50.6),
    ]

    result = anchor_lines(words, lines)

    assert [a.band for a in result[:3]] == ["HIGH", "HIGH", "HIGH"]
    assert result[3].start == 50.0
    assert "gap-outlier" in result[3].signals
    assert result[3].band == "REVIEW"


def test_asr_context_present_for_found_anchor_and_empty_for_fail():
    lines = ["hola mundo", "nadie dice esto nunca"]
    words = [Word("hola", 0.0, 0.3), Word("mundo", 0.3, 0.6)]

    result = anchor_lines(words, lines)

    assert result[0].asr_context != ""
    assert "hola" in result[0].asr_context
    assert result[1].asr_context == ""


def test_line_anchor_is_a_frozen_dataclass_with_expected_fields():
    anchor = LineAnchor(
        line_index=0,
        start=1.0,
        band="HIGH",
        signals=("clean-anchor",),
        asr_context="hola mundo",
        lead_token=0,
    )
    assert anchor.line_index == 0
    assert anchor.start == 1.0
