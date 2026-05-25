# Legal Opinion Cleanup & Rendering Pipeline

## Summary

Build a Python 3.10+ pipeline that ingests `opinion_bucket_export_20_each.csv` (60 federal appellate opinions) and produces clean, readable HTML for each opinion plus an index page.

## Data Analysis Findings

- **60 rows** total: 20 easy, 20 medium, 20 hard
- **HTML formats**: 56 XML-flavored (`<?xml ...><opinion type="majority">`) + 4 div/center-flavored
- **Star pagination** (XML format): `<span citation-index="1" class="star-pagination" label="153"> *153 </span>`
- **Star pagination** (div format): `<span class="star-pagination">*311</span>`
- **Footnotes** (XML format): `<a class="footnote" href="#fn1" id="fn1_ref">`, `<div class="footnotes">`, `<div class="footnote" id="fn1" label="1">`
- **Numbered lines** in ca2 hard opinions (e.g., ` 1   UNITED STATES COURT...`)
- **Page breaks** in plain_text: `\f` (form feed char)

## Architecture

```
pipeline.py          # Entry point: reads CSV, iterates rows, calls processor, handles errors
src/
  parser.py          # Detects format, parses HTML → normalized AST (BeautifulSoup)
  cleaner.py         # Plain-text cleaning fallback (headers, line numbers, whitespace)
  transformer.py     # Converts parsed content → output HTML (star-pagination, footnotes, citations)
  renderer.py        # Jinja2-based final render with page template + CSS
  index.py           # Builds index.html listing all 60 opinions
output/
  index.html
  <opinion_id>.html × 60
  assets/
    style.css
tests/
  test_cleaner.py
  test_parser.py
  test_transformer.py
README.md
requirements.txt
```

## Strategy: Prefer `html_with_citations` with plain_text fallback

Primary source: `html_with_citations` — already has semantic markup (citations, star-pagination, footnotes, paragraph structure). Much better starting point than raw text.

Fallback: `plain_text` — used when HTML is missing/empty, or to extract page-break positions (`\f`) as a supplement.

For **form-feed page breaks** from plain_text: cross-reference with star-pagination spans in HTML (if present). If plain_text has `\f` markers but HTML has no star-pagination, inject page-break markers from plain_text by character-count heuristic.

## Key Processing Steps

### 1. Format Detection & Parsing
- If `<?xml` or `<opinion type=` → XML-flavored (use `BeautifulSoup` with `lxml-xml` or `html.parser`)
- Otherwise → div/center-flavored HTML
- Handle malformed XML gracefully by falling back to `html.parser`

### 2. Section Identification
- Caption block: `<center>` elements or leading `<p>` before body text
- Counsel block: paragraph with attorney names/addresses
- Per curiam / majority / dissent: `<opinion type="...">` or heuristic on headings

### 3. Running Header Removal
- In plain_text: detect repeated short lines (≤80 chars, appears on multiple pages) → strip
- In HTML: short `<p>` blocks that repeat verbatim across star-pagination boundaries → strip

### 4. Numbered-Line Stripping (2nd Circuit)
- Pattern: `^\s+\d{1,3}\s{2,}` at start of text node
- Only strip if ≥5 such lines appear in sequence (avoid stripping genuine numbered lists)

### 5. Star-Pagination → Anchors
- `<span class="star-pagination" label="N">` → `<a id="star-N" class="star-page" href="#star-N">*N</a>`
- Add a subtle visual marker (margin note with reporter page number)

### 6. Footnote Bidirectional Links
- Forward ref: `<a class="footnote" href="#fn1" id="fn1_ref">1</a>` → keep & style
- Footnote body: `<div class="footnote" id="fn1">` → add back-link `<a href="#fn1_ref">↩</a>`
- Renumber consistently if IDs are already 1-based (most are)

### 7. Citation Preservation
- Keep all `<span class="citation">` tags
- If wrapped in `<a href>`, keep clickable
- If `href` is a relative CourtListener path (e.g., `/opinion/...`), prepend `https://www.courtlistener.com`

### 8. Whitespace Cleanup
- Collapse 3+ consecutive blank lines → 2
- Strip leading/trailing whitespace from text nodes
- Fix `&nbsp;` chains

### 9. Encoding Fix
- Run `ftfy.fix_text()` on raw text before parsing (mojibake fix)

## Output HTML Template

Each opinion page includes:
- Rich dark-mode design with sans-serif body font (Inter from embedded CSS, self-hosted via data URI fallback)
- Metadata header: case name, court, date, docket number, judges, status
- Table of contents (auto-generated from section headings)
- Opinion body with page-break markers as margin annotations
- Footnotes section at bottom with back-links
- Self-contained (single HTML file, inline CSS, no external dependencies)

## Index Page

Table with columns: Bucket, Opinion ID, Case Name, Court, Date Filed, Link.
Sorted by bucket then opinion_id.

## Dependencies

```
beautifulsoup4>=4.12
lxml>=5.0
ftfy>=6.1
Jinja2>=3.1
```

## Tests

- `test_cleaner.py`: running header detection, numbered-line stripping, whitespace normalization
- `test_parser.py`: XML format detection, div format detection, malformed XML fallback
- `test_transformer.py`: star-pagination anchor injection, footnote bidirectional links, citation URL fix

## Verification Plan

1. Run `python pipeline.py` and confirm 60 HTML files + index.html generated
2. Open index.html in browser, confirm all 60 links work
3. Open one easy, one medium, one hard opinion — check visually
4. Test star-pagination anchors: `opinion_355.html#star-153` should jump to page 153
5. Test footnote links: clicking footnote marker jumps to footnote; back-link returns to marker
6. Test citation links: CourtListener links are clickable
7. Run unit tests: `python -m pytest tests/ -v`
