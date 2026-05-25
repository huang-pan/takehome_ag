"""
src/transformer.py

Transform a BeautifulSoup tree (parsed from html_with_citations) into a
normalised, clean, render-ready structure.

Responsibilities:
  1. Normalise star-pagination spans → anchor elements
  2. Enforce bidirectional footnote links
  3. Fix citation link URLs (relative CourtListener → absolute)
  4. Remove residual CourtListener artefacts (script, style, etc.)
  5. Sanitise whitespace in text nodes
  6. Strip running headers embedded in HTML paragraph blocks
  7. Identify structural sections (caption, counsel, body, dissent)
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Optional

import ftfy
from bs4 import BeautifulSoup, NavigableString, Tag

from .parser import HtmlFormat

logger = logging.getLogger(__name__)

_CL_BASE = "https://www.courtlistener.com"

# Patterns for running headers inside HTML (short, repeated paragraphs)
_MAX_HEADER_LEN = 100
_MIN_REPETITIONS = 2


# ── Main entry ────────────────────────────────────────────────────────

def transform(soup: BeautifulSoup, fmt: HtmlFormat) -> BeautifulSoup:
    """
    Run all transformation passes on *soup* in-place and return it.
    """
    _remove_noise_tags(soup)
    _fix_encoding(soup)
    _normalise_star_pagination(soup, fmt)
    _fix_citation_urls(soup)
    _fix_footnotes(soup, fmt)
    _remove_html_running_headers(soup, fmt)
    _normalise_whitespace(soup)
    return soup


# ── Noise removal ────────────────────────────────────────────────────

def _remove_noise_tags(soup: BeautifulSoup) -> None:
    """Drop tags that should never appear in a rendered opinion."""
    for tag in soup.find_all(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()


# ── Encoding ─────────────────────────────────────────────────────────

def _fix_encoding(soup: BeautifulSoup) -> None:
    """Apply ftfy to all text nodes to fix mojibake."""
    for node in soup.find_all(string=True):
        fixed = ftfy.fix_text(node)
        if fixed != node:
            node.replace_with(fixed)


# ── Star-pagination ───────────────────────────────────────────────────

# XML format: <span citation-index="1" class="star-pagination" label="153"> *153 </span>
# Div format: <span class="star-pagination">*311</span>
_STAR_LABEL_RE = re.compile(r"\*(\d+)")


def _normalise_star_pagination(soup: BeautifulSoup, fmt: HtmlFormat) -> None:
    """
    Convert all star-pagination spans into anchor-able elements with a
    consistent data-page attribute.
    """
    for span in soup.find_all("span", class_=lambda c: c and "star-pagination" in c):
        # Determine the page number
        page_num: Optional[str] = None

        if fmt == HtmlFormat.XML_OPINION:
            page_num = span.get("label") or span.get("citation-index")

        if not page_num:
            # Try to extract from text content e.g. "*311"
            text = span.get_text(strip=True)
            m = _STAR_LABEL_RE.search(text)
            if m:
                page_num = m.group(1)

        if not page_num:
            continue  # Can't determine page; leave as-is

        # Replace with a clean anchor span
        anchor_id = f"star-{page_num}"
        new_tag = soup.new_tag(
            "a",
            href=f"#{anchor_id}",
            id=anchor_id,
            attrs={"class": "star-page-inline", "data-page": page_num},
        )
        new_tag.string = f"*{page_num}"
        span.replace_with(new_tag)


# ── Citation URLs ─────────────────────────────────────────────────────

def _fix_citation_urls(soup: BeautifulSoup) -> None:
    """
    Make CourtListener citation links absolute.

    CourtListener relative paths look like: /opinion/.../ or /c/F.3d/...
    """
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/"):
            a["href"] = _CL_BASE + href
        # Keep external URLs as-is


# ── Footnotes ────────────────────────────────────────────────────────

def _fix_footnotes(soup: BeautifulSoup, fmt: HtmlFormat) -> None:
    """
    Ensure bidirectional footnote links:
      Forward: <a class="footnote" href="#fn1" id="fn1_ref">N</a>
      Backward: (added by us) <a class="footnote-backref" href="#fn1_ref">↩</a>

    The XML format already has well-structured footnote divs.
    We enrich them with back-references if missing.
    """
    footnote_divs = soup.find_all("div", class_="footnote")
    if not footnote_divs:
        # Try <footnote> XML elements
        footnote_divs = soup.find_all("footnote")

    for fn_div in footnote_divs:
        fn_id = fn_div.get("id") or fn_div.get("label")
        if not fn_id:
            continue

        # Normalise id format: "fn1", "fn2", ...
        if not fn_id.startswith("fn"):
            fn_id = "fn" + fn_id
            fn_div["id"] = fn_id

        # Add back-ref link if not already present
        if not fn_div.find("a", class_="footnote-backref"):
            ref_id = fn_id + "_ref"
            backref = soup.new_tag(
                "a",
                href=f"#{ref_id}",
                attrs={"class": "footnote-backref", "aria-label": "Back to reference"},
            )
            backref.string = " ↩"
            # Append after last child
            fn_div.append(backref)

    # Also normalise forward references
    for a in soup.find_all("a", class_="footnote"):
        href = a.get("href", "")
        # Ensure they have a back-anchor id
        if href.startswith("#fn") and not a.get("id"):
            fn_num = href.lstrip("#fn")
            a["id"] = f"fn{fn_num}_ref"


# ── Running header removal in HTML ────────────────────────────────────

def _remove_html_running_headers(soup: BeautifulSoup, fmt: HtmlFormat) -> None:
    """
    Remove <p> blocks that appear verbatim multiple times across the document.
    These are typically running headers/footers embedded in the paragraph stream.

    IMPORTANT: paragraphs inside <div class="footnote"> are excluded from both
    the candidate count and the removal sweep.  The same citation text often
    appears verbatim in both the opinion body and a footnote (e.g. "Smith v.
    Jones, 123 F.3d 456 (2010)."), which would otherwise be misidentified as a
    repeated running header and stripped from the footnote.
    """
    if fmt != HtmlFormat.XML_OPINION:
        return  # div/center format doesn't have this issue

    def _inside_footnote(tag: Tag) -> bool:
        """Return True if *tag* is a descendant of a footnote div.

        Works with both lxml-xml (class is a str) and html.parser (class is a list).
        """
        for ancestor in tag.parents:
            if ancestor.name == "div":
                cls = ancestor.get("class") or ""
                # cls is a list with html.parser, a str with lxml-xml
                cls_str = " ".join(cls) if isinstance(cls, list) else str(cls)
                if "footnote" in cls_str.split():
                    return True
        return False

    paragraphs = soup.find_all("p")
    text_counter: Counter[str] = Counter()

    for p in paragraphs:
        if _inside_footnote(p):
            continue  # don't count footnote paragraphs as header candidates
        text = p.get_text(strip=True)
        if 4 <= len(text) <= _MAX_HEADER_LEN:
            text_counter[text] += 1

    headers = {t for t, c in text_counter.items() if c >= _MIN_REPETITIONS}
    if not headers:
        return

    removed = 0
    for p in paragraphs:
        if _inside_footnote(p):
            continue  # never remove footnote paragraphs
        if p.get_text(strip=True) in headers:
            p.decompose()
            removed += 1

    if removed:
        logger.debug("Removed %d repeated paragraph headers", removed)


# ── Whitespace normalisation ──────────────────────────────────────────

_MULTI_SPACE_RE = re.compile(r" {3,}")
_NBSP_RE = re.compile(r"\xa0+")


def _normalise_whitespace(soup: BeautifulSoup) -> None:
    """
    Collapse excessive whitespace in text nodes.
    Preserves single newlines (paragraph structure) but removes multi-space runs.
    """
    for node in soup.find_all(string=True):
        parent = node.parent
        if parent and parent.name in ("pre", "code"):
            continue
        text = str(node)
        # Replace NBSP with regular space
        text = _NBSP_RE.sub(" ", text)
        # Collapse 3+ spaces to single space
        text = _MULTI_SPACE_RE.sub(" ", text)
        if text != str(node):
            node.replace_with(text)
