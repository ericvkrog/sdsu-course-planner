# Prerequisite Architecture

How prerequisites are enforced in the planning engine. There are **three** places
prereqs are checked, each with a distinct scope. They are intentionally kept
separate — see "Why two checkers?" below.

## The three enforcement points

### 1. Solver — `backend/engine/solver.py` (`plan_courses`)
Enforces prereq groups **during** placement. A course is only placed into a
semester once every one of its prereq AND-groups has a member already placed in a
**strictly earlier** semester (or in the completed set). This is what *prevents*
bad plans from being generated in the first place.

A conflict raised here means **"couldn't place this course"** — not "the plan
validated wrong." Unplaced real courses and leftover placeholders fall through to
the diagnostic conflict list.

### 2. `validate_plan` — `backend/engine/validator.py`
Checks **immediate** (direct, one-hop) prerequisites of every course: each
course's direct prereq AND/OR-groups must sit in a strictly earlier semester (or
be completed). Also checks **standing** (cumulative units before the semester),
**offering term** (fall/spring), and the **unit cap** (soft — over-target is a
`warning`, not an `error`). Runs *after* placement, on any plan (generated,
dragged, or swapped).

### 3. `check_prereq_chains` — `backend/engine/prereq_checker.py`
A **transitive** walk of the full prereq graph. Catches ordering violations that
are deeper than one hop — e.g. A→B→C where C lands before A even though C's
*direct* prereq B is correctly ordered. Runs *after* placement, alongside
`validate_plan`.

## Why two checkers? (immediate + transitive)

They have **different scope** and both are cheap, so both run:

- `validate_plan` is the broad post-hoc constraint check (prereqs **plus** standing,
  offering, units). It reports the immediate, student-legible cause ("Prerequisite
  CS 150 is in the same semester as CS 160").
- `check_prereq_chains` is purely about prereq **ordering**, but transitively — it
  catches multi-hop mis-orderings a one-hop check misses.

Merging them into one pass was explicitly considered and **rejected**: the immediate
checker also owns standing/offering/units (orthogonal to chain depth), and the
transitive checker's graph walk is a different algorithm. Keeping them separate
keeps each one simple and individually testable.

## Shared prereq source

All three consume **one enriched prereq source**, assembled the same way
everywhere (see `backend/api/routes/plan.py` and `test_solver.py`):

1. DB / catalog prereq rows
2. `catalog_fixes.apply_course_aliases` — old course number → current number
3. `prereq_groups.apply_prereq_groups` — the OR-group overlay (`prereq_group`
   column; rows sharing a group for a course are OR-alternatives, different groups
   are AND-requirements)
4. `catalog_fixes.get_catalog_fix_prereqs` — `MISSING_PREREQS` the scraper missed
5. Synthetic GE/GR placeholder rows (`ge_requirements`, `graduation_requirements`)

The **NetworkX** graph is used **only** by the solver (for ordering) and the
course-detail D3 route (for visualization) — **not** by either checker. The
checkers operate directly on the enriched prereq rows.

## Dedup of immediate vs transitive conflicts

`/plan/generate`, `/plan/adjust`, and `/plan/swap` all run both `validate_plan`
and `check_prereq_chains`, then merge. The same prereq problem can surface in both
lists, so chain violations already reported as immediate conflicts are dropped.

The merge (`_merge_chain_violations` in `routes/plan.py`) dedups on a **structural
key** — `(course_code, prereq_code)` — not on the human `reason` string. An
immediate prereq conflict carries `prereq_codes` (the unmet group members, added
in `validator.py`); a chain violation names a single `prereq_code`. A chain
violation is a duplicate when an immediate conflict for the same course already
covers that prereq code. (This replaced an earlier `(course_code, reason)` match
that silently broke whenever either checker's wording changed.)

## Special cases handled in all three

- **OR-groups** (`prereq_group`): satisfied if *any* member is available.
- **Mutual co-requisites** (A requires B *and* B requires A, e.g. PHYS 180A↔180B):
  detected and skipped by solver, validator, and checker — all three co-place them
  and none flags same-semester placement as a violation.
- **Lab/lecture ordering**: a lab (code ending in `L`) goes in the semester *after*
  its base lecture; the lecture→lab edge is restored after cycle detection.
