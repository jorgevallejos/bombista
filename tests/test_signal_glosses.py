"""
Plain-language glosses for the confidence signals — B20 §8.3.

`anchor_lines` emits bare tokens (`lead-fallback`, `gap-outlier`, …). They
are printed in the markdown QA report, in the report JSON and on B16's
HTML page, and a user who has not read `anchoring.py` cannot act on any of
them. One sentence per signal, living beside the signal names so all three
writers say the same words.

These tests are structural and synthetic — no whisper model, no audio (see
CLAUDE.md, Development Protocol).
"""
from __future__ import annotations

import ast
import inspect
import json
import re
import textwrap
from html import unescape
from pathlib import Path

from bombista import anchoring, report, writers
from bombista.anchoring import SIGNAL_GLOSSES, LineAnchor
from bombista.models import TimelineEntry
from bombista.report import render_qa_report
from bombista.writers import write_html_review, write_report_json

NOT_PROBLEMS = {"clean-anchor", "override"}
"""The only two signals that are not problems, named explicitly rather
than letting the "every problem has a sentence" test wave any empty value
through. `clean-anchor` means nothing happened; `override` means the human
already decided. Neither has anything to tell a user."""


# ---------------------------------------------------------------------------
# the signal set, read out of anchor_lines rather than listed here
# ---------------------------------------------------------------------------


def emitted_signal_names() -> set[str]:
    """Every signal name `anchor_lines` can put in a `LineAnchor`, derived
    from its source.

    Deliberately not a literal list: a hardcoded one drifts silently the
    day a new signal is added, which is the exact failure this whole item
    exists to prevent. Two shapes carry a signal name in that function —
    `signals.append("…")` and a tuple literal handed to `LineAnchor` —
    and both are read here.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(anchoring.anchor_lines)))
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "signals"
        ):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    names.add(arg.value)
        if isinstance(node, ast.Tuple):
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    names.add(elt.value)
    return names


def test_the_deriver_still_matches_the_source():
    """Guard against a vacuous pass: if `anchor_lines` is refactored into a
    shape this reader does not recognise it returns an empty set, and every
    test built on it would pass while proving nothing."""
    names = emitted_signal_names()

    assert len(names) >= 7, (
        f"only found {sorted(names)} in anchor_lines — the reader has stopped "
        "matching the source, so the coverage test below is not proving anything"
    )


def test_every_emitted_signal_has_a_gloss():
    missing = emitted_signal_names() - set(SIGNAL_GLOSSES)

    assert not missing, f"signals with no gloss: {sorted(missing)}"


def test_every_problem_signal_has_a_sentence():
    for name in sorted(emitted_signal_names() - NOT_PROBLEMS):
        assert SIGNAL_GLOSSES[name].strip(), f"{name} has no plain-language sentence"


def test_the_two_non_problems_are_the_only_empty_glosses():
    empty = {name for name, gloss in SIGNAL_GLOSSES.items() if not gloss.strip()}

    assert empty == NOT_PROBLEMS


def _internal_names() -> set[str]:
    """Every name a gloss must not mention: this package's module names,
    `anchoring`'s functions, and its tuning constants."""
    names = {
        path.stem
        for path in Path(anchoring.__file__).parent.glob("*.py")
        if not path.stem.startswith("__")
    }
    for name, value in vars(anchoring).items():
        if name.startswith("__"):
            continue
        if inspect.isfunction(value) and value.__module__ == anchoring.__name__:
            names.add(name)
        elif re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            names.add(name)
    return names


def test_no_gloss_names_a_function_a_module_or_a_threshold():
    """The gloss is for someone who has never read the source. It says what
    the tool observed and where to listen — never what the code did."""
    internal = _internal_names()

    for signal, gloss in SIGNAL_GLOSSES.items():
        lowered = gloss.lower()
        named = sorted(n for n in internal if n.lower() in lowered)
        assert not named, f"{signal}'s gloss names {named}"


def test_the_glosses_are_defined_once():
    """report.py and writers.py import the mapping; neither keeps a copy
    that can drift out of step with the other two surfaces."""
    assert report.SIGNAL_GLOSSES is SIGNAL_GLOSSES
    assert writers.SIGNAL_GLOSSES is SIGNAL_GLOSSES


# ---------------------------------------------------------------------------
# the three surfaces that print signals
# ---------------------------------------------------------------------------

LINES = ["hola mundo", "desde nino quiere mas que latir", "no encontrado"]
ANCHORS = [
    LineAnchor(0, 10.0, "HIGH", ("clean-anchor",), "hola mundo bonito", 0),
    LineAnchor(1, 37.54, "REVIEW", ("lead-fallback", "gap-outlier"), "nino quiere mas", 1),
    LineAnchor(2, None, "FAIL", ("no-anchor",), "", None),
]
ENTRIES = [
    TimelineEntry(10.0, 37.54),
    TimelineEntry(37.54, 41.20),
    TimelineEntry(41.20, 42.20),
]
PROVENANCE = {
    "audio": "songs/audio/pimiento.m4a",
    "sha256": "4f2a9c" + "0" * 58,
    "durationSec": 172.4,
    "model": "faster-whisper:medium",
    "device": "cpu/int8",
    "lang": "es",
    "extractedAt": "2026-08-15T16:45:34+02:00",
    "toolVersion": "bombista 0.9.0",
}
LEAD_IN_BLOCK = {
    "durationSec": 8.92,
    "source": "measured",
    "confidence": "low",
    "apply": False,
}
FLAGGED_SIGNALS = ("lead-fallback", "gap-outlier", "no-anchor")


def test_the_qa_report_spells_out_the_signal_for_each_flagged_line():
    rendered = render_qa_report(
        anchors=ANCHORS,
        lines=LINES,
        line_entries=ENTRIES,
        lead_in=8.92,
        song_title="Pimiento",
        song_path=Path("songs/pimiento.json"),
        audio_path=Path(PROVENANCE["audio"]),
        model_size="medium",
        lang="es",
        staging_dir=Path("staging/pimiento"),
        provenance=PROVENANCE,
    )

    for signal in FLAGGED_SIGNALS:
        assert SIGNAL_GLOSSES[signal] in rendered, f"{signal} printed as a bare token"


def test_the_html_review_page_spells_out_the_signal_for_each_flagged_line(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    audio = tmp_path / "pimiento.m4a"
    audio.write_bytes(b"")
    out = staging / "pimiento-review.html"

    write_html_review(
        song_title="Pimiento",
        song_path=tmp_path / "pimiento.json",
        audio_path=audio,
        staging_dir=staging,
        words_path=staging / "asr-words.jsonl",
        lang="es",
        provenance=PROVENANCE,
        lead_in=8.92,
        anchors=ANCHORS,
        lines=LINES,
        line_entries=ENTRIES,
        out_path=out,
    )
    # Unescaped: the page escapes its text, so a gloss carrying an
    # apostrophe reaches the file as `song&#x27;s`.
    html = unescape(out.read_text(encoding="utf-8"))

    for signal in FLAGGED_SIGNALS:
        assert SIGNAL_GLOSSES[signal] in html, f"{signal} printed as a bare token"


def test_the_report_json_carries_the_gloss_alongside_the_signal(tmp_path):
    out = tmp_path / "pimiento-report.json"

    result = write_report_json(
        provenance=PROVENANCE,
        lines_hash="sha256:abc123",
        lead_in_block=LEAD_IN_BLOCK,
        anchors=ANCHORS,
        lines=LINES,
        line_entries=ENTRIES,
        out_path=out,
    )
    by_index = {line["i"]: line for line in result["lines"]}

    assert by_index[1]["signalGlosses"] == {
        "lead-fallback": SIGNAL_GLOSSES["lead-fallback"],
        "gap-outlier": SIGNAL_GLOSSES["gap-outlier"],
    }
    assert by_index[2]["signalGlosses"] == {"no-anchor": SIGNAL_GLOSSES["no-anchor"]}
    # A signal with nothing to say adds no key — an empty string per line
    # would be noise in an audit document.
    assert "signalGlosses" not in by_index[0]
    assert json.loads(out.read_text(encoding="utf-8"))["lines"] == result["lines"]
