# Backend Walkthrough

How each module works and how a request travels through the app. For setup, see [README.md](README.md).

## Request lifecycle

```
HTTP request
   │
   ▼
CORS middleware (main.py)            checks the origin against CORS_ORIGINS
   │
   ▼
Router (routers/*.py)                matches the path, Pydantic validates the body/query (422 on bad input)
   │
   ├── catalogue reads ──────────▶  data/load() (JSON, cached in memory)
   │
   ├── writes ───────────────────▶  SessionDep → AsyncSession → PostgreSQL
   │
   └── carousel ─────────────────▶  services/carousel_ai → Claude (async) or template engine
   │
   ▼
Response model (schemas.py)          shapes and validates the JSON sent back
```

Everything is non-blocking. Routes are `async def`, the database goes through asyncpg, Claude through `AsyncAnthropic`, and the JSON files are read once at startup, so no request does file I/O.

---

## `app/main.py`: application entry point

- **Loads `.env`** with `python-dotenv` before anything reads the environment.
- **`lifespan`** runs once when the server starts and once when it stops:
  1. `db.connect()` creates the async engine and connection pool.
  2. `db.init_db()` runs `Base.metadata.create_all`, which creates any missing tables.
  3. `load("providers")` and `load("courses")` load the JSON catalogue into memory.
  4. On shutdown it closes the shared Claude client and disposes of the DB pool.
- **CORS** allows only the origins listed in `CORS_ORIGINS`.
- **Routers** are registered under `/api/pets`, `/api/edu` and `/api/carousel`.
- **`GET /api/health`** runs `SELECT 1` against the database and reports `{"status": "ok", "database": "up"}` or `"degraded"` / `"down"`.
- Running `python app/main.py` directly starts Uvicorn with auto-reload. That's for development only; production uses the `uvicorn` command in the README.

## `app/db.py`: database layer

| Piece | What it does |
|---|---|
| `Base` | The SQLAlchemy `DeclarativeBase` that every model inherits from |
| `_database_url()` | Reads `DATABASE_URL`, fails with a clear message if it's missing, switches the driver to `postgresql+asyncpg`, and maps `sslmode=` to asyncpg's `ssl=` |
| `_ensure_database()` | Local-dev helper: connects to the `postgres` maintenance DB and runs `CREATE DATABASE` if the target doesn't exist. Skipped quietly on managed hosts where that isn't allowed. |
| `connect()` | Builds the async engine (`pool_size`, `max_overflow`, `pool_pre_ping` to discard dead connections, `pool_recycle` every 30 min) and an `async_sessionmaker` |
| `init_db()` | Imports `models` so the tables are registered, then runs `conn.run_sync(Base.metadata.create_all)` |
| `get_session()` / `SessionDep` | FastAPI dependency that gives each request its own `AsyncSession` and closes it afterwards |
| `ping()` | Used by the health route; never raises |
| `close()` | Disposes of the engine on shutdown |

`create_all` only creates **missing** tables. It doesn't change existing ones, so adding a column later needs an `ALTER TABLE` (or Alembic, if you add migrations).

## `app/models.py`: tables

Every table shares three columns from the `_Row` mixin:

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | Primary key, assigned by Postgres |
| `created_at` | `TIMESTAMPTZ` | `DEFAULT now()` |
| `payload` | `JSONB` | The full validated submission, so no field is lost even if it has no column of its own |

| Model → table | Extra columns |
|---|---|
| `Lead` → `leads` | `course_id`, `kind`, `name`, `email`, `phone` |
| `Listing` → `listings` | `business_name`, `category`, `city`, `phone` |
| `Correction` → `corrections` | `provider_id`, `field` |
| `Carousel` → `carousels` | `idea`, `source` (`claude` or `template`) |

The separate columns are the fields you would filter or report on. `payload` keeps everything else.

## `app/schemas.py`: validation

Pydantic models define exactly what each endpoint accepts and returns. Invalid input gets an automatic **422** with field-level messages, which the frontend shows to the user.

- **Inputs:** `ListingIn`, `CorrectionIn`, `LeadIn`, `CarouselRequest`. They enforce length limits, phone regex, `EmailStr`, and fixed `Literal` choices for category, lead kind, tone, platform and so on.
- **Outputs:** `Provider`, `ProviderPage`, `Ack` (`{ok, id, message}`, returned by every write), and `Carousel` with its nested `Slide` and `VisualDirection`.

## `app/data/`: catalogue

`load(name)` reads `data/<name>.json` once and keeps it in memory (`lru_cache`). The providers (18) and courses (3) are sample seed data. They are read-only, so they live in JSON rather than the database.

---

## `routers/providers.py`: Practo for Animals (`/api/pets`)

- **`GET /meta`** builds the homepage numbers from the catalogue: each category with its provider count, the list of cities, the pet types, and totals (providers, cities, verified).
- **`GET /providers`** is the search engine. It filters in memory, in this order:
  1. `q`: free text matched against name, area, city, category and services
  2. `category`, `city`, `pet`
  3. on/off filters: `open_24x7`, `emergency`, `home_visit`, `verified`
  4. `min_rating`, `max_price` (providers with no listed price are kept)
  5. **sort**: `rating` (then review count), `distance`, `price`, or `relevance`. Relevance puts verified providers first, then ranks by `rating × reviews^0.25` with the review count capped at 2000, so one place with a huge number of reviews can't dominate.
  6. paging with `limit` (max 100) and `offset`, returning `{total, items}`
- **`GET /providers/{id}`** returns one provider, or a 404.
- **`POST /listings`** validates a `ListingIn`, saves a `Listing` row and returns its id with a confirmation message.
- **`POST /corrections`** checks that the provider exists (404 otherwise), saves a `Correction` row and returns its id.

## `routers/courses.py`: AI Education (`/api/edu`)

- **`GET /courses`** and **`GET /courses/{id}`** read from the catalogue.
- **`POST /leads`** handles all four lead types: `register`, `enquiry`, `brochure`, `callback`. If a `course_id` is sent it must exist. Saves a `Lead` row and returns a message that depends on the lead type. The comment marks where a CRM, WhatsApp or n8n webhook call would go.
- **`GET /stats`** returns the lead count via `SELECT COUNT(*)`.

## `routers/carousel.py`: Carousel Studio (`/api/carousel`)

- **`GET /status`** returns `{ai_enabled}`, which tells the UI whether a Claude key is set.
- **`POST /generate`** awaits `generate_carousel()`, saves the idea, the source and the full carousel as a `Carousel` row, then returns the carousel.

## `services/carousel_ai.py`: generation pipeline

The pipeline is **idea → research → structure → copy → visual direction**.

**With `ANTHROPIC_API_KEY` set (Claude path):**
1. One shared `AsyncAnthropic` client is created on first use, which reuses its HTTP connections.
2. A single **structured-output** call sends a system prompt describing the four steps, plus the idea, platform, tone, brand and slide count. A JSON schema forces the reply into exactly the `Carousel` shape.
3. Rate limits, API errors, connection errors, refusals, `max_tokens` cut-offs and unparseable JSON all return `None`. The request then falls back to the template engine, so the user always gets a result.

**Without a key, or on fallback (template engine):**
- `_topic()` pulls a short topic from the first sentence of the idea, and `_points()` splits the rest into bullet-style points.
- It builds a **cover** slide, content slides (the user's points first, then built-in default tips), a **quote** slide and a **CTA** slide, to exactly the requested slide count.
- It also writes three hook options, a caption, hashtags, research reminders, and a `VisualDirection` from one of four themes: `educational`, `bold`, `friendly`, `professional`.

`aclose()` closes the shared client on shutdown.

---

## Error handling

| Situation | Response |
|---|---|
| Invalid body or query | 422 with per-field details |
| Unknown provider or course id | 404 |
| Database unreachable | `/api/health` reports `degraded` / `down`. Writes return 500. |
| Claude fails for any reason | Logged as a warning; the template engine's result is returned (still 200) |
| `DATABASE_URL` missing | The app refuses to start, with a clear error |

## Quick manual test

```bash
curl http://127.0.0.1:8000/api/health
curl "http://127.0.0.1:8000/api/pets/providers?category=vet_clinic&sort=rating&limit=3"
curl -X POST http://127.0.0.1:8000/api/carousel/generate \
     -H "Content-Type: application/json" \
     -d '{"idea":"Monsoon tick prevention for dogs","platform":"instagram","slides":5}'
```
