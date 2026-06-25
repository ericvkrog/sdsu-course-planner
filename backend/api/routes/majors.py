from fastapi import APIRouter, Depends
from supabase import Client

from backend.api.main import get_db
from backend.engine.major_requirements import SUPPORTED_MAJORS

router = APIRouter(tags=["majors"])


@router.get("/departments")
def list_departments(db: Client = Depends(get_db)):
    rows = db.table("departments").select("*").order("dept_code").execute()
    return rows.data or []


@router.get("/majors")
def list_majors(verified_only: bool = False):
    """
    List supported majors.

    Verified majors are hand-curated and validated clean; scraped majors are
    auto-generated from the catalog and may have requirement gaps. Pass
    verified_only=true to return just the curated set.
    """
    majors = sorted(SUPPORTED_MAJORS.values(), key=lambda m: (not m.verified, m.name))
    return [
        {
            "code": m.code,
            "name": m.name,
            "degree": m.degree,
            "total_units": m.total_units,
            "catalog_url": m.catalog_url,
            "verified": m.verified,
        }
        for m in majors
        if m.verified or not verified_only
    ]
