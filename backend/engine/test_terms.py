"""
Assertion tests for academic term ordering (optional summer/winter support).

    python -m backend.engine.test_terms

Checks that sort_semesters produces true calendar order and that a plan with an
optional summer term validates correctly (prereqs respected across the inserted term).
Exits non-zero on failure.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.engine.terms import sort_semesters, chronological_key, TERM_RANK
from backend.engine.prereq_checker import check_prereq_chains
from backend.engine.validator import validate_plan


def _course(code, units=3):
    return {"course_code": code, "title": code, "units": units,
            "department": code.split()[0], "offered_fall": True, "offered_spring": True}


def run_term_tests() -> bool:
    print("=" * 60)
    print("TERM ORDERING TESTS")
    print("=" * 60)
    failures = []

    def check(name, cond):
        print(f"  [{'ok' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    # Calendar order within and across years.
    check("Winter < Spring < Summer < Fall within a year",
          TERM_RANK["Winter"] < TERM_RANK["Spring"] < TERM_RANK["Summer"] < TERM_RANK["Fall"])

    scrambled = [
        {"semester": "Summer", "year": 2028, "courses": []},
        {"semester": "Fall", "year": 2027, "courses": []},
        {"semester": "Fall", "year": 2028, "courses": []},
        {"semester": "Winter", "year": 2028, "courses": []},
        {"semester": "Spring", "year": 2028, "courses": []},
    ]
    order = [(s["semester"], s["year"]) for s in sort_semesters(scrambled)]
    check("sort_semesters yields Fall2027, Winter2028, Spring2028, Summer2028, Fall2028",
          order == [("Fall", 2027), ("Winter", 2028), ("Spring", 2028), ("Summer", 2028), ("Fall", 2028)])

    # A prereq in Spring with its dependent dragged to the following Summer is VALID
    # (summer comes after spring). The checkers are index-based, so feed sorted order.
    prereqs = [{"course_code": "CS 160", "prereq_code": "CS 150",
                "prereq_type": "required", "min_standing": None, "prereq_group": None}]
    good = sort_semesters([
        {"semester": "Spring", "year": 2027, "courses": [_course("CS 150")], "total_units": 3},
        {"semester": "Summer", "year": 2027, "courses": [_course("CS 160")], "total_units": 3},
    ])
    cg = check_prereq_chains(semesters=good, prerequisites=prereqs, completed_course_codes=[])
    vg = validate_plan(good, prereqs, completed_course_codes=[])
    check("prereq in Spring, dependent in following Summer → valid", not cg and not vg)

    # Reverse (dependent in Spring, prereq in the later Summer) → flagged.
    bad = sort_semesters([
        {"semester": "Spring", "year": 2027, "courses": [_course("CS 160")], "total_units": 3},
        {"semester": "Summer", "year": 2027, "courses": [_course("CS 150")], "total_units": 3},
    ])
    cb = check_prereq_chains(semesters=bad, prerequisites=prereqs, completed_course_codes=[])
    check("dependent in Spring, prereq in later Summer → flagged", len(cb) > 0)

    if failures:
        print(f"\n{len(failures)} term test(s) FAILED: {failures}")
        return False
    print("\nAll term-ordering tests passed.")
    return True


if __name__ == "__main__":
    if not run_term_tests():
        sys.exit(1)
