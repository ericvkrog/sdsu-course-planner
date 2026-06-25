"""
SDSU graduation requirements beyond the major — structured placeholder data.

Source: 2026-2027 SDSU General Catalog
        catalog.sdsu.edu, catoid=12

Covers every non-major requirement a CS student must complete:
  - General Education (delegates to ge_requirements.py)
  - GWAR  — Graduation Writing Assessment Requirement
  - AI    — American Institutions (US History & Government, California law)
  - CD    — Cultural Diversity (CSU system requirement)
  - UD    — Upper-Division unit minimum (tracked, not a placeable course)

Placeholder codes use the "GR " prefix to distinguish from "GE " slots:
  GR GWAR   Upper-division writing-intensive course (3u, junior standing)
  GR AI     American Institutions course (3u, no standing requirement)

Cultural Diversity is documented here but needs no placeholder for CS students —
Area 6 (Ethnic Studies, GE 6) satisfies it automatically. GWAR is satisfied by any
upper-division W-suffix course (e.g. RWS 392W); no CS course is W-certified, so CS
majors get an explicit GWAR slot. These are preserved as placeholders so the
planner can include them when the student needs an explicit slot.
"""

import re

from typing import Any, Optional


# ── GWAR ──────────────────────────────────────────────────────────────────────
# Every SDSU undergraduate must pass one upper-division GWAR-certified course.
# At SDSU, GWAR-certified courses are marked by a "W" suffix on the course number
# (e.g. RWS 392W "Writing for Engineers", ECON 449W). The W suffix IS the marker —
# a plan satisfies GWAR if it contains any course whose number ends in W. No CS
# course is W-certified, so CS majors take a separate W course (the official MAP
# shows GWAR as its own slot for exactly this reason).

GWAR_PLACEHOLDER: dict[str, Any] = {
    "code": "GR GWAR",
    "label": "GWAR: Graduation Writing Assessment Requirement",
    "units": 3,
    "notes": (
        "Satisfy with any upper-division GWAR-certified course — these are "
        "marked by a 'W' suffix on the course number (e.g. RWS 392W 'Writing "
        "for Engineers'). No CS course is W-certified, so this is a separate "
        "requirement for CS majors."
    ),
    "min_standing": "junior",
}

# A GWAR-certified course is identified by a "W" suffix on its number, e.g.
# "RWS 392W" or "ECON 449W". Matches the trailing digits-then-W pattern so a
# course like "CS 532" (no W) does not count.
_GWAR_W_SUFFIX = re.compile(r"\d+\s*W$")


def is_gwar_course(code: str) -> bool:
    """True if ``code`` is a GWAR-certified W-suffix course (e.g. 'RWS 392W')."""
    return bool(_GWAR_W_SUFFIX.search(code.strip()))


# Explicit non-W courses that nonetheless satisfy GWAR for a given major. Empty by
# default: the W-suffix rule above is authoritative. A major's JSON may still pass
# an override list, but it should be reserved for genuine catalog exceptions.
GWAR_COVERED_BY: list[str] = []


def _gwar_is_covered(
    required: set[str], completed: set[str], extra_covered: list[str]
) -> bool:
    """GWAR is covered when any required/completed course is W-certified, or
    appears in an explicit per-major override list."""
    codes = required | completed
    if any(is_gwar_course(c) for c in codes):
        return True
    return any(c in codes for c in extra_covered)


# ── American Institutions ──────────────────────────────────────────────────────
# California Education Code §89032 requires every CSU graduate to pass a course
# in US History and Government. Must be satisfied by an approved course;
# AP US History (score ≥ 3) or AP US Government (score ≥ 3) can waive it.
# Typical satisfying courses: HIST 140, POLS 101.

# Courses that satisfy American Institutions (the pickable set for the GR AI slot).
# Canonical catalog codes (verified against data/catalog May 2026): US history
# (HIST 109/110) and US/California government (POL S 101/102). The planner models
# AI as a single 3-unit slot, so any one of these fills the GR AI placeholder.
AI_COURSES: list[str] = ["HIST 109", "HIST 110", "POL S 101", "POL S 102"]

AI_PLACEHOLDER: dict[str, Any] = {
    "code": "GR AI",
    "label": "American Institutions: US History & Government",
    "units": 3,
    "notes": (
        "Required by California law (Ed Code §89032). "
        "Satisfy with US history (HIST 109 or HIST 110) or US/California government "
        "(POL S 101 or POL S 102). AP US History or AP US Government score ≥ 3 waives this."
    ),
    "min_standing": None,
}


# ── Cultural Diversity ─────────────────────────────────────────────────────────
# CSU system requirement. For CS students it is satisfied automatically by
# GE Area 6 (Ethnic Studies), which is already a placeholder slot (GE 6).
# No separate placeholder is needed; this entry is documentation only.

CULTURAL_DIVERSITY_NOTE: str = (
    "Satisfied automatically by GE Area 6 (Ethnic Studies). "
    "The GE 6 placeholder slot covers both the GE requirement and the "
    "CSU Cultural Diversity requirement."
)


# ── Upper-Division Unit Minimum ────────────────────────────────────────────────
# SDSU requires at least 40 units of upper-division coursework (courses numbered
# 300–499 for undergrad, or cross-listed). The CS major fulfills this naturally;
# tracked here for completeness, not a placeable course.

UPPER_DIVISION_MINIMUM_UNITS: int = 40


# ── GE Area Reference ─────────────────────────────────────────────────────────
# Canonical SDSU GE area names for UI labels and documentation.
# Matches the 2026-2027 catalog section headings exactly.

GE_AREA_NAMES: dict[str, str] = {
    "1A":  "Area 1A — English Composition",
    "1B":  "Area 1B — Rhetoric and Critical Thinking",
    "1C":  "Area 1C — Oral Communication",
    "2":   "Area 2 — Quantitative Reasoning",
    "3A":  "Area 3A — Arts",
    "3B":  "Area 3B — Humanities",
    "4A":  "Area 4A — Social and Behavioral Sciences",
    "4B":  "Area 4B — Social and Behavioral Sciences (second course)",
    "5A":  "Area 5A — Physical Science",
    "5B":  "Area 5B — Life Science",
    "5C":  "Area 5C — Laboratory Activity",
    "6":   "Area 6 — Ethnic Studies",
    "UD2": "Upper-Division Area 2/5 — Science or Quantitative Reasoning",
    "UD3": "Upper-Division Area 3 — Arts and Humanities",
    "UD4": "Upper-Division Area 4 — Social Sciences",
}


# ── Requirement category registry ─────────────────────────────────────────────
# Maps a short key to human-readable metadata. Used by the API and frontend to
# display what each toggle turns on.

REQUIREMENT_CATEGORIES: dict[str, dict[str, Any]] = {
    "GE": {
        "label": "General Education (43 units)",
        "description": (
            "SDSU GE program: Areas 1–6 plus Upper-Division Explorations. "
            "Areas 2, 5A, and 5C are satisfied by CS major double-counts."
        ),
        "units": 43,
        "placeholder_prefix": "GE ",
    },
    "GWAR": {
        "label": "GWAR — Graduation Writing Assessment (3 units)",
        "description": GWAR_PLACEHOLDER["notes"],
        "units": 3,
        "placeholder_prefix": "GR GWAR",
        "auto_satisfied_by": GWAR_COVERED_BY,
    },
    "AI": {
        "label": "American Institutions — US History & Government (3 units)",
        "description": AI_PLACEHOLDER["notes"],
        "units": 3,
        "placeholder_prefix": "GR AI",
    },
    "CD": {
        "label": "Cultural Diversity (satisfied by GE Area 6)",
        "description": CULTURAL_DIVERSITY_NOTE,
        "units": 0,
        "placeholder_prefix": None,
        "auto_satisfied_by": ["GE 6"],
    },
}


# ── Public API ─────────────────────────────────────────────────────────────────

def get_additional_placeholder_courses(
    include_gwar: bool = False,
    include_ai: bool = True,
    completed_courses: Optional[list[str]] = None,
    required_courses: Optional[list[str]] = None,
    gwar_covered_by: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """
    Return synthetic course dicts for non-GE graduation requirement placeholders.

    Args:
        include_gwar: Include the GWAR placeholder slot.
        include_ai: Include the American Institutions placeholder slot.
        completed_courses: Codes the student has already completed.
        required_courses: Codes in the student's required list.
        gwar_covered_by: Explicit non-W courses from this major that nonetheless
            satisfy GWAR (genuine catalog exceptions). Defaults to GWAR_COVERED_BY
            (empty — the W-suffix rule in is_gwar_course is authoritative).

    Returns:
        List of synthetic course dicts compatible with the solver's course list.
    """
    completed: set[str] = set(completed_courses or [])
    required: set[str] = set(required_courses or [])
    wgwar_covered = gwar_covered_by if gwar_covered_by is not None else GWAR_COVERED_BY

    results: list[dict[str, Any]] = []

    if include_gwar:
        gwar_covered = _gwar_is_covered(required, completed, wgwar_covered)
        if not gwar_covered and GWAR_PLACEHOLDER["code"] not in completed:
            results.append(_make_course_dict(GWAR_PLACEHOLDER))

    if include_ai:
        if AI_PLACEHOLDER["code"] not in completed:
            results.append(_make_course_dict(AI_PLACEHOLDER))

    return results


def get_additional_placeholder_prereqs(
    include_gwar: bool = False,
    include_ai: bool = True,
    completed_courses: Optional[list[str]] = None,
    required_courses: Optional[list[str]] = None,
    gwar_covered_by: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """
    Return synthetic prerequisite rows for non-GE graduation requirement
    placeholders. Only requirements with a standing constraint produce rows.
    """
    completed: set[str] = set(completed_courses or [])
    required: set[str] = set(required_courses or [])
    wgwar_covered = gwar_covered_by if gwar_covered_by is not None else GWAR_COVERED_BY

    results: list[dict[str, Any]] = []

    if include_gwar:
        gwar_covered = _gwar_is_covered(required, completed, wgwar_covered)
        if not gwar_covered and GWAR_PLACEHOLDER["code"] not in completed:
            if GWAR_PLACEHOLDER["min_standing"]:
                results.append(_make_prereq_dict(GWAR_PLACEHOLDER))

    if include_ai and AI_PLACEHOLDER["min_standing"]:
        if AI_PLACEHOLDER["code"] not in completed:
            results.append(_make_prereq_dict(AI_PLACEHOLDER))

    return results


def get_additional_placeholder_codes(
    include_gwar: bool = False,
    include_ai: bool = True,
    completed_courses: Optional[list[str]] = None,
    required_courses: Optional[list[str]] = None,
    gwar_covered_by: Optional[list[str]] = None,
) -> list[str]:
    """Return the placeholder codes that would be included given the flags."""
    courses = get_additional_placeholder_courses(
        include_gwar=include_gwar,
        include_ai=include_ai,
        completed_courses=completed_courses,
        required_courses=required_courses,
        gwar_covered_by=gwar_covered_by,
    )
    return [c["course_code"] for c in courses]


def is_additional_placeholder(code: str) -> bool:
    """Return True if the code is a non-GE graduation requirement placeholder."""
    return code.startswith("GR ")


# ── Free electives ──────────────────────────────────────────────────────────────
# Every ~120-unit degree includes free/unrestricted electives that fill the gap
# between major + GE + graduation requirements and the degree total. Modeling
# them matters for two reasons:
#   1. Realism — the plan should total the degree's unit count, not just majors.
#   2. It prevents a junior-standing DEADLOCK in upper-division-heavy majors:
#      without enough non-gated lower-division units, cumulative units never
#      reach 60, so junior-standing courses can never be placed. Free electives
#      (no prereq, no standing) keep early semesters full so standing advances.
# Placeholder codes use the "FREE " prefix: FREE 1, FREE 2, …

FREE_ELECTIVE_UNITS = 3
_MAX_FREE_ELECTIVES = 20  # safety cap


def is_free_elective(code: str) -> bool:
    return code.startswith("FREE ")


def get_free_elective_codes(n: int) -> list[str]:
    n = max(0, min(n, _MAX_FREE_ELECTIVES))
    return [f"FREE {i + 1}" for i in range(n)]


def get_free_elective_courses(n: int) -> list[dict[str, Any]]:
    return [
        {
            "course_code": code,
            "title": "Free Elective",
            "units": FREE_ELECTIVE_UNITS,
            "department": "FREE",
            "description": "Unrestricted elective — any course toward the degree total.",
            "grading_method": None,
            "offered_fall": True,
            "offered_spring": True,
            "max_credits": None,
            "notes": "Choose any course that counts toward the degree unit total.",
        }
        for code in get_free_elective_codes(n)
    ]


def free_electives_needed(
    placed_units: int, total_units: int, slot_units: int = FREE_ELECTIVE_UNITS
) -> int:
    """How many free-elective slots fill the gap to the degree total."""
    gap = total_units - placed_units
    if gap <= 0:
        return 0
    return min(_MAX_FREE_ELECTIVES, round(gap / slot_units))


# ── Private helpers ────────────────────────────────────────────────────────────

def _make_course_dict(placeholder: dict[str, Any]) -> dict[str, Any]:
    return {
        "course_code": placeholder["code"],
        "title": placeholder["label"],
        "units": placeholder["units"],
        "department": "GR",
        "description": placeholder["notes"],
        "grading_method": None,
        "offered_fall": True,
        "offered_spring": True,
        "max_credits": None,
        "notes": placeholder["notes"],
    }


def _make_prereq_dict(placeholder: dict[str, Any]) -> dict[str, Any]:
    return {
        "course_code": placeholder["code"],
        "prereq_code": None,
        "prereq_type": "required",
        "min_standing": placeholder["min_standing"],
        "prereq_group": None,
    }
