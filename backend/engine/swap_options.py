"""
Elective swap options — the deterministic "valid swaps" layer.

For an elective slot in an already-generated plan, return the set of courses the
student could legally put there *instead*. A swap is legal when the candidate is:

  1. In the SAME elective area as the slotted course (same `elective_areas` group
     in the major definition).
  2. Prerequisite-satisfiable AT THAT POINT IN THIS PLAN — every prereq AND-group
     has at least one member completed before the plan or placed in a strictly
     earlier semester.
  3. Standing-satisfiable — enough cumulative units before the slot's semester.
  4. Offered in the slot's term (fall vs spring).
  5. Not already placed in the plan or completed.

This layer must always be correct (it is what the UI lets students act on). The
unit budget is treated as a SOFT signal — over-target candidates are returned but
flagged (`fits_budget=False`), matching the soft-cap decision; they are not hidden.

The "which of these is worth taking" ranking (RMP, theme tags) is a separate,
later layer — this module only answers "which are legal."
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from backend.engine.major_requirements import SUPPORTED_MAJORS
from backend.engine.prereq_checker import build_full_prereq_graph
from backend.engine.solver import STANDING_UNITS
from backend.engine.validator import _highest_standing

logger = logging.getLogger(__name__)

# GE area → approved course codes, scraped by backend/scraper/ge_scraper.py.
# Absent file → GE slots fall back to "needs_data" (picking shows "coming soon").
_GE_AREAS_PATH = Path(__file__).resolve().parents[2] / "data" / "catalog" / "ge_areas.json"
_GE_AREAS: dict[str, list[str]] = {}
try:
    _GE_AREAS = json.loads(_GE_AREAS_PATH.read_text())
except FileNotFoundError:
    logger.warning("GE area lists not found at %s — GE slot picking disabled "
                   "(run backend.scraper.ge_scraper).", _GE_AREAS_PATH)
except (OSError, ValueError) as exc:
    logger.warning("GE area lists at %s unreadable (%s) — GE picking disabled.", _GE_AREAS_PATH, exc)


def get_ge_area_courses(ge_code: str) -> list[str]:
    """Approved course codes for a GE placeholder code (e.g. 'GE 3A' → Area 3A list)."""
    area = ge_code.upper().strip()
    if area.startswith("GE "):
        area = area[3:].strip()
    return list(_GE_AREAS.get(area, []))


def find_elective_area(major: str, code: str) -> Optional[str]:
    """Return the name of the elective area containing ``code``, or None.

    A course in no elective area is a firm requirement (not swappable).
    """
    defn = SUPPORTED_MAJORS.get(major.upper())
    if defn is None:
        return None
    for area_name, codes in defn.elective_areas.items():
        if code in codes:
            return area_name
    return None


def all_elective_codes(major: str) -> list[str]:
    """Union of every elective-area course list for ``major`` (dedup, order-preserving).

    The major's `elective_areas` groups together ARE the catalog's official set of
    "courses that may count as an elective" for this degree, so the legal swap pool
    for any elective slot is the union of all areas — not just the slot's home area.
    """
    defn = SUPPORTED_MAJORS.get(major.upper())
    if defn is None:
        return []
    seen: set[str] = set()
    pool: list[str] = []
    for codes in defn.elective_areas.values():
        for code in codes:
            if code not in seen:
                seen.add(code)
                pool.append(code)
    return pool


def classify_role(major: str, code: str) -> str:
    """
    Classify a course code's role in a plan so the UI can show which cards are
    *choices* vs fixed requirements.

    Returns one of:
      "free"        — FREE elective placeholder (fill with any catalog course)
      "ge"          — General Education area placeholder (GE 1A, GE UD2, ...)
      "grad"        — other graduation-requirement placeholder (GR GWAR, GR AI)
      "elective"    — a real course that sits in one of the major's elective_areas
      "requirement" — a fixed major/lower/upper required course (not swappable)
    """
    code = code.upper().strip()
    if code.startswith("FREE "):
        return "free"
    if code.startswith("GE "):
        return "ge"
    if code.startswith("GR "):
        return "grad"
    if find_elective_area(major, code) is not None:
        return "elective"
    return "requirement"


def get_swap_options(
    major: str,
    plan_semesters: list[dict[str, Any]],
    slot_code: str,
    slot_semester: str,
    slot_year: int,
    completed_courses: list[str],
    courses: list[dict[str, Any]],
    prerequisites: list[dict[str, Any]],
    max_units_per_semester: int = 15,
) -> dict[str, Any]:
    """
    Compute legal swap alternatives for one elective slot.

    Args:
        major: Major code (must be in SUPPORTED_MAJORS).
        plan_semesters: The plan, list of {semester, year, courses:[{course_code, units, ...}]}.
        slot_code: The elective currently in the slot being swapped.
        slot_semester / slot_year: Which semester the slot is in.
        completed_courses: Courses finished before the plan.
        courses: Catalog records for every candidate course in the area (+ the slot).
        prerequisites: Prereq rows for the candidate courses.
        max_units_per_semester: The plan's unit target (soft).

    Returns:
        {
          "area": <area name or None>,
          "slot": {course_code, year, semester},
          "options": [ {course_code, title, units, department, offered_fall,
                        offered_spring, fits_budget}... ],   # legal swaps only
          "excluded": <count of same-area courses that were not legal>,
        }
    """
    major = major.upper()
    area = find_elective_area(major, slot_code)
    if area is None:
        return {"area": None, "slot": {"course_code": slot_code, "semester": slot_semester, "year": slot_year},
                "options": [], "excluded": 0}

    # Pool = the union of ALL the major's elective areas (the catalog's full set
    # of courses that may count as an elective), permissive: gated options are
    # returned flagged, not hidden.
    candidate_codes = all_elective_codes(major)
    options, excluded = _evaluate_candidates(
        candidate_codes, plan_semesters, slot_code, slot_semester, slot_year,
        completed_courses, courses, prerequisites, max_units_per_semester, strict=False,
    )
    return {
        "area": area,
        "slot": {"course_code": slot_code, "semester": slot_semester, "year": slot_year},
        "options": options,
        "excluded": excluded,
    }


# Human labels per non-elective slot type.
_GRAD_LABEL = {"GR AI": "American Institutions", "GR GWAR": "GWAR — writing requirement"}


def get_slot_options(
    major: str,
    plan_semesters: list[dict[str, Any]],
    slot_code: str,
    slot_semester: str,
    slot_year: int,
    completed_courses: list[str],
    courses: list[dict[str, Any]],
    prerequisites: list[dict[str, Any]],
    max_units_per_semester: int = 15,
    slot_identity: Optional[str] = None,
) -> dict[str, Any]:
    """
    Role-aware fill options for ANY slot type (the generalized swap engine).

    `slot_code` is the course currently in the slot (used for plan position and
    self-exclusion). `slot_identity` is the slot's *requirement* identity — for a
    real course that replaced a placeholder it is that placeholder (e.g. a chosen
    GE course carries identity "GE 1A"), so a filled slot stays interchangeable.
    Defaults to slot_code (placeholders are their own identity).

    The route supplies the right `courses`/`prerequisites` candidate pool per slot
    type; this returns a uniform shape:
        { area, slot_type, options, excluded, needs_data, search, hint, slot }

    - elective  → candidates = the major's elective_areas group (strict)
    - grad/AI   → candidates = the AI course set (strict)
    - grad/GWAR → candidates = supplied W-suffix courses (permissive, search-driven)
    - free      → candidates = supplied catalog search hits (permissive, search-driven)
    - ge        → candidates = the area's approved courses (permissive, search-driven)
    - requirement → not fillable (empty)
    """
    from backend.engine.graduation_requirements import AI_COURSES
    from backend.engine.ge_requirements import ge_placeholder_label

    major = major.upper()
    identity = (slot_identity or slot_code).upper().strip()
    role = classify_role(major, identity)
    base = {
        "slot": {"course_code": slot_code, "semester": slot_semester, "year": slot_year},
        "slot_type": role, "options": [], "excluded": 0,
        "needs_data": False, "search": False, "hint": None, "area": None,
    }

    if role == "requirement":
        return base

    # Determine the candidate code pool + strictness by slot type. Browse/search
    # slots (GE, GWAR, FREE) are permissive: show the full menu, flag ineligible.
    strict = True
    if role == "elective":
        # `area` is the slot's home area (for display); the candidate pool is the
        # union of every area, shown permissively (gated options flagged).
        area = find_elective_area(major, identity)
        candidate_codes = all_elective_codes(major)
        base["area"] = area
        strict = False
    elif role == "ge":
        base["area"] = ge_placeholder_label(identity)
        if not get_ge_area_courses(identity):
            base["needs_data"] = True
            base["hint"] = "Specific GE course selection is coming soon."
            return base
        candidate_codes = [c["course_code"] for c in courses]
        base["search"] = True
        base["hint"] = "Approved courses for this GE area. Type to filter."
        strict = False
    elif role == "grad" and identity == "GR AI":
        candidate_codes = list(AI_COURSES)
        base["area"] = _GRAD_LABEL["GR AI"]
    elif role == "grad" and identity == "GR GWAR":
        candidate_codes = [c["course_code"] for c in courses]  # route supplies W-courses
        base["area"] = _GRAD_LABEL["GR GWAR"]
        base["search"] = True
        base["hint"] = "Any W-suffix (writing-certified) course. Type to search."
        strict = False
    elif role == "free":
        candidate_codes = [c["course_code"] for c in courses]  # route supplies search hits
        base["area"] = "Free elective"
        base["search"] = True
        base["hint"] = "Any course toward your degree total. Type to search."
        strict = False
    else:
        return base  # unknown grad slot

    options, excluded = _evaluate_candidates(
        candidate_codes, plan_semesters, slot_code, slot_semester, slot_year,
        completed_courses, courses, prerequisites, max_units_per_semester, strict=strict,
    )
    base["options"] = options
    base["excluded"] = excluded
    return base


def _evaluate_candidates(
    candidate_codes: list[str],
    plan_semesters: list[dict[str, Any]],
    slot_code: str,
    slot_semester: str,
    slot_year: int,
    completed_courses: list[str],
    courses: list[dict[str, Any]],
    prerequisites: list[dict[str, Any]],
    max_units_per_semester: int,
    strict: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    """
    Evaluate a candidate code list and return (options, excluded).

    Each candidate gets `eligible` (passes prereq/standing/offering for this slot
    right now) + a `note` explaining why not, plus a soft `fits_budget`. Already-
    placed candidates and ones with no catalog record are always dropped.

      - strict=True  (electives / AI): only eligible candidates are returned.
      - strict=False (GE / GWAR / FREE browse): ALL candidates are returned, with
        ineligible ones flagged — the user sees the full approved menu and the plan
        validator surfaces any conflict if they pick a gated one. Eligible first.

    Shared by major-elective swaps (`get_swap_options`) and the generalized
    `get_slot_options`, so every slot type uses the SAME correctness rules.
    """
    courses_by_code = {c["course_code"]: c for c in courses}
    prereq_graph = build_full_prereq_graph(prerequisites)

    standing_by_code: dict[str, Optional[str]] = {}
    for code in candidate_codes:
        rows = [r for r in prerequisites if r.get("course_code") == code]
        standing_by_code[code] = _highest_standing(r.get("min_standing") for r in rows)

    completed: set[str] = set(completed_courses)

    slot_idx: Optional[int] = None
    for i, sem in enumerate(plan_semesters):
        if sem.get("semester") == slot_semester and sem.get("year") == slot_year:
            slot_idx = i
            break

    available_before: set[str] = set(completed)
    cumulative_units = 0
    placed_anywhere: set[str] = set(completed)
    slot_units = 0
    slot_sem_units = 0
    for i, sem in enumerate(plan_semesters):
        sem_codes = {c["course_code"] for c in sem.get("courses", [])}
        placed_anywhere |= sem_codes
        if slot_idx is not None and i < slot_idx:
            available_before |= sem_codes
            cumulative_units += sum(c.get("units", 0) for c in sem.get("courses", []))
        if i == slot_idx:
            slot_sem_units = sum(c.get("units", 0) for c in sem.get("courses", []))
            for c in sem.get("courses", []):
                if c["course_code"] == slot_code:
                    slot_units = c.get("units", 0)

    term_is_fall = slot_semester.strip().lower() == "fall"

    term_label = slot_semester.strip().lower()
    options: list[dict[str, Any]] = []
    excluded = 0
    seen: set[str] = set()
    for code in candidate_codes:
        if code == slot_code or code in seen:
            continue
        seen.add(code)
        if code in placed_anywhere:          # already in the plan or completed
            excluded += 1
            continue
        rec = courses_by_code.get(code)
        if rec is None:                       # no catalog record — can't offer it
            excluded += 1
            continue

        # Determine eligibility (don't necessarily exclude — depends on `strict`).
        note: Optional[str] = None
        offered = rec.get("offered_fall", True) if term_is_fall else rec.get("offered_spring", True)
        if not offered:
            note = f"not offered in {term_label}"
        elif not _groups_satisfied(prereq_graph.get(code, []), available_before):
            note = _unmet_prereq_note(prereq_graph.get(code, []), available_before)
        else:
            standing = standing_by_code.get(code)
            if standing and cumulative_units < STANDING_UNITS.get(standing, 0):
                threshold = STANDING_UNITS.get(standing, 0)
                note = f"requires {standing} standing ({threshold}+ units)"
        eligible = note is None

        if strict and not eligible:
            excluded += 1
            continue

        units = rec.get("units", 3)
        new_sem_units = slot_sem_units - slot_units + units
        options.append({
            "course_code": code,
            "title": rec.get("title", code),
            "units": units,
            "department": rec.get("department", code.split()[0]),
            "offered_fall": rec.get("offered_fall", True),
            "offered_spring": rec.get("offered_spring", True),
            "fits_budget": new_sem_units <= max_units_per_semester,
            "eligible": eligible,
            "note": note,
        })

    # Eligible options first, then by course number.
    options.sort(key=lambda o: (not o["eligible"], _course_number(o["course_code"])))
    return options, excluded


def _groups_satisfied(groups: list[set[str]], available: set[str]) -> bool:
    """Every AND-group must have at least one member available (OR within group)."""
    return all(any(m in available for m in group) for group in groups)


def _unmet_prereq_note(groups: list[set[str]], available: set[str]) -> str:
    """Human note naming the missing prerequisites.

    Each unsatisfied AND-group becomes one clause; OR-alternatives within a group
    join with " or ", and multiple groups join with " and ". Falls back to a
    generic message if the groups are empty (shouldn't happen when called).
    """
    unmet = [g for g in groups if not any(m in available for m in g)]
    if not unmet:
        return "needs a prerequisite first"
    clauses = [" or ".join(sorted(g)) for g in unmet]
    return "requires " + " and ".join(clauses) + " first"


def _course_number(code: str) -> int:
    import re
    m = re.search(r"(\d+)", code)
    return int(m.group(1)) if m else 0
