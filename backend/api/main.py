import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

app = FastAPI(title="SDSU Course Planner API")

FRONTEND_URL = os.environ.get("FRONTEND_URL")
if not FRONTEND_URL:
    # No FRONTEND_URL set — fall back to local dev origin, but make the
    # assumption loud so a misconfigured prod deploy doesn't silently block
    # the real frontend with an opaque CORS failure.
    FRONTEND_URL = "http://localhost:3000"
    print(
        "[startup] WARNING: FRONTEND_URL is not set; defaulting CORS origin to "
        f"{FRONTEND_URL}. Set FRONTEND_URL in production or the deployed "
        "frontend will be blocked by CORS."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> Client:
    try:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
    except KeyError as missing:
        raise RuntimeError(
            f"Missing required environment variable {missing}. Set SUPABASE_URL "
            "and SUPABASE_SERVICE_KEY (see .env.example) before calling the API."
        ) from missing
    return create_client(url, key)


from backend.api.routes import courses, majors, plan  # noqa: E402

app.include_router(courses.router)
app.include_router(majors.router)
app.include_router(plan.router)


@app.get("/health")
def health():
    return {"status": "ok"}
