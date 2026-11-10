# Prototype Backend (FastAPI)

The async REST API for three prototypes:

1. **Practo for Animals**: search for vets, hospitals and other pet-care providers; list a business; report a correction.
2. **AI Education**: course catalogue and lead capture.
3. **AI Carousel Studio**: turns a raw idea into a social media carousel, using Claude when an API key is set and a built-in template engine otherwise.

For how each part works, see **[WALKTHROUGH.md](WALKTHROUGH.md)**.

## Tech stack

| Layer | Choice |
|---|---|
| Framework | FastAPI (all routes `async`) |
| Validation | Pydantic v2 |
| Database | PostgreSQL |
| ORM / driver | SQLAlchemy 2.x async, asyncpg |
| AI (optional) | Anthropic Python SDK (`AsyncAnthropic`) |
| Server | Uvicorn |

## Folder structure

```
backend/
├── README.md             ← you are here
├── WALKTHROUGH.md        ← how every module works
├── requirements.txt
├── .env.example          ← copy to .env
├── .gitignore            ← keeps .env, *.db, .venv out of git
└── app/
    ├── main.py           ← app factory, lifespan (DB connect/create tables), CORS, health route
    ├── db.py             ← async engine, session dependency, Base, create_all
    ├── models.py         ← ORM tables: leads, listings, corrections, carousels
    ├── schemas.py        ← Pydantic request/response models
    ├── data/
    │   ├── __init__.py   ← cached JSON loader
    │   ├── providers.json← 18 sample pet-care providers
    │   └── courses.json  ← 3 sample AI courses
    ├── routers/
    │   ├── providers.py  ← /api/pets/*
    │   ├── courses.py    ← /api/edu/*
    │   └── carousel.py   ← /api/carousel/*
    └── services/
        └── carousel_ai.py← Claude pipeline + offline template engine
```

## Run locally

Requirements: **Python 3.10+** and a running **PostgreSQL 13+** server.

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate             # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env             # macOS/Linux: cp .env.example .env, then edit the values
uvicorn app.main:app --reload --port 8000
```

- Interactive API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

On startup the app creates the database named in `DATABASE_URL` if it is missing (when the user has permission), then creates any missing tables.

## Environment variables

Every value is read from the environment, from `.env` locally or from the host's settings in production. Nothing secret is written in the code.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | **yes** | none | Postgres URL, e.g. `postgresql://user:pass@host:5432/db`. `postgres://` and `postgresql://` are switched to the async driver automatically, and `?sslmode=require` is supported. |
| `CORS_ORIGINS` | yes, in production | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated list of frontend origins allowed to call the API |
| `ANTHROPIC_API_KEY` | no | empty | Turns on Claude-generated carousels. Without it the template engine is used. |
| `CLAUDE_MODEL` | no | `claude-opus-5-5` | Model used for carousel generation |
| `DB_POOL_SIZE` | no | `5` | Connections kept open in the pool |
| `DB_MAX_OVERFLOW` | no | `10` | Extra connections allowed during bursts |

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | API and database status |
| GET | `/api/pets/meta` | Categories with counts, cities, pet types, headline stats |
| GET | `/api/pets/providers` | Search, filter, sort and page through providers |
| GET | `/api/pets/providers/{id}` | One provider |
| POST | `/api/pets/listings` | Submit a "list your business" request |
| POST | `/api/pets/corrections` | Report wrong details on a listing |
| GET | `/api/edu/courses` | All courses |
| GET | `/api/edu/courses/{id}` | One course |
| POST | `/api/edu/leads` | Register, enquiry, brochure or callback lead |
| GET | `/api/edu/stats` | Lead count |
| GET | `/api/carousel/status` | Whether Claude is enabled |
| POST | `/api/carousel/generate` | Generate a carousel from an idea |

The full request and response schemas are at `/docs`.

## Deploy (Render)

1. Create a **PostgreSQL** instance and a **Web Service** for this repo, both in the **same region**.
2. Web Service settings:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health check path:** `/api/health`
3. Environment variables:
   - `DATABASE_URL`: the database's **Internal Database URL**, unchanged. It doesn't need SSL.
   - `CORS_ORIGINS`: your deployed frontend URL, e.g. `https://your-frontend.onrender.com`.
   - `ANTHROPIC_API_KEY`: optional.

The tables are created on the first start. Use the **External** URL with `?sslmode=require` only when connecting from outside Render, for example with `psql` from your laptop.
