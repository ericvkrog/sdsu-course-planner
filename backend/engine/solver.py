"""
Deterministic semester planner.

Receives a required course set (from major_requirements.py or the API caller),
orders it using the prerequisite DAG, and packs courses into future semesters
while respecting:
  - prerequisite ordering
  - fall / spring availability flags
  - per-semester unit cap
  - standing requirements (freshman/sophomore/junior/senior)
  - already-completed courses (skipped, units counted toward standing)

Returns a PlannerResult with a partial plan + conflict list instead of raising.
Callers should surface conflicts to users rather than treating them as crashes.
"""

import heapq
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.engine.graph import break_cycles, build_graph


# Minimum cumulative units needed to reach each standing level.
STANDING_UNITS: dict[str, int] = {
    "freshman": 0,
    "sophomore": 30,
    "junior": 60,
    "senior": 90,
}

# Max units per semester Pass A will hold back for GE/GR/FREE placeholders, so
# electives are spread across semesters rather than clustered at the end. ~6 units
# ≈ two GE courses of headroom; the actual reserve is the smaller of this and an
# even share of the placeholders still to place.
_MAX_PLACEHOLDER_RESERVE = 6


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class SemesterPlan:
    semester: str           # "Fall" or "Spring"
    year: int
    courses: list[dict[str, Any]] = field(default_factory=list)
    total_units: int = 0


@dataclass
class PlannerResult:
    semesters: list[SemesterPlan]
    conflicts: list[dict[str, str]]


# ── Public API ─────────────────────────────────────────────────────────────

def plan_courses(
    required_course_codes: list[str],
    completed_course_codes: list[str],
    courses: list[dict[str, Any]],
    prerequisites: list[dict[str, Any]],
    max_units_per_semester: int = 15,
    start_semester: str = "Fall",
    start_year: int = 2025,
    semester_count: int = 8,
) -> PlannerResult:
    """
    Build a semester plan for a known set of required courses.

    Args:
        required_course_codes: Every course the student must complete.
        completed_course_codes: Courses already finished (counted for standing,
            not re-placed in the plan).
        courses: Full course records from the DB for every code in either list.
        prerequisites: Prerequisite rows from the DB (course_code, prereq_code,
            prereq_type, min_standing) for the relevant courses.
        max_units_per_semester: Hard unit cap per semester (default 17).
        start_semester: "Fall" or "Spring".
        start_year: Calendar year of the first semester.
        semester_count: Number of semesters to allocate (default 8 = 4 years).

    Returns:
        PlannerResult with semesters (may be partial) and a list of conflicts.
        Conflicts describe courses that could not be placed and why.
    """
    courses_by_code: dict[str, dict] = {c["course_code"]: c for c in courses}
    completed: set[str] = set(completed_course_codes)

    # Remove duplicates from required while preserving order, drop completed.
    required: list[str] = [
        code for code in dict.fromkeys(required_course_codes)
        if code not in completed
    ]
    required_set: set[str] = set(required)

    # Build the prereq graph from rows that involve at least one required course.
    # This captures both "required course has prereq" and "required course is a
    # prereq of another required course" edges.
    graph_rows = [
        row for row in prerequisites
        if row.get("course_code") in required_set
        or row.get("prereq_code") in required_set
    ]
    graph = build_graph(graph_rows)

    # Ensure every required course is a node even if it has no edges.
    graph.add_nodes_from(required)

    # Break cycles (e.g. co-requisite lab/lecture pairs scraped as mutual prereqs).
    # Track removed pairs so placement constraints can skip them too.
    removed_edges: set[tuple[str, str]] = set(break_cycles(graph))

    # For lecture/lab pairs both edges are removed as a mutual cycle. Restore the
    # lecture → lab direction for TOPOLOGICAL ORDER only — so the lecture is emitted
    # (and placed) before the lab. The lab is then co-placed in the SAME semester
    # (it is a co-requisite, not a strict-earlier prereq — see _build_prereq_groups
    # and the Pass A co-req handling).
    for code in required:
        if code.endswith("L"):
            base = code[:-1].rstrip()
            if (
                base in required_set
                and (base, code) in removed_edges
                and (code, base) in removed_edges
            ):
                graph.add_edge(base, code)
                removed_edges.discard((base, code))

    # Priority-based topological sort (Kahn's algorithm).
    #
    # Sort key: (standing_rank, original_required_index)
    #   - standing_rank 0 = no/freshman standing (lower-div, GE, rank-0 electives)
    #   - standing_rank 2 = junior-standing courses (upper-div)
    #   - original_required_index breaks ties within the same rank
    #
    # This ensures lower-division and GE courses are placed BEFORE upper-division
    # courses that have standing requirements, so enough units accumulate before
    # the solver tries to schedule junior-standing courses. Topological correctness
    # is still guaranteed by Kahn's algorithm — a course only enters the heap
    # once all its graph predecessors have been emitted.
    _srank: dict[Optional[str], int] = {
        None: 0, "freshman": 0, "sophomore": 1, "junior": 2, "senior": 3
    }

    def _course_srank(code: str) -> int:
        rows = [r for r in prerequisites if r.get("course_code") == code]
        lvl = _effective_min_standing(code, rows)
        return _srank.get(lvl, 0)

    priority_idx = {code: i for i, code in enumerate(required)}
    in_deg: dict[str, int] = {code: 0 for code in required}
    for code in required:
        if code in graph:
            for pred in graph.predecessors(code):
                if pred in required_set:
                    in_deg[code] += 1

    def _heap_key(code: str) -> tuple[int, int]:
        return (_course_srank(code), priority_idx.get(code, len(required)))

    heap: list[tuple[tuple[int, int], str]] = [
        (_heap_key(c), c) for c, d in in_deg.items() if d == 0
    ]
    heapq.heapify(heap)

    ordered: list[str] = []
    while heap:
        _, code = heapq.heappop(heap)
        ordered.append(code)
        if code in graph:
            for succ in graph.successors(code):
                if succ in required_set and succ in in_deg:
                    in_deg[succ] -= 1
                    if in_deg[succ] == 0:
                        heapq.heappush(heap, (_heap_key(succ), succ))

    # Courses not reached by Kahn's (shouldn't happen after cycle breaking).
    emitted = set(ordered)
    ordered.extend(c for c in required if c not in emitted)

    # Split real courses from GE/GR/FREE placeholders. Real courses claim
    # semester slots FIRST (two-pass placement below) so a core major course
    # like MATH 150 is never crowded out of an early semester by GE placeholders.
    real_ordered: list[str] = [c for c in ordered if not _is_placeholder(c)]
    placeholder_queue: list[str] = [c for c in ordered if _is_placeholder(c)]

    # Allocate semester slots.
    slots = _semester_sequence(start_semester, start_year, semester_count)
    semesters: list[SemesterPlan] = [SemesterPlan(semester=s, year=y) for s, y in slots]

    # Units completed before the plan starts (affects standing calculations).
    completed_units: int = sum(
        courses_by_code.get(code, {}).get("units", 0) for code in completed
    )

    # Precompute prereq groups + strictest standing per real course (reused across
    # the per-semester passes). Each prereq_groups element is a set of OR
    # alternatives — satisfying ANY ONE member satisfies that group; all groups
    # must be satisfied (AND). Rows with prereq_group=None are singleton groups.
    prereq_groups_by_code: dict[str, list[set[str]]] = {}
    min_standing_by_code: dict[str, Optional[str]] = {}
    for course_code in real_ordered:
        prereq_rows = [
            row for row in prerequisites
            if row.get("course_code") == course_code
        ]
        prereq_groups_by_code[course_code] = _build_prereq_groups(
            prereq_rows, required_set, completed, removed_edges, course_code
        )
        min_standing_by_code[course_code] = _effective_min_standing(course_code, prereq_rows)

    # Placeholders carry no prereqs, but some (GE UD2/UD3/UD4 — upper-division GE)
    # require junior standing. Pass B must honor that, so precompute it here.
    for code in placeholder_queue:
        rows = [row for row in prerequisites if row.get("course_code") == code]
        min_standing_by_code[code] = _highest_standing(row.get("min_standing") for row in rows)

    # Flattened prereq members per course (co-req labs already excluded by
    # _build_prereq_groups). Used to forbid a course sharing a semester with any
    # of its real prerequisites, even OR-alternatives that are otherwise satisfied
    # by an earlier course (e.g. MATH 245 must not sit with MATH 151 just because
    # MATH 150 already satisfies its "Calc I/II/124" group).
    prereq_members_by_code: dict[str, set[str]] = {
        code: {p for grp in groups for p in grp}
        for code, groups in prereq_groups_by_code.items()
    }

    # Lab → its base lecture (both required). A lab is a co-requisite: it must land
    # in the SAME semester as its lecture, and is allowed a little unit-cap headroom
    # so a 1-unit lab never gets bumped off its lecture's semester by the cap.
    lecture_of_lab: dict[str, str] = {}
    for code in real_ordered:
        if code.endswith("L"):
            base = code[:-1].rstrip()
            if base in required_set:
                lecture_of_lab[code] = base

    # Track which semester index (0-based) each course was placed into.
    placed_index: dict[str, int] = {}
    conflicts: list[dict[str, str]] = []
    unplaced_real: list[str] = list(real_ordered)

    # Two-pass placement, semester by semester:
    #   Pass A — place eligible real courses (topo order), but only up to a REAL
    #            cap that reserves room for this semester's fair share of GE/GR/FREE
    #            placeholders, so electives are sprinkled THROUGH the plan instead of
    #            clustering at the end (a 15-unit semester reads "3 major + 2 GE",
    #            not "5 major").
    #   Pass B — fill the reserved headroom with placeholders.
    # Placeholders count toward units, so early-semester accumulation stays intact
    # and junior-standing courses still see >=60 units before them.
    remaining_ph_units = sum(
        courses_by_code.get(c, {}).get("units", 0) for c in placeholder_queue
    )
    for idx, semester in enumerate(semesters):
        units_before = completed_units + sum(s.total_units for s in semesters[:idx])

        # Reserve an even share of the remaining placeholder units for this semester
        # (capped so majors are never starved). real_cap is what Pass A may use.
        sems_left = len(semesters) - idx
        reserve = 0
        if remaining_ph_units > 0 and sems_left > 0:
            reserve = min(-(-remaining_ph_units // sems_left), _MAX_PLACEHOLDER_RESERVE)
        real_cap = max(0, max_units_per_semester - reserve)

        def _place_reals(cap: int) -> None:
            """Place every eligible real course into this semester up to `cap`."""
            for course_code in list(unplaced_real):
                if course_code in placed_index:      # co-requisite partner already placed
                    unplaced_real.remove(course_code)
                    continue
                course = courses_by_code.get(course_code)
                if not course:                       # missing data — reported after the loop
                    continue
                if not _offered_in(course, semester.semester):
                    continue

                # A lab co-requisite must sit in its lecture's semester: only placeable
                # once the lecture is placed, and never strictly before it. Topo order
                # emits the lecture first, so this lands the lab in the SAME semester.
                lecture = lecture_of_lab.get(course_code)
                if lecture is not None and placed_index.get(lecture) is None:
                    continue
                is_coreq_lab_here = lecture is not None and placed_index.get(lecture) == idx

                # Unit cap. Co-req labs joining their lecture this semester get headroom
                # equal to their own (small) unit count, so the cap can't split the pair.
                effective_cap = cap + (course["units"] if is_coreq_lab_here else 0)
                if semester.total_units + course["units"] > effective_cap:
                    continue

                min_standing = min_standing_by_code[course_code]
                if min_standing and units_before < STANDING_UNITS[min_standing]:
                    continue
                if not _groups_satisfied(
                    prereq_groups_by_code[course_code], completed, placed_index, idx
                ):
                    continue
                # No real prerequisite may share this course's semester (OR-alternatives
                # included). Co-req labs are already excluded from prereq_members_by_code.
                if any(placed_index.get(p) == idx for p in prereq_members_by_code[course_code]):
                    continue
                semester.courses.append(course)
                semester.total_units += course["units"]
                placed_index[course_code] = idx
                unplaced_real.remove(course_code)

        # ── Pass A: real courses, holding back the reserved placeholder room ──
        _place_reals(real_cap)

        # ── Pass B: top up headroom with placeholders ──
        # Placeholders have no prereqs, but upper-division GE (GE UD*) requires
        # junior standing — honor it so a UD placeholder never lands before 60 units.
        i = 0
        while i < len(placeholder_queue):
            code = placeholder_queue[i]
            course = courses_by_code.get(code)
            ph_standing = min_standing_by_code.get(code)
            if (
                course is None
                or not _offered_in(course, semester.semester)
                or semester.total_units + course["units"] > max_units_per_semester
                or (ph_standing and units_before < STANDING_UNITS[ph_standing])
            ):
                i += 1
                continue
            semester.courses.append(course)
            semester.total_units += course["units"]
            placed_index[code] = idx
            remaining_ph_units -= course["units"]
            placeholder_queue.pop(i)   # next placeholder shifts into position i

        # ── Pass C: reclaim any reserved room placeholders couldn't fill ──
        # If Pass B left headroom empty (no eligible placeholder — e.g. they ran out,
        # or only junior-gated GE UD remains early), pack it with real courses up to
        # the full cap. This keeps semesters full so units accumulate at the normal
        # rate (junior-standing courses still reach 60 units on time); the reservation
        # only delays a real course when a placeholder actually takes its seat.
        if semester.total_units < max_units_per_semester:
            _place_reals(max_units_per_semester)

    # ── Relaxation pass: standing is a SOFT gate ──
    # After the main passes, anything still unplaced is blocked only by STANDING:
    # cumulative units never reached the course's threshold (a scraped major missing
    # its lower division can stall a couple of units short of 60, so every remaining
    # junior course — and GE UD — waits forever for units that can't arrive). Place
    # these best-effort, IGNORING standing but still respecting prereq order, offering,
    # the lab co-req, the no-same-semester-prereq rule, AND the unit cap. Because the
    # cap is respected, courses land in the earliest semester that still has ROOM —
    # i.e. the empty late semesters where the most units have accumulated, minimizing
    # the standing shortfall. Well-formed majors (every verified one) reach 60 units
    # normally and never enter this pass, so it can't mask a real ordering bug there.
    def _relaxed_place(course_code: str, is_real: bool) -> bool:
        course = courses_by_code.get(course_code)
        if not course:
            return False
        for idx, semester in enumerate(semesters):
            if not _offered_in(course, semester.semester):
                continue
            if semester.total_units + course["units"] > max_units_per_semester:
                continue
            if is_real:
                lecture = lecture_of_lab.get(course_code)
                if lecture is not None and placed_index.get(lecture) is None:
                    continue
                if not _groups_satisfied(
                    prereq_groups_by_code[course_code], completed, placed_index, idx
                ):
                    continue
                if any(placed_index.get(p) == idx for p in prereq_members_by_code[course_code]):
                    continue
            semester.courses.append(course)
            semester.total_units += course["units"]
            placed_index[course_code] = idx
            return True
        return False

    # Reals first (topo order, so a relaxed-placed prereq unblocks its dependents),
    # then leftover placeholders (GE UD).
    for course_code in list(real_ordered):
        if course_code in unplaced_real and course_code not in placed_index:
            if _relaxed_place(course_code, is_real=True):
                unplaced_real.remove(course_code)
    for code in list(placeholder_queue):
        if _relaxed_place(code, is_real=False):
            placeholder_queue.remove(code)

    # Any real course still unplaced → conflict with a diagnostic reason.
    for course_code in unplaced_real:
        course = courses_by_code.get(course_code)
        if not course:
            conflicts.append({
                "course_code": course_code,
                "reason": "Course data not found — check that the course code "
                          "exists in the database.",
            })
            continue
        all_prereqs = {p for grp in prereq_groups_by_code[course_code] for p in grp}
        unplaced_prereqs = [
            p for p in all_prereqs
            if p not in completed and p not in placed_index
        ]
        if unplaced_prereqs:
            reason = (
                f"Prerequisite(s) could not be placed before this course: "
                f"{', '.join(sorted(unplaced_prereqs))}"
            )
        else:
            reason = (
                "No semester satisfies all of: offering type, unit cap, "
                "and standing requirement."
            )
        conflicts.append({"course_code": course_code, "reason": reason})

    # Any placeholder still unplaced → conflict (e.g. unit cap too low).
    for code in placeholder_queue:
        conflicts.append({
            "course_code": code,
            "reason": "No semester satisfies all of: offering type, unit cap, "
                      "and standing requirement.",
        })

    return PlannerResult(semesters=semesters, conflicts=conflicts)


# ── Private helpers ────────────────────────────────────────────────────────

def _semester_sequence(
    start_semester: str,
    start_year: int,
    count: int,
) -> list[tuple[str, int]]:
    """Generate alternating Fall/Spring slots starting from the given term."""
    sem = start_semester.title()
    if sem not in {"Fall", "Spring"}:
        raise ValueError("start_semester must be 'Fall' or 'Spring'")
    year = start_year
    slots: list[tuple[str, int]] = []
    for _ in range(count):
        slots.append((sem, year))
        if sem == "Fall":
            sem, year = "Spring", year + 1
        else:
            sem = "Fall"
    return slots


def _offered_in(course: dict[str, Any], semester: str) -> bool:
    """Return True if the course is offered in the given semester type."""
    if semester == "Fall":
        return bool(course.get("offered_fall", True))
    if semester == "Spring":
        return bool(course.get("offered_spring", True))
    return False


def _highest_standing(levels) -> Optional[str]:
    """Return the most restrictive standing level from an iterable of strings."""
    valid = [lvl for lvl in levels if lvl and lvl in STANDING_UNITS]
    if not valid:
        return None
    return max(valid, key=lambda lvl: STANDING_UNITS[lvl])


def _build_prereq_groups(
    prereq_rows: list[dict[str, Any]],
    required_set: set[str],
    completed: set[str],
    removed_edges: set[tuple[str, str]],
    course_code: str,
) -> list[set[str]]:
    """
    Build OR-grouped prerequisite sets from prerequisite table rows.

    - Only hard-required prereqs that are part of the plan (in required_set
      or already completed) are included. External prereqs are skipped.
    - Rows with a `prereq_group` value are OR alternatives — any one member
      of the group satisfies it. Rows without a group are standalone AND reqs.
    - Edges removed during cycle-breaking are excluded.

    Returns a list of sets. Satisfying at least one member of every set
    satisfies all prerequisites (AND across groups, OR within each group).
    """
    from collections import defaultdict
    standalone: list[set[str]] = []
    grouped: dict[Any, set[str]] = defaultdict(set)

    # A lab's own lecture is a CO-REQUISITE (taken in the SAME semester), not a
    # strict-earlier prerequisite. Drop it here so it never forces the lab into a
    # later semester (and, in an OR group, so the remaining real prereqs still apply).
    base_lecture = course_code[:-1].rstrip() if course_code.endswith("L") else None

    for row in prereq_rows:
        prereq_code = row.get("prereq_code")
        if not prereq_code:
            continue
        if row.get("prereq_type") != "required":
            continue
        if prereq_code not in required_set and prereq_code not in completed:
            continue
        if (prereq_code, course_code) in removed_edges:
            continue
        if base_lecture is not None and prereq_code == base_lecture:
            continue

        group_id = row.get("prereq_group")
        if group_id is None:
            standalone.append({prereq_code})
        else:
            grouped[group_id].add(prereq_code)

    return standalone + [s for s in grouped.values()]


def _is_placeholder(code: str) -> bool:
    """True for GE/GR/FREE filler slots (no prereqs, no standing, fill headroom)."""
    return code.startswith(("GE ", "GR ", "FREE "))


def _course_number(code: str) -> int:
    """Leading course number (e.g. 'CS 370' → 370, 'M E 202' → 202). 0 if none."""
    import re
    m = re.search(r"(\d+)", code)
    return int(m.group(1)) if m else 0


def _effective_min_standing(code: str, prereq_rows: list[dict[str, Any]]) -> Optional[str]:
    """Strictest standing a course requires.

    Combines any explicit ``min_standing`` from the prereq rows with SDSU's
    upper-division rule: a real course numbered 300 or higher requires at least
    JUNIOR standing (60+ units completed before it). Placeholders are exempt.
    """
    lvl = _highest_standing(row.get("min_standing") for row in prereq_rows)
    if not _is_placeholder(code) and _course_number(code) >= 300:
        lvl = _highest_standing([lvl, "junior"])
    return lvl


def _groups_satisfied(
    prereq_groups: list[set[str]],
    completed: set[str],
    placed_index: dict[str, int],
    target_idx: int,
) -> bool:
    """
    Return True iff every prereq group has at least one member satisfied
    before `target_idx`.

    A prereq is satisfied if it is in `completed` or placed in a semester
    strictly before `target_idx`. Within each group, ANY ONE satisfied member
    is enough (OR). All groups must be satisfied (AND).
    """
    for group in prereq_groups:
        group_ok = False
        for prereq in group:
            if prereq in completed:
                group_ok = True
                break
            if placed_index.get(prereq, target_idx) < target_idx:
                group_ok = True
                break
        if not group_ok:
            return False
    return True
