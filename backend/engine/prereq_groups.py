"""
Prerequisite OR-group overlay.

The original catalog scrape discarded the "and"/"or" connectives between
prerequisites, so every listed prereq was treated as an AND requirement. The
enrichment pass (backend/scraper/enrich_prereq_groups.py) re-parses the live
catalog and records, in data/catalog/prereq_groups.json, which courses have
OR-grouped prerequisites:

    { "SPAN 307": { "SPAN 301": 1, "SPAN 302": 1, "SPAN 381": 1, "SPAN 382": 1 }, ... }

apply_prereq_groups() stamps these group ids onto prerequisite rows at plan
time, so both the JSON-backed engine path and the DB-backed API path get OR
semantics without a reseed. Rows sharing a (course_code, group) are OR
alternatives; the solver, validator, and prereq_checker already honour
prereq_group.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_OVERLAY_PATH = Path(__file__).resolve().parents[2] / "data" / "catalog" / "prereq_groups.json"

# Loaded once at import. {course_code: {prereq_code: group_id}}
# An absent or unreadable overlay is NOT silent: without it every prerequisite
# collapses to an AND requirement, which over-constrains plans (a course needing
# "X or Y" would demand both). Warn loudly so the data gap is visible.
_OVERLAY: dict[str, dict[str, int]] = {}
try:
    _OVERLAY = json.loads(_OVERLAY_PATH.read_text())
except FileNotFoundError:
    logger.warning(
        "OR-group overlay not found at %s — all prerequisites will be treated "
        "as AND requirements. Run backend.scraper.enrich_prereq_groups to "
        "regenerate it.",
        _OVERLAY_PATH,
    )
except (OSError, ValueError) as exc:
    logger.warning(
        "OR-group overlay at %s could not be read (%s) — all prerequisites "
        "will be treated as AND requirements.",
        _OVERLAY_PATH,
        exc,
    )


def apply_prereq_groups(prereqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Return prereq rows with prereq_group set from the OR-group overlay.

    A row gets a group id when its (course_code, prereq_code) pair appears in
    the overlay; otherwise its existing prereq_group is preserved (defaulting
    to None). Does not mutate the input rows.
    """
    if not _OVERLAY:
        return prereqs
    out: list[dict[str, Any]] = []
    for row in prereqs:
        course = row.get("course_code")
        prereq = row.get("prereq_code")
        group = _OVERLAY.get(course, {}).get(prereq) if course and prereq else None
        if group is not None:
            out.append({**row, "prereq_group": group})
        else:
            out.append(row)
    return out
