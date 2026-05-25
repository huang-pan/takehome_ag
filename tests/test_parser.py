"""
tests/test_parser.py

Unit tests for the HTML format detection and parsing module.
"""

import pytest
from bs4 import BeautifulSoup

from src.parser import HtmlFormat, detect_format, parse_html


# ── detect_format ─────────────────────────────────────────────────────

def test_detect_xml_opinion_with_prolog():
    html = '<?xml version="1.0" encoding="utf-8"?>\n<opinion type="majority"><p>Hello</p></opinion>'
    assert detect_format(html) == HtmlFormat.XML_OPINION


def test_detect_xml_opinion_bare():
    html = '<opinion type="majority"><p>Hello</p></opinion>'
    assert detect_format(html) == HtmlFormat.XML_OPINION


def test_detect_div_center():
    html = '<div>\n<center><b>598 F.3d 1061</b></center>\n<p>Text.</p>\n</div>'
    assert detect_format(html) == HtmlFormat.DIV_CENTER


def test_detect_empty():
    assert detect_format("") == HtmlFormat.EMPTY
    assert detect_format("   \n  ") == HtmlFormat.EMPTY


# ── parse_html ────────────────────────────────────────────────────────

def test_parse_xml_opinion_returns_soup():
    html = '<?xml version="1.0"?>\n<opinion type="majority"><p id="p1">Body text.</p></opinion>'
    soup = parse_html(html, HtmlFormat.XML_OPINION)
    assert isinstance(soup, BeautifulSoup)
    p = soup.find("p")
    assert p is not None
    assert "Body text." in p.get_text()


def test_parse_div_center_returns_soup():
    html = '<div><center><h1>Case Name</h1></center><p>Opinion text.</p></div>'
    soup = parse_html(html, HtmlFormat.DIV_CENTER)
    assert isinstance(soup, BeautifulSoup)
    h1 = soup.find("h1")
    assert h1 is not None
    assert "Case Name" in h1.get_text()


def test_parse_malformed_xml_falls_back():
    """Malformed XML (unclosed tag) should still produce a parseable tree."""
    html = '<?xml version="1.0"?>\n<opinion type="majority"><p>Unclosed para'
    soup = parse_html(html, HtmlFormat.XML_OPINION)
    # Should not raise; soup should have some content
    assert isinstance(soup, BeautifulSoup)
    text = soup.get_text()
    assert "Unclosed para" in text


def test_parse_without_explicit_format():
    """parse_html should auto-detect format if none provided."""
    html = '<?xml version="1.0"?>\n<opinion type="majority"><p>Hello</p></opinion>'
    soup = parse_html(html)
    assert soup.find("p") is not None


def test_parse_div_with_citations():
    html = (
        '<div><p>See <span class="citation"><a href="/opinion/123/">Smith v. Jones</a></span>.</p></div>'
    )
    soup = parse_html(html, HtmlFormat.DIV_CENTER)
    span = soup.find("span", class_="citation")
    assert span is not None


# ── Real-data shape tests ─────────────────────────────────────────────

def test_xml_opinion_type_attribute():
    html = '<?xml version="1.0"?>\n<opinion type="dissent"><p>Dissenting text.</p></opinion>'
    soup = parse_html(html, HtmlFormat.XML_OPINION)
    opinion_tag = soup.find("opinion")
    assert opinion_tag is not None
    assert opinion_tag.get("type") == "dissent"
