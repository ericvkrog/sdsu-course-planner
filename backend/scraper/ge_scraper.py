"""
Scrapes SDSU General Education approved-course lists from catalog.sdsu.edu
(catoid=12, the same catalog as the course/program data).

The GE requirements page lists, per area, the approved courses inline as linked
course codes. This walks each acalog-core section, maps its header to a GE area
code, normalizes the codes against the course catalog, and writes:

    data/catalog/ge_areas.json   { "1A": ["AAS 150", ...], "2": [...], ... }

Area codes match the GE placeholder areas in ge_requirements.py:
    1A 1B 1C 2 3A 3B 4A 4B 5A 5B 5C 6  (lower division)
    UD2 UD3 UD4                          (upper-division Explorations)

The lower-division "Area 4" list feeds BOTH 4A and 4B (one approved pool, two
slots). The upper-division areas appear after the "Explorations of Human
Experience" header: "Area 2 or 5" → UD2, "Area 3" → UD3, "Area 4" → UD4.

Usage:
    python -m backend.scraper.ge_scraper            # scrape + write
    python -m backend.scraper.ge_scraper --dry-run  # print counts, don't write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.engine.course_codes import CodeResolver
from backend.scraper.program_scraper import get_soup, _course_codes_from_section

CATOID = 12
GE_POID = 11884
URL = f"https://catalog.sdsu.edu/preview_program.php?catoid={CATOID}&poid={GE_POID}"
CATALOG_DIR = ROOT / "data" / "catalog"
OUT_PATH = CATALOG_DIR / "ge_areas.json"


def _area_keys(header: str, upper_division: bool) -> list[str]:
    """Map a section header to its GE area code(s). Returns [] for non-area headers."""
    h = header.strip()
    if upper_division:
        # Explorations: only three upper-division areas.
        if re.match(r"Area\s+2\s+or\s+5", h, re.I):
            return ["UD2"]
        if re.match(r"Area\s+3\b", h, re.I):
            return ["UD3"]
        if re.match(r"Area\s+4\b", h, re.I):
            return ["UD4"]
        return []
    # Lower division. Sub-area headers like "1A. English Composition".
    m = re.match(r"(\d[ABC])\.", h)
    if m:
        return [m.group(1)]
    # Single-list areas titled "Area N. ...".
    m = re.match(r"Area\s+(\d)\b", h, re.I)
    if m:
        n = m.group(1)
        if n == "2":
            return ["2"]
        if n == "4":
            return ["4A", "4B"]   # one approved pool fills both Area 4 slots
        if n == "6":
            return ["6"]
    return []


def scrape_ge_areas(session: requests.Session, resolver: CodeResolver) -> dict[str, list[str]]:
    soup = get_soup(URL, session)
    areas: dict[str, list[str]] = {}
    unresolved: list[str] = []
    upper_division = False

    for core in soup.find_all("div", class_="acalog-core"):
        header_tag = core.find(["h2", "h3", "h4"])
        header = header_tag.get_text(" ", strip=True) if header_tag else ""
        if "Explorations of Human Experience" in header:
            upper_division = True
            continue

        keys = _area_keys(header, upper_division)
        if not keys:
            continue
        raw_codes = _course_codes_from_section(core)
        if not raw_codes:
            continue
        resolved, unres = resolver.resolve_list(raw_codes)
        unresolved.extend(unres)
        for key in keys:
            bucket = areas.setdefault(key, [])
            for code in resolved:
                if code not in bucket:
                    bucket.append(code)

    # Stable, lowest-number-first ordering within each area.
    def _num(code: str) -> int:
        m = re.search(r"(\d+)", code)
        return int(m.group(1)) if m else 999
    for key in areas:
        areas[key] = sorted(areas[key], key=lambda c: (c.split()[0], _num(c)))

    if unresolved:
        print(f"  ({len(set(unresolved))} unresolved codes skipped)")
    return areas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Print counts without writing")
    args = ap.parse_args()

    resolver = CodeResolver.from_catalog_dir(CATALOG_DIR)
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; SDSU-planner/1.0)"

    areas = scrape_ge_areas(session, resolver)
    order = ["1A", "1B", "1C", "2", "3A", "3B", "4A", "4B", "5A", "5B", "5C", "6", "UD2", "UD3", "UD4"]
    print("GE area course counts:")
    for k in order:
        print(f"  {k:4} {len(areas.get(k, [])):4} courses")
    missing = [k for k in order if not areas.get(k)]
    if missing:
        print(f"WARNING: no courses found for areas {missing}")

    if args.dry_run:
        print("\n(dry run — not written)")
        return
    # Write in canonical area order.
    ordered = {k: areas[k] for k in order if k in areas}
    OUT_PATH.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n")
    print(f"\nWrote {OUT_PATH} ({sum(len(v) for v in ordered.values())} course entries)")


if __name__ == "__main__":
    main()
