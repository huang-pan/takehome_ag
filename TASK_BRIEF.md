# Technical Assessment — Legal Opinion Cleanup & Rendering Pipeline

**Role:** Data Engineer

---

## Context

Our pipeline ingests US federal court opinions sourced from [CourtListener](https://www.courtlistener.com) (Free Law Project). Each opinion ships in two forms: a dirty `plain_text` field extracted from the source PDF, and an `html_with_citations` field with some semantic markup already applied. Both have problems:

- The plain text carries every PDF extraction artifact you'd expect: form-feed page breaks, repeated running headers, line numbers from typewriter-style briefs, page numbers stranded mid-stream, ragged justified-text whitespace, footnotes whose layout collapsed, captions flattened into one column.
- The HTML is markup but not pretty. It arrives in **at least two distinct formats** — a CourtListener-style XML structure (`<opinion type="majority">` with `<p id="...">` blocks) and an older `<div>/<center>` style — and neither renders as a polished reading experience out of the box.

We want a clean, repeatable pipeline that produces a readable HTML version of any opinion in the corpus: proper structure, citations preserved, original page boundaries visible, footnotes that actually work.

---

## The dataset

`opinion_bucket_export_20_each.csv` — **60 federal appellate opinions** from Circuit Courts 1–11 plus the Federal Circuit, all filed 2010. Key columns:

- **`plain_text`** — the dirty raw extraction. Form-feed (`\f`) marks original page breaks.
- **`html_with_citations`** — already-tagged HTML in one of two formats (XML-flavored or div/center-flavored). Contains inline `<span class="citation">…</span>` tags and `<span class="star-pagination">` markers for original reporter pagination (e.g. `*311` = page 311 of the bound volume begins here — this is how lawyers cite specific passages).
- **`bucket`** — `easy`, `medium`, or `hard`, 20 of each. This is your roadmap.
- `case_name`, `court_id`, `date_filed`, `docket_number`, `judges`, `precedential_status` — metadata for the rendered page header.
- `page_count`, `opinion_type`, `extracted_by_ocr` — useful signals.

Bucket shape:

| Bucket | Avg pages | Avg text size | Typical character |
|---|---|---|---|
| easy   |  ~3 | ~4 KB  | Short unpublished per curiam, simple structure |
| medium |  ~9 | ~15 KB | Published opinions with full captions and citation density |
| hard   | ~15 | ~28 KB | Multi-opinion (majority + dissent), numbered lines, OCR-ish whitespace, mixed formatting |

---

## Your task

Build a Python pipeline that, given the CSV, produces a clean, readable HTML rendering of each opinion. Specifically:

1. **Choose your input source(s) deliberately.** You can clean `plain_text`, transform `html_with_citations`, or fuse the two. Justify the choice in your README. A pipeline that handles the heterogeneity of `html_with_citations` (or that gracefully degrades when one source is unusable) earns more credit than one that hard-codes to a single format.
2. **Clean structure.** Strip repeated running headers, drop stranded page and line numbers, collapse pathological whitespace, fix any encoding mojibake, identify and mark sections (caption block, counsel block, per curiam / opinion / dissent), preserve italics and emphasis where present in the source.
3. **Page boundaries.** Each original page break must be visible in the rendered output — pick a visual treatment you like (margin marker, subtle divider, hover tooltip). Preserve the **star-pagination** markers as well; they should be visible and ideally anchor-linkable so a URL like `…/opinion_355.html#star-414` jumps to that reporter page.
4. **Citations.** The source HTML already tags many citations with `<span class="citation">…</span>`. Preserve them, and if there's a useful URL (some are already wrapped in `<a href>` in the data), keep it clickable.
5. **Footnotes.** Where opinions have footnotes, render them with bidirectional links: marker in body → footnote at end of opinion → back to marker. Numbering should be consistent within each opinion.
6. **Rendered output.** Write one HTML file per opinion to an `output/` directory, plus an `index.html` listing all 60 (bucket, case name, court, date, link).
7. **Document your work.** A `README.md` covering: which fields you used and why, the cleaning decisions you made, what works per bucket, what's broken, and what you'd fix next.

---

## Deliverables

```
.
├── README.md
├── pipeline.py            # or src/ — your call
├── requirements.txt
├── output/
│   ├── index.html
│   ├── <opinion_id>.html  × 60
│   └── assets/            # optional separate CSS
└── tests/                 # unit tests on the trickiest bits
```

---

## Constraints

- **Python 3.10+.**
- **Libraries:** standard library preferred. You may use production-grade tools (BeautifulSoup, lxml, ftfy, Jinja2, etc.) — be ready to justify the choice.
- **No LLM API calls** for the cleaning itself. We're evaluating your engineering, not your prompting.
- **Self-contained outputs.** Each HTML should render correctly when opened directly from the filesystem. Relative `assets/` is fine; no CDN dependencies.
- **No JS frameworks.** Footnote and page-anchor linking should work with plain `<a href>`.
- **Failure isolation.** A crash on one opinion must not abort the run for the other 59. Log and continue.

---

## Evaluation criteria

| Area | Weight | What we're looking for |
|---|---|---|
| Easy bucket quality | 25% | Clean, readable, no obvious artifacts left. If easy isn't solid the rest doesn't matter. |
| Medium bucket quality | 20% | Citations preserved, captions readable, paragraphs reflowed correctly. |
| Hard bucket quality | 15% | Doesn't have to be perfect, but should be visibly *better* than raw — and you should know what's still broken. |
| Pipeline design | 15% | Modular, reusable, deals with format heterogeneity, isolates per-row failures. |
| Page / footnote / citation handling | 15% | Page boundaries visible, star-pagination preserved and anchored, bidirectional footnote links working. |
| Communication | 10% | README explains decisions, trade-offs, and known limitations honestly. |

---

## Notes & clarifications

- The bucketing is a rough difficulty signal, not a separate spec per tier. Treat the buckets as scoring weights, not as conditional code paths.
- Some opinions (Second Circuit especially) have **numbered lines** from typewriter-style brief format: `" 1   highly prejudicial..."` at the start of each line. Stripping these without mangling text that genuinely begins with a digit is a worthwhile small problem.
- Some `html_with_citations` values are well-formed XML; others are loose HTML. A lenient parser (`lxml.html`, BeautifulSoup with the `html.parser` backend) handles both; a strict XML parser will choke on the second group.
- Star-pagination appears as `<span class="star-pagination" label="414"> *414 </span>` (XML format) or `<span class="star-pagination">*311</span>` (div format). Both are real reporter page boundaries — preserve them and make them anchor-able.
- `extracted_by_ocr` is `f` (false) for every row in this sample, so you don't need to handle scanned PDFs — but writing your code so it *could* is a plus.
