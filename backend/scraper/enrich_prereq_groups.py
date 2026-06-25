"""
Prerequisite OR-group enrichment.

The original catalog scrape flattened prerequisites to individual course codes
and discarded the "and"/"or" connectives, so the engine treated every listed
prereq as an AND requirement. Courses whose catalog text reads "A or B" (e.g.
SPAN 307: "SPAN 301 and SPAN 302, or SPAN 381 or SPAN 382") were therefore
over-constrained and could not be placed.

This script re-fetches each department page, re-parses prerequisites with the
OR-aware catalog_scraper.parse_prereqs (which now emits prereq_group), and
writes a SPARSE overlay — data/catalog/prereq_groups.json — listing only the
courses that have an OR-group. It does NOT touch the existing catalog JSON.

The overlay is applied at plan time by backend.engine.prereq_groups, so both
the JSON-backed engine path and the DB-backed API path pick up the groups
without a reseed.

Usage:
    python -m backend.scraper.enrich_prereq_groups            # all departments
    python -m backend.scraper.enrich_prereq_groups --delay 1.0
    python -m backend.scraper.enrich_prereq_groups --dept SPAN # one dept (test)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scraper.catalog_scraper import (
    DATA_DIR,
    DEFAULT_DELAY,
    get_departments,
    scrape_department,
)

OVERLAY_PATH = DATA_DIR / "prereq_groups.json"


def build_overlay(dept_codes: list[str], session: requests.Session, delay: float) -> dict:
    """
    Return {course_code: {prereq_code: group_id}} for every course that has an
    OR-grouped prerequisite. Courses with only AND prereqs are omitted.
    """
    overlay: dict[str, dict[str, int]] = {}
    for i, dept in enumerate(dept_codes, 1):
        courses = scrape_department(dept, session, delay)
        dept_or = 0
        for course in courses:
            groups: dict[str, int] = {}
            for row in course.get("prerequisites", []):
                gid = row.get("prereq_group")
                code = row.get("prereq_code")
                if gid is not None and code:
                    groups[code] = gid
            if groups:
                overlay[course["course_code"]] = groups
                dept_or += 1
        print(f"[{i}/{len(dept_codes)}] {dept}: {len(courses)} courses, {dept_or} with OR-groups")
    return overlay


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Seconds between requests")
    ap.add_argument("--dept", type=str, default=None, help="Single department code (testing)")
    args = ap.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; SDSU-planner/1.0)"

    if args.dept:
        dept_codes = [args.dept]
    else:
        dept_codes = [d["dept_code"] for d in get_departments(session)]
    print(f"Enriching OR-groups for {len(dept_codes)} department(s).\n")

    overlay = build_overlay(dept_codes, session, args.delay)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OVERLAY_PATH.write_text(
        json.dumps(overlay, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )
    total_pairs = sum(len(v) for v in overlay.values())
    print(
        f"\nDone. {len(overlay)} courses with OR-groups "
        f"({total_pairs} prereq rows) → {OVERLAY_PATH.name}"
    )


if __name__ == "__main__":
    main()
