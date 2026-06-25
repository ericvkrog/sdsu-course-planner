from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from backend.api.main import get_db
from backend.api.models import CourseDetailOut, PrereqGraphOut
from backend.engine.catalog_fixes import MISSING_PREREQS, apply_course_aliases
from backend.engine.graph import build_graph, prereq_chain, to_d3

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("/{code}", response_model=CourseDetailOut)
def get_course(code: str, db: Client = Depends(get_db)):
    code = code.upper()
    # `.single()` raises (rather than returning empty data) when zero or many
    # rows match, so translate that into a clean 404 instead of a 500.
    try:
        row = db.table("courses").select("*").eq("course_code", code).single().execute()
    except Exception:
        raise HTTPException(404, f"Course {code} not found")
    if not row.data:
        raise HTTPException(404, f"Course {code} not found")
    db_prereqs = (
        db.table("prerequisites").select("*").eq("course_code", code).execute().data or []
    )
    prereqs = apply_course_aliases(db_prereqs) + [
        row for row in MISSING_PREREQS if row["course_code"] == code
    ]
    return {**row.data, "prerequisites": prereqs}


@router.get("/{code}/prereq-graph", response_model=PrereqGraphOut)
def get_prereq_graph(code: str, db: Client = Depends(get_db)):
    code = code.upper()
    db_prereqs = db.table("prerequisites").select("*").execute().data or []
    # Apply the same catalog fixes the solver uses, so the prereq graph matches
    # what the planner enforces even when the DB hasn't been migrated yet.
    all_prereqs = apply_course_aliases(db_prereqs) + MISSING_PREREQS
    G = build_graph(all_prereqs)
    subgraph = prereq_chain(G, code)

    # If the course has no prerequisites and isn't in the graph at all,
    # synthesize a single-node graph so the frontend can still render the card.
    if len(subgraph.nodes) == 0:
        course_row = db.table("courses").select("course_code,title,units").eq("course_code", code).execute().data
        if not course_row:
            raise HTTPException(404, f"Course {code} not found")
        return to_d3(subgraph, {})  # empty graph — no prereqs

    codes = list(subgraph.nodes)
    courses_data = db.table("courses").select("course_code,title,units").in_("course_code", codes).execute().data or []
    courses_by_code = {c["course_code"]: c for c in courses_data}
    return to_d3(subgraph, courses_by_code)
