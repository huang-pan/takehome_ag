"""
src/parser.py

Detect the CourtListener HTML format and parse it into a BeautifulSoup tree.

Two distinct formats exist in the dataset:
  1. XML-flavored  – starts with <?xml ...?><opinion type="...">
  2. div/center    – starts with <div> ... <center> ... legacy style

Both are parsed leniently so that malformed XML/HTML doesn't crash the run.
"""

from __future__ import annotations

import logging
import re
from enum import Enum, auto
from typing import Optional

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


class HtmlFormat(Enum):
    XML_OPINION  = auto()   # <?xml ...><opinion type="...">
    DIV_CENTER   = auto()   # <div><center>... (legacy CourtListener)
    EMPTY        = auto()   # blank / whitespace-only


def detect_format(html: str) -> HtmlFormat:
    """Return the detected format enum for *html*."""
    stripped = html.strip()
    if not stripped:
        return HtmlFormat.EMPTY

    # XML prolog or bare <opinion> root
    if stripped.startswith("<?xml") or re.match(r"^\s*<opinion\b", stripped):
        return HtmlFormat.XML_OPINION

    return HtmlFormat.DIV_CENTER


def parse_html(html: str, fmt: Optional[HtmlFormat] = None) -> BeautifulSoup:
    """
    Parse *html* into a BeautifulSoup tree.

    For XML-flavored opinions we first try lxml's XML parser (strictest,
    preserves namespaces correctly), then fall back to html.parser if the
    document is malformed.
    """
    if fmt is None:
        fmt = detect_format(html)

    if fmt == HtmlFormat.XML_OPINION:
        try:
            soup = BeautifulSoup(html, "lxml-xml")
            # Sanity-check: the root should have an <opinion> tag somewhere
            if soup.find("opinion"):
                return soup
            # lxml-xml sometimes wraps everything in <html><body> if parsing fails
            logger.debug("lxml-xml produced no <opinion>; falling back to html.parser")
        except Exception as exc:
            logger.debug("lxml-xml raised %s; falling back to html.parser", exc)

        # Lenient fallback
        return BeautifulSoup(html, "html.parser")

    # div/center format – always use html.parser (lxml-xml would reject it)
    return BeautifulSoup(html, "html.parser")


def get_opinion_type(soup: BeautifulSoup, fmt: HtmlFormat) -> str:
    """
    Return a human-readable label for the opinion type
    ('majority', 'dissent', 'concurrence', etc.).
    """
    if fmt == HtmlFormat.XML_OPINION:
        tag = soup.find("opinion")
        if tag:
            return (tag.get("type") or "majority").lower()
    return "majority"
