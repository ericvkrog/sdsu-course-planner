"""
Loads scraped JSON from data/catalog/*.json into Supabase.

Run after schema.sql has been applied to your Supabase project:
    python seed.py               # load all departments
    python seed.py --dept CS     # single department
    python seed.py --dry-run     # print stats without writing to DB
"""

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "catalog"
DEPARTMENT_INDEX_PATH = DATA_DIR / "departments.json"
BATCH_SIZE = 100  # rows per upsert call


def get_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    return create_client(url, key)


def load_json_files(dept_filter: Optional[str]) -> list[dict]:
    pattern = DATA_DIR / "*.json"
    all_courses: list[dict] = []
    for path in sorted(glob.glob(str(pattern))):
        if Path(path).name in (DEPARTMENT_INDEX_PATH.name, "prereq_groups.json", "ge_areas.json"):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if dept_filter:
            data = [c for c in data if c["department"].upper() == dept_filter.upper()]
        all_courses.extend(data)
    return all_courses


def load_department_index() -> dict[str, dict]:
    if not DEPARTMENT_INDEX_PATH.exists():
        return {}
    with open(DEPARTMENT_INDEX_PATH, encoding="utf-8") as f:
        rows = json.load(f)
    return {row["dept_code"]: row for row in rows}


def upsert_courses(client: Client, courses: list[dict], dry_run: bool) -> int:
    rows = [
        {
            "course_code": c["course_code"],
            "title": c["title"],
            "units": c["units"],
            "department": c["department"],
            "description": c.get("description"),
            "grading_method": c.get("grading_method"),
            "offered_fall": c.get("offered_fall", True),
            "offered_spring": c.get("offered_spring", True),
            "max_credits": c.get("max_credits"),
            "notes": c.get("notes"),
        }
        for c in courses
    ]
    if dry_run:
        return len(rows)
    for i in range(0, len(rows), BATCH_SIZE):
        client.table("courses").upsert(rows[i : i + BATCH_SIZE]).execute()
    return len(rows)


def upsert_departments(client: Client, courses: list[dict], dry_run: bool) -> int:
    index = load_department_index()
    seen: dict[str, dict] = {}
    for c in courses:
        code = c["department"]
        seen[code] = {
            "dept_code": code,
            "dept_name": index.get(code, {}).get("dept_name", code),
            "catalog_url": index.get(code, {}).get("catalog_url"),
        }
    rows = list(seen.values())
    if dry_run:
        return len(rows)
    for i in range(0, len(rows), BATCH_SIZE):
        client.table("departments").upsert(rows[i : i + BATCH_SIZE]).execute()
    return len(rows)


def upsert_prerequisites(client: Client, courses: list[dict], dry_run: bool) -> int:
    known_codes = {c["course_code"] for c in courses}
    rows = []
    seen_rows = set()
    skipped = []
    for c in courses:
        for p in c.get("prerequisites", []):
            if not p.get("prereq_code") and not p.get("min_standing"):
                continue
            prereq_code = p.get("prereq_code")
            if prereq_code and prereq_code not in known_codes:
                skipped.append((c["course_code"], prereq_code))
                continue
            row = {
                "course_code": c["course_code"],
                "prereq_code": prereq_code,
                "prereq_type": p.get("prereq_type", "required"),
                "min_standing": p.get("min_standing"),
            }
            key = tuple(row.values())
            if key in seen_rows:
                continue
            seen_rows.add(key)
            rows.append(row)
    if skipped:
        print(f"  Skipped {len(skipped)} prereq rows referencing unknown course codes")
        for course_code, prereq_code in skipped[:10]:
            print(f"    {course_code} -> {prereq_code}")
        if len(skipped) > 10:
            print(f"    ...and {len(skipped) - 10} more")
    if dry_run:
        return len(rows)
    # Delete existing prereqs for every loaded course before re-inserting.
    # This removes stale rows when a course now has no prerequisites.
    course_codes = [course["course_code"] for course in courses]
    for i in range(0, len(course_codes), BATCH_SIZE):
        chunk = course_codes[i : i + BATCH_SIZE]
        client.table("prerequisites").delete().in_("course_code", chunk).execute()
    for i in range(0, len(rows), BATCH_SIZE):
        client.table("prerequisites").insert(rows[i : i + BATCH_SIZE]).execute()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Supabase from scraped JSON")
    parser.add_argument("--dept", help="Load only this department (e.g. CS)")
    parser.add_argument("--dry-run", action="store_true", help="Count rows without writing")
    args = parser.parse_args()

    print("Loading JSON files...")
    courses = load_json_files(args.dept)
    print(f"  {len(courses)} courses from {len({c['department'] for c in courses})} departments")

    if args.dry_run:
        print("[DRY RUN — no DB writes]")
        client = None
    else:
        client = get_client()

    print("Upserting departments...")
    n = upsert_departments(client, courses, args.dry_run)
    print(f"  {n} departments")

    print("Upserting courses...")
    n = upsert_courses(client, courses, args.dry_run)
    print(f"  {n} courses")

    print("Upserting prerequisites...")
    n = upsert_prerequisites(client, courses, args.dry_run)
    print(f"  {n} prerequisite rows")

    print("Done.")


if __name__ == "__main__":
    main()
