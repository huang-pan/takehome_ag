"""
src/cleaner.py

Text-level cleaning utilities applied to plain_text content.

Used:
  - as the primary source when html_with_citations is empty
  - as a supplementary source for locating form-feed page breaks
    when the HTML has no star-pagination markers

Key cleaning steps:
  1. Encoding repair via ftfy
  2. Form-feed detection → page-break markers
  3. Running header/footer removal
  4. Numbered-line stripping (2nd Circuit typewriter style)
  5. Stranded page-number removal
  6. Pathological whitespace normalisation
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Optional

import ftfy

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

_FORM_FEED = "\f"

# Numbered-line pattern: leading whitespace, 1–3 digits, 2+ spaces, then content.
# We guard against matching lines that genuinely start with a digit by requiring
# that the number is preceded by whitespace-only.
_NUMBERED_LINE_RE = re.compile(r"^[ \t]+(\d{1,3})[ \t]{2,}(.+)$")

# Stranded page number: a line that is ONLY digits (maybe surrounded by spaces)
_STRANDED_PAGE_RE = re.compile(r"^\s*\d{1,4}\s*$")

# Pathological justified-text whitespace: 3+ spaces between words inside a line
_MULTI_SPACE_RE = re.compile(r"(?<=\S) {3,}(?=\S)")

# Blank lines
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


# ── Public API ────────────────────────────────────────────────────────

def clean_plain_text(
    text: str,
    *,
    strip_numbered_lines: bool = True,
    page_break_marker: str = "<!-- PAGE_BREAK -->",
) -> str:
    """
    Full cleaning pipeline for *text* extracted from a PDF.

    Returns cleaned text with ``page_break_marker`` inserted where
    form-feed characters were found.
    """
    # 1. Encoding repair
    text = ftfy.fix_text(text)

    # 2. Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Replace form-feeds with a placeholder we can find later
    text = text.replace(_FORM_FEED, f"\n{page_break_marker}\n")

    # 4. Split into lines for per-line processing
    lines = text.split("\n")

    # 5. Detect and remove running headers
    lines = _remove_running_headers(lines, page_break_marker=page_break_marker)

    # 6. Strip numbered lines (2nd Circuit typewriter style)
    if strip_numbered_lines:
        lines = _strip_numbered_lines(lines)

    # 7. Strip stranded page numbers (isolated digit-only lines)
    lines = _strip_stranded_page_numbers(lines)

    # 8. Per-line whitespace: collapse multi-space inside justified text
    lines = [_MULTI_SPACE_RE.sub(" ", ln) for ln in lines]

    # 9. Rejoin, then collapse excessive blank lines
    cleaned = "\n".join(lines)
    cleaned = _MULTI_BLANK_RE.sub("\n\n", cleaned)

    return cleaned.strip()


def extract_page_breaks(plain_text: str) -> list[int]:
    """
    Return the character positions of each \f (form-feed) in *plain_text*.
    Useful for cross-referencing with HTML star-pagination markers.
    """
    return [i for i, ch in enumerate(plain_text) if ch == _FORM_FEED]


# ── Internal helpers ──────────────────────────────────────────────────

def _remove_running_headers(
    lines: list[str],
    *,
    page_break_marker: str,
    min_length: int = 4,
    max_length: int = 120,
    min_repetitions: int = 2,
) -> list[str]:
    """
    Remove lines that repeat verbatim across page boundaries.

    Strategy:
    - Collect lines within a window of ±3 lines from each page-break marker.
    - Count how many times each such line appears across the whole document.
    - Lines appearing ≥ min_repetitions times AND fitting within the length
      bounds are treated as headers/footers and dropped.
    """
    # Find page-break line indices
    pb_indices = [i for i, ln in enumerate(lines) if page_break_marker in ln]
    if not pb_indices:
        return lines

    # Candidate header/footer lines: short, near page breaks
    candidate_counter: Counter[str] = Counter()
    window = 4
    for pb in pb_indices:
        start = max(0, pb - window)
        end   = min(len(lines), pb + window + 1)
        for ln in lines[start:end]:
            stripped = ln.strip()
            if min_length <= len(stripped) <= max_length:
                candidate_counter[stripped] += 1

    headers = {
        ln for ln, count in candidate_counter.items()
        if count >= min_repetitions
    }

    if not headers:
        return lines

    logger.debug("Removing %d running header/footer patterns", len(headers))
    return [ln for ln in lines if ln.strip() not in headers]


def _strip_numbered_lines(lines: list[str]) -> list[str]:
    """
    Strip leading line-numbers from typewriter-style 2nd Circuit opinions.

    We only activate stripping if we find ≥5 consecutive numbered lines,
    avoiding false positives on opinions that genuinely start paragraphs
    with a digit.
    """
    # First pass: mark which lines are numbered
    numbered_flags = [bool(_NUMBERED_LINE_RE.match(ln)) for ln in lines]

    # Find maximum consecutive run
    max_run = 0
    run = 0
    for f in numbered_flags:
        run = run + 1 if f else 0
        max_run = max(max_run, run)

    if max_run < 5:
        # Not a numbered-line opinion
        return lines

    logger.debug("Stripping numbered lines (max consecutive run = %d)", max_run)

    result: list[str] = []
    for ln, is_numbered in zip(lines, numbered_flags):
        if is_numbered:
            m = _NUMBERED_LINE_RE.match(ln)
            # Keep only the text content (group 2)
            result.append(m.group(2))  # type: ignore[union-attr]
        else:
            result.append(ln)
    return result


def _strip_stranded_page_numbers(lines: list[str]) -> list[str]:
    """
    Remove lines that contain only a page number (pure digits, possibly
    surrounded by whitespace).  These are PDF artifacts that appear mid-text.
    """
    return [ln for ln in lines if not _STRANDED_PAGE_RE.match(ln)]
