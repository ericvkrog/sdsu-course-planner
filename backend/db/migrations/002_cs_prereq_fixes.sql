-- Migration 002: Fix missing and incorrect CS prerequisite relationships
--
-- The catalog scraper missed several CS prerequisite links. This migration
-- brings the DB into sync with the corrected data/catalog/cs.json.
--
-- Changes:
--   CS 150  : remove erroneous CS 150L prerequisite (lecture/lab cycle in catalog)
--   CS 160  : add CS 150 as required prerequisite
--   CS 420  : add CS 210 as required prerequisite
--   CS 450  : add CS 210 as required prerequisite
--   CS 460  : add CS 210 and MATH 245 as required prerequisites
--   CS 480  : add CS 210 and CS 240 as required prerequisites
--   CS 577  : replace old STAT 119 code with current STAT 250

-- ── Remove bad rows ────────────────────────────────────────────────────────

-- CS 150 erroneously lists CS 150L as a prereq (a catalog cycle artifact).
DELETE FROM prerequisites
WHERE course_code = 'CS 150' AND prereq_code = 'CS 150L';

-- Remove old STAT 119 reference from CS 577 (renamed to STAT 250).
DELETE FROM prerequisites
WHERE course_code = 'CS 577' AND prereq_code = 'STAT 119';

-- ── Insert missing rows (idempotent via ON CONFLICT DO NOTHING) ────────────

INSERT INTO prerequisites (course_code, prereq_code, prereq_type, min_standing)
VALUES
    ('CS 160',  'CS 150',   'required', NULL),
    ('CS 240',  'CS 150',   'required', NULL),
    ('CS 250',  'CS 150',   'required', NULL),
    ('CS 420',  'CS 210',   'required', NULL),
    ('CS 450',  'CS 210',   'required', NULL),
    ('CS 460',  'CS 210',   'required', NULL),
    ('CS 460',  'MATH 245', 'required', NULL),
    ('CS 480',  'CS 210',   'required', NULL),
    ('CS 480',  'CS 240',   'required', NULL),
    ('CS 577',  'STAT 250', 'required', NULL)
ON CONFLICT DO NOTHING;
