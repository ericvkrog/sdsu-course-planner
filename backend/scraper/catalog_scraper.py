"""
Scrapes catalog.sdsu.edu (2026-2027, catoid=12) and outputs one JSON file
per department to data/catalog/.

Strategy: one request per department using the built-in filter+expand URL,
which returns all courses for a department inline — no per-course page fetches.
~128 requests total instead of ~5200.

Usage:
    python catalog_scraper.py               # all departments
    python catalog_scraper.py --dept CS     # single department
    python catalog_scraper.py --delay 0.5   # custom delay in seconds
"""

import argparse
import json
import re
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://catalog.sdsu.edu"
CATOID = 12
NAVOID = 1121
DEPT_URL = (
    f"{BASE_URL}/content.php?catoid={CATOID}&navoid={NAVOID}"
    "&filter%5B27%5D={dept}&filter%5B32%5D=1&cur_cat_oid={catoid}"
    "&expand=1&search_database=Filter&filter%5Bexact_match%5D=1"
)
INDEX_URL = f"{BASE_URL}/content.php?catoid={CATOID}&navoid={NAVOID}"
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "catalog"
DEPARTMENT_INDEX_PATH = DATA_DIR / "departments.json"

DEFAULT_DELAY = 1.0

STANDING_RANK = {"freshman": 1, "sophomore": 2, "junior": 3, "senior": 4}


def get_soup(url: str, session: requests.Session) -> BeautifulSoup:
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def get_departments(session: requests.Session) -> list[dict]:
    """Read department codes/names from the filter[27] dropdown on the index page."""
    soup = get_soup(INDEX_URL, session)
    sel = soup.find("select", {"name": "filter[27]"})
    if not sel:
        raise RuntimeError("Could not find department filter dropdown")
    departments = []
    for option in sel.find_all("option"):
        code = option.get("value")
        if not code or code == "-1":
            continue
        departments.append(
            {
                "dept_code": code.strip(),
                "dept_name": option.get_text(" ", strip=True),
                "catalog_url": DEPT_URL.format(
                    dept=requests.utils.quote(code.strip()),
                    catoid=CATOID,
                ),
            }
        )
    return departments


def get_department_codes(session: requests.Session) -> list[str]:
    """Read department codes from the filter[27] dropdown on the index page."""
    return [dept["dept_code"] for dept in get_departments(session)]


def _min_standing(text: str) -> Optional[str]:
    """
    Extract minimum standing from strings like 'Sophomore; Junior; or Senior standing.'
    Returns the lowest-rank level mentioned.
    """
    block_re = re.compile(
        r"((?:freshman|sophomore|junior|senior)"
        r"(?:[\s;,]+(?:or\s+)?(?:freshman|sophomore|junior|senior))*)"
        r"\s+standing",
        re.IGNORECASE,
    )
    m = block_re.search(text)
    if not m:
        return None
    levels = re.findall(r"\b(freshman|sophomore|junior|senior)\b", m.group(1), re.IGNORECASE)
    return min(levels, key=lambda l: STANDING_RANK.get(l.lower(), 99)).lower() if levels else None


def _normalize_code(raw: str) -> str:
    """
    Collapse non-breaking spaces and runs of whitespace to a single space,
    then strip. Catalog HTML sometimes uses \xa0 between dept and number,
    which prevents naive dedup.
    """
    return re.sub(r"\s+", " ", raw.replace("\xa0", " ")).strip()


def parse_prereqs(li: Tag, course_code: Optional[str] = None) -> list[dict]:
    """
    Extract prerequisites from the inline <li> course block.
    Linked course codes → required prereqs; standing text → min_standing.

    Cleanup applied:
      - Whitespace-normalize captured codes so "CS\xa0150" and "CS 150" dedupe.
      - Drop self-lab artifacts (course X listing X+'L' as a prereq — always
        a scraper-misread of co-requisite wording, never a real prerequisite).
      - Dedupe by (code, standing) at the final list level.
    """
    prereqs: list[dict] = []

    prereq_strong = next(
        (s for s in li.find_all("strong") if re.search(r"prerequisite", s.get_text(), re.I)),
        None,
    )
    if not prereq_strong:
        return prereqs

    prereq_text = ""
    prereq_codes: list[str] = []
    # Ordered token stream of ("code", value) / ("text", value) so we can read
    # the connective words BETWEEN consecutive prereq codes (and/or) without
    # picking up the trailing course description that follows the last code.
    tokens: list[tuple[str, str]] = []

    for sib in prereq_strong.next_siblings:
        if isinstance(sib, Tag) and sib.name == "strong" and sib.get_text(strip=True):
            break
        if isinstance(sib, Tag) and sib.name == "a" and "preview_course" in sib.get("href", ""):
            # On the inline page link text is the bare code e.g. "ACCTG 202"
            # aria-label is "View course details for ACCTG 202" — also works
            aria = sib.get("aria-label", "")
            code_match = re.search(r"([A-Z]{1,10}(?:\s[A-Z])?\s+\d{3}[A-Z]?)", aria or sib.get_text(strip=True))
            if code_match:
                code = _normalize_code(code_match.group(1))
                prereq_codes.append(code)
                tokens.append(("code", code))
        elif hasattr(sib, "get_text"):
            text = sib.get_text(" ")
            prereq_text += text + " "
            tokens.append(("text", text))
        else:
            prereq_text += str(sib) + " "
            tokens.append(("text", str(sib)))

    standing = _min_standing(prereq_text)
    # Are the prereqs OR alternatives? True when an "or" connective appears in
    # the text BETWEEN the first and last prereq code. Rows then share a group
    # so the planner treats any one as sufficient. ("(A and B) or C" collapses
    # to a single OR group — lenient, but always yields a buildable plan.)
    is_or_group = _has_or_connective(tokens)

    self_lab = (course_code + "L") if course_code else None

    seen: set[tuple[str, Optional[str]]] = set()
    group_id = 1 if is_or_group else None
    for code in prereq_codes:
        if code == self_lab:
            continue
        key = (code, standing)
        if key in seen:
            continue
        seen.add(key)
        prereqs.append({
            "prereq_code": code,
            "prereq_type": "required",
            "min_standing": standing,
            "prereq_group": group_id,
        })

    if not prereqs and standing:
        prereqs.append({
            "prereq_code": None,
            "prereq_type": "required",
            "min_standing": standing,
            "prereq_group": None,
        })

    return prereqs


def _has_or_connective(tokens: list[tuple[str, str]]) -> bool:
    """
    True if an 'or' joins prerequisite course codes.

    Only the text tokens that fall BETWEEN the first and last "code" token are
    inspected — text after the last code is the course description and must not
    be considered (it routinely contains the word "or" in prose).
    """
    code_positions = [i for i, (kind, _) in enumerate(tokens) if kind == "code"]
    if len(code_positions) < 2:
        return False
    first, last = code_positions[0], code_positions[-1]
    connective = " ".join(
        val for kind, val in tokens[first + 1 : last] if kind == "text"
    )
    return bool(re.search(r"\bor\b", connective, re.I))


def parse_offered(li: Tag) -> tuple[bool, bool]:
    text = li.get_text(" ", strip=True)
    m = re.search(r"Typically Offered:\s*([^\n<]+)", text, re.IGNORECASE)
    if not m:
        return True, True
    offered = m.group(1).strip().lower()
    fall = "fall" in offered
    spring = "spring" in offered
    return (fall, spring) if (fall or spring) else (True, True)


def parse_units(text: str) -> Optional[int]:
    """
    Parse fixed or variable units from catalog text.
    The schema stores one integer, so variable-unit courses use the upper bound.
    """
    units_m = re.search(
        r"Units?:\s*(?P<low>\d+(?:\.\d+)?)(?:\s*(?:-|to)\s*(?P<high>\d+(?:\.\d+)?))?",
        text,
        re.IGNORECASE,
    )
    if not units_m:
        return None
    value = units_m.group("high") or units_m.group("low")
    return int(float(value))


def parse_course_block(li: Tag) -> Optional[dict]:
    """Parse a single inline <li> course block into a course dict."""
    h3 = li.find("h3")
    if not h3:
        return None

    # Title: "ACCTG 201 - Financial Accounting Fundamentals" (may have \xa0)
    title_text = h3.get_text(strip=True)
    m = re.match(r"^(?P<code>[A-Z]{1,10}(?:\s[A-Z])?\s+\d{3}[A-Z]?)\s*[\s ]-[\s ]\s*(?P<title>.+)$", title_text)
    if not m:
        return None

    course_code = m.group("code").strip()
    title = m.group("title").strip()
    department = course_code.split()[0]

    # Units
    text = li.get_text(" ", strip=True)
    units = parse_units(text)
    if units is None:
        return None

    # Grading method (code prefix only)
    grading = None
    for strong in li.find_all("strong"):
        if "grading method" in strong.get_text(strip=True).lower():
            sib = strong.next_sibling
            while sib:
                t = str(sib).strip() if not hasattr(sib, "get_text") else sib.get_text(strip=True)
                if t and t not in ("<br/>", "<br>"):
                    grading = t.split(":")[0].strip()[:10]
                    break
                sib = sib.next_sibling
            break

    offered_fall, offered_spring = parse_offered(li)
    prereqs = parse_prereqs(li, course_code=course_code)

    # Max credits
    max_credits = None
    max_m = re.search(r"maximum of (\d+) units", text, re.IGNORECASE)
    if max_m:
        max_credits = int(max_m.group(1))
    else:
        for strong in li.find_all("strong"):
            if "maximum credits" in strong.get_text(strip=True).lower():
                sib = strong.next_sibling
                while sib:
                    t = str(sib).strip() if not hasattr(sib, "get_text") else sib.get_text(strip=True)
                    if t and t not in ("<br/>", "<br>"):
                        try:
                            max_credits = int(t)
                        except ValueError:
                            pass
                        break
                    sib = sib.next_sibling
                break

    # Notes (Note: field)
    note = None
    for strong in li.find_all("strong"):
        if strong.get_text(strip=True).lower() in ("note:", "note"):
            sib = strong.next_sibling
            while sib:
                t = str(sib).strip() if not hasattr(sib, "get_text") else sib.get_text(strip=True)
                if t and t not in ("<br/>", "<br>"):
                    note = t
                    break
                sib = sib.next_sibling
            break

    # Description: text after the empty <strong></strong> marker
    description = None
    for strong in li.find_all("strong"):
        if strong.get_text(strip=True) == "":
            for sib in strong.next_siblings:
                if isinstance(sib, str):
                    t = sib.strip()
                    if t:
                        description = t
                        break
                elif hasattr(sib, "get_text") and sib.name not in ("br", "hr", "strong"):
                    t = sib.get_text(strip=True)
                    if t:
                        description = t
                        break
            if description:
                break

    return {
        "course_code": course_code,
        "title": title,
        "units": units,
        "department": department,
        "description": description,
        "grading_method": grading,
        "offered_fall": offered_fall,
        "offered_spring": offered_spring,
        "max_credits": max_credits,
        "notes": note,
        "prerequisites": prereqs,
    }


def scrape_department(dept_code: str, session: requests.Session, delay: float) -> list[dict]:
    url = DEPT_URL.format(dept=requests.utils.quote(dept_code), catoid=CATOID)
    time.sleep(delay)
    try:
        soup = get_soup(url, session)
    except requests.RequestException as e:
        print(f"  [WARN] {dept_code}: {e}")
        return []

    course_lis = [li for li in soup.find_all("li") if li.find("h3")]
    courses = []
    for li in course_lis:
        c = parse_course_block(li)
        if c:
            courses.append(c)
    return courses


def save_department(dept_code: str, courses: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    safe = dept_code.lower().replace(" ", "_")
    out_path = DATA_DIR / f"{safe}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(courses, f, indent=2, ensure_ascii=False)
    print(f"  Saved {dept_code}: {len(courses)} courses → {out_path.name}")


def save_department_index(departments: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DEPARTMENT_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(departments, f, indent=2, ensure_ascii=False)
    print(f"Saved department index: {len(departments)} departments → {DEPARTMENT_INDEX_PATH.name}")


def validation_summary(courses: list[dict]) -> dict:
    codes = [course["course_code"] for course in courses]
    duplicate_codes = sorted({code for code in codes if codes.count(code) > 1})
    prereq_refs = {
        prereq["prereq_code"]
        for course in courses
        for prereq in course.get("prerequisites", [])
        if prereq.get("prereq_code")
    }
    return {
        "courses": len(courses),
        "duplicates": duplicate_codes,
        "prereq_refs": len(prereq_refs),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="SDSU catalog scraper")
    parser.add_argument("--dept", help="Scrape only this department (e.g. CS)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    args = parser.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = "sdsu-course-planner-scraper/1.0 (academic project)"

    print("Fetching department list...")
    departments = get_departments(session)
    all_depts = [dept["dept_code"] for dept in departments]
    print(f"Found {len(all_depts)} departments")
    save_department_index(departments)

    targets = [args.dept] if args.dept else all_depts

    total_courses = 0
    duplicate_departments = []
    for i, dept in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {dept}")
        courses = scrape_department(dept, session, args.delay)
        if courses:
            save_department(dept, courses)
            total_courses += len(courses)
            summary = validation_summary(courses)
            if summary["duplicates"]:
                duplicate_departments.append(dept)
                print(f"  [WARN] Duplicate course codes: {', '.join(summary['duplicates'])}")
            print(f"  Parsed {summary['prereq_refs']} unique prerequisite references")
        else:
            print(f"  (no courses)")

    print(f"\nDone. {total_courses} courses across {len(targets)} departments.")
    if duplicate_departments:
        print(f"Review duplicate course codes in: {', '.join(duplicate_departments)}")


if __name__ == "__main__":
    main()
