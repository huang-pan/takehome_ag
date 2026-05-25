"""
src/index_builder.py

Build the output/index.html listing all 60 opinions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from jinja2 import Environment

_INDEX_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Federal Appellate Opinions — OurFirm Legal</title>
  <meta name="description" content="Index of 60 federal appellate opinions from Circuit Courts, filed 2010.">
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>

<div style="display:flex; flex-direction:column; min-height:100vh;">

  <header class="site-header" role="banner">
    <div class="logo"><a href="index.html" data-same-tab>Our<span>Firm</span> Legal</a></div>
    <nav class="header-meta" aria-label="breadcrumb">Federal Appellate Opinions — 2010</nav>
  </header>

  <div class="index-hero">
    <h1>Federal Appellate Opinions</h1>
    <p>
      60 opinions from U.S. Circuit Courts (Circuits 1–11 + Federal Circuit),
      filed 2010. Sourced from CourtListener / Free Law Project.
    </p>
  </div>

  <div class="index-container">

    <div class="filter-bar">
      <input
        type="search"
        id="search-input"
        class="filter-input"
        placeholder="Search case name, court, docket…"
        aria-label="Search opinions"
        autocomplete="off"
      >
    </div>

    <div class="stats-bar" id="stats-bar">
      Showing <strong id="visible-count">{{ rows|length }}</strong> of {{ rows|length }} opinions
    </div>

    {% for bucket in ['easy', 'medium', 'hard'] %}
    {% set group = rows | selectattr('bucket', 'equalto', bucket) | list %}
    {% if group %}
    <div class="bucket-group" data-bucket="{{ bucket }}">
      <div class="bucket-heading">
        {{ bucket | capitalize }} bucket — {{ group|length }} opinions
      </div>
      <table class="opinions-table" aria-label="{{ bucket }} opinions">
        <thead>
          <tr>
            <th>ID</th>
            <th>Case Name</th>
            <th>Court</th>
            <th style="white-space:nowrap">Date Filed</th>
            <th>Docket</th>
            <th>Status</th>
            <th>Pages</th>
            <th style="width:6rem;white-space:nowrap">Link</th>
          </tr>
        </thead>
        <tbody>
          {% for row in group %}
          <tr class="op-row" data-search="{{ row.case_name|lower }} {{ row.court_id|lower }} {{ row.docket_number|lower }}">
            <td>{{ row.opinion_id }}</td>
            <td class="case-name">{{ row.case_name }}</td>
            <td>{{ row.court_id | upper }}</td>
            <td style="white-space:nowrap">{{ row.date_filed }}</td>
            <td style="font-family:var(--font-mono);font-size:0.75rem">{{ row.docket_number }}</td>
            <td>
              {% if row.precedential_status|lower == 'published' %}
              <span class="badge badge-published">Published</span>
              {% else %}
              <span class="badge badge-unpublished">{{ row.precedential_status }}</span>
              {% endif %}
            </td>
            <td>{{ row.page_count }}</td>
            <td style="white-space:nowrap">
              {% if row.ok %}
              <a href="{{ row.opinion_id }}.html" class="op-link" data-same-tab>
                View &rarr;
              </a>
              {% else %}
              <span style="color:var(--text-muted);font-size:0.78rem;font-family:var(--font-ui)">
                ⚠ Error
              </span>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% endif %}
    {% endfor %}

  </div>

</div>

<script>
(function(){
  var input = document.getElementById('search-input');
  var counter = document.getElementById('visible-count');
  var rows = document.querySelectorAll('.op-row');

  function filter(){
    var q = input.value.toLowerCase().trim();
    var visible = 0;
    rows.forEach(function(row){
      var match = !q || row.dataset.search.indexOf(q) !== -1;
      row.style.display = match ? '' : 'none';
      if(match) visible++;
    });
    counter.textContent = visible;
  }

  input.addEventListener('input', filter);

  // Open all non-anchor, non-nav links in a new tab
  document.querySelectorAll('a[href]').forEach(function(a){
    var h = a.getAttribute('href');
    if(h && !h.startsWith('#') && !a.hasAttribute('data-same-tab')){
      a.setAttribute('target', '_blank');
      a.setAttribute('rel', 'noopener noreferrer');
    }
  });
})();
</script>

</body>
</html>"""


@dataclass
class IndexRow:
    opinion_id: str
    case_name: str
    court_id: str
    date_filed: str
    docket_number: str
    precedential_status: str
    page_count: str
    bucket: str
    ok: bool = True  # False if pipeline errored on this opinion


def build_index(rows: list[IndexRow]) -> str:
    """Render the index HTML page."""
    env = Environment(autoescape=True)
    tmpl = env.from_string(_INDEX_TEMPLATE)
    return tmpl.render(rows=rows)
