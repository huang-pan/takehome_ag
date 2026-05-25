"""
tests/test_transformer.py

Unit tests for the HTML transformation module.
"""

import pytest
from bs4 import BeautifulSoup

from src.parser import HtmlFormat
from src.transformer import (
    transform,
    _normalise_star_pagination,
    _fix_citation_urls,
    _fix_footnotes,
    _remove_html_running_headers,
)


# ── Star pagination ───────────────────────────────────────────────────

def test_star_pagination_xml_format():
    """XML-format star-pagination span with label attribute → anchor link."""
    html = '<opinion type="majority"><p>Text <span citation-index="1" class="star-pagination" label="311"> *311 </span> continued.</p></opinion>'
    soup = BeautifulSoup(html, "html.parser")
    _normalise_star_pagination(soup, HtmlFormat.XML_OPINION)

    anchor = soup.find("a", id="star-311")
    assert anchor is not None, "Expected <a id='star-311'>"
    assert anchor.get("class") == ["star-page-inline"]
    assert anchor["data-page"] == "311"


def test_star_pagination_div_format():
    """div-format star-pagination span with text content → anchor link."""
    html = '<div><p>Text <span class="star-pagination">*414</span> more.</p></div>'
    soup = BeautifulSoup(html, "html.parser")
    _normalise_star_pagination(soup, HtmlFormat.DIV_CENTER)

    anchor = soup.find("a", id="star-414")
    assert anchor is not None, "Expected <a id='star-414'>"
    assert anchor["data-page"] == "414"


def test_star_pagination_anchor_href():
    """The anchor href should be a fragment pointing to itself."""
    html = '<p><span class="star-pagination" label="99"> *99 </span></p>'
    soup = BeautifulSoup(html, "html.parser")
    _normalise_star_pagination(soup, HtmlFormat.XML_OPINION)

    anchor = soup.find("a", id="star-99")
    assert anchor is not None
    assert anchor["href"] == "#star-99"


def test_star_pagination_no_page_number_left_intact():
    """A span with no discernible page number should survive without error."""
    html = '<p><span class="star-pagination"> * </span></p>'
    soup = BeautifulSoup(html, "html.parser")
    # Should not raise
    _normalise_star_pagination(soup, HtmlFormat.XML_OPINION)


# ── Citation URLs ─────────────────────────────────────────────────────

def test_citation_relative_url_made_absolute():
    html = '<p><a href="/opinion/123/smith-v-jones/">Smith v. Jones</a></p>'
    soup = BeautifulSoup(html, "html.parser")
    _fix_citation_urls(soup)

    a = soup.find("a")
    assert a["href"].startswith("https://www.courtlistener.com")
    assert a["href"] == "https://www.courtlistener.com/opinion/123/smith-v-jones/"


def test_citation_absolute_url_unchanged():
    html = '<p><a href="https://example.com/case">External link</a></p>'
    soup = BeautifulSoup(html, "html.parser")
    _fix_citation_urls(soup)

    a = soup.find("a")
    assert a["href"] == "https://example.com/case"


def test_citation_courtlistener_relative_paths():
    html = '<span class="citation"><a href="/c/F.3d/598/1061/">598 F.3d 1061</a></span>'
    soup = BeautifulSoup(html, "html.parser")
    _fix_citation_urls(soup)

    a = soup.find("a")
    assert a["href"] == "https://www.courtlistener.com/c/F.3d/598/1061/"


# ── Footnotes ─────────────────────────────────────────────────────────

def test_footnote_backref_added():
    """Back-reference link should be added to footnote divs that lack one."""
    html = '''
    <div class="footnotes">
      <div class="footnote" id="fn1" label="1">
        <p>Footnote text here.</p>
      </div>
    </div>
    '''
    soup = BeautifulSoup(html, "html.parser")
    _fix_footnotes(soup, HtmlFormat.XML_OPINION)

    backref = soup.find("a", class_="footnote-backref")
    assert backref is not None
    assert backref["href"] == "#fn1_ref"


def test_footnote_backref_not_duplicated():
    """If a back-reference already exists, don't add another."""
    html = '''
    <div class="footnotes">
      <div class="footnote" id="fn2" label="2">
        <p>Text.</p>
        <a class="footnote-backref" href="#fn2_ref">↩</a>
      </div>
    </div>
    '''
    soup = BeautifulSoup(html, "html.parser")
    _fix_footnotes(soup, HtmlFormat.XML_OPINION)

    backrefs = soup.find_all("a", class_="footnote-backref")
    assert len(backrefs) == 1, "Should not duplicate existing back-reference"


def test_footnote_forward_ref_gets_id():
    """Forward footnote references lacking an id should have one added."""
    html = '<p>See note.<a class="footnote" href="#fn1">1</a></p>'
    soup = BeautifulSoup(html, "html.parser")
    _fix_footnotes(soup, HtmlFormat.XML_OPINION)

    a = soup.find("a", class_="footnote")
    assert a.get("id") == "fn1_ref"


# ── Running header removal ────────────────────────────────────────────

def test_running_headers_removed():
    """Short paragraphs that appear ≥2 times should be dropped."""
    html = '''
    <opinion type="majority">
      <p>PUBLISHED</p>
      <p>First paragraph of the opinion body.</p>
      <p>PUBLISHED</p>
      <p>Second paragraph of the opinion body.</p>
    </opinion>
    '''
    soup = BeautifulSoup(html, "html.parser")
    _remove_html_running_headers(soup, HtmlFormat.XML_OPINION)

    paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
    assert "PUBLISHED" not in paragraphs
    assert "First paragraph of the opinion body." in paragraphs


def test_unique_paragraphs_preserved():
    """Paragraphs that appear only once must not be removed."""
    html = '''
    <opinion type="majority">
      <p>Unique first paragraph.</p>
      <p>Another unique paragraph.</p>
    </opinion>
    '''
    soup = BeautifulSoup(html, "html.parser")
    _remove_html_running_headers(soup, HtmlFormat.XML_OPINION)

    paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
    assert "Unique first paragraph." in paragraphs
    assert "Another unique paragraph." in paragraphs


# ── Full transform pipeline ───────────────────────────────────────────

def test_transform_does_not_crash_on_empty():
    """transform() should handle an empty opinion without error."""
    html = '<opinion type="majority"></opinion>'
    soup = BeautifulSoup(html, "html.parser")
    result = transform(soup, HtmlFormat.XML_OPINION)
    assert result is not None


def test_transform_removes_script_tags():
    html = '<opinion type="majority"><script>alert("xss")</script><p>Text.</p></opinion>'
    soup = BeautifulSoup(html, "html.parser")
    result = transform(soup, HtmlFormat.XML_OPINION)
    assert result.find("script") is None


def test_transform_end_to_end_xml():
    """Full transform on a realistic XML opinion snippet."""
    html = '''<?xml version="1.0" encoding="utf-8"?>
<opinion type="majority">
<author id="a1">HALL, Circuit Judge:</author>
<p id="p1">
  Defendants appeal the October 1, 2007 judgment.
  <span citation-index="1" class="star-pagination" label="153"> *153 </span>
  The court affirms.
</p>
<p id="p2">See <span class="citation no-link">42 U.S.C. § 12101</span>.</p>
<div class="footnotes">
  <div class="footnote" id="fn1" label="1">
    <p>Footnote one text.</p>
  </div>
</div>
</opinion>'''
    soup = BeautifulSoup(html, "html.parser")
    result = transform(soup, HtmlFormat.XML_OPINION)

    # Star-pagination → anchor
    star = result.find("a", id="star-153")
    assert star is not None

    # Footnote back-ref added
    backref = result.find("a", class_="footnote-backref")
    assert backref is not None
