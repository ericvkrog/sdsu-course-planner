-- Migration 003: Clean up catalog-wide scraper artifacts.
--
-- Two patterns fixed here, identified by auditing all 119 department JSONs:
--
--   1. Self-lab cycles — courses that list their own lab as a prerequisite
--      (e.g. CHEM 232 → CHEM 232L). A lab cannot be a prereq of its own
--      lecture; this is a scraper artifact from "co-requisite" wording.
--      Affected: BIOL 100, CHEM 232, CHEM 432, CSP 600, CSP 621, ENS 653,
--      ENS 654, ENS 655, ENS 663, ENS 664, ENS 665, GEOG 591, GEOG 592,
--      NURS 501.
--
--   2. Duplicate prereq rows — same (course_code, prereq_code, min_standing)
--      appearing more than once. Pure data-quality cleanup.
--
-- Both fixes are also reflected in data/catalog/*.json so a reseed produces
-- the same state.

-- ── 1. Drop self-lab prereq rows ───────────────────────────────────────────
DELETE FROM prerequisites
WHERE prereq_code = course_code || 'L';

-- ── 2. Deduplicate prereq rows ─────────────────────────────────────────────
-- Keep the lowest-id row in each (course_code, prereq_code, min_standing) group.
DELETE FROM prerequisites a
USING prerequisites b
WHERE a.id > b.id
  AND a.course_code = b.course_code
  AND a.prereq_code IS NOT DISTINCT FROM b.prereq_code
  AND a.min_standing IS NOT DISTINCT FROM b.min_standing;
