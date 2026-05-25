#!/usr/bin/env python3
"""
pipeline.py

Entry point for the Legal Opinion Cleanup & Rendering Pipeline.

Usage:
    python pipeline.py [--csv PATH] [--output DIR] [--log-level LEVEL]

Reads opinion_bucket_export_20_each.csv and writes:
  output/
    index.html          — searchable listing of all 60 opinions
    <opinion_id>.html   — one rendered file per opinion
    assets/style.css    — stylesheet (must already exist in output/assets/)
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import traceback
from pathlib import Path
from typing import Any

from src.cleaner import clean_plain_text
from src.index_builder import IndexRow, build_index
from src.parser import HtmlFormat, detect_format, parse_html
from src.renderer import (
    OpinionSection,
    RenderContext,
    TocEntry,
    _extract_sections_div,
    _extract_sections_xml,
    build_toc,
    render_opinion,
)
from src.transformer import transform

# ── Logging setup ─────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── CLI ───────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Legal Opinion Rendering Pipeline")
    p.add_argument(
        "--csv",
        default="opinion_bucket_export_20_each.csv",
        help="Path to the source CSV file",
    )
    p.add_argument(
        "--output",
        default="docs",
        help="Directory to write HTML output",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return p.parse_args()


# ── Per-opinion processing ────────────────────────────────────────────

def process_row(row: dict[str, Any], output_dir: Path) -> bool:
    """
    Process a single CSV row and write the rendered HTML file.

    Returns True on success, False on error.
    A failure here must NOT propagate to the caller (failure isolation).
    """
    opinion_id = row["opinion_id"]

    try:
        html_source = row.get("html_with_citations", "").strip()
        plain_source = row.get("plain_text", "").strip()

        # ── Choose primary source ──────────────────────────────────────
        fmt = detect_format(html_source)

        if fmt == HtmlFormat.EMPTY:
            # Fall back to plain text
            logger.warning(
                "[%s] html_with_citations is empty — falling back to plain_text", opinion_id
            )
            html_source = _plain_text_to_minimal_html(plain_source, row)
            fmt = HtmlFormat.DIV_CENTER

        # ── Parse ──────────────────────────────────────────────────────
        soup = parse_html(html_source, fmt)

        # ── Transform ─────────────────────────────────────────────────
        soup = transform(soup, fmt)

        # ── Extract sections ──────────────────────────────────────────
        if fmt == HtmlFormat.XML_OPINION:
            caption_html, counsel_html, sections, footnotes_html = _extract_sections_xml(soup)
        else:
            caption_html, counsel_html, sections, footnotes_html = _extract_sections_div(soup)

        # ── Fallback: if sections are empty, use cleaned plain_text ───
        if not any(sec.body_html.strip() for sec in sections) and plain_source:
            logger.warning(
                "[%s] HTML extraction produced no content — using plain_text fallback", opinion_id
            )
            cleaned = clean_plain_text(plain_source)
            body_html = _text_to_html_paragraphs(cleaned)
            sections = [OpinionSection(label="majority", body_html=body_html)]

        # ── Build TOC ─────────────────────────────────────────────────
        toc = build_toc(sections)

        # ── Assemble render context ───────────────────────────────────
        ctx = RenderContext(
            opinion_id=opinion_id,
            case_name=row.get("case_name") or row.get("case_name_full") or f"Opinion {opinion_id}",
            court_id=row.get("court_id", ""),
            date_filed=row.get("date_filed", ""),
            docket_number=row.get("docket_number", ""),
            judges=row.get("judges", ""),
            precedential_status=row.get("precedential_status", ""),
            opinion_type=row.get("opinion_type", ""),
            page_count=row.get("page_count", ""),
            bucket=row.get("bucket", ""),
            extracted_by_ocr=row.get("extracted_by_ocr", "f"),
            caption_html=caption_html,
            counsel_html=counsel_html,
            sections=sections,
            footnotes_html=footnotes_html,
            toc=toc,
            assets_path="assets/style.css",
        )

        # ── Render ────────────────────────────────────────────────────
        html_out = render_opinion(ctx)

        # ── Write ─────────────────────────────────────────────────────
        out_path = output_dir / f"{opinion_id}.html"
        out_path.write_text(html_out, encoding="utf-8")
        logger.info("[%s] ✓ %s (%s, %s pages)", opinion_id, row.get("case_name", "")[:60], row.get("bucket"), row.get("page_count"))
        return True

    except Exception:  # noqa: BLE001
        logger.error(
            "[%s] ✗ Pipeline error:\n%s", opinion_id, traceback.format_exc()
        )
        return False


# ── Helper: plain text → minimal HTML ────────────────────────────────

def _plain_text_to_minimal_html(text: str, row: dict[str, Any]) -> str:
    """
    Convert cleaned plain text to a minimal HTML document so we can
    pass it through the div/center parser pathway.
    """
    cleaned = clean_plain_text(text)
    paragraphs = _text_to_html_paragraphs(cleaned)
    title = row.get("case_name", "Opinion")
    return f"<div>\n<h1>{title}</h1>\n{paragraphs}\n</div>"


def _text_to_html_paragraphs(text: str) -> str:
    """
    Convert cleaned plain text into HTML paragraphs.
    Double-newline separated blocks → <p> elements.
    Page-break markers → star-page visual dividers.
    """
    import re
    PAGE_BREAK_MARKER = "<!-- PAGE_BREAK -->"
    blocks = re.split(r"\n{2,}", text)
    parts: list[str] = []
    page_num = 1
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if PAGE_BREAK_MARKER in block:
            block = block.replace(PAGE_BREAK_MARKER, "").strip()
            # Insert a page break marker
            parts.append(
                f'<a id="page-{page_num}" class="star-page-inline" '
                f'data-page="{page_num}" href="#page-{page_num}" '
                f'title="Page {page_num}">p.{page_num}</a>'
            )
            page_num += 1
            if block:
                parts.append(f"<p>{block}</p>")
        else:
            parts.append(f"<p>{block}</p>")
    return "\n".join(parts)


# ── Main ──────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    logging.getLogger().setLevel(args.log_level)

    csv_path = Path(args.csv)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(exist_ok=True)

    if not csv_path.exists():
        logger.error("CSV file not found: %s", csv_path)
        return 1

    # Read all rows
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    logger.info("Loaded %d opinions from %s", len(rows), csv_path)

    # Process opinions
    index_rows: list[IndexRow] = []
    success = 0
    failure = 0

    for row in rows:
        ok = process_row(row, output_dir)
        if ok:
            success += 1
        else:
            failure += 1

        index_rows.append(
            IndexRow(
                opinion_id=row["opinion_id"],
                case_name=row.get("case_name") or row.get("case_name_full") or f"Opinion {row['opinion_id']}",
                court_id=row.get("court_id", ""),
                date_filed=row.get("date_filed", ""),
                docket_number=row.get("docket_number", ""),
                precedential_status=row.get("precedential_status", ""),
                page_count=row.get("page_count", ""),
                bucket=row.get("bucket", ""),
                ok=ok,
            )
        )

    # Write index
    index_html = build_index(index_rows)
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")
    logger.info("Wrote index.html")

    logger.info(
        "Pipeline complete: %d/%d succeeded, %d failed.",
        success,
        len(rows),
        failure,
    )
    return 0 if failure == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
