# SDSU Course Planner

An academic planning tool for San Diego State University students. It helps users choose a major, map completed coursework, and generate a semester-by-semester plan that stays aligned with prerequisites and graduation requirements.

This public repository was migrated from a private version, with history cleaned before publication.

## What It Does

- Turns degree requirements into a clear semester plan
- Accounts for prerequisites, standing, GE requirements, and term availability
- Lets users adjust course placement and recheck the plan
- Surfaces course details and prerequisite relationships in the UI

## Why It Exists

The project demonstrates a practical mix of product thinking and engineering: taking messy academic requirements, normalizing them, and presenting them in a simple planning workflow.

## Tech Stack

- Frontend: React, Vite, Tailwind CSS
- Backend: Python, FastAPI, Pydantic
- Data store: Supabase / PostgreSQL
- Planning logic: NetworkX and a custom constraint solver

## Local Setup

### Backend

```bash
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
uvicorn backend.api.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
