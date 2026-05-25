# Legal Opinion Pipeline — Walkthrough

## What Was Built

A Python 3.10+ pipeline (`pipeline.py`) that reads 60 federal appellate opinions from `opinion_bucket_export_20_each.csv` and produces clean, self-contained HTML for each opinion plus a searchable index page.

## Final Pipeline Results

- **60/60 opinions processed — 0 failures**
- **37/37 unit tests passing**
- **231** star-pagination anchors rendered and linkable (e.g. `opinion_355.html#star-153`)
- **173** footnote back-links generated
- **1,792** citation spans preserved (most with clickable links)
- **59/60** opinions have a navigable table of contents

## Deliverables Structure

```
.
├── README.md                   ← Design decisions, per-bucket quality notes, known issues
├── pipeline.py                 ← Entry point (python pipeline.py)
├── requirements.txt
├── src/
│   ├── parser.py               ← Format detection + BeautifulSoup parsing
│   ├── cleaner.py              ← Plain-text artifact removal (fallback path)
│   ├── transformer.py          ← HTML normalisation (star-pagination, footnotes, citations)
│   ├── renderer.py             ← Section extraction + Jinja2 templating
│   └── index_builder.py        ← index.html generation
├── output/
│   ├── index.html              ← Searchable table of all 60 opinions
│   ├── assets/style.css        ← Self-contained CSS (no CDN dependencies)
│   └── <opinion_id>.html × 60
└── tests/
    ├── test_cleaner.py         ← 12 tests
    ├── test_parser.py          ← 11 tests
    └── test_transformer.py     ← 14 tests
```

## Key Features Verified

### Star-Pagination Anchors
URL like `355.html#star-153` jumps directly to reporter page 153 mid-opinion. Handled in both XML format (`label="153"` attribute) and div format (parsed from text content).

### Footnotes — Bidirectional
- Forward ref: `<a class="footnote-ref" href="#fn1" id="fn1_ref">1</a>` in body
- Back-ref: `<a class="footnote-backref" href="#fn1_ref">↩</a>` appended to each footnote item

### Citation Preservation
All `<span class="citation">` spans preserved. Relative CourtListener paths (`/opinion/...`) made absolute (`https://www.courtlistener.com/opinion/...`).

### Format Heterogeneity
- 56 XML-flavored opinions: parsed with `lxml-xml` (falls back to `html.parser` on malformed docs)
- 4 div/center-flavored opinions (ca9, cafc): parsed with `html.parser`, caption detected from leading `<center>/<h1>` blocks

### Hard Bucket Highlights
- **Opinion 46** (Cameron v. City of New York, 29 pages, ca2): 15 star-pagination anchors, numbered-line stripping active
- **Opinion 98** (United States v. Davis, 17 pages): 14 star anchors
- **Opinion 46** renders fully at 89KB — no truncation

### Design — Dark Mode Premium
- Dark glassmorphic theme (`#0f1117` background, accent blues/gold)
- Sidebar table of contents with active-section highlighting via IntersectionObserver
- Metadata card with bucket badge (Easy/Medium/Hard color-coded), court, date, docket
- Index page with live search filtering by case name, court, docket

## Tests Run

```
37 passed, 1 warning in 0.41s
```

The warning is a BeautifulSoup advisory in one test that intentionally uses `html.parser` on XML (expected and harmless in that test context).
