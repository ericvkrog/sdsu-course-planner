"""
Multi-major validation harness.

Runs the planning engine for every supported major against local JSON catalog
data (no DB/API needed) and reports placement counts + conflicts for each.
Mirrors the dynamic semester_count logic used by the /plan/generate route.

Run from the project root:
    python -m backend.engine.validate_all_majors
"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.engine.ge_requirements import (
    get_ge_placeholder_courses,
    get_ge_placeholder_prereqs,
)
from backend.engine.catalog_fixes import apply_course_aliases, get_catalog_fix_prereqs
from backend.engine.graduation_requirements import (
    get_additional_placeholder_courses,
    get_additional_placeholder_prereqs,
    get_free_elective_courses,
)
from backend.engine.major_requirements import SUPPORTED_MAJORS, get_required_courses
from backend.engine.prereq_checker import check_prereq_chains
from backend.engine.solver import plan_courses
from backend.engine.test_solver import load_courses_from_json
from backend.engine.validator import validate_plan

MAX_UNITS = 15
# Mirror the route's adaptive-semester ceiling (see routes/plan.py MAX_SEMESTERS).
MAX_SEMESTERS = 14


def validate_major(major: str, all_courses: list[dict], all_prereqs_base: list[dict], verbose: bool = True) -> dict:
    units_by_code = {c["course_code"]: c.get("units", 3) for c in all_courses}
    required = get_required_courses(
        major=major, completed_courses=[], include_ge=True, include_ai=True,
        units_by_code=units_by_code,
    )

    prereqs = apply_course_aliases(list(all_prereqs_base))
    prereqs = prereqs + get_catalog_fix_prereqs(set(required))
    prereqs = prereqs + get_ge_placeholder_prereqs()
    gr_courses = get_additional_placeholder_courses(
        include_gwar=True, include_ai=True, completed_courses=[], required_courses=required
    )
    gr_prereqs = get_additional_placeholder_prereqs(
        include_gwar=True, include_ai=True, completed_courses=[], required_courses=required
    )
    n_free = sum(1 for c in required if c.startswith("FREE "))
    courses = all_courses + get_ge_placeholder_courses() + gr_courses + get_free_elective_courses(n_free)
    prereqs = prereqs + gr_prereqs

    needed = set(required)
    relevant_courses = [c for c in courses if c["course_code"] in needed]
    relevant_prereqs = [p for p in prereqs if p["course_code"] in needed]

    # Adaptive semester count — same logic as /plan/generate: units estimate
    # as a floor, then retry up to 10 and keep the first conflict-free plan.
    courses_by_code = {c["course_code"]: c for c in relevant_courses}
    total_units = sum(courses_by_code.get(c, {}).get("units", 3) for c in required)
    effective_rate = max(MAX_UNITS - 1, 1)
    floor_count = min(MAX_SEMESTERS, max(8, math.ceil(total_units / effective_rate)))

    result = None
    semester_count = floor_count
    for sc in range(floor_count, MAX_SEMESTERS + 1):
        candidate = plan_courses(
            required_course_codes=required,
            completed_course_codes=[],
            courses=relevant_courses,
            prerequisites=relevant_prereqs,
            max_units_per_semester=MAX_UNITS,
            semester_count=sc,
        )
        if result is None or len(candidate.conflicts) < len(result.conflicts):
            result, semester_count = candidate, sc
        if not candidate.conflicts:
            break

    placed = sum(len(s.courses) for s in result.semesters)
    val = validate_plan(
        semesters=[
            {"semester": s.semester, "year": s.year, "courses": s.courses, "total_units": s.total_units}
            for s in result.semesters
        ],
        prerequisites=relevant_prereqs,
        max_units_per_semester=MAX_UNITS,
        completed_course_codes=[],
    )
    chain = check_prereq_chains(
        semesters=result.semesters, prerequisites=relevant_prereqs, completed_course_codes=[]
    )

    n_conflicts = len(result.conflicts) + len(val) + len(chain)
    clean = n_conflicts == 0

    if verbose:
        status = "CLEAN" if clean else "CONFLICTS"
        print(f"{major:30.30} {placed}/{len(required)} placed, {status}, {semester_count} sems")
        for c in result.conflicts:
            print(f"    [solver]    [{c['course_code']}] {c['reason']}")
        for c in val:
            print(f"    [validator] [{c['course_code']}] {c['reason']}")
        for v in chain:
            print(f"    [chain]     [{v['course_code']}] {v['reason']}")

    return {
        "clean": clean,
        "placed": placed,
        "total": len(required),
        "n_conflicts": n_conflicts,
        "semesters": semester_count,
    }


if __name__ == "__main__":
    all_courses, all_prereqs = load_courses_from_json()
    print(f"Loaded {len(all_courses)} courses, {len(all_prereqs)} prereq rows.")
    print(f"Majors in registry: {len(SUPPORTED_MAJORS)}\n")

    verified = {c for c, m in SUPPORTED_MAJORS.items() if m.verified}
    scraped = {c for c in SUPPORTED_MAJORS if c not in verified}

    # ── Verified majors: must all be clean (these gate the build) ──────────
    print("=== VERIFIED MAJORS (must be clean) ===")
    verified_results = {
        m: validate_major(m, all_courses, all_prereqs, verbose=True)
        for m in sorted(verified)
    }
    verified_ok = all(r["clean"] for r in verified_results.values())

    # ── Scraped majors: coverage report, conflicts expected ───────────────
    print(f"\n=== SCRAPED MAJORS ({len(scraped)}) — coverage report ===")
    scraped_results = {
        m: validate_major(m, all_courses, all_prereqs, verbose=False)
        for m in sorted(scraped)
    }
    if scraped_results:
        clean_n = sum(1 for r in scraped_results.values() if r["clean"])
        placed_pct = [
            r["placed"] / r["total"] for r in scraped_results.values() if r["total"]
        ]
        avg_placed = (sum(placed_pct) / len(placed_pct) * 100) if placed_pct else 0
        full_place = sum(1 for r in scraped_results.values() if r["placed"] == r["total"])
        print(f"  {len(scraped_results)} scraped majors")
        print(f"  {clean_n} fully clean (zero conflicts)")
        print(f"  {full_place} place 100% of courses")
        print(f"  {avg_placed:.0f}% average course placement")
        # Worst offenders
        worst = sorted(scraped_results.items(), key=lambda kv: kv[1]["n_conflicts"], reverse=True)[:8]
        print("  Most conflicts:")
        for code, r in worst:
            if r["n_conflicts"]:
                print(f"    {code:40.40} {r['n_conflicts']} conflicts, {r['placed']}/{r['total']} placed")

    print()
    if verified_ok:
        print("VERIFIED MAJORS ALL CLEAN.")
    else:
        failed = [m for m, r in verified_results.items() if not r["clean"]]
        print(f"VERIFIED FAILURES: {', '.join(failed)}")
        sys.exit(1)
