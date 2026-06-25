"""
End-to-end test of the Phase 2 planning engine.

Runs entirely from local JSON files — no database or API server required.
Run from the project root:

    python -m backend.engine.test_solver

Or:
    cd "Course Selector"
    python backend/engine/test_solver.py

Expected output for a first-run CS student (no completed courses):
  - 8 semesters of courses, lower-div courses in early semesters
  - Upper-div electives in later semesters
  - Zero or very few conflicts (some may exist for STAT 119 data-quality gap)
"""

import glob
import json
import sys
from pathlib import Path
from typing import Optional

# Make the project root importable when run as a script.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.engine.ge_requirements import (
    get_ge_placeholder_courses,
    get_ge_placeholder_prereqs,
)
from backend.engine.catalog_fixes import apply_course_aliases, get_catalog_fix_prereqs
from backend.engine.prereq_groups import apply_prereq_groups
from backend.engine.graduation_requirements import (
    get_additional_placeholder_courses,
    get_additional_placeholder_prereqs,
)
from backend.engine.major_requirements import get_required_courses
from backend.engine.prereq_checker import check_prereq_chains
from backend.engine.solver import plan_courses
from backend.engine.validator import validate_plan

DATA_DIR = ROOT / "data" / "catalog"


def load_courses_from_json() -> "tuple[list[dict], list[dict]]":
    """
    Load all course records and build prerequisite rows from local JSON.

    Returns:
        (courses, prereqs) — same format as the DB returns.
    """
    courses: list[dict] = []
    prereqs: list[dict] = []

    # Non-course data files that live in the same directory.
    _NON_COURSE = {"departments.json", "prereq_groups.json", "ge_areas.json"}
    for path in sorted(glob.glob(str(DATA_DIR / "*.json"))):
        if Path(path).name in _NON_COURSE:
            continue
        with open(path, encoding="utf-8") as f:
            dept_courses = json.load(f)

        for course in dept_courses:
            # Build a DB-compatible course dict (drop the source_url scraper field).
            courses.append({
                "course_code": course["course_code"],
                "title": course["title"],
                "units": course["units"],
                "department": course["department"],
                "description": course.get("description"),
                "grading_method": course.get("grading_method"),
                "offered_fall": course.get("offered_fall", True),
                "offered_spring": course.get("offered_spring", True),
                "max_credits": course.get("max_credits"),
                "notes": course.get("notes"),
            })

            # Build prereq rows (same shape as the prerequisites table).
            for p in course.get("prerequisites", []):
                if not p.get("prereq_code") and not p.get("min_standing"):
                    continue
                prereqs.append({
                    "course_code": course["course_code"],
                    "prereq_code": p.get("prereq_code"),
                    "prereq_type": p.get("prereq_type", "required"),
                    "min_standing": p.get("min_standing"),
                    "prereq_group": p.get("prereq_group"),
                })

    # Overlay OR-groups recovered by the enrichment pass (catalog JSON predates
    # the OR-aware scraper, so groups arrive via the overlay rather than inline).
    prereqs = apply_prereq_groups(prereqs)
    return courses, prereqs


def run_test(
    completed: Optional[list[str]] = None,
    start_semester: str = "Fall",
    start_year: int = 2025,
    max_units: int = 17,
    include_ge: bool = False,
    include_ai: bool = False,
    verbose: bool = True,
) -> None:
    """
    Run the solver for the CS major and print the resulting plan.

    Args:
        completed: List of course codes the student has already taken.
        start_semester: "Fall" or "Spring"
        start_year: Year of first semester.
        max_units: Unit cap per semester.
        verbose: Print each course's details (vs. just codes).
    """
    completed = completed or []
    required = get_required_courses(
        major="CS",
        completed_courses=completed,
        include_ge=include_ge,
        include_ai=include_ai,
    )

    extras = []
    if include_ge:
        extras.append("+GE")
    if include_ai:
        extras.append("+AI")
    extras_str = " ".join(extras)

    print(f"\n{'='*60}")
    print(f"CS B.S. PLAN — {start_semester} {start_year} start {extras_str}")
    print(f"  Required courses : {len(required)}")
    print(f"  Already completed: {len(completed)}")
    print(f"  Unit cap         : {max_units}/semester")
    print(f"{'='*60}\n")

    print("Loading course data from JSON files...")
    all_courses, all_prereqs = load_courses_from_json()

    # Apply course aliases (old→current names) then inject missing prereqs.
    all_prereqs = apply_course_aliases(all_prereqs)
    all_prereqs = all_prereqs + get_catalog_fix_prereqs(set(required) | set(completed))

    # Inject GE placeholder records so the solver can place them.
    if include_ge:
        all_courses = all_courses + get_ge_placeholder_courses()
        all_prereqs = all_prereqs + get_ge_placeholder_prereqs()

    # Inject graduation requirement placeholder records.
    # GWAR is always included; placeholder only appears when not covered by CS 532.
    gr_courses = get_additional_placeholder_courses(
        include_gwar=True, include_ai=include_ai,
        completed_courses=completed, required_courses=required,
    )
    gr_prereqs = get_additional_placeholder_prereqs(
        include_gwar=True, include_ai=include_ai,
        completed_courses=completed, required_courses=required,
    )
    all_courses = all_courses + gr_courses
    all_prereqs = all_prereqs + gr_prereqs

    codes_by_course = {c["course_code"]: c for c in all_courses}

    # Only pass courses and prereqs relevant to this plan.
    needed_codes = set(required) | set(completed)
    relevant_courses = [c for c in all_courses if c["course_code"] in needed_codes]
    relevant_prereqs = [p for p in all_prereqs if p["course_code"] in set(required)]

    missing = [c for c in required if c not in codes_by_course]
    if missing:
        print(f"WARNING: {len(missing)} required course(s) not found in JSON data:")
        for code in missing:
            print(f"  {code}")
        print()

    print("Running solver...\n")
    result = plan_courses(
        required_course_codes=required,
        completed_course_codes=completed,
        courses=relevant_courses,
        prerequisites=relevant_prereqs,
        max_units_per_semester=max_units,
        start_semester=start_semester,
        start_year=start_year,
        semester_count=8,
    )

    # ── Print plan ──────────────────────────────────────────────────────────
    total_placed = 0
    for sem in result.semesters:
        if not sem.courses:
            print(f"{sem.semester} {sem.year}  (empty)")
            continue
        print(f"{sem.semester} {sem.year}  [{sem.total_units} units]")
        for course in sem.courses:
            if verbose:
                print(f"  {course['course_code']:<12} {course['title'][:45]:<46} {course['units']}u")
            else:
                print(f"  {course['course_code']}", end="  ")
        if not verbose:
            print()
        total_placed += len(sem.courses)
        print()

    print(f"Placed {total_placed} / {len(required)} required courses.\n")

    # ── Print conflicts ─────────────────────────────────────────────────────
    if result.conflicts:
        print(f"CONFLICTS ({len(result.conflicts)}):")
        for c in result.conflicts:
            print(f"  [{c['course_code']}] {c['reason']}")
    else:
        print("No conflicts — plan is valid.")

    # ── Revalidate with validator ───────────────────────────────────────────
    semesters_as_dicts = [
        {
            "semester": sem.semester,
            "year": sem.year,
            "courses": sem.courses,
            "total_units": sem.total_units,
        }
        for sem in result.semesters
    ]
    validation_conflicts = validate_plan(
        semesters=semesters_as_dicts,
        prerequisites=relevant_prereqs,
        max_units_per_semester=max_units,
        completed_course_codes=completed,
    )
    if validation_conflicts:
        print(f"\nVALIDATOR found {len(validation_conflicts)} additional issue(s):")
        for c in validation_conflicts:
            print(f"  [{c['course_code']}] {c['reason']}")
    else:
        print("Validator confirms plan is constraint-clean.")

    # ── Deep prereq chain check ─────────────────────────────────────────────
    chain_violations = check_prereq_chains(
        semesters=result.semesters,
        prerequisites=relevant_prereqs,
        completed_course_codes=completed,
    )
    if chain_violations:
        print(f"\nPREREQ CHAIN CHECK found {len(chain_violations)} violation(s):")
        for v in chain_violations:
            print(f"  [{v['course_code']}] {v['reason']}")
    else:
        print("Prereq chain check: all dependencies satisfied in correct order.")
    print()


def _course(code: str, units: int = 3, fall: bool = True, spring: bool = True) -> dict:
    """Minimal course dict for hand-built negative-test plans."""
    return {
        "course_code": code,
        "title": code,
        "units": units,
        "department": code.split()[0],
        "offered_fall": fall,
        "offered_spring": spring,
    }


def run_negative_tests() -> bool:
    """
    Assert the validator and chain-checker REJECT known-bad plans.

    The positive scenarios above prove the engine can build a clean plan; these
    prove it actually catches violations instead of passing everything. Returns
    True if every bad plan was flagged as expected.
    """
    print("\n" + "=" * 60)
    print("NEGATIVE TESTS — every bad plan must be flagged")
    print("=" * 60)

    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        status = "ok" if condition else "FAIL"
        print(f"  [{status}] {name}")
        if not condition:
            failures.append(name)

    # 1. Prereq in the SAME semester as its dependent → both validator + chain.
    prereqs = [{"course_code": "CS 160", "prereq_code": "CS 150",
                "prereq_type": "required", "min_standing": None, "prereq_group": None}]
    same_sem = [{"semester": "Fall", "year": 2025,
                 "courses": [_course("CS 150"), _course("CS 160")], "total_units": 6}]
    v = validate_plan(same_sem, prereqs, completed_course_codes=[])
    c = check_prereq_chains(semesters=same_sem, prerequisites=prereqs, completed_course_codes=[])
    check("validator flags prereq in same semester", any("same semester" in x["reason"].lower() for x in v))
    check("chain check flags prereq in same semester", any(x["course_code"] == "CS 160" for x in c))

    # 2. Prereq placed in a LATER semester than its dependent → chain check.
    later = [
        {"semester": "Fall", "year": 2025, "courses": [_course("CS 160")], "total_units": 3},
        {"semester": "Spring", "year": 2026, "courses": [_course("CS 150")], "total_units": 3},
    ]
    c2 = check_prereq_chains(semesters=later, prerequisites=prereqs, completed_course_codes=[])
    check("chain check flags prereq placed after dependent", len(c2) > 0)

    # 3. Semester exceeding the unit cap → validator emits a "*" conflict.
    over = [{"semester": "Fall", "year": 2025,
             "courses": [_course("AAA 100", 5), _course("BBB 100", 5),
                         _course("CCC 100", 5), _course("DDD 100", 5)], "total_units": 20}]
    v3 = validate_plan(over, [], max_units_per_semester=15, completed_course_codes=[])
    check("validator flags over-cap semester", any(x["course_code"] == "*" for x in v3))

    # 4. Fall-only course dropped into a Spring slot → validator offering check (D3).
    fall_only = [{"semester": "Spring", "year": 2026,
                  "courses": [_course("ZZZ 300", 3, fall=True, spring=False)], "total_units": 3}]
    v4 = validate_plan(fall_only, [], completed_course_codes=[])
    check("validator flags fall-only course in spring", any("not offered in the spring" in x["reason"] for x in v4))

    # 5. Sanity: a correct ordering produces NO conflicts (guards false positives).
    good = [
        {"semester": "Fall", "year": 2025, "courses": [_course("CS 150")], "total_units": 3},
        {"semester": "Spring", "year": 2026, "courses": [_course("CS 160")], "total_units": 3},
    ]
    vg = validate_plan(good, prereqs, completed_course_codes=[])
    cg = check_prereq_chains(semesters=good, prerequisites=prereqs, completed_course_codes=[])
    check("clean plan produces no conflicts", not vg and not cg)

    if failures:
        print(f"\n{len(failures)} negative test(s) FAILED: {failures}")
        return False
    print("\nAll negative tests passed — bad plans are correctly rejected.")
    return True


def run_coreq_tests() -> bool:
    """
    Lock in the 2026-06-08 placement rules (apply to every major):
      - a lab is CO-PLACED in its lecture's semester (co-requisite),
      - no course shares a semester with a real prereq, including OR-alternatives,
      - co-req labs get unit-cap headroom (validator does not warn for them).
    """
    print("\n" + "=" * 60)
    print("CO-REQ + PREREQ-SEPARATION TESTS")
    print("=" * 60)
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  [{'ok' if condition else 'FAIL'}] {name}")
        if not condition:
            failures.append(name)

    courses = [
        _course("MATH 150"), _course("MATH 151"), _course("MATH 245"),
        _course("CS 150"), _course("CS 150L", units=1),
        _course("CS 160"), _course("CS 160L", units=1),
    ]
    P = lambda c, p, g=None: {"course_code": c, "prereq_code": p,
                              "prereq_type": "required", "min_standing": None, "prereq_group": g}
    prereqs = [
        P("MATH 151", "MATH 150"),
        P("MATH 245", "MATH 150", 1), P("MATH 245", "MATH 151", 1),   # OR group
        P("CS 150L", "CS 150"),                                       # single lecture prereq
        P("CS 160", "CS 150"),
        P("CS 160L", "CS 150", 1), P("CS 160L", "CS 160", 1),         # OR group incl. own lecture
    ]
    req = [c["course_code"] for c in courses]
    r = plan_courses(required_course_codes=req, completed_course_codes=[], courses=courses,
                     prerequisites=prereqs, max_units_per_semester=15, semester_count=8)
    loc = {c["course_code"]: i for i, s in enumerate(r.semesters) for c in s.courses}

    check("plan has no solver conflicts", not r.conflicts)
    check("CS 150L co-placed with CS 150", loc.get("CS 150L") == loc.get("CS 150"))
    check("CS 160L co-placed with CS 160", loc.get("CS 160L") == loc.get("CS 160"))
    check("MATH 245 is NOT in MATH 151's semester (OR-alt prereq)", loc.get("MATH 245") != loc.get("MATH 151"))
    check("MATH 245 is strictly after MATH 151", loc.get("MATH 245", -1) > loc.get("MATH 151", 99))
    # Validator: a 16u semester whose 16th unit is a co-req lab does NOT warn;
    # the same 16u WITHOUT the lab's lecture present DOES warn.
    with_lab = [{"semester": "Fall", "year": 2025, "courses": [
        _course("CS 150"), _course("CS 150L", 1), _course("AA 1", 3),
        _course("BB 2", 3), _course("CC 3", 3), _course("DD 4", 3)], "total_units": 16}]
    no_lecture = [{"semester": "Fall", "year": 2025, "courses": [
        _course("ZZ 9L", 1), _course("AA 1", 3), _course("BB 2", 3),
        _course("CC 3", 3), _course("DD 4", 3), _course("EE 5", 3)], "total_units": 16}]
    vw = validate_plan(with_lab, prereqs, max_units_per_semester=15, completed_course_codes=[])
    vn = validate_plan(no_lecture, [], max_units_per_semester=15, completed_course_codes=[])
    check("co-req lab gets cap headroom (16u w/ lab+lecture → no over-cap warning)",
          not any(x["course_code"] == "*" for x in vw))
    check("16u without the lab's lecture still warns", any(x["course_code"] == "*" for x in vn))

    if failures:
        print(f"\n{len(failures)} co-req test(s) FAILED: {failures}")
        return False
    print("\nAll co-req + prereq-separation tests passed.")
    return True


def run_standing_tests() -> bool:
    """
    Lock in the 2026-06-08 placement rules:
      - upper-division (course number >= 300) requires junior standing (60+ units),
        even with no explicit min_standing in the catalog,
      - that standing gate is SOFT: a 300+ course is still placed best-effort when
        60 units is genuinely unreachable (a scraped major missing its lower div),
      - GE/elective placeholders are sprinkled across semesters, not clustered at the end.
    """
    print("\n" + "=" * 60)
    print("STANDING + DISTRIBUTION TESTS")
    print("=" * 60)
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  [{'ok' if condition else 'FAIL'}] {name}")
        if not condition:
            failures.append(name)

    # 60 units of GE (no standing) + a lower-div course are enough to reach junior;
    # UP 300 has NO prereq and NO explicit standing, so only the 300+ rule gates it.
    ge = [f"GE {i}" for i in range(1, 21)]            # 20 × 3u = 60u, all placeholders
    courses = [_course("LD 100"), _course("UP 300")] + [_course(c) for c in ge]
    required = ["LD 100", "UP 300"] + ge
    r = plan_courses(required_course_codes=required, completed_course_codes=[], courses=courses,
                     prerequisites=[], max_units_per_semester=15, semester_count=10)
    cum = 0
    up_before = None
    for s in r.semesters:
        if any(c["course_code"] == "UP 300" for c in s.courses):
            up_before = cum
            break
        cum += s.total_units
    check("UP 300 (300-level, no explicit standing) is placed", up_before is not None)
    check("UP 300 waits until 60 units are accumulated", up_before is not None and up_before >= 60)
    # GE sprinkling: the early semesters (before UP 300) carry GE placeholders.
    first = r.semesters[0]
    check("GE placeholders are sprinkled into the first semester",
          any(c["course_code"].startswith("GE ") for c in first.courses))

    # Soft gate: only 15u of non-junior content, so 60 units is UNREACHABLE — the
    # 400-level course must still be placed best-effort, not dropped.
    ge2 = [f"GE {i}" for i in range(1, 6)]            # 5 × 3u = 15u only
    courses2 = [_course("UP 400")] + [_course(c) for c in ge2]
    required2 = ["UP 400"] + ge2
    r2 = plan_courses(required_course_codes=required2, completed_course_codes=[], courses=courses2,
                      prerequisites=[], max_units_per_semester=15, semester_count=8)
    placed2 = {c["course_code"] for s in r2.semesters for c in s.courses}
    check("a 300+ course is placed best-effort when 60 units is unreachable", "UP 400" in placed2)

    if failures:
        print(f"\n{len(failures)} standing test(s) FAILED: {failures}")
        return False
    print("\nAll standing + distribution tests passed.")
    return True


if __name__ == "__main__":
    # Scenario 1: Clean-slate freshman starting Fall 2025 (major only).
    run_test(completed=[], start_semester="Fall", start_year=2025)

    # Scenario 2: Transfer student who completed lower-div CS and math.
    print("\n" + "─" * 60)
    run_test(
        completed=[
            "CS 150", "CS 150L", "CS 160", "CS 160L",
            "MATH 150", "MATH 151", "MATH 245",
        ],
        start_semester="Fall",
        start_year=2025,
        verbose=False,
    )

    # Scenario 3: Freshman with GE requirements included.
    print("\n" + "─" * 60)
    run_test(
        completed=[],
        start_semester="Fall",
        start_year=2025,
        include_ge=True,
        verbose=False,
    )

    # Scenario 4: Freshman with all graduation requirements (GE + American Institutions).
    print("\n" + "─" * 60)
    run_test(
        completed=[],
        start_semester="Fall",
        start_year=2025,
        include_ge=True,
        include_ai=True,
        verbose=False,
    )

    # Negative tests: prove the engine rejects bad plans. Non-zero exit on failure.
    ok = run_negative_tests()
    # Co-req + prereq-separation rules (labs co-placed; OR-alt prereqs never same sem).
    ok = run_coreq_tests() and ok
    # Upper-division standing gate + GE distribution.
    ok = run_standing_tests() and ok
    if not ok:
        sys.exit(1)
