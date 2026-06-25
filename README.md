# SDSU Course Planner

An unofficial academic planning tool for San Diego State University students. Students choose a major, enter completed coursework, set a unit-load preference, and generate a semester-by-semester plan that respects prerequisites, standing requirements, GE requirements, graduation requirements, and term availability.

This project was built as a full-stack resume project focused on constraint solving, catalog data processing, and an interactive planning UI.

## Features

- Generate prerequisite-aware degree plans for SDSU bachelor's programs
- Supports SDSU major requirements, GE placeholders, GWAR, American Institutions, and free electives
- Drag courses between semesters and revalidate the plan
- Swap elective, GE, GWAR, AI, and free-elective slots with eligible alternatives
- Balance semester unit loads with a configurable max-units setting
- View course details and prerequisite relationships
- Scrape and normalize SDSU catalog data into structured course and prerequisite records

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React, Vite, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic |
| Database | Supabase / PostgreSQL |
| Planning engine | NetworkX, custom constraint solver |
| Data pipeline | requests, BeautifulSoup |

## Project Structure

```text
.
├── backend/
│   ├── api/          # FastAPI app, routes, request/response models
│   ├── db/           # Database schema, migrations, seed script
│   ├── engine/       # Planning solver, validators, swap logic, requirement models
│   └── scraper/      # SDSU catalog and requirement scrapers
├── docs/             # Engineering notes and architecture docs
├── frontend/
│   ├── src/api/      # Frontend API client
│   ├── src/components/
│   ├── src/hooks/
│   └── src/pages/
├── data/             # Local scraped data, ignored by Git
└── .env.example      # Backend environment variable template
```

## How It Works

The backend builds a prerequisite graph from catalog data and uses a constraint solver to place courses into valid terms. The solver accounts for:

- prerequisite order
- co-requisite lecture/lab placement
- fall and spring availability
- unit caps
- junior standing for upper-division courses
- major requirements, GE requirements, and graduation requirements
- completed courses supplied by the student

After a plan is generated, the frontend lets users drag courses or swap slots. Each change is sent back to the API and revalidated so the UI can surface conflicts instead of silently creating an invalid plan.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Supabase project with the schema from `backend/db/schema.sql`

### Backend Setup

Create a virtual environment and install dependencies:

```bash
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

Fill in the Supabase values:

```text
DATABASE_URL=
SUPABASE_URL=
SUPABASE_KEY=
SUPABASE_SERVICE_KEY=
FRONTEND_URL=http://localhost:3000
```

Start the API:

```bash
uvicorn backend.api.main:app --reload
```

The backend runs at `http://localhost:8000`.

### Frontend Setup

Install dependencies:

```bash
cd frontend
npm install
```

Start the Vite dev server:

```bash
npm run dev
```

The frontend runs at `http://localhost:3000` and proxies `/api` requests to `http://localhost:8000`.

## Useful Commands

Run the frontend production build:

```bash
cd frontend
npm run build
```

Run the core planning tests:

```bash
python -m backend.engine.test_solver
python -m backend.engine.test_swap_options
python -m backend.engine.test_terms
```

Validate supported majors through the planning engine:

```bash
python -m backend.engine.validate_all_majors
```

## API Overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | API health check |
| `GET` | `/majors` | List supported majors |
| `GET` | `/departments` | List departments |
| `GET` | `/courses/{code}` | Fetch course details |
| `GET` | `/courses/{code}/prereq-graph` | Fetch prerequisite graph data |
| `POST` | `/plan/generate` | Generate a plan |
| `POST` | `/plan/adjust` | Move a course and revalidate |
| `POST` | `/plan/swap-options` | Get eligible replacements for a slot |
| `POST` | `/plan/swap` | Apply a course swap and revalidate |

## Environment and Secrets

Real environment variables should live in `.env`, which is ignored by Git. The tracked `.env.example` files contain placeholders only.

Never commit Supabase service keys, database URLs, or production credentials.

## Status

This is an MVP/prototype academic planning tool. It is not affiliated with San Diego State University and should not replace official academic advising.

## License

No license has been selected yet.
