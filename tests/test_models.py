"""
Tests for the Word model — the interchange type between the aligner
(which produces recognized words with timestamps) and the anchoring
stage (which consumes them).
"""
import pytest

from timeline_extractor.models import Word


def test_word_carries_text_and_times():
    w = Word(text="acuestan", start=1.02, end=1.48)
    assert w.text == "acuestan"
    assert w.start == 1.02
    assert w.end == 1.48


def test_word_is_immutable():
    w = Word(text="cama", start=2.0, end=2.3)
    with pytest.raises(Exception):
        w.text = "otra"


def test_word_rejects_negative_times():
    with pytest.raises(ValueError):
        Word(text="mal", start=-0.5, end=0.2)
