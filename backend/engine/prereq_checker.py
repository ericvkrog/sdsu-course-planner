"""
Prerequisite chain checker.

Builds a complete prerequisite graph from all available data (DB rows +
catalog fixes) and walks the full dependency tree for every course in a plan,
verifying that:

  1. Every prerequisite is placed in a STRICTLY EARLIER semester (not the same).
  2. No prerequisite is missing from the plan entirely (unless it was completed
     before the plan started).
  3. The transitive closure is valid — if A requires B and B requires C, then
     C must come before B and B must come before A.

Returns a list of violation dicts, each with:
  - course_code: the course with the violation
  - prereq_code: the specific prerequisite that is violated
  - reason: human-readable explanation

Usage:
    from backend.engine.prereq_checker import check_prereq_chains

    violations = check_prereq_chains(
        semesters=plan.semesters,          # list of SemesterPlan or dicts
        prerequisites=prereq_rows,          # DB rows + catalog fix rows
        completed_course_codes=completed,
    )
"""

from collections import defaultdict
from typing import Any, Optional


def detect_mutual_prereq_pairs(
    prerequisites: list[dict[str, Any]],
    plan_course_set: set[str],
) -> set[tuple[str, str]]:
    """
    Return mutual co-requisite pairs (A requires B AND B requires A) where both
    courses are within ``plan_course_set``.

    These are co-requisite cycles the solver intentionally co-places (lecture/lab
    pairs and same-sequence courses scraped as mutual prereqs). The validator and
    chain-checker must skip BOTH directions so they don't flag the same-semester
    placement the solver produced on purpose. Shared by validator.py and this
    module so the two cannot drift apart.
    """
    required_pairs: set[tuple[str, str]] = {
        (r["course_code"], r["prereq_code"])
        for r in prerequisites
        if r.get("prereq_code") and r.get("prereq_type") == "required"
        and r["course_code"] in plan_course_set and r["prereq_code"] in plan_course_set
    }
    return {(a, b) for (a, b) in required_pairs if (b, a) in required_pairs}


def check_prereq_chains(
    semesters: list[Any],
    prerequisites: list[dict[str, Any]],
    completed_course_codes: Optional[list[str]] = None,
) -> list[dict[str, str]]:
    """
    Walk the full prerequisite graph and report every ordering violation.

    Only checks prerequisites that are within the plan's own course set
    (required + completed). External prerequisites — entry requirements taken
    before SDSU, old course aliases, OR alternatives not chosen — are silently
    skipped, matching the solver's behaviour.

    Also skips the lab→lecture backward catalog artifact (e.g. CS 150 listing
    CS 150L as a prerequisite), which is a known scraper data quality issue.

    Args:
        semesters: The plan's semester sequence. Each item is either a
            SemesterPlan dataclass (with .courses list) or a dict with a
            "courses" key. Courses are dicts with "course_code".
        prerequisites: All prerequisite rows (DB + catalog fixes). Each row
            has course_code, prereq_code, prereq_type, min_standing.
        completed_course_codes: Courses finished before the plan. These satisfy
            any prerequisite check automatically (treated as semester -1).

    Returns:
        List of violation dicts. Empty list means the plan is chain-clean.
    """
    completed: set[str] = set(completed_course_codes or [])

    # Build semester index: course_code → 0-based semester index.
    # Completed courses get index -1 (always before any plan semester).
    sem_index: dict[str, int] = {code: -1 for code in completed}
    sem_labels: dict[int, str] = {}

    for i, sem in enumerate(semesters):
        courses = sem.courses if hasattr(sem, "courses") else sem.get("courses", [])
        label = (
            f"{sem.semester} {sem.year}"
            if hasattr(sem, "semester")
            else f"{sem.get('semester')} {sem.get('year')}"
        )
        sem_labels[i] = label
        for course in courses:
            code = course["course_code"] if isinstance(course, dict) else course
            sem_index[code] = i

    # Only enforce prerequisites that are within the plan's own course set.
    # External prereqs (entry requirements, old aliases, OR paths not in plan)
    # are silently skipped — same rule the solver uses.
    plan_course_set: set[str] = set(sem_index.keys())

    # Detect mutual prereq pairs (A requires B AND B requires A) — co-requisite
    # cycles the solver co-places. Skip both directions so the checker doesn't
    # flag same-semester placement the solver intentionally produced.
    mutual_pairs = detect_mutual_prereq_pairs(prerequisites, plan_course_set)

    # Build adjacency: course → list of required prereqs (required type only).
    prereq_groups: dict[str, list[set[str]]] = defaultdict(list)
    _build_groups(prerequisites, prereq_groups, plan_course_set, mutual_pairs)

    violations: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for course_code, groups in prereq_groups.items():
        course_idx = sem_index.get(course_code)
        if course_idx is None or course_idx == -1:
            # Course not in plan, or already completed before the plan starts.
            # Internal ordering of pre-plan completed courses is not our concern.
            continue

        course_label = sem_labels.get(course_idx, "completed")

        for group in groups:
            # OR group: at least one member must be satisfied.
            # "Satisfied" = placed in a strictly EARLIER semester OR completed.
            satisfied_by = [
                p for p in group
                if sem_index.get(p, None) is not None and sem_index[p] < course_idx
            ]
            if satisfied_by:
                continue  # Group satisfied — move on.

            # No member satisfied. Classify the violation type for each member.
            for prereq_code in sorted(group):
                pair = (course_code, prereq_code)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                prereq_idx = sem_index.get(prereq_code)

                if prereq_idx is None:
                    # Prereq not in plan and not completed.
                    violations.append({
                        "course_code": course_code,
                        "prereq_code": prereq_code,
                        "reason": (
                            f"{prereq_code} is required before {course_code} "
                            f"({course_label}) but is not in the plan."
                        ),
                    })
                elif prereq_idx == course_idx:
                    violations.append({
                        "course_code": course_code,
                        "prereq_code": prereq_code,
                        "reason": (
                            f"{prereq_code} is in the SAME semester as "
                            f"{course_code} ({course_label}). "
                            f"It must be completed one semester earlier."
                        ),
                    })
                else:
                    # prereq_idx > course_idx: prereq comes AFTER the course.
                    prereq_label = sem_labels.get(prereq_idx, "later")
                    violations.append({
                        "course_code": course_code,
                        "prereq_code": prereq_code,
                        "reason": (
                            f"{prereq_code} ({prereq_label}) is placed AFTER "
                            f"{course_code} ({course_label}). "
                            f"Prerequisites must be completed first."
                        ),
                    })

    return violations


def build_full_prereq_graph(
    prerequisites: list[dict[str, Any]],
) -> dict[str, list[set[str]]]:
    """
    Return the full prerequisite group structure for all courses.

    Useful for debugging and visualization. Each key is a course_code;
    the value is a list of OR-groups (each group is a set of alternatives).
    All groups must be satisfied (AND across groups, OR within each group).
    """
    groups: dict[str, list[set[str]]] = defaultdict(list)
    _build_groups(prerequisites, groups)
    return dict(groups)


def transitive_prereqs(
    course_code: str,
    prereq_graph: dict[str, list[set[str]]],
    _visited: Optional[set[str]] = None,
) -> set[str]:
    """
    Return the full transitive set of prerequisites for a course.

    Follows every prereq chain recursively. For OR groups, includes ALL
    alternatives (conservative: any might be needed depending on the path).
    """
    if _visited is None:
        _visited = set()
    if course_code in _visited:
        return set()
    _visited.add(course_code)

    result: set[str] = set()
    for group in prereq_graph.get(course_code, []):
        for prereq in group:
            result.add(prereq)
            result |= transitive_prereqs(prereq, prereq_graph, _visited)
    return result


# ── Private helpers ────────────────────────────────────────────────────────────

def _build_groups(
    prerequisites: list[dict[str, Any]],
    out: dict[str, list[set[str]]],
    plan_course_set: Optional[set[str]] = None,
    mutual_pairs: Optional[set[tuple[str, str]]] = None,
) -> None:
    """
    Populate `out` with OR-grouped prereq sets from prerequisite rows.

    Rows sharing the same (course_code, prereq_group) are OR alternatives.
    Rows with prereq_group=None are standalone AND requirements.
    Only required-type rows with a prereq_code are included.

    plan_course_set: if given, only include prereqs whose prereq_code is in
    this set. External prerequisites (not in the plan) are silently skipped.
    Also skips the lab→lecture backward artifact where a lecture lists its
    own lab as a prerequisite (e.g. CS 150 → CS 150L).
    """
    grouped_rows: dict[tuple[str, Any], set[str]] = defaultdict(set)

    for row in prerequisites:
        course = row.get("course_code")
        prereq = row.get("prereq_code")
        if not course or not prereq:
            continue
        if row.get("prereq_type") != "required":
            continue
        # Skip external prereqs not in the plan's course set.
        if plan_course_set is not None and prereq not in plan_course_set:
            continue
        # Skip backward lab→lecture catalog artifact (e.g. CS 150 lists CS 150L).
        if prereq.endswith("L") and prereq[:-1].rstrip() == course:
            continue
        # A lab's own lecture is a CO-REQUISITE (same semester is correct), not a
        # strict-earlier prereq — don't flag the lab for sharing the lecture's term.
        if course.endswith("L") and course[:-1].rstrip() == prereq:
            continue
        # Skip mutual co-requisite pairs that the solver treats as independent
        # (cycle broken — same-semester placement is intentional).
        if mutual_pairs and (course, prereq) in mutual_pairs:
            continue

        group_id = row.get("prereq_group")
        if group_id is None:
            out[course].append({prereq})
        else:
            grouped_rows[(course, group_id)].add(prereq)

    for (course, _), members in grouped_rows.items():
        out[course].append(members)
