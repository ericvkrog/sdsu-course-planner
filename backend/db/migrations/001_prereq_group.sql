-- Migration 001: Add prereq_group column to prerequisites table.
--
-- Rows sharing the same prereq_group value for a given course_code are OR
-- alternatives — the student needs to satisfy ANY ONE of them.
-- Rows with prereq_group IS NULL are standalone AND requirements (default).
--
-- Run this in the Supabase SQL editor.

ALTER TABLE prerequisites
    ADD COLUMN IF NOT EXISTS prereq_group INTEGER DEFAULT NULL;

-- Index so the solver can group efficiently.
CREATE INDEX IF NOT EXISTS idx_prereqs_group
    ON prerequisites(course_code, prereq_group)
    WHERE prereq_group IS NOT NULL;

COMMENT ON COLUMN prerequisites.prereq_group IS
    'Rows sharing the same group value for a course are OR alternatives. NULL = standalone AND requirement.';
