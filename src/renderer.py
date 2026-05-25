"""
src/renderer.py

Convert a transformed BeautifulSoup tree into a final, self-contained HTML file.

Responsibilities:
  1. Extract structured sections from the soup:
       - Metadata block (title, author, etc.)
       - Caption / header block
       - Counsel block
       - Opinion body (one or more: majority, dissent, concurrence)
       - Footnotes
  2. Build a Table of Contents from section headings
  3. Render via Jinja2 template
  4. Return the HTML string
"""

from __future__ import annotations

import logging
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag
from jinja2 import Environment, FileSystemLoader

from .parser import HtmlFormat

logger = logging.getLogger(__name__)

_CL_BASE = "https://www.courtlistener.com"

# ── Data structures ───────────────────────────────────────────────────

@dataclass
class TocEntry:
    level: int           # 1, 2, or 3
    text: str
    anchor_id: str


@dataclass
class OpinionSection:
    label: str           # 'majority', 'dissent', 'concurrence', etc.
    body_html: str


@dataclass
class RenderContext:
    opinion_id: str
    case_name: str
    court_id: str
    date_filed: str
    docket_number: str
    judges: str
    precedential_status: str
    opinion_type: str
    page_count: str
    bucket: str
    extracted_by_ocr: str

    # Rendered body fragments
    caption_html: str = ""
    counsel_html: str = ""
    sections: list[OpinionSection] = field(default_factory=list)
    footnotes_html: str = ""
    toc: list[TocEntry] = field(default_factory=list)

    assets_path: str = "assets/style.css"


# ── Template (inline Jinja2) ──────────────────────────────────────────

_TEMPLATE_STR = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ ctx.case_name }} — OurFirm Legal</title>
  <meta name="description" content="Court opinion: {{ ctx.case_name }}, {{ ctx.court_id }}, {{ ctx.date_filed }}.">
  <link rel="stylesheet" href="{{ ctx.assets_path }}">
</head>
<body>

<div class="layout">

  <!-- ── Site header ── -->
  <header class="site-header" role="banner">
    <div class="logo">Our<span>Firm</span> Legal</div>
    <nav class="header-meta" aria-label="breadcrumb">
      <a href="index.html">All Opinions</a>
      &rsaquo; Opinion {{ ctx.opinion_id }}
    </nav>
  </header>

  <!-- ── Sidebar / TOC ── -->
  <aside class="sidebar" aria-label="Table of contents">
    <div class="toc-title">Contents</div>
    {% if ctx.toc %}
    <ul class="toc-list" role="list">
      {% for entry in ctx.toc %}
      <li class="toc-l{{ entry.level }}">
        <a href="#{{ entry.anchor_id }}">{{ entry.text }}</a>
      </li>
      {% endfor %}
    </ul>
    {% else %}
    <p style="padding:0 1.25rem;font-family:var(--font-ui);font-size:0.78rem;color:var(--text-muted);">No sections detected.</p>
    {% endif %}
  </aside>

  <!-- ── Main content ── -->
  <main class="main" id="main-content">

    <!-- Metadata card -->
    <article>
      <div class="opinion-meta">
        <h1 class="opinion-title">{{ ctx.case_name }}</h1>
        <div class="meta-grid">
          <div class="meta-item">
            <span class="meta-label">Court</span>
            <span class="meta-value">{{ ctx.court_id | upper }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Date Filed</span>
            <span class="meta-value">{{ ctx.date_filed }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Docket</span>
            <span class="meta-value">{{ ctx.docket_number }}</span>
          </div>
          {% if ctx.judges %}
          <div class="meta-item">
            <span class="meta-label">Judges</span>
            <span class="meta-value">{{ ctx.judges }}</span>
          </div>
          {% endif %}
          <div class="meta-item">
            <span class="meta-label">Status</span>
            <span class="meta-value">
              {% if ctx.precedential_status|lower == 'published' %}
                <span class="badge badge-published">Published</span>
              {% else %}
                <span class="badge badge-unpublished">{{ ctx.precedential_status }}</span>
              {% endif %}
            </span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Bucket</span>
            <span class="meta-value">
              <span class="badge badge-{{ ctx.bucket }}">{{ ctx.bucket | capitalize }}</span>
            </span>
          </div>
          {% if ctx.page_count %}
          <div class="meta-item">
            <span class="meta-label">Pages</span>
            <span class="meta-value">{{ ctx.page_count }}</span>
          </div>
          {% endif %}
          <div class="meta-item">
            <span class="meta-label">Opinion&nbsp;ID</span>
            <span class="meta-value">{{ ctx.opinion_id }}</span>
          </div>
        </div>
      </div>

      <!-- Caption / header block -->
      {% if ctx.caption_html %}
      <section class="opinion-caption" id="section-caption" aria-label="Case caption">
        {{ ctx.caption_html | safe }}
      </section>
      {% endif %}

      <!-- Counsel block -->
      {% if ctx.counsel_html %}
      <div class="counsel-block" id="section-counsel">
        <div class="section-label">Counsel</div>
        {{ ctx.counsel_html | safe }}
      </div>
      {% endif %}

      <!-- Opinion sections (majority / dissent / concurrence) -->
      {% for sec in ctx.sections %}
      <section
        id="section-{{ sec.label }}"
        class="opinion-section{% if sec.label in ('dissent','concurrence') %} dissent-section{% endif %}"
        aria-label="{{ sec.label | capitalize }} opinion"
      >
        <div class="section-label">{{ sec.label | capitalize }} Opinion</div>
        <div class="opinion-body">
          {{ sec.body_html | safe }}
        </div>
      </section>
      {% endfor %}

      <!-- Footnotes -->
      {% if ctx.footnotes_html %}
      <section class="footnotes-section" id="footnotes" aria-label="Footnotes">
        <div class="footnotes-title">Footnotes</div>
        {{ ctx.footnotes_html | safe }}
      </section>
      {% endif %}

    </article>
  </main>

</div><!-- .layout -->

<!-- Back-to-top -->
<a href="#main-content" id="back-to-top" aria-label="Back to top" title="Back to top">↑</a>

<script>
(function(){
  var btn = document.getElementById('back-to-top');
  window.addEventListener('scroll', function(){
    btn.classList.toggle('visible', window.scrollY > 400);
  }, {passive: true});

  // TOC active highlight
  var links = document.querySelectorAll('.toc-list a');
  var observer = new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if(e.isIntersecting){
        links.forEach(function(l){ l.classList.remove('active'); });
        var l = document.querySelector('.toc-list a[href="#'+e.target.id+'"]');
        if(l) l.classList.add('active');
      }
    });
  }, {rootMargin: '-10% 0px -80% 0px'});

  document.querySelectorAll('[id^="section-"], [id^="star-"]').forEach(function(el){
    observer.observe(el);
  });
})();
</script>

</body>
</html>"""


# ── Section extraction ────────────────────────────────────────────────

# Headings that indicate a new section starting
_SECTION_HEADING_RE = re.compile(
    r"^(I{1,4}\.?|II{1,3}\.?|IV\.?|V{1,3}\.?|[A-Z]{1,4}\.)\s*$|"
    r"^(DISCUSSION|ANALYSIS|BACKGROUND|CONCLUSION|HELD|AFFIRM|REVERS|REMAND"
    r"|DISSENT|CONCUR|MAJORITY|OPINION|ORDER|PER CURIAM|NOTES?)\b",
    re.IGNORECASE,
)

# Counsel block heuristic: paragraphs with Attorney / Counsel / Esq. patterns
_COUNSEL_RE = re.compile(
    r"\b(Esq\.|Attorney|Counsel|ARGUED|ON BRIEF|for Appellant|for Appellee"
    r"|for Petitioner|for Respondent|for Plaintiff|for Defendant)\b",
    re.IGNORECASE,
)


def _slugify(text: str) -> str:
    """Convert *text* to a URL-safe id fragment."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:60]


def _render_star_anchor(tag: Tag) -> str:
    """Render a star-page inline anchor as a wrapped block marker."""
    page = tag.get("data-page", "")
    anchor_id = tag.get("id", f"star-{page}")
    return (
        f'<span class="star-page-wrapper">'
        f'<a id="{anchor_id}" href="#{anchor_id}" class="star-page-anchor"'
        f' title="Reporter page {page}" aria-label="Reporter page {page}">*{page}</a>'
        f"</span>"
    )


def _extract_sections_xml(soup: BeautifulSoup) -> tuple[str, str, list[OpinionSection], str]:
    """
    Extract sections from XML-flavored opinion.

    Returns (caption_html, counsel_html, sections, footnotes_html).
    """
    caption_parts: list[str] = []
    counsel_parts: list[str] = []
    footnotes_parts: list[str] = []
    sections: list[OpinionSection] = []

    # Walk top-level opinion tags
    for opinion_tag in soup.find_all("opinion"):
        op_type = (opinion_tag.get("type") or "majority").lower()
        body_parts: list[str] = []

        for child in opinion_tag.children:
            if isinstance(child, NavigableString):
                continue
            if not isinstance(child, Tag):
                continue

            tag_name = child.name

            # Author tag → becomes a heading in the body
            if tag_name == "author":
                text = child.get_text(strip=True)
                if text:
                    anchor = _slugify(text)
                    body_parts.append(
                        f'<h2 id="{anchor}" class="opinion-author">{_render_inline(child)}</h2>'
                    )
                continue

            # Footnote container → goes to footnotes section
            if tag_name == "div" and "footnotes" in (child.get("class") or []):
                footnotes_parts.append(_render_footnotes(child, soup))
                continue

            # Individual footnote div → also goes to footnotes
            if tag_name == "div" and "footnote" in (child.get("class") or []):
                footnotes_parts.append(_render_single_footnote(child, soup))
                continue

            # Paragraph
            if tag_name == "p":
                rendered = _render_paragraph(child, soup)
                if rendered:
                    body_parts.append(rendered)
                continue

            # Fallback: render tag as-is
            rendered = _render_tag_generic(child, soup)
            if rendered:
                body_parts.append(rendered)

        body_html = "\n".join(body_parts)
        sections.append(OpinionSection(label=op_type, body_html=body_html))

    # If no <opinion> tags found (some XML-flavored docs have flat structure)
    if not sections:
        body_parts = _extract_flat_body(soup)
        sections.append(OpinionSection(label="majority", body_html="\n".join(body_parts)))

    caption_html = "\n".join(caption_parts)
    counsel_html = "\n".join(counsel_parts)
    footnotes_html = "\n".join(footnotes_parts)
    return caption_html, counsel_html, sections, footnotes_html


def _extract_sections_div(soup: BeautifulSoup) -> tuple[str, str, list[OpinionSection], str]:
    """
    Extract sections from div/center-style opinion.

    Returns (caption_html, counsel_html, sections, footnotes_html).
    """
    root = soup.find("div")
    if not root:
        root = soup

    caption_parts: list[str] = []
    body_parts: list[str] = []
    footnotes_parts: list[str] = []
    in_caption = True

    # Heuristic: center/h1/h2 blocks at the top are the caption
    for child in root.children:
        if isinstance(child, NavigableString):
            s = str(child).strip()
            if s:
                body_parts.append(f"<p>{s}</p>")
            continue
        if not isinstance(child, Tag):
            continue

        tag_name = child.name

        if tag_name == "div" and "footnotes" in (child.get("class") or []):
            footnotes_parts.append(_render_footnotes(child, soup))
            continue
        if tag_name == "div" and "footnote" in (child.get("class") or []):
            footnotes_parts.append(_render_single_footnote(child, soup))
            continue

        # Caption detection: center/h1 at beginning
        if in_caption and tag_name in ("center", "h1", "h2", "h3"):
            rendered = _render_tag_generic(child, soup)
            caption_parts.append(rendered)
            continue

        # Once we hit a <p> or <div> that looks like body text, stop caption mode
        if tag_name == "p":
            in_caption = False
            body_parts.append(_render_paragraph(child, soup))
            continue

        if tag_name in ("h1", "h2", "h3", "h4"):
            in_caption = False
            text = child.get_text(strip=True)
            anchor = _slugify(text)
            body_parts.append(f'<h2 id="{anchor}">{_render_inline(child)}</h2>')
            continue

        if tag_name == "br":
            continue

        in_caption = False
        rendered = _render_tag_generic(child, soup)
        if rendered:
            body_parts.append(rendered)

    caption_html = "\n".join(caption_parts)
    counsel_html = ""
    body_html = "\n".join(body_parts)
    footnotes_html = "\n".join(footnotes_parts)
    sections = [OpinionSection(label="majority", body_html=body_html)]
    return caption_html, counsel_html, sections, footnotes_html


# ── Inline / paragraph rendering ─────────────────────────────────────

def _render_inline(tag: Tag) -> str:
    """Render a tag's contents as inline HTML, preserving em/strong/citations/anchors."""
    parts: list[str] = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            parts.append(_escape(str(child)))
        elif isinstance(child, Tag):
            parts.append(_render_inline_tag(child))
    return "".join(parts)


def _render_inline_tag(tag: Tag) -> str:
    """Render a single inline tag."""
    name = tag.name
    inner = _render_inline(tag)
    classes = tag.get("class") or []

    if isinstance(classes, list):
        class_str = " ".join(classes)
    else:
        class_str = str(classes)

    # Star-page anchors (already transformed)
    if "star-page-inline" in class_str:
        page = tag.get("data-page", "")
        anchor_id = tag.get("id", f"star-{page}")
        return (
            f'<a id="{anchor_id}" href="#{anchor_id}" class="star-page-inline"'
            f' data-page="{page}" title="Reporter page {page}">*{page}</a>'
        )

    # Citations
    if "citation" in class_str:
        # CourtListener sometimes wraps the link as a child <a> inside the <span class="citation">
        # rather than putting href on the span itself.
        href = tag.get("href", "")
        if not href:
            child_a = tag.find("a", href=True)
            if child_a:
                href = child_a.get("href", "")
                # Make relative URLs absolute
                if href.startswith("/"):
                    href = _CL_BASE + href
                # inner already rendered the child <a> as a link, but we want the clean version
                inner_text = tag.get_text()
                return f'<span class="citation"><a href="{_escape(href)}">{_escape(inner_text.strip())}</a></span>'
        if href:
            return f'<span class="citation"><a href="{_escape(href)}">{inner}</a></span>'
        return f'<span class="citation no-link">{inner}</span>'

    # Footnote references
    if name == "a" and "footnote" in class_str:
        href = tag.get("href", "#")
        fn_id = tag.get("id", "")
        ref_attrs = f'href="{_escape(href)}"'
        if fn_id:
            ref_attrs += f' id="{_escape(fn_id)}"'
        return f'<a class="footnote-ref" {ref_attrs}>{inner}</a>'

    # Generic anchor
    if name == "a":
        href = tag.get("href", "")
        if href:
            return f'<a href="{_escape(href)}">{inner}</a>'
        return inner

    # Emphasis
    if name in ("em", "i"):
        return f"<em>{inner}</em>"
    if name in ("strong", "b"):
        return f"<strong>{inner}</strong>"

    # Superscript
    if name == "sup":
        return f"<sup>{inner}</sup>"

    # Span passthrough
    if name == "span":
        if class_str:
            return f'<span class="{_escape(class_str)}">{inner}</span>'
        return inner

    # br
    if name == "br":
        return "<br>"

    return inner


def _render_paragraph(p_tag: Tag, soup: BeautifulSoup) -> str:
    """Render a <p> tag as an HTML paragraph."""
    inner = _render_inline(p_tag)
    inner_stripped = inner.strip()
    if not inner_stripped:
        return ""
    # Skip very short repeated fragments (already handled in transformer but belt-and-braces)
    return f"<p>{inner}</p>"


def _render_tag_generic(tag: Tag, soup: BeautifulSoup) -> str:
    """Render an arbitrary tag by preserving its structure."""
    name = tag.name
    if name in ("p",):
        return _render_paragraph(tag, soup)
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        text = tag.get_text(strip=True)
        anchor = _slugify(text)
        level = name[1]
        return f'<h{level} id="{anchor}">{_render_inline(tag)}</h{level}>'
    if name == "center":
        inner = _render_inline(tag)
        return f'<div class="center-block">{inner}</div>'
    if name == "br":
        return ""
    # Fallback: render inline content
    inner = _render_inline(tag)
    if inner.strip():
        return f"<p>{inner}</p>"
    return ""


def _extract_flat_body(soup: BeautifulSoup) -> list[str]:
    """Fallback: extract body from a flat structure without <opinion> wrappers."""
    parts: list[str] = []
    for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "center"]):
        rendered = _render_tag_generic(tag, soup)
        if rendered:
            parts.append(rendered)
    return parts


# ── Footnote rendering ────────────────────────────────────────────────

def _render_footnotes(container: Tag, soup: BeautifulSoup) -> str:
    """Render a <div class="footnotes"> container."""
    parts: list[str] = []
    for fn in container.find_all("div", class_="footnote"):
        parts.append(_render_single_footnote(fn, soup))
    return "\n".join(parts)


def _render_single_footnote(fn: Tag, soup: BeautifulSoup) -> str:
    """
    Render a single <div class="footnote" id="fn1" label="1"> element
    as a styled footnote item with backref link.
    """
    fn_id = fn.get("id", "")
    label = fn.get("label", "")
    if not fn_id:
        return ""
    if not label:
        # Derive label from id
        label = re.sub(r"\D", "", fn_id) or "?"

    # Backref (our canonical styled version)
    backref_html = (
        f'<a href="#{fn_id}_ref" class="footnote-backref" aria-label="Back to reference">↩</a>'
    )

    # Body content — skip any back-pointing links that CourtListener or the transformer
    # already placed inside the footnote div (we add our own canonical one above).
    body_parts: list[str] = []
    for child in fn.children:
        if isinstance(child, NavigableString):
            s = str(child).strip()
            if s:
                body_parts.append(_escape(s))
        elif isinstance(child, Tag):
            child_classes = child.get("class") or []
            child_href = child.get("href", "")

            # Skip any link that:
            # (a) already has class "footnote-backref" (added by transformer), OR
            # (b) has class "footnote" and its href points back to the body ref (e.g. "#fn1_ref")
            #     — this is the CourtListener internal back-pointer number link
            is_backref = (
                "footnote-backref" in child_classes
                or (
                    child.name == "a"
                    and "footnote" in child_classes
                    and child_href.endswith("_ref")
                )
            )
            if is_backref:
                continue

            body_parts.append(_render_inline_tag(child))

    body_html = "".join(body_parts)
    # Even if body_html is empty (some CourtListener footnotes have no text),
    # we still render the anchor so forward refs in the body can link to it.
    if not fn_id:
        return ""

    body_display = body_html if body_html.strip() else '<em style="color:var(--text-muted);font-size:0.8em">No text available</em>'

    return (
        f'<div class="footnote-item" id="{_escape(fn_id)}">'
        f'<div class="footnote-num">{_escape(str(label))}</div>'
        f'<div class="footnote-body">{body_display}{backref_html}</div>'
        f"</div>"
    )


# ── Table of Contents ─────────────────────────────────────────────────

_TOC_TAG_LEVELS = {"h1": 1, "h2": 2, "h3": 3, "h4": 3}

# Headings that are too generic to be useful TOC entries
_TOC_SKIP_RE = re.compile(
    r"^(majority|dissent|concurrence|per curiam|opinion|counsel)$",
    re.IGNORECASE,
)


def build_toc(sections: list[OpinionSection]) -> list[TocEntry]:
    """Build TOC from rendered section HTML."""
    entries: list[TocEntry] = []
    for sec in sections:
        soup = BeautifulSoup(sec.body_html, "html.parser")
        for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
            text = tag.get_text(strip=True)
            if not text or _TOC_SKIP_RE.match(text):
                continue
            anchor = tag.get("id") or _slugify(text)
            level = _TOC_TAG_LEVELS.get(tag.name, 2)
            entries.append(TocEntry(level=level, text=text[:60], anchor_id=anchor))
            if len(entries) >= 30:
                break
    return entries


# ── Main renderer ─────────────────────────────────────────────────────

from jinja2 import Environment


def render_opinion(ctx: RenderContext) -> str:
    """Render a complete opinion HTML page from *ctx*."""
    env = Environment(autoescape=True)
    tmpl = env.from_string(_TEMPLATE_STR)
    return tmpl.render(ctx=ctx)


# ── Escape helper ─────────────────────────────────────────────────────

_HTML_ESCAPE = str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})


def _escape(text: str) -> str:
    """HTML-escape *text*."""
    return text.translate(_HTML_ESCAPE)
