import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from backend.api.main import get_db
from backend.api.models import (
    AdjustPlanRequest,
    GeneratePlanRequest,
    PlanResponse,
    SwapApplyRequest,
    SwapOptionsRequest,
    SwapOptionsResponse,
)
from backend.engine.ge_requirements import (
    get_ge_placeholder_courses,
    get_ge_placeholder_prereqs,
)
from backend.engine.catalog_fixes import apply_course_aliases, get_catalog_fix_prereqs
from backend.engine.prereq_groups import apply_prereq_groups
from backend.engine.graduation_requirements import (
    AI_COURSES,
    get_additional_placeholder_courses,
    get_additional_placeholder_prereqs,
    get_free_elective_courses,
    is_additional_placeholder,
    is_gwar_course,
)
from backend.engine.major_requirements import SUPPORTED_MAJORS, get_required_courses
from backend.engine.prereq_checker import check_prereq_chains
from backend.engine.solver import plan_courses
from backend.engine.terms import sort_semesters
from backend.engine.swap_options import (
    all_elective_codes,
    classify_role,
    get_ge_area_courses,
    get_slot_options,
    get_swap_options,
)
from backend.engine.validator import validate_plan

router = APIRouter(prefix="/plan", tags=["plan"])

# Upper bound on the adaptive semester search. See the comment in generate_plan
# for why 14 (heavy interdisciplinary degrees need 11-12 semesters at 15 units).
MAX_SEMESTERS = 14


def _tag_roles(courses: list[dict], major: Optional[str]) -> list[dict]:
    """Return course dicts with `role` set (requirement/elective/ge/grad/free).

    Role is intrinsic to (major, course_code); without a major we can't tell a
    major elective from a fixed requirement, so we leave `role` untouched and let
    the frontend keep the roles it already has from /plan/generate.
    """
    if not major:
        return list(courses)
    out = []
    for c in courses:
        # A course that filled a placeholder slot keeps that slot's role so the
        # tile stays interchangeable (e.g. a chosen GE course stays role "ge").
        identity = c.get("fills") or c["course_code"]
        out.append({**c, "role": classify_role(major, identity)})
    return out


def _is_slot_placeholder(code: str) -> bool:
    """True for a synthetic slot placeholder (GE / GR / FREE) — the slot identity."""
    c = code.upper()
    return c.startswith("GE ") or c.startswith("GR ") or c.startswith("FREE ")


def _retag_plan(semesters: list[dict], major: Optional[str]) -> list[dict]:
    """Re-tag every course's role across a plan (used by adjust/swap when major is given)."""
    if not major:
        return semesters
    for sem in semesters:
        sem["courses"] = _tag_roles(sem["courses"], major)
    return semesters


@router.post("/generate", response_model=PlanResponse)
def generate_plan(req: GeneratePlanRequest, db: Client = Depends(get_db)):
    """
    Generate a semester plan for a given major and set of completed courses.

    If `required_courses` is empty (the normal case), the major's requirements
    are loaded from major_requirements.py. For Phase 2 only "CS" is supported.

    If `required_courses` is supplied explicitly, those codes override the
    major defaults — useful for testing individual requirement subsets.
    """
    major = req.major.upper()

    # Resolve required course list.
    if req.required_courses:
        # Caller is overriding with an explicit list (testing / advanced use).
        required_codes = [c.upper() for c in req.required_courses]
    else:
        if major not in SUPPORTED_MAJORS:
            raise HTTPException(
                400,
                f"Major '{req.major}' is not supported yet. "
                f"Supported: {list(SUPPORTED_MAJORS.keys())}",
            )
        required_codes = get_required_courses(
            major=major,
            completed_courses=req.completed_courses,
            include_ge=req.include_ge,
            include_ai=req.include_ai,
        )

    completed_codes = [c.upper() for c in req.completed_courses]

    # Placeholder codes ("GE " and "GR " prefixes) are synthetic — skip DB queries.
    ge_codes = {c for c in required_codes if c.startswith("GE ")}
    gr_codes = {c for c in required_codes if is_additional_placeholder(c)}
    db_required_codes = [c for c in required_codes if c not in ge_codes and c not in gr_codes]

    # Fetch course records for every real (non-GE) code we'll need.
    all_needed = list(dict.fromkeys(db_required_codes + completed_codes))
    courses = (
        db.table("courses")
        .select("*")
        .in_("course_code", all_needed)
        .execute()
        .data
        or []
    )

    # Inject synthetic GE placeholder records so the solver can place them.
    if ge_codes:
        ge_records = get_ge_placeholder_courses()
        courses = courses + [r for r in ge_records if r["course_code"] in ge_codes]

    # Fetch prerequisites for all real required courses.
    prereqs = (
        db.table("prerequisites")
        .select("*")
        .in_("course_code", db_required_codes)
        .execute()
        .data
        or []
    )

    # Apply course aliases (old→current names) then inject missing prereqs.
    all_plan_codes = set(required_codes) | set(completed_codes)
    prereqs = apply_course_aliases(prereqs)
    prereqs = apply_prereq_groups(prereqs)
    prereqs = prereqs + get_catalog_fix_prereqs(all_plan_codes)

    # Inject synthetic GE standing prerequisites (UD areas need junior standing).
    if ge_codes:
        ge_prereqs = get_ge_placeholder_prereqs()
        prereqs = prereqs + [r for r in ge_prereqs if r["course_code"] in ge_codes]

    # Inject synthetic GR (graduation requirement) placeholder records.
    if gr_codes:
        gr_courses = get_additional_placeholder_courses(
            include_gwar="GR GWAR" in gr_codes,
            include_ai="GR AI" in gr_codes,
            completed_courses=req.completed_courses,
            required_courses=list(gr_codes) + db_required_codes,
        )
        courses = courses + [r for r in gr_courses if r["course_code"] in gr_codes]
        gr_prereqs = get_additional_placeholder_prereqs(
            include_gwar="GR GWAR" in gr_codes,
            include_ai="GR AI" in gr_codes,
            completed_courses=req.completed_courses,
            required_courses=list(gr_codes) + db_required_codes,
        )
        prereqs = prereqs + [r for r in gr_prereqs if r["course_code"] in gr_codes]

    # Pad with free electives to reach the degree total. Re-derive the required
    # list now that we have real course units; this both models real degrees and
    # prevents a junior-standing deadlock in upper-division-heavy majors. Free
    # electives have no prereqs or standing, so only their records are injected.
    if not req.required_courses and major in SUPPORTED_MAJORS:
        units_by_code = {c["course_code"]: c.get("units", 3) for c in courses}
        padded = get_required_courses(
            major=major,
            completed_courses=req.completed_courses,
            include_ge=req.include_ge,
            include_ai=req.include_ai,
            units_by_code=units_by_code,
        )
        free_codes = [c for c in padded if c.startswith("FREE ")]
        if free_codes:
            required_codes = required_codes + free_codes
            courses = courses + get_free_elective_courses(len(free_codes))

    # Decide how many semesters to allocate. A pure units/cap formula can't
    # tell majors apart — the real bottleneck is standing/offering structure,
    # not unit count (e.g. CS fits in 8 while lighter MATH needs 9). So we use
    # the units estimate only as a floor, then retry up to MAX_SEMESTERS and
    # keep the first conflict-free plan (or the fewest-conflict one otherwise).
    # MAX_SEMESTERS is 14 because heavy interdisciplinary degrees (e.g. the
    # International Business language emphases, 150-170 units) genuinely need
    # 11-12 semesters at the 15-unit cap; a 10-semester ceiling dropped their
    # senior-standing capstones. Anything needing >14 semesters at 15 units is
    # >210 units — broken scraped data, not a schedulable plan.
    total_units_needed = sum(
        c.get("units", 3) for c in courses
        if c["course_code"] in set(required_codes) - set(completed_codes)
    )
    effective_rate = max(req.max_units_per_semester - 1, 1)
    floor_count = min(MAX_SEMESTERS, max(8, math.ceil(total_units_needed / effective_rate)))

    result = None
    for semester_count in range(floor_count, MAX_SEMESTERS + 1):
        candidate = plan_courses(
            required_course_codes=required_codes,
            completed_course_codes=completed_codes,
            courses=courses,
            prerequisites=prereqs,
            max_units_per_semester=req.max_units_per_semester,
            start_semester=req.start_semester,
            start_year=req.start_year,
            semester_count=semester_count,
        )
        if result is None or len(candidate.conflicts) < len(result.conflicts):
            result = candidate
        if not candidate.conflicts:
            break

    chain_violations = check_prereq_chains(
        semesters=result.semesters,
        prerequisites=prereqs,
        completed_course_codes=completed_codes,
    )

    all_conflicts = _merge_chain_violations(result.conflicts, chain_violations)

    return PlanResponse(
        semesters=[
            {
                "semester": sem.semester,
                "year": sem.year,
                "courses": _tag_roles(sem.courses, major),
                "total_units": sem.total_units,
            }
            for sem in result.semesters
        ],
        conflicts=all_conflicts,
    )


@router.post("/adjust", response_model=PlanResponse)
def adjust_plan(req: AdjustPlanRequest, db: Client = Depends(get_db)):
    """
    Move a single course from one semester to another and revalidate the plan.

    The full plan is revalidated after the move. Conflicts are returned but
    the move is still applied — the frontend decides whether to show a warning
    or block the drop.
    """
    moved_code = req.course_code.upper()

    # Work on a mutable copy of the plan's semesters.
    semesters = [sem.model_dump() for sem in req.plan.semesters]

    # Lift the course out of its source semester.
    moved_course: dict | None = None
    for sem in semesters:
        if sem["semester"] == req.from_semester and sem["year"] == req.from_year:
            remaining = []
            for course in sem["courses"]:
                if course["course_code"].upper() == moved_code:
                    moved_course = course
                else:
                    remaining.append(course)
            sem["courses"] = remaining
            sem["total_units"] = sum(c["units"] for c in remaining)
            break

    if moved_course is None:
        raise HTTPException(
            404,
            f"Course {moved_code} not found in "
            f"{req.from_semester} {req.from_year}.",
        )

    # Drop it into the target semester.
    placed = False
    for sem in semesters:
        if sem["semester"] == req.to_semester and sem["year"] == req.to_year:
            sem["courses"].append(moved_course)
            sem["total_units"] = sum(c["units"] for c in sem["courses"])
            placed = True
            break

    if not placed:
        raise HTTPException(
            404,
            f"Target semester {req.to_semester} {req.to_year} not found in plan.",
        )

    completed_codes = [c.upper() for c in (req.completed_courses or [])]
    semesters = sort_semesters(semesters)  # keep optional summer/winter terms in calendar order
    all_conflicts = _revalidate_plan(
        semesters, completed_codes, req.max_units_per_semester, db
    )
    return PlanResponse(semesters=_retag_plan(semesters, req.major), conflicts=all_conflicts)


def _revalidate_plan(
    semesters: list[dict],
    completed_codes: list[str],
    max_units: int,
    db: Client,
) -> list[dict]:
    """
    Re-run the full constraint check on a mutated plan (after a drag or a swap).

    Fetches prereqs for every real course in the plan, enriches them exactly like
    /plan/generate (aliases, OR-groups, catalog fixes, synthetic GE/GR rows), then
    runs the same two-stage check (validate_plan + check_prereq_chains, deduped).
    Shared by /plan/adjust and /plan/swap so they cannot diverge.

    Semesters are sorted into true calendar order first (Fall → Winter → Spring →
    Summer → Fall …) so a course dragged into an optional Summer/Winter term is
    checked against the correct chronological neighbors. The checkers are
    index-based, so correct ordering is all they need.
    """
    semesters = sort_semesters(semesters)
    all_codes = list(dict.fromkeys(
        c["course_code"] for sem in semesters for c in sem["courses"]
    ))
    db_codes = [
        c for c in all_codes
        if not c.startswith("GE ") and not is_additional_placeholder(c)
    ]
    prereqs = (
        db.table("prerequisites").select("*").in_("course_code", db_codes).execute().data or []
    )

    all_plan_codes = set(all_codes) | set(completed_codes)
    prereqs = apply_course_aliases(prereqs)
    prereqs = apply_prereq_groups(prereqs)
    prereqs = prereqs + get_catalog_fix_prereqs(all_plan_codes)

    ge_codes = {c for c in all_codes if c.startswith("GE ")}
    if ge_codes:
        ge_prereqs = get_ge_placeholder_prereqs()
        prereqs = prereqs + [r for r in ge_prereqs if r["course_code"] in ge_codes]

    gr_codes = {c for c in all_codes if is_additional_placeholder(c)}
    if gr_codes:
        gr_prereqs = get_additional_placeholder_prereqs(
            include_gwar="GR GWAR" in gr_codes,
            include_ai="GR AI" in gr_codes,
            completed_courses=completed_codes,
            required_courses=list(all_codes),
        )
        prereqs = prereqs + [r for r in gr_prereqs if r["course_code"] in gr_codes]

    conflicts = validate_plan(
        semesters, prereqs,
        max_units_per_semester=max_units,
        completed_course_codes=completed_codes,
    )
    chain_violations = check_prereq_chains(
        semesters=semesters, prerequisites=prereqs, completed_course_codes=completed_codes,
    )
    return _merge_chain_violations(conflicts, chain_violations)


def _merge_chain_violations(conflicts: list[dict], chain_violations: list[dict]) -> list[dict]:
    """Append transitive prereq-chain violations not already reported as immediate ones.

    Dedup is STRUCTURAL — keyed on (course_code, prereq_code) — not on the human
    `reason` string, so it stays correct if either checker's wording changes. An
    immediate prereq conflict carries `prereq_codes` (the unmet group members);
    a chain violation names a single `prereq_code`. A chain violation is a
    duplicate when an immediate conflict for the same course already covers that
    prereq code.
    """
    immediate_pairs: set[tuple[str, str]] = set()
    for c in conflicts:
        for pc in c.get("prereq_codes", []):
            immediate_pairs.add((c["course_code"], pc))
    return conflicts + [
        v for v in chain_violations
        if (v["course_code"], v.get("prereq_code")) not in immediate_pairs
    ]


@router.post("/swap", response_model=PlanResponse)
def swap_course(req: SwapApplyRequest, db: Client = Depends(get_db)):
    """
    Replace one elective (from_code) with a chosen alternative (to_code) in the
    same semester, then revalidate. The alternative's catalog record is pulled
    from the DB so the new card carries real units/offering data. Conflicts are
    returned but the swap is applied — the frontend decides how to surface them.
    """
    from_code = req.from_code.upper()
    to_code = req.to_code.upper()
    completed_codes = [c.upper() for c in (req.completed_courses or [])]

    semesters = [sem.model_dump() for sem in req.plan.semesters]

    # Fetch the chosen course's catalog record.
    rows = db.table("courses").select("*").eq("course_code", to_code).execute().data or []
    if not rows:
        raise HTTPException(404, f"Course {to_code} not found in the catalog.")
    new_course = rows[0]

    # Locate the slot semester, remove from_code, insert the chosen course.
    replaced = False
    for sem in semesters:
        if sem["semester"] == req.semester and sem["year"] == req.year:
            removed = next((c for c in sem["courses"] if c["course_code"].upper() == from_code), None)
            if removed is None:
                raise HTTPException(
                    404, f"Course {from_code} not found in {req.semester} {req.year}."
                )
            if any(c["course_code"].upper() == to_code for c in sem["courses"]):
                raise HTTPException(400, f"Course {to_code} is already in {req.semester} {req.year}.")
            # Preserve the slot identity so the new card stays interchangeable. If the
            # course being replaced filled a placeholder (carries `fills`), inherit it;
            # otherwise if we're replacing a placeholder directly, that's the identity.
            new_course["fills"] = removed.get("fills") or (
                from_code if _is_slot_placeholder(from_code) else None
            )
            sem["courses"] = [c for c in sem["courses"] if c["course_code"].upper() != from_code]
            sem["courses"].append(new_course)
            sem["total_units"] = sum(c["units"] for c in sem["courses"])
            replaced = True
            break

    if not replaced:
        raise HTTPException(404, f"Semester {req.semester} {req.year} not found in plan.")

    semesters = sort_semesters(semesters)  # keep optional summer/winter terms in calendar order
    all_conflicts = _revalidate_plan(
        semesters, completed_codes, req.max_units_per_semester, db
    )
    return PlanResponse(semesters=_retag_plan(semesters, req.major), conflicts=all_conflicts)


@router.post("/swap-options", response_model=SwapOptionsResponse)
def swap_options(req: SwapOptionsRequest, db: Client = Depends(get_db)):
    """
    Return the legal courses a student can put in a given slot (any slot type).

    Deterministic, no AI. Dispatches by the slot's role:
      - elective  → courses in the same major elective area (strict)
      - GR AI     → American Institutions set (HIST 109/110, POL S 101/102)
      - GR GWAR   → W-suffix (writing-certified) courses — search-driven
      - FREE      → any catalog course — search-driven (send `query`)
      - GE        → the area's approved courses (search-driven)
    Browse/search slots show the full menu with each option flagged `eligible`
    (+ a `note` if it needs a prereq / standing / different term); the plan
    validator surfaces any conflict if a gated option is picked. The slot's
    *identity* comes from the plan course's `fills` when set, so a filled slot
    (e.g. a chosen GE course) re-offers the same area and stays interchangeable.
    """
    major = req.major.upper()
    slot_code = req.course_code.upper()

    # Slot identity = the requirement this slot fills. A real course that replaced
    # a placeholder carries `fills` (e.g. "GE 1A"); otherwise the code is its own
    # identity. We dispatch on the identity but keep slot_code for plan position.
    identity = slot_code
    for sem in req.plan.semesters:
        for c in sem.courses:
            if c.course_code.upper() == slot_code:
                identity = (c.fills or slot_code).upper()
                break
    role = classify_role(major, identity)

    _SEARCH_LIMIT = 60
    _GE_LIMIT = 250  # GE areas can be large; show the full approved menu

    # Resolve the candidate code pool per slot type, fetching from the DB where needed.
    candidate_codes: list[str] = []
    if role == "elective":
        # Union of all the major's elective areas (the full legal swap pool).
        candidate_codes = all_elective_codes(major)
    elif role == "grad" and identity == "GR AI":
        candidate_codes = list(AI_COURSES)
    elif role == "grad" and identity == "GR GWAR":
        # All W-suffix courses, optionally narrowed by the search query.
        q = db.table("courses").select("*").ilike("course_code", "%W")
        if req.query:
            q = q.or_(f"course_code.ilike.%{req.query}%,title.ilike.%{req.query}%")
        rows = q.limit(_SEARCH_LIMIT).execute().data or []
        candidate_codes = [r["course_code"] for r in rows if is_gwar_course(r["course_code"])]
    elif role == "free":
        # Any catalog course matching the search; empty query → just prompt to search.
        if req.query:
            rows = (
                db.table("courses").select("*")
                .or_(f"course_code.ilike.%{req.query}%,title.ilike.%{req.query}%")
                .limit(_SEARCH_LIMIT).execute().data or []
            )
            candidate_codes = [r["course_code"] for r in rows]
    elif role == "ge":
        # The full approved list for the GE area, optionally narrowed by the query.
        ge_codes = get_ge_area_courses(identity)
        if req.query:
            ql = req.query.lower()
            ge_codes = [c for c in ge_codes if ql in c.lower()]
        candidate_codes = ge_codes[:_GE_LIMIT]
    # role == "requirement" → no candidates (handled by get_slot_options).

    # Fetch catalog records + enriched prereqs for the candidate pool.
    courses: list[dict] = []
    prereqs: list[dict] = []
    if candidate_codes:
        courses = (
            db.table("courses").select("*").in_("course_code", candidate_codes).execute().data or []
        )
        prereqs = (
            db.table("prerequisites").select("*").in_("course_code", candidate_codes).execute().data or []
        )
        prereqs = apply_course_aliases(prereqs)
        prereqs = apply_prereq_groups(prereqs)
        prereqs = prereqs + get_catalog_fix_prereqs(set(candidate_codes))

    plan_semesters = [sem.model_dump() for sem in req.plan.semesters]
    result = get_slot_options(
        major=major,
        plan_semesters=plan_semesters,
        slot_code=slot_code,
        slot_semester=req.semester,
        slot_year=req.year,
        completed_courses=[c.upper() for c in req.completed_courses],
        courses=courses,
        prerequisites=prereqs,
        max_units_per_semester=req.max_units_per_semester,
        slot_identity=identity,
    )

    return SwapOptionsResponse(
        area=result["area"],
        slot_type=result["slot_type"],
        course_code=slot_code,
        semester=req.semester,
        year=req.year,
        options=result["options"],
        excluded=result["excluded"],
        needs_data=result["needs_data"],
        search=result["search"],
        hint=result["hint"],
    )
