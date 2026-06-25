"""
Canonical course-code normalization.

THE PROBLEM
───────────
SDSU course codes have multi-word department prefixes containing internal
spaces — "M E 190", "B A 100", "POL S 101", "GEN S 100A". 797 of the 4,817
cataloged courses use this format. Different data sources render the same code
inconsistently: a program/roadmap page may write "ME 190", "M E 190", or
"ME190" for what the course catalog stores as "M E 190". Naive whitespace
collapsing does NOT fix this — it can't know that "ME" should become "M E".

THE SOLUTION
────────────
Treat the scraped course catalog as the single source of truth. Build a
space-insensitive index of every real course code, then resolve any incoming
code (from program pages, prereq fixes, user input) against it:

    "ME 190"  → "M E 190"
    "me190"   → "M E 190"
    "M E 190" → "M E 190"
    "CS 150"  → "CS 150"

A code that can't be resolved to a real catalog code is returned in a cleaned
canonical form and flagged by resolve_code(strict=False) returning None, so
callers can surface data-quality problems instead of silently mismatching.

USAGE
─────
    from backend.engine.course_codes import CodeResolver

    resolver = CodeResolver.from_catalog_dir("data/catalog")
    resolver.resolve("ME 190")        # -> "M E 190"
    resolver.resolve("BOGUS 999")     # -> None (not a real course)
    resolver.clean("m e  190")        # -> "M E 190" (format only, no lookup)
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional


def clean_code(raw: str) -> str:
    """
    Normalize formatting only (no catalog lookup).

    - Replace non-breaking spaces with regular spaces.
    - Collapse runs of whitespace to a single space.
    - Uppercase and strip.

    This produces a consistent surface form but does NOT canonicalize
    department spacing (e.g. "ME 190" stays "ME 190"). Use CodeResolver.resolve
    for that.
    """
    if raw is None:
        return ""
    s = raw.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


def _spaceless(code: str) -> str:
    """Key for space-insensitive matching: uppercase, all spaces removed."""
    return clean_code(code).replace(" ", "")


# Placeholder prefixes that are synthetic (not real catalog courses) but are
# still valid plan codes. They must pass through normalization untouched.
_PLACEHOLDER_PREFIXES = ("GE ", "GR ")


def is_placeholder(code: str) -> bool:
    """True for synthetic GE/GR placeholder codes (not real catalog courses)."""
    c = clean_code(code)
    return c.startswith(_PLACEHOLDER_PREFIXES)


class CodeResolver:
    """
    Resolves arbitrary course-code spellings to canonical catalog codes.

    Built from the set of real course codes (the source of truth). Construct
    via from_catalog_dir() in normal use, or from_codes() in tests.
    """

    def __init__(self, canonical_codes: Iterable[str]) -> None:
        self._canonical: set[str] = set()
        self._by_spaceless: dict[str, str] = {}
        self._ambiguous: set[str] = set()

        for code in canonical_codes:
            c = clean_code(code)
            if not c:
                continue
            self._canonical.add(c)
            key = _spaceless(c)
            if key in self._by_spaceless and self._by_spaceless[key] != c:
                # Two different canonical codes collapse to the same spaceless
                # key (should not happen for SDSU data, but guard anyway).
                self._ambiguous.add(key)
            else:
                self._by_spaceless[key] = c

    # ── Construction ────────────────────────────────────────────────────────

    @classmethod
    def from_codes(cls, codes: Iterable[str]) -> "CodeResolver":
        return cls(codes)

    @classmethod
    def from_catalog_dir(cls, catalog_dir: str | Path) -> "CodeResolver":
        """Build from every course_code in data/catalog/*.json."""
        codes: list[str] = []
        for path in glob.glob(str(Path(catalog_dir) / "*.json")):
            if Path(path).name in ("departments.json", "prereq_groups.json", "ge_areas.json"):
                continue
            with open(path, encoding="utf-8") as f:
                for course in json.load(f):
                    code = course.get("course_code")
                    if code:
                        codes.append(code)
        return cls(codes)

    @classmethod
    def from_courses(cls, courses: Iterable[dict[str, Any]]) -> "CodeResolver":
        """Build from a list of course dicts (DB or JSON rows)."""
        return cls(c["course_code"] for c in courses if c.get("course_code"))

    # ── Resolution ──────────────────────────────────────────────────────────

    def resolve(self, raw: str) -> Optional[str]:
        """
        Resolve `raw` to a canonical catalog code, or None if it isn't a real
        course. Placeholder codes (GE/GR) pass through as their cleaned form.

        Resolution order:
          1. Cleaned form is already a canonical code → return it.
          2. Placeholder (GE/GR) → return cleaned form.
          3. Space-insensitive match against the catalog → return canonical.
          4. No match → None.
        """
        c = clean_code(raw)
        if not c:
            return None
        if c in self._canonical:
            return c
        if c.startswith(_PLACEHOLDER_PREFIXES):
            return c
        key = _spaceless(c)
        if key in self._ambiguous:
            return None
        return self._by_spaceless.get(key)

    def resolve_or_clean(self, raw: str) -> str:
        """
        Resolve to canonical if possible, otherwise return the cleaned form.
        Use when you need a value regardless of catalog membership (the result
        may not be a real course — check with is_known()).
        """
        return self.resolve(raw) or clean_code(raw)

    def is_known(self, raw: str) -> bool:
        """True if `raw` resolves to a real catalog course."""
        c = clean_code(raw)
        if c.startswith(_PLACEHOLDER_PREFIXES):
            return True
        return self.resolve(raw) is not None

    def resolve_list(
        self, raws: Iterable[str]
    ) -> tuple[list[str], list[str]]:
        """
        Resolve many codes at once.

        Returns (resolved, unresolved):
          - resolved:   canonical codes, order-preserving, de-duplicated
          - unresolved: cleaned forms of codes that aren't real catalog courses
        """
        resolved: list[str] = []
        unresolved: list[str] = []
        seen: set[str] = set()
        for raw in raws:
            r = self.resolve(raw)
            if r is None:
                cleaned = clean_code(raw)
                if cleaned and cleaned not in unresolved:
                    unresolved.append(cleaned)
            elif r not in seen:
                seen.add(r)
                resolved.append(r)
        return resolved, unresolved

    @property
    def canonical_codes(self) -> set[str]:
        return set(self._canonical)
