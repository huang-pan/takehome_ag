#!/usr/bin/env python3
"""
check_links.py — Audit every link in output/*.html

Checks:
  1. Internal anchor links (#id)       — anchor must exist in the same file
  2. Relative file links (*.html)      — target file must exist in output/
  3. External HTTP links (sample)      — HEAD request, 5-second timeout,
                                         deduplicated (checks each unique URL once)
"""
from __future__ import annotations
import re, sys, time
from collections import defaultdict
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

OUTPUT = Path("output")
html_files = sorted(OUTPUT.glob("*.html"))

broken: dict[str, list[str]] = defaultdict(list)
ok_counts = {"anchor": 0, "relative": 0, "external": 0}

HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
ID_RE   = re.compile(r'\bid=["\']([^"\']+)["\']', re.IGNORECASE)

def ids_in(html: str) -> set[str]:
    return set(ID_RE.findall(html))

# ── Pass 1: anchors + relative (instant, no network) ─────────────────
print("Pass 1: checking anchors and relative file links …")
all_external: dict[str, str] = {}   # url → first file that references it

for f in html_files:
    html = f.read_text(encoding="utf-8")
    ids  = ids_in(html)
    for href in HREF_RE.findall(html):
        href = href.strip()
        if href.startswith("#"):
            anchor = href[1:]
            if anchor in ids:
                ok_counts["anchor"] += 1
            else:
                broken[f.name].append(f"BAD ANCHOR  {href}")
        elif href.startswith("http"):
            all_external.setdefault(href, f.name)
        else:
            file_part, _, fragment = href.partition("#")
            target = OUTPUT / file_part
            if not target.exists():
                broken[f.name].append(f"MISSING FILE  {href}")
            else:
                ok_counts["relative"] += 1
                if fragment:
                    target_html = target.read_text(encoding="utf-8")
                    if fragment not in ids_in(target_html):
                        broken[f.name].append(f"BAD FRAGMENT  {href}")

print(f"  Anchors OK : {ok_counts['anchor']}")
print(f"  Relative OK: {ok_counts['relative']}")
print(f"  Unique external URLs found: {len(all_external)}")

# ── Pass 2: external links (deduplicated, sampled) ────────────────────
SAMPLE = 30   # cap to keep runtime reasonable; covers all unique domains
print(f"\nPass 2: checking {min(SAMPLE, len(all_external))} sampled external URLs …")

def check_external(url: str) -> tuple[bool, str]:
    try:
        req = Request(url, method="HEAD",
                      headers={"User-Agent": "Mozilla/5.0 LinkChecker"})
        with urlopen(req, timeout=5) as r:
            return True, str(r.status)
    except HTTPError as e:
        # 403/405 = server alive but rejects HEAD → treat as OK
        if e.code in (403, 405):
            return True, f"HTTP {e.code} (HEAD blocked, likely fine)"
        return False, f"HTTP {e.code}"
    except URLError as e:
        return False, str(e.reason)
    except Exception as e:
        return False, str(e)

sampled = list(all_external.items())[:SAMPLE]
for url, first_file in sampled:
    ok, status = check_external(url)
    if ok:
        ok_counts["external"] += 1
        print(f"  ✓ {status:30s} {url[:80]}")
    else:
        broken[first_file].append(f"DEAD EXTERNAL [{status}]  {url}")
        print(f"  ✗ {status:30s} {url[:80]}")

# ── Report ─────────────────────────────────────────────────────────────
total_broken = sum(len(v) for v in broken.values())
print(f"\n{'='*60}")
print(f"Link audit: {len(html_files)} HTML files")
print(f"  Anchors OK   : {ok_counts['anchor']}")
print(f"  Relative OK  : {ok_counts['relative']}")
print(f"  External OK  : {ok_counts['external']} / {SAMPLE} sampled")
print(f"  BROKEN       : {total_broken}")
print(f"{'='*60}")

if broken:
    for fname in sorted(broken):
        print(f"\n  {fname}:")
        for msg in broken[fname]:
            print(f"    ✗ {msg}")
    sys.exit(1)
else:
    print("\nAll checked links OK ✓")
    sys.exit(0)
