"""
Prerequisite relationships missing or wrong in the catalog scrape.

These rows are injected at plan-time as a safety net. The authoritative fix
is in data/catalog/cs.json (applied via migration 002_cs_prereq_fixes.sql).
This file keeps the same rows so plans work correctly even against a DB that
has not yet had the migration applied.

Source: 2026-2027 SDSU General Catalog, verified against course descriptions.
Format matches the prerequisites table schema.
"""

from typing import Any


# Old course numbers still appearing in DB prerequisite rows (pre-migration).
# Maps scraped code → current equivalent. Applied before any prereq processing.
# Migration 002 removes the STAT 119 row from the DB; alias kept for safety.
COURSE_ALIASES: dict[str, str] = {
    "STAT 119": "STAT 250",
}


MISSING_PREREQS: list[dict[str, Any]] = [
    # ── CS lower division ──────────────────────────────────────────────────
    # CS 160 (Intermediate Programming) requires CS 150 — missing from catalog.
    {
        "course_code": "CS 160",
        "prereq_code": "CS 150",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },
    # CS 240 (Computer Organization) requires CS 150 and CS 160 — both missing from catalog.
    {
        "course_code": "CS 240",
        "prereq_code": "CS 150",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },
    {
        "course_code": "CS 240",
        "prereq_code": "CS 160",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },
    # CS 250 (Introduction to Software Systems) requires CS 150 and CS 160 — both missing from catalog.
    {
        "course_code": "CS 250",
        "prereq_code": "CS 150",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },
    {
        "course_code": "CS 250",
        "prereq_code": "CS 160",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },

    # ── CS upper division required ─────────────────────────────────────────
    # CS 420, 450, 460, 480 all show empty prereqs in the scrape.
    # Actual prereqs per 2026-2027 catalog:

    # CS 420: Advanced Programming Languages — requires CS 210
    {
        "course_code": "CS 420",
        "prereq_code": "CS 210",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },

    # CS 450: Introduction to Artificial Intelligence — requires CS 210
    {
        "course_code": "CS 450",
        "prereq_code": "CS 210",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },

    # CS 460: Algorithms — requires CS 210 and MATH 245
    {
        "course_code": "CS 460",
        "prereq_code": "CS 210",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },
    {
        "course_code": "CS 460",
        "prereq_code": "MATH 245",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },

    # CS 480: Operating Systems — requires CS 210 and CS 240
    {
        "course_code": "CS 480",
        "prereq_code": "CS 210",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },
    {
        "course_code": "CS 480",
        "prereq_code": "CS 240",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },

    # CS 577 lists STAT 119 (old number) — current equivalent is STAT 250.
    # Add STAT 250 as the effective prereq so the solver enforces it.
    {
        "course_code": "CS 577",
        "prereq_code": "STAT 250",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },

    # ── ME upper division ──────────────────────────────────────────────────
    # M E 430: Automatic Control — requires A E 280 (Methods) and M E 350 (Thermo)
    {
        "course_code": "M E 430",
        "prereq_code": "A E 280",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },
    {
        "course_code": "M E 430",
        "prereq_code": "M E 350",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },
    # M E 490W: Senior Project — junior standing required so it lands in year 3+
    {
        "course_code": "M E 490W",
        "prereq_code": None,
        "prereq_type": "required",
        "min_standing": "junior",
        "prereq_group": None,
    },

    # ── EE upper division ──────────────────────────────────────────────────
    # E E 300: Computational/Statistical Methods — requires E E 200
    {
        "course_code": "E E 300",
        "prereq_code": "E E 200",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },
    # COMPE 375: Embedded Systems — requires COMPE 271 (Computer Organization)
    {
        "course_code": "COMPE 375",
        "prereq_code": "COMPE 271",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },
    # E E 491W: Senior Design A — requires E E 410 (Signals and Systems)
    {
        "course_code": "E E 491W",
        "prereq_code": "E E 410",
        "prereq_type": "required",
        "min_standing": None,
        "prereq_group": None,
    },
]


def get_catalog_fix_prereqs(course_codes: set[str]) -> list[dict[str, Any]]:
    """
    Return fix rows relevant to the given set of course codes.

    Args:
        course_codes: All course codes in the current plan (required + completed).

    Returns:
        Prerequisite rows to inject alongside the real prereq data.
    """
    return [
        row for row in MISSING_PREREQS
        if row["course_code"] in course_codes
    ]


def apply_course_aliases(
    prereqs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Replace old/renamed course codes in prereq_code fields with their
    current equivalents, per COURSE_ALIASES.

    Returns a new list; does not mutate the input.
    """
    result = []
    for row in prereqs:
        code = row.get("prereq_code")
        if code and code in COURSE_ALIASES:
            row = {**row, "prereq_code": COURSE_ALIASES[code]}
        result.append(row)
    return result
