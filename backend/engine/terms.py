"""
Academic term ordering.

The planner generates Fall/Spring plans, but students may add optional Summer or
Winter terms (as manual relief valves — drag a class there to lighten a Fall/Spring
load). For prerequisite/standing checks to stay correct, the plan's semesters must
be processed in true chronological order. This module is the single source of that
order, used by the API's revalidation step (and mirrored in the frontend).

SDSU calendar order WITHIN a calendar year:
    Winter (January intersession) → Spring → Summer → Fall

So a course in Fall 2026 precedes Winter 2027, which precedes Spring 2027, etc.
"""

from typing import Any

# Rank of each term within its calendar year (lower = earlier).
TERM_RANK: dict[str, int] = {"Winter": 0, "Spring": 1, "Summer": 2, "Fall": 3}

# Terms a student may add on top of the generated Fall/Spring plan.
OPTIONAL_TERMS: tuple[str, ...] = ("Winter", "Summer")


def chronological_key(semester: str, year: int) -> tuple[int, int]:
    """Sort key placing (semester, year) in true calendar order.

    Unknown term names sort last within their year (rank 9) so bad data never
    silently reorders real terms ahead of themselves.
    """
    return (int(year), TERM_RANK.get((semester or "").strip().title(), 9))


def sort_semesters(semesters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the plan's semesters in chronological order (stable)."""
    return sorted(
        semesters,
        key=lambda s: chronological_key(s.get("semester", ""), s.get("year", 0)),
    )
