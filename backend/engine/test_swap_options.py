"""
Assertion tests for the elective swap-options engine (no DB / API needed).

    python -m backend.engine.test_swap_options

Builds a real CS plan from local JSON, then checks that get_swap_options returns
a correct legal alternative set for an elective slot and refuses firm requirements.
Exits non-zero on any failure.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.engine.major_requirements import get_required_courses, SUPPORTED_MAJORS
from backend.engine.test_solver import load_courses_from_json
from backend.engine.ge_requirements import get_ge_placeholder_courses, get_ge_placeholder_prereqs
from backend.engine.catalog_fixes import apply_course_aliases, get_catalog_fix_prereqs
from backend.engine.graduation_requirements import (
    get_additional_placeholder_courses,
    get_additional_placeholder_prereqs,
    get_free_elective_courses,
)
from backend.engine.solver import plan_courses
from backend.engine.swap_options import (
    get_swap_options,
    get_slot_options,
    find_elective_area,
    classify_role,
)
from backend.engine.graduation_requirements import AI_COURSES


def _build_cs_plan():
    all_courses, all_prereqs = load_courses_from_json()
    ubc = {c["course_code"]: c.get("units", 3) for c in all_courses}
    required = get_required_courses(major="CS", completed_courses=[], include_ge=True,
                                    include_ai=True, units_by_code=ubc)
    prereqs = (apply_course_aliases(list(all_prereqs)) + get_catalog_fix_prereqs(set(required))
               + get_ge_placeholder_prereqs())
    gr_c = get_additional_placeholder_courses(include_gwar=True, include_ai=True,
                                              completed_courses=[], required_courses=required)
    gr_p = get_additional_placeholder_prereqs(include_gwar=True, include_ai=True,
                                              completed_courses=[], required_courses=required)
    n_free = sum(1 for c in required if c.startswith("FREE "))
    courses = all_courses + get_ge_placeholder_courses() + gr_c + get_free_elective_courses(n_free)
    prereqs = prereqs + gr_p
    needed = set(required)
    rc = [c for c in courses if c["course_code"] in needed]
    rp = [p for p in prereqs if p["course_code"] in needed]
    r = plan_courses(required_course_codes=required, completed_course_codes=[], courses=rc,
                     prerequisites=rp, max_units_per_semester=15, semester_count=9)
    plan = [{"semester": s.semester, "year": s.year,
             "courses": [dict(c) for c in s.courses], "total_units": s.total_units}
            for s in r.semesters]
    return plan, all_courses, all_prereqs


def run_swap_tests() -> bool:
    print("=" * 60)
    print("SWAP-OPTIONS TESTS")
    print("=" * 60)
    failures: list[str] = []

    def check(name, cond):
        print(f"  [{'ok' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    # Area membership
    check("CS 530 is in an elective area", find_elective_area("CS", "CS 530") is not None)
    check("CS 150 (firm req) is in NO elective area", find_elective_area("CS", "CS 150") is None)

    plan, all_courses, all_prereqs = _build_cs_plan()
    placed = {c["course_code"]: (s["semester"], s["year"]) for s in plan for c in s["courses"]}

    # Pick a placed CS elective slot
    slot = next((c for c in SUPPORTED_MAJORS["CS"].default_electives
                 if c in placed and find_elective_area("CS", c)), None)
    check("a CS elective is placed in the plan", slot is not None)
    if slot is None:
        return False
    sem, yr = placed[slot]
    area = find_elective_area("CS", slot)
    from backend.engine.swap_options import all_elective_codes
    pool_codes = set(all_elective_codes("CS"))
    cand_courses = [c for c in all_courses if c["course_code"] in pool_codes]
    cand_prereqs = [p for p in apply_course_aliases(list(all_prereqs)) + get_catalog_fix_prereqs(pool_codes)
                    if p["course_code"] in pool_codes]
    res = get_swap_options(major="CS", plan_semesters=plan, slot_code=slot, slot_semester=sem,
                           slot_year=yr, completed_courses=[], courses=cand_courses,
                           prerequisites=cand_prereqs, max_units_per_semester=15)
    opt_codes = [o["course_code"] for o in res["options"]]
    eligible_codes = [o["course_code"] for o in res["options"] if o["eligible"]]

    check("returns the home area for display", res["area"] == area)
    check("returns at least one option", len(opt_codes) > 0)
    check("every option is in the major's elective pool (union of areas)",
          all(c in pool_codes for c in opt_codes))
    # The pool spans more than one area, so options should cross area boundaries.
    other_area_codes = pool_codes - set(SUPPORTED_MAJORS["CS"].elective_areas[area])
    check("options span more than the slot's home area",
          any(c in other_area_codes for c in opt_codes))
    check("the slot course is not offered as its own swap", slot not in opt_codes)
    check("no option is already placed in the plan", not any(c in placed for c in opt_codes))
    # Permissive: gated options are present but flagged eligible=False with a reason.
    check("gated options are flagged ineligible with a reason, not excluded",
          any(o["eligible"] is False and o["note"] for o in res["options"]))
    check("eligible options sort before ineligible ones",
          [o["eligible"] for o in res["options"]]
          == sorted([o["eligible"] for o in res["options"]], reverse=True))
    # Within each eligibility band, sorted by course number.
    elig_band = [o["course_code"] for o in res["options"] if o["eligible"]]
    check("eligible options are sorted by course number",
          elig_band == sorted(elig_band, key=lambda c: int("".join(ch for ch in c if ch.isdigit()) or 0)))
    term_fall = sem.lower() == "fall"
    by_code = {c["course_code"]: c for c in cand_courses}
    check("every ELIGIBLE option is offered in the slot's term",
          all((by_code[c].get("offered_fall", True) if term_fall else by_code[c].get("offered_spring", True))
              for c in eligible_codes))
    # A default elective already in the plan (anywhere in the pool) must be excluded, not offered.
    pool_placed = [c for c in SUPPORTED_MAJORS["CS"].default_electives
                   if c in placed and c in pool_codes and c != slot]
    if pool_placed:
        check("an already-placed pool elective is excluded",
              all(c not in opt_codes for c in pool_placed))

    # Firm requirement returns no swap options.
    res_firm = get_swap_options(major="CS", plan_semesters=plan, slot_code="CS 150",
                                slot_semester="Fall", slot_year=plan[0]["year"], completed_courses=[],
                                courses=all_courses, prerequisites=all_prereqs, max_units_per_semester=15)
    check("firm requirement returns area=None and no options",
          res_firm["area"] is None and not res_firm["options"])

    # ── classify_role ──────────────────────────────────────────────────────
    check("classify_role: major elective", classify_role("CS", slot) == "elective")
    check("classify_role: fixed requirement", classify_role("CS", "CS 150") == "requirement")
    check("classify_role: GE slot", classify_role("CS", "GE 1A") == "ge")
    check("classify_role: grad slot", classify_role("CS", "GR AI") == "grad")
    check("classify_role: free slot", classify_role("CS", "FREE 1") == "free")

    # ── get_slot_options: GR AI ────────────────────────────────────────────
    ai_loc = {c["course_code"]: (s["semester"], s["year"]) for s in plan for c in s["courses"]}
    if "GR AI" in ai_loc:
        ai_sem, ai_yr = ai_loc["GR AI"]
        ai_courses = [c for c in all_courses if c["course_code"] in AI_COURSES]
        ai_prereqs = [p for p in all_prereqs if p["course_code"] in AI_COURSES]
        ai = get_slot_options(major="CS", plan_semesters=plan, slot_code="GR AI",
                              slot_semester=ai_sem, slot_year=ai_yr, completed_courses=[],
                              courses=ai_courses, prerequisites=ai_prereqs, max_units_per_semester=15)
        ai_codes = [o["course_code"] for o in ai["options"]]
        check("GR AI slot_type is grad", ai["slot_type"] == "grad")
        check("GR AI options are all real AI courses",
              len(ai_codes) > 0 and all(c in AI_COURSES for c in ai_codes))

    # ── get_slot_options: GE slot offers approved area courses ─────────────
    from backend.engine.swap_options import get_ge_area_courses
    ge_area_codes = get_ge_area_courses("GE 1A")
    check("GE area list is loaded (ge_areas.json scraped)", len(ge_area_codes) > 0)
    ge_loc = {c["course_code"]: (s["semester"], s["year"]) for s in plan for c in s["courses"]}
    if "GE 1A" in ge_loc and ge_area_codes:
        gsem, gyr = ge_loc["GE 1A"]
        ge_courses = [c for c in all_courses if c["course_code"] in set(ge_area_codes)]
        ge_prereqs = [p for p in all_prereqs if p["course_code"] in set(ge_area_codes)]
        ge = get_slot_options(major="CS", plan_semesters=plan, slot_code="GE 1A",
                              slot_semester=gsem, slot_year=gyr, completed_courses=[],
                              courses=ge_courses, prerequisites=ge_prereqs, max_units_per_semester=15)
        ge_codes = [o["course_code"] for o in ge["options"]]
        check("GE slot is no longer needs_data (lists scraped)", ge["needs_data"] is False)
        check("GE options are all approved Area 1A courses",
              len(ge_codes) > 0 and all(c in set(ge_area_codes) for c in ge_codes))
        # Permissive: GE shows the full menu incl. prereq-gated courses flagged ineligible.
        check("GE shows prereq-gated options flagged eligible=False",
              any(o["eligible"] is False and o["note"] for o in ge["options"]))
        check("GE eligible options sort before ineligible ones",
              [o["eligible"] for o in ge["options"]] == sorted([o["eligible"] for o in ge["options"]], reverse=True))

        # slot_identity: a real course occupying the GE slot still offers GE area courses
        # (this is what keeps a filled slot interchangeable).
        ge_via_identity = get_slot_options(
            major="CS", plan_semesters=plan, slot_code=ge_codes[0], slot_semester=gsem,
            slot_year=gyr, completed_courses=[], courses=ge_courses, prerequisites=ge_prereqs,
            max_units_per_semester=15, slot_identity="GE 1A")
        check("filled GE slot (via slot_identity) still resolves to GE area",
              ge_via_identity["slot_type"] == "ge" and len(ge_via_identity["options"]) > 0)

    # ── get_slot_options: FREE slot filters an already-placed candidate ─────
    free_loc = next((c for c in ai_loc if c.startswith("FREE ")), None)
    if free_loc:
        fsem, fyr = ai_loc[free_loc]
        # Candidate pool: one course already placed in the plan (must be excluded) + two not.
        placed_real = next((c["course_code"] for s in plan for c in s["courses"]
                            if c["course_code"].startswith("CS ") and c["course_code"] != free_loc), None)
        pool_codes = [placed_real, "CS 596"]
        pool = [c for c in all_courses if c["course_code"] in pool_codes]
        fr = get_slot_options(major="CS", plan_semesters=plan, slot_code=free_loc,
                              slot_semester=fsem, slot_year=fyr, completed_courses=[],
                              courses=pool, prerequisites=[], max_units_per_semester=15)
        fr_codes = [o["course_code"] for o in fr["options"]]
        check("FREE slot is search-driven", fr["search"] is True)
        check("FREE slot excludes an already-placed candidate", placed_real not in fr_codes)

    if failures:
        print(f"\n{len(failures)} swap test(s) FAILED: {failures}")
        return False
    print(f"\nAll swap-options tests passed (slot {slot}: {len(opt_codes)} legal, {res['excluded']} excluded).")
    return True


if __name__ == "__main__":
    if not run_swap_tests():
        sys.exit(1)
