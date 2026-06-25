"""
Scrapes SDSU degree-program requirements from catalog.sdsu.edu (catoid=12,
the current 2026-2027 catalog — same catalog the course data was scraped from,
so course codes line up).

Output: one JSON file per bachelor's program in data/majors/, in the schema
major_requirements.py loads. Every course code is normalized against the
course catalog (backend/engine/course_codes.CodeResolver) so scraped codes
match the catalog exactly ("ME 190" → "M E 190").

Verified, hand-curated majors (verified=true in their JSON) are NEVER
overwritten — the scraper skips any program whose poid matches one of them.

Usage:
    python -m backend.scraper.program_scraper                # all bachelor's
    python -m backend.scraper.program_scraper --limit 5      # first 5 (testing)
    python -m backend.scraper.program_scraper --poid 11969   # one program
    python -m backend.scraper.program_scraper --delay 0.5    # custom rate limit
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.engine.course_codes import CodeResolver, clean_code

BASE_URL = "https://catalog.sdsu.edu"
CATOID = 12
SUMMARY_NAVOID = 1120  # "Summary of Curricula Offered" — lists every program
MAJORS_DIR = ROOT / "data" / "majors"
CATALOG_DIR = ROOT / "data" / "catalog"
DEFAULT_DELAY = 1.0

# Elective/choice sections: header or intro text containing any of these means
# the courses are a pool to choose from, not all-required.
_ELECTIVE_HINTS = re.compile(
    r"\b(elective|choose|select|one of|two of|three of|following|"
    r"any of|chosen from|from the following|emphasis|concentration)\b",
    re.I,
)

# Only undergraduate bachelor's degrees. Name ends in B.A., B.S., B.M., or B.F.A.
# The leading (?<![A-Za-z.]) stops "M.B.A." / "M.S." master's degrees from
# matching on their trailing "B.A."/letters. The end-anchor excludes 4+1
# BS/MS combos ("...Degree"), credential-prep ("...Credential"), etc.
_BACHELOR_RE = re.compile(r"(?<![A-Za-z.])B\.\s*(?:[AS]\.|M\.|F\.\s*A\.)\s*$")


def get_soup(url: str, session: requests.Session) -> BeautifulSoup:
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


# ── Program enumeration ──────────────────────────────────────────────────────

def list_programs(session: requests.Session) -> list[dict]:
    """
    Return every program on the Summary of Curricula page as
    {poid, name}. Includes all degree types; filter later.
    """
    url = f"{BASE_URL}/content.php?catoid={CATOID}&navoid={SUMMARY_NAVOID}"
    soup = get_soup(url, session)
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"preview_program\.php\?catoid=%d&(?:amp;)?poid=(\d+)" % CATOID, a["href"])
        if not m:
            continue
        poid = m.group(1)
        name = re.sub(r"\s+", " ", a.get_text(" ")).strip()
        if not name or poid in seen:
            continue
        seen.add(poid)
        out.append({"poid": poid, "name": name})
    return out


def is_bachelors(name: str) -> bool:
    return bool(_BACHELOR_RE.search(name))


# ── Program parsing ──────────────────────────────────────────────────────────

def _course_codes_from_section(section_html: BeautifulSoup) -> list[str]:
    """Extract raw course codes from a section's acalog-course list items."""
    codes: list[str] = []
    for li in section_html.find_all("li", class_="acalog-course"):
        a = li.find("a", attrs={"aria-label": True})
        raw = None
        if a and a.get("aria-label"):
            m = re.search(r"View course details for\s+(.+?)\s+-\s+", a["aria-label"])
            if m:
                raw = m.group(1)
        if not raw:
            # Fallback: leading "DEPT NUM" of the link text.
            txt = li.get_text(" ", strip=True)
            m = re.match(r"([A-Z][A-Z ]*?\s*\d+[A-Z]*)\s*-", txt)
            if m:
                raw = m.group(1)
        if raw:
            codes.append(raw)
    return codes


def _is_upper(canonical_code: str) -> bool:
    """True if a course is upper-division (number >= 300)."""
    m = re.search(r"(\d+)", canonical_code)
    return bool(m) and int(m.group(1)) >= 300


def _course_number(canonical_code: str) -> int:
    m = re.search(r"(\d+)", canonical_code)
    return int(m.group(1)) if m else 999


def _stated_units(text: str) -> Optional[int]:
    """
    Extract a section's required unit count from its intro/header, e.g.
    "(15 units)", "Three units selected from", "A minimum of 33 upper division
    units". Returns None if no count is stated.
    """
    if not text:
        return None
    m = re.search(r"\((\d+)\s*units?\)", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"minimum of\s+(\d+)\s+(?:upper\s+division\s+|transferable\s+)?units", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d+)\s+units?\s+selected\s+from", text, re.I)
    if m:
        return int(m.group(1))
    words = {"one": 3, "two": 6, "three": 9, "four": 12}  # "three units" → 3, but as course-count fallback
    m = re.search(r"\b(one|two|three|four)\s+units?\s+selected", text, re.I)
    if m:
        return {"one": 1, "two": 2, "three": 3, "four": 4}[m.group(1).lower()] * 1  # literal small unit counts
    return None


def _pick_to_units(
    courses: list[str], target_units: int, units_by_code: dict[str, int]
) -> list[str]:
    """
    Pick courses from a pool to satisfy a unit target. Prefers lower-numbered
    courses (fewer prerequisites, easier to place). Falls back to course count
    when units are unknown (assume 3u each).
    """
    ordered = sorted(courses, key=_course_number)
    picked: list[str] = []
    acc = 0
    for c in ordered:
        if acc >= target_units:
            break
        picked.append(c)
        acc += units_by_code.get(c, 3)
    return picked


def parse_program(
    poid: str,
    name: str,
    session: requests.Session,
    resolver: CodeResolver,
    units_by_code: Optional[dict[str, int]] = None,
) -> Optional[dict]:
    """
    Fetch and parse one program page into a major JSON dict.
    Returns None if the page has no parseable course requirements.

    Elective detection uses the catalog's own unit budgeting: if a section
    lists more course-units than its stated unit requirement, it's a
    choose-from pool, and the stated units determine how many to pick for
    default_electives.
    """
    units_by_code = units_by_code or {}
    url = f"{BASE_URL}/preview_program.php?catoid={CATOID}&poid={poid}"
    soup = get_soup(url, session)

    lower: list[str] = []
    upper: list[str] = []
    elective_areas: dict[str, list[str]] = {}
    # (pool_key, courses, target_units) for default_electives selection
    pools: list[tuple[str, list[str], int]] = []
    unresolved: list[str] = []

    cores = soup.find_all("div", class_="acalog-core")
    for core in cores:
        header_tag = core.find(["h2", "h3"])
        header = header_tag.get_text(" ", strip=True) if header_tag else "Requirements"
        intro = " ".join(p.get_text(" ", strip=True) for p in core.find_all("p")[:2])
        hint_text = f"{header} {intro}"

        raw_codes = _course_codes_from_section(core)
        resolved, unres = resolver.resolve_list(raw_codes)
        unresolved.extend(unres)
        if not resolved:
            continue

        stated = _stated_units(hint_text)
        listed_units = sum(units_by_code.get(c, 3) for c in resolved)

        is_elective = bool(_ELECTIVE_HINTS.search(hint_text))
        # Unit-budget signal: more courses listed than the section requires.
        if stated is not None and listed_units > stated + 1:
            is_elective = True
        # Sections with no stated unit budget and many courses are almost always
        # nested choose-from pools (e.g. interdisciplinary "cluster" sub-lists).
        # Real required cores nearly always carry an explicit "(N units)" label.
        if stated is None and len(resolved) > 7:
            is_elective = True

        if is_elective:
            key = header
            n = 2
            while key in elective_areas:
                key = f"{header} ({n})"
                n += 1
            elective_areas[key] = resolved
            # Target units to pick: stated, else assume one ~3u course.
            target = stated if stated is not None else 3
            pools.append((key, resolved, target))
        else:
            for code in resolved:
                (upper if _is_upper(code) else lower).append(code)

    if not lower and not upper and not elective_areas:
        return None

    lower = list(dict.fromkeys(lower))
    upper = list(dict.fromkeys(upper))

    # Build default_electives: satisfy each pool's unit target, lower-numbered
    # courses first. Skip courses already required to avoid double-counting.
    required_set = set(lower) | set(upper)
    default_electives: list[str] = []
    chosen: set[str] = set()
    for _key, pool_courses, target in pools:
        candidates = [c for c in pool_courses if c not in required_set and c not in chosen]
        picks = _pick_to_units(candidates, target, units_by_code)
        for c in picks:
            chosen.add(c)
            default_electives.append(c)

    degree = "B.A." if name.rstrip().endswith("B.A.") else "B.S."
    gwar = [c for c in upper if c.rstrip().endswith("W")]

    return {
        "code": _slug_code(name),
        "name": name,
        "degree": degree,
        "total_units": _estimate_units(soup),
        "catalog_url": url,
        "verified": False,
        "source": f"scraped:catoid={CATOID}:poid={poid}",
        "poid": poid,
        "covered_ge_areas": [],          # not auto-detectable; conservative
        "gwar_covered_by": gwar,
        "lower_division": lower,
        "upper_required": upper,
        "elective_areas": elective_areas,
        "default_electives": default_electives,  # unit-budgeted picks from pools
        "unresolved_codes": sorted(set(unresolved)),
    }


def _slug_code(name: str) -> str:
    """Unique, opaque major code from the program name (uppercase + underscores)."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return s[:60]


def _estimate_units(soup: BeautifulSoup) -> int:
    """Best-effort total units from a 'Total Units: N' style mention."""
    text = soup.get_text(" ")
    m = re.search(r"total\s*[:\-]?\s*(\d{2,3})\s*units", text, re.I)
    if m:
        return int(m.group(1))
    return 120


# ── Main ─────────────────────────────────────────────────────────────────────

def load_units_by_code(catalog_dir: Path = CATALOG_DIR) -> dict[str, int]:
    """Map canonical course code → units from the scraped course catalog."""
    units: dict[str, int] = {}
    for path in catalog_dir.glob("*.json"):
        if path.name in ("departments.json", "prereq_groups.json", "ge_areas.json"):
            continue
        try:
            for c in json.loads(path.read_text()):
                code = clean_code(c.get("course_code", ""))
                if code:
                    units[code] = int(c.get("units", 3) or 3)
        except Exception:
            continue
    return units


def verified_markers() -> tuple[set[str], set[str]]:
    """
    Return (poids, names) of hand-verified majors so the scraper never
    overwrites or duplicates them. Names are matched case-insensitively.
    """
    poids: set[str] = set()
    names: set[str] = set()
    for path in MAJORS_DIR.glob("*.json"):
        try:
            d = json.loads(path.read_text())
        except Exception:
            continue
        if d.get("verified"):
            m = re.search(r"poid=(\d+)", d.get("catalog_url", ""))
            if m:
                poids.add(m.group(1))
            if d.get("name"):
                names.add(d["name"].strip().lower())
    return poids, names


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="Max programs to scrape")
    ap.add_argument("--poid", type=str, default=None, help="Scrape a single poid")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Seconds between requests")
    args = ap.parse_args()

    MAJORS_DIR.mkdir(parents=True, exist_ok=True)
    resolver = CodeResolver.from_catalog_dir(CATALOG_DIR)
    units_by_code = load_units_by_code(CATALOG_DIR)
    print(f"Catalog resolver: {len(resolver.canonical_codes)} canonical codes, "
          f"{len(units_by_code)} unit values.")

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; SDSU-planner/1.0)"

    skip_poids, skip_names = verified_markers()
    print(f"Verified majors (will skip): {len(skip_poids)} poids / {len(skip_names)} names\n")

    if args.poid:
        targets = [{"poid": args.poid, "name": f"poid {args.poid}"}]
    else:
        all_progs = list_programs(session)
        targets = [p for p in all_progs if is_bachelors(p["name"])]
        print(f"{len(all_progs)} total programs, {len(targets)} bachelor's degrees.")
        if args.limit:
            targets = targets[: args.limit]

    written = skipped = empty = 0
    code_collisions: dict[str, int] = {}

    for i, prog in enumerate(targets, 1):
        poid, name = prog["poid"], prog["name"]
        if poid in skip_poids or name.strip().lower() in skip_names:
            skipped += 1
            print(f"[{i}/{len(targets)}] SKIP verified  {name}")
            continue
        try:
            data = parse_program(poid, name, session, resolver, units_by_code)
        except requests.HTTPError as e:
            print(f"[{i}/{len(targets)}] ERROR {name}: {e}")
            time.sleep(args.delay)
            continue
        if data is None:
            empty += 1
            print(f"[{i}/{len(targets)}] EMPTY (no courses)  {name}")
            time.sleep(args.delay)
            continue

        # Resolve code collisions (e.g. duplicate slugs) by suffixing.
        code = data["code"]
        if code in code_collisions:
            code_collisions[code] += 1
            code = f"{code}_{code_collisions[code]}"
            data["code"] = code
        else:
            code_collisions[code] = 1

        n_lower, n_upper = len(data["lower_division"]), len(data["upper_required"])
        n_elec = sum(len(v) for v in data["elective_areas"].values())
        (MAJORS_DIR / f"{code}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        )
        written += 1
        unres = f" UNRESOLVED={data['unresolved_codes']}" if data["unresolved_codes"] else ""
        print(f"[{i}/{len(targets)}] OK {name}  ({n_lower}LD/{n_upper}UD/{n_elec}elec){unres}")
        time.sleep(args.delay)

    print(f"\nDone. written={written} skipped={skipped} empty={empty}")


if __name__ == "__main__":
    main()
