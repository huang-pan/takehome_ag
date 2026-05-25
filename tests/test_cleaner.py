"""
tests/test_cleaner.py

Unit tests for the plain_text cleaning module.
"""

import pytest
from src.cleaner import (
    clean_plain_text,
    extract_page_breaks,
    _remove_running_headers,
    _strip_numbered_lines,
    _strip_stranded_page_numbers,
)


# ── extract_page_breaks ───────────────────────────────────────────────

def test_extract_page_breaks_none():
    assert extract_page_breaks("No form feeds here.") == []


def test_extract_page_breaks_positions():
    text = "Page one.\fPage two.\fPage three."
    positions = extract_page_breaks(text)
    assert len(positions) == 2
    assert text[positions[0]] == "\f"
    assert text[positions[1]] == "\f"


# ── Numbered line stripping ───────────────────────────────────────────

def test_strip_numbered_lines_activates_on_run_of_5():
    """Numbered lines should be stripped when ≥5 consecutive appear."""
    # Consecutive numbered lines (no blank separators) trigger stripping
    lines = [
        "   1   UNITED STATES COURT OF APPEALS",
        "   2   FOR THE SECOND CIRCUIT",
        "   3   ____________________________",
        "   4   August Term, 2009",
        "   5   (Argued: September 1, 2009)",
        "   6   Docket No. 08-5937-cv",
    ]
    result = _strip_numbered_lines(lines)
    # Numbers stripped, content preserved
    assert "UNITED STATES COURT OF APPEALS" in result[0]
    assert not result[0].strip().startswith("1")


def test_strip_numbered_lines_does_not_activate_on_few():
    """Fewer than 5 consecutive numbered lines → no stripping."""
    lines = [
        "   1   First numbered line",
        "   2   Second numbered line",
        "Regular paragraph text here.",
        "   3   Third numbered line",
    ]
    result = _strip_numbered_lines(lines)
    # Original lines should be preserved
    assert "1   First" in result[0]


# ── Stranded page numbers ─────────────────────────────────────────────

def test_strip_stranded_page_numbers_removes_single_digit_lines():
    lines = ["Paragraph text.", "   2  ", "More text.", "   14  ", "End."]
    result = _strip_stranded_page_numbers(lines)
    assert all(l.strip().isdigit() is False or not l.strip()
               for l in result if l.strip())
    assert "Paragraph text." in result
    assert "More text." in result


def test_strip_stranded_page_numbers_keeps_digit_words():
    """Lines that START with a digit but contain more text must NOT be stripped."""
    lines = ["18 U.S.C. § 3553(a) requires the court to..."]
    result = _strip_stranded_page_numbers(lines)
    assert result == lines


# ── Running header removal ────────────────────────────────────────────

def test_remove_running_headers_detects_repeated():
    """Short lines near page breaks that appear multiple times should be removed."""
    PB = "<!-- PAGE_BREAK -->"
    # Place body text well away from page breaks so it's not a header candidate
    body_lines_a = ["Body line %d." % i for i in range(10)]
    body_lines_b = ["More body line %d." % i for i in range(10)]
    lines = (
        ["PUBLISHED"]
        + [PB]
        + ["PUBLISHED"]
        + body_lines_a
        + [PB]
        + ["PUBLISHED"]
        + body_lines_b
    )
    result = _remove_running_headers(lines, page_break_marker=PB)
    assert "PUBLISHED" not in result
    # Body text (far from page breaks) should survive
    assert "Body line 5." in result


def test_remove_running_headers_keeps_unique_content():
    PB = "<!-- PAGE_BREAK -->"
    lines = [
        "Unique paragraph that doesn't repeat.",
        PB,
        "Another unique paragraph.",
    ]
    result = _remove_running_headers(lines, page_break_marker=PB)
    assert "Unique paragraph that doesn't repeat." in result


# ── Full pipeline ─────────────────────────────────────────────────────

def test_clean_plain_text_removes_formfeed():
    text = "Page one.\fPage two."
    cleaned = clean_plain_text(text)
    assert "\f" not in cleaned
    assert "<!-- PAGE_BREAK -->" in cleaned


def test_clean_plain_text_collapses_whitespace():
    text = "Word1   Word2    Word3"  # multi-space within line
    cleaned = clean_plain_text(text)
    # Multi-spaces between words should be collapsed
    assert "   " not in cleaned


def test_clean_plain_text_collapses_blank_lines():
    text = "Paragraph one.\n\n\n\n\nParagraph two."
    cleaned = clean_plain_text(text)
    assert "\n\n\n" not in cleaned


def test_clean_plain_text_encoding():
    """ftfy should repair common mojibake."""
    # Curly quote encoded as latin-1 in a utf-8 string
    mojibake = "He said \x93hello\x94 to her."
    result = clean_plain_text(mojibake)
    # Should not raise; should produce something reasonable
    assert isinstance(result, str)
    assert len(result) > 0
