"""
SDSU major requirement data — loaded from data/majors/*.json.

Each major is one JSON file in data/majors/, loaded at import into
SUPPORTED_MAJORS. Course codes in those files are already canonical (the
scraper normalizes them against the course catalog before writing — see
backend/engine/course_codes.py), so this module does no normalization itself;
it just loads and serves.

JSON schema (one object per file)
─────────────────────────────────
    {
      "code": "CS",                       # uppercase major code (filename stem)
      "name": "Computer Science, B.S.",
      "degree": "B.S.",                   # "B.S." or "B.A."
      "total_units": 120,
      "catalog_url": "https://catalog.sdsu.edu/preview_program.php?...",
      "verified": true,                   # hand-verified vs. auto-scraped
      "source": "hand-verified",          # provenance label
      "covered_ge_areas": ["2","5A","5C"],# GE areas satisfied by required courses
      "gwar_covered_by": [],              # non-W courses that satisfy GWAR (rare; usually [])
      "lower_division": [...],            # required lower-div course codes
      "upper_required": [...],            # required upper-div course codes
      "elective_areas": {"A — ...": [...]},# named elective pools
      "default_electives": [...]          # default selection from the pools
    }

Adding / editing a major
────────────────────────
- Hand: create or edit data/majors/<CODE>.json. Codes must be canonical
  catalog codes ("M E 190", not "ME 190"). Run validate_all_majors to check.
- Auto: the program scraper writes these files with verified=false.

Valid covered_ge_areas codes: "1A","1B","1C","2","3A","3B","4A","4B",
"5A","5B","5C","6","UD2","UD3","UD4".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.engine.ge_requirements import (
    get_ge_placeholder_codes,
    get_ge_placeholder_courses,
)
from backend.engine.graduation_requirements import (
    get_additional_placeholder_codes,
    free_electives_needed,
    get_free_elective_codes,
)

# GE placeholder code → units (5C is 1u; the rest are 3u).
_GE_UNITS: dict[str, int] = {
    c["course_code"]: c["units"] for c in get_ge_placeholder_courses()
}

# data/majors/ lives at the project root (three parents up from this file:
# backend/engine/major_requirements.py -> backend/engine -> backend -> root).
MAJORS_DIR = Path(__file__).resolve().parents[2] / "data" / "majors"


@dataclass
class MajorDef:
    code: str
    name: str
    degree: str
    total_units: int
    catalog_url: str
    lower_division: list[str]
    upper_required: list[str]
    elective_areas: dict[str, list[str]]
    default_electives: list[str]
    gwar_covered_by: list[str] = field(default_factory=list)
    covered_ge_areas: set[str] = field(default_factory=set)
    verified: bool = False
    source: str = "unknown"

    @classmethod
    def from_dict(cls, d: dict) -> "MajorDef":
        return cls(
            code=d["code"].upper(),
            name=d["name"],
            degree=d.get("degree", "B.S."),
            total_units=int(d.get("total_units", 120)),
            catalog_url=d.get("catalog_url", ""),
            lower_division=list(d.get("lower_division", [])),
            upper_required=list(d.get("upper_required", [])),
            elective_areas=dict(d.get("elective_areas", {})),
            default_electives=list(d.get("default_electives", [])),
            gwar_covered_by=list(d.get("gwar_covered_by", [])),
            covered_ge_areas=set(d.get("covered_ge_areas", [])),
            verified=bool(d.get("verified", False)),
            source=d.get("source", "unknown"),
        )


def _load_majors(majors_dir: Path = MAJORS_DIR) -> dict[str, MajorDef]:
    """Load every data/majors/*.json into a {code: MajorDef} registry."""
    registry: dict[str, MajorDef] = {}
    if not majors_dir.exists():
        return registry
    for path in sorted(majors_dir.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        defn = MajorDef.from_dict(data)
        registry[defn.code] = defn
    return registry


SUPPORTED_MAJORS: dict[str, MajorDef] = _load_majors()


def reload_majors() -> dict[str, MajorDef]:
    """Re-read data/majors from disk (useful after the scraper runs)."""
    global SUPPORTED_MAJORS
    SUPPORTED_MAJORS = _load_majors()
    return SUPPORTED_MAJORS


# ── Public API ─────────────────────────────────────────────────────────────

def get_required_courses(
    major: str,
    completed_courses: Optional[list[str]] = None,
    include_electives: bool = True,
    custom_electives: Optional[list[str]] = None,
    include_ge: bool = False,
    include_ai: bool = False,
    units_by_code: Optional[dict[str, int]] = None,
) -> list[str]:
    """
    Return all course codes required to complete a major.

    Args:
        major: Major code (e.g. "CS", "ME"). Must be in SUPPORTED_MAJORS.
        completed_courses: Already-completed courses (informs GE filtering).
        include_electives: Append the major's default elective selection.
        custom_electives: Override default electives. Each code must appear in
            one of the major's elective_areas.
        include_ge: Append GE placeholder slots, excluding areas already
            covered by the major's required courses.
        include_ai: Append the American Institutions placeholder slot.

    Returns:
        Flat, ordered list of course codes (lower-div → upper-div → electives
        → GE placeholders → other graduation requirements).

    Raises:
        ValueError: Unsupported major or invalid custom elective codes.
    """
    major = major.upper()
    if major not in SUPPORTED_MAJORS:
        raise ValueError(
            f"Major '{major}' is not supported. "
            f"Supported: {sorted(SUPPORTED_MAJORS.keys())}"
        )

    defn = SUPPORTED_MAJORS[major]
    required: list[str] = list(defn.lower_division) + list(defn.upper_required)

    # Track which codes are discretionary electives — these are the only courses
    # eligible for trimming if the requirement set overshoots the degree's
    # stated total_units (see the unit-budget trim below).
    elective_codes: list[str] = []
    if include_electives:
        if custom_electives is not None:
            all_elective_codes = {
                c for area in defn.elective_areas.values() for c in area
            }
            bad = [c for c in custom_electives if c not in all_elective_codes]
            if bad:
                raise ValueError(
                    f"Electives not in any {major} elective area: {bad}"
                )
            elective_codes = list(custom_electives)
        else:
            elective_codes = list(defn.default_electives)
        required.extend(elective_codes)

    if include_ge:
        ge_codes = get_ge_placeholder_codes(
            completed_courses=completed_courses,
            covered_ge_areas=defn.covered_ge_areas,
        )
        required.extend(ge_codes)

    extra_codes = get_additional_placeholder_codes(
        include_gwar=True,
        include_ai=include_ai,
        completed_courses=completed_courses,
        required_courses=required,
        gwar_covered_by=defn.gwar_covered_by,
    )
    required.extend(extra_codes)

    # Pad with free electives to reach the degree's total unit count. Requires
    # unit data to size the gap; skipped when units_by_code is not provided.
    # This both models real degrees (which include unrestricted electives) and
    # prevents a junior-standing deadlock in upper-division-heavy majors.
    if units_by_code is not None:
        def _unit_of(code: str) -> int:
            if code in _GE_UNITS:
                return _GE_UNITS[code]
            if code.startswith("GR "):
                return 3
            return units_by_code.get(code, 3)

        # Unit-budget trim: scraped majors sometimes over-pick electives (or
        # misclassify a required block as a choose-from pool), pushing the
        # requirement set well past the degree's stated total_units. Trim only
        # discretionary electives — highest course number first, so foundational
        # lower-division prep courses survive — until we're within budget. Firm
        # requirements, GE, and GR slots are never trimmed. Hand-verified majors
        # are authoritative and never trimmed.
        total = sum(_unit_of(c) for c in required)
        over = total - defn.total_units
        if over > 0 and elective_codes and not defn.verified:
            elective_set = set(elective_codes)
            droppable = sorted(
                (c for c in required if c in elective_set),
                key=_course_number,
                reverse=True,
            )
            to_drop: set[str] = set()
            for c in droppable:
                if over <= 0:
                    break
                to_drop.add(c)
                over -= _unit_of(c)
            if to_drop:
                required = [c for c in required if c not in to_drop]

        placed_units = sum(_unit_of(c) for c in required)
        n_free = free_electives_needed(placed_units, defn.total_units)
        required.extend(get_free_elective_codes(n_free))

    return required


def _course_number(code: str) -> int:
    """Numeric portion of a course code, for ordering (e.g. 'CIV E 521' -> 521)."""
    m = re.search(r"(\d+)", code)
    return int(m.group(1)) if m else 0
