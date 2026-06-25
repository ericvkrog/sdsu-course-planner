-- SDSU Course Planner — PostgreSQL schema
-- Run against your Supabase project SQL editor

CREATE TABLE courses (
    course_code     TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    units           INTEGER NOT NULL,
    department      TEXT NOT NULL,
    description     TEXT,
    grading_method  TEXT,
    offered_fall    BOOLEAN DEFAULT TRUE,
    offered_spring  BOOLEAN DEFAULT TRUE,
    max_credits     INTEGER,
    notes           TEXT
);

CREATE TABLE prerequisites (
    id              SERIAL PRIMARY KEY,
    course_code     TEXT REFERENCES courses(course_code),
    prereq_code     TEXT REFERENCES courses(course_code),
    prereq_type     TEXT DEFAULT 'required',
    min_standing    TEXT,
    prereq_group    TEXT                     -- OR-group key: rows sharing this for a course are OR-alternatives; NULL/distinct groups are AND (see migrations/001_prereq_group.sql)
);

CREATE TABLE departments (
    dept_code       TEXT PRIMARY KEY,
    dept_name       TEXT NOT NULL,
    college         TEXT,
    catalog_url     TEXT
);

CREATE TABLE professors (
    id                      SERIAL PRIMARY KEY,
    name                    TEXT NOT NULL,
    department              TEXT,
    rmp_rating              FLOAT,
    rmp_difficulty          FLOAT,
    rmp_would_take_again    FLOAT,
    rmp_tags                TEXT[]
);

CREATE TABLE user_plans (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID,
    major               TEXT NOT NULL,
    minor               TEXT,
    transfer_units      INTEGER DEFAULT 0,
    target_graduation   TEXT,
    completed_courses   TEXT[]
);

CREATE TABLE plan_semesters (
    id               SERIAL PRIMARY KEY,
    plan_id          UUID REFERENCES user_plans(id),
    semester         TEXT NOT NULL,
    year             INTEGER NOT NULL,
    courses          TEXT[],
    total_units      INTEGER,
    difficulty_score FLOAT
);

CREATE INDEX idx_prereqs_course ON prerequisites(course_code);
CREATE INDEX idx_prereqs_prereq ON prerequisites(prereq_code);
CREATE INDEX idx_courses_dept   ON courses(department);
