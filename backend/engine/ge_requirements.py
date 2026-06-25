"""
SDSU General Education requirements for inclusion in degree plans.

Source: 2026-2027 SDSU General Catalog — General Education Requirements
        catalog.sdsu.edu, catoid=12, poid=11884

Total: 43 units (34 lower-division + 9 upper-division Explorations).

GE slots appear in plans as placeholder course codes in the "GE" department:

  Lower-Division (34 units):
    GE 1A   Area 1A — English Composition (3u)
    GE 1B   Area 1B — Critical Thinking (3u)
    GE 1C   Area 1C — Oral Communication (3u)
    GE 2    Area 2  — Quantitative Reasoning (3u)
    GE 3A   Area 3A — Arts (3u)
    GE 3B   Area 3B — Humanities (3u)
    GE 4A   Area 4A — Social Sciences I (3u)
    GE 4B   Area 4B — Social Sciences II (3u)
    GE 5A   Area 5A — Physical Science (3u)
    GE 5B   Area 5B — Biological Science (3u)
    GE 5C   Area 5C — Science Laboratory (1u)
    GE 6    Area 6  — Ethnic Studies (3u)

  Upper-Division Explorations (9 units, require junior standing):
    GE UD2  UD Area 2/5 — Science/Quantitative (3u)
    GE UD3  UD Area 3   — Arts & Humanities (3u)
    GE UD4  UD Area 4   — Social Sciences (3u)

Majors that double-count courses toward GE areas pass their covered_ge_areas
set to get_ge_placeholder_codes() so those placeholder slots are excluded.

Example:
  CS major covers Area 2 (MATH 150), Area 5A (PHYS 195), Area 5C (PHYS 195L).
  → pass covered_ge_areas={"2", "5A", "5C"} to skip those three placeholders.
"""

from typing import Any, Optional


# ── Placeholder definitions ────────────────────────────────────────────────
# Each entry: code, label, units, min_standing
# ALL areas are listed here. Callers filter out areas already covered by the
# major's required courses by passing covered_ge_areas.

GE_PLACEHOLDERS: list[dict[str, Any]] = [
    # Area 1: English Communication (9u) ─────────────────────────────────
    {
        "code": "GE 1A",
        "label": "Area 1A: English Composition",
        "units": 3,
        "notes": "Satisfy with any approved Area 1A course (e.g. RWS 100, ECL 100)",
        "min_standing": None,
    },
    {
        "code": "GE 1B",
        "label": "Area 1B: Critical Thinking",
        "units": 3,
        "notes": "Satisfy with any approved Area 1B course (e.g. RWS 200, PHIL 200)",
        "min_standing": None,
    },
    {
        "code": "GE 1C",
        "label": "Area 1C: Oral Communication",
        "units": 3,
        "notes": "Satisfy with any approved Area 1C course (e.g. COMM 103)",
        "min_standing": None,
    },
    # Area 2: Quantitative Reasoning (3u) ─────────────────────────────────
    {
        "code": "GE 2",
        "label": "Area 2: Quantitative Reasoning",
        "units": 3,
        "notes": "Satisfy with any approved Area 2 course (e.g. MATH 119, STAT 119). "
                 "Often double-counted with major math requirements.",
        "min_standing": None,
    },
    # Area 3: Arts and Humanities (6u) ────────────────────────────────────
    {
        "code": "GE 3A",
        "label": "Area 3A: Arts",
        "units": 3,
        "notes": "Satisfy with any approved Area 3A course (e.g. ART 157, MUSIC 151, TFM 160)",
        "min_standing": None,
    },
    {
        "code": "GE 3B",
        "label": "Area 3B: Humanities",
        "units": 3,
        "notes": "Satisfy with any approved Area 3B course (e.g. HIST 100, PHIL 100)",
        "min_standing": None,
    },
    # Area 4: Social and Behavioral Sciences (6u) ─────────────────────────
    {
        "code": "GE 4A",
        "label": "Area 4A: Social Sciences",
        "units": 3,
        "notes": "Satisfy with any approved Area 4 course (e.g. PSY 101, SOC 101, ANTH 102)",
        "min_standing": None,
    },
    {
        "code": "GE 4B",
        "label": "Area 4B: Social Sciences",
        "units": 3,
        "notes": "Satisfy with a second Area 4 course from a different department",
        "min_standing": None,
    },
    # Area 5: Physical and Biological Sciences ────────────────────────────
    {
        "code": "GE 5A",
        "label": "Area 5A: Physical Science",
        "units": 3,
        "notes": "Satisfy with any approved Area 5A course (e.g. PHYS 195, CHEM 100, ASTR 101). "
                 "Often double-counted with major science requirements.",
        "min_standing": None,
    },
    {
        "code": "GE 5B",
        "label": "Area 5B: Biological Science",
        "units": 3,
        "notes": "Satisfy with any approved Area 5B course (e.g. BIOL 100, BIOL 101)",
        "min_standing": None,
    },
    {
        "code": "GE 5C",
        "label": "Area 5C: Science Laboratory",
        "units": 1,
        "notes": "Satisfy with any approved Area 5C lab course (e.g. PHYS 195L, CHEM 100L). "
                 "Often double-counted with major lab requirements.",
        "min_standing": None,
    },
    # Area 6: Ethnic Studies (3u) ─────────────────────────────────────────
    {
        "code": "GE 6",
        "label": "Area 6: Ethnic Studies",
        "units": 3,
        "notes": "Satisfy with any Africana, American Indian, Asian American, or Chicana/o Studies course",
        "min_standing": None,
    },
    # Upper-Division Explorations (9u) ────────────────────────────────────
    # Requires junior standing (60+ completed units) before enrollment.
    {
        "code": "GE UD2",
        "label": "Upper-Div Area 2/5: Science or Quantitative",
        "units": 3,
        "notes": "Satisfy with any approved upper-division Area 2 or 5 course (e.g. BIOL 315, CHEM 300)",
        "min_standing": "junior",
    },
    {
        "code": "GE UD3",
        "label": "Upper-Div Area 3: Arts & Humanities",
        "units": 3,
        "notes": "Satisfy with any approved upper-division Area 3 course (e.g. PHIL 351, HIST 421)",
        "min_standing": "junior",
    },
    {
        "code": "GE UD4",
        "label": "Upper-Div Area 4: Social Sciences",
        "units": 3,
        "notes": "Satisfy with any approved upper-division Area 4 course (e.g. SOC 355, GEOG 312)",
        "min_standing": "junior",
    },
]

# Index by code for quick lookup.
_BY_CODE: dict[str, dict] = {p["code"]: p for p in GE_PLACEHOLDERS}

# GE area code → placeholder code (e.g. "2" → "GE 2")
_AREA_TO_PLACEHOLDER: dict[str, str] = {
    "1A": "GE 1A", "1B": "GE 1B", "1C": "GE 1C",
    "2":  "GE 2",
    "3A": "GE 3A", "3B": "GE 3B",
    "4A": "GE 4A", "4B": "GE 4B",
    "5A": "GE 5A", "5B": "GE 5B", "5C": "GE 5C",
    "6":  "GE 6",
    "UD2": "GE UD2", "UD3": "GE UD3", "UD4": "GE UD4",
}


def get_ge_placeholder_codes(
    completed_courses: Optional[list[str]] = None,
    covered_ge_areas: Optional[set[str]] = None,
) -> list[str]:
    """
    Return GE placeholder codes the student still needs.

    Args:
        completed_courses: Placeholder codes already completed (excluded).
        covered_ge_areas: GE area codes pre-satisfied by the major's required
            courses (e.g. {"2", "5A", "5C"} for CS). Placeholders for these
            areas are excluded because the major course already fills the slot.

    Returns:
        List of GE placeholder codes that must still appear in the plan.
    """
    completed: set[str] = set(completed_courses or [])
    skipped_placeholders: set[str] = {
        _AREA_TO_PLACEHOLDER[area]
        for area in (covered_ge_areas or set())
        if area in _AREA_TO_PLACEHOLDER
    }

    return [
        p["code"]
        for p in GE_PLACEHOLDERS
        if p["code"] not in completed and p["code"] not in skipped_placeholders
    ]


def get_ge_placeholder_courses() -> list[dict[str, Any]]:
    """
    Return synthetic course dicts for ALL GE placeholder slots.

    Injected into the solver's course list alongside real DB courses.
    Callers filter to just the codes they need before passing to the solver.
    """
    return [
        {
            "course_code": p["code"],
            "title": p["label"],
            "units": p["units"],
            "department": "GE",
            "description": p["notes"],
            "grading_method": None,
            "offered_fall": True,
            "offered_spring": True,
            "max_credits": None,
            "notes": p["notes"],
        }
        for p in GE_PLACEHOLDERS
    ]


def get_ge_placeholder_prereqs() -> list[dict[str, Any]]:
    """
    Return synthetic prerequisite rows for GE placeholder courses.

    Only upper-division GE slots have prerequisites (junior standing).
    """
    return [
        {
            "course_code": p["code"],
            "prereq_code": None,
            "prereq_type": "required",
            "min_standing": p["min_standing"],
            "prereq_group": None,
        }
        for p in GE_PLACEHOLDERS
        if p["min_standing"]
    ]


def ge_placeholder_label(code: str) -> str:
    """Human-readable label for a GE placeholder code."""
    return _BY_CODE.get(code, {}).get("label", code)
