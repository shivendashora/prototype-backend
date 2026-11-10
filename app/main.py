import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Allow `python main.py` from inside backend/app: put backend/ on the path
# and treat this file as part of the `app` package so relative imports work.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "app"

from dotenv import load_dotenv

load_dotenv()
import uvicorn

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from . import db  # noqa: E402
from .data import load  # noqa: E402
from .routers import carousel, courses, providers  # noqa: E402
from .services import carousel_ai  # noqa: E402

@asynccontextmanager
async def lifespan(_app):
    await db.connect()
    await db.init_db()
    # Warm the JSON catalogue cache so no request ever does blocking file I/O.
    load("providers")
    load("courses")
    try:
        yield
    finally:
        await carousel_ai.aclose()
        await db.close()


app = FastAPI(
    lifespan=lifespan,
    title="Assignment API",
    description="Backend for Practo for Animals, the AI course landing page and the carousel studio.",
    version="1.0.0",
)

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

app.include_router(providers.router)
app.include_router(courses.router)
app.include_router(carousel.router)


@app.get("/api/health")
async def health():
    db_ok = await db.ping()
    return {"status": "ok" if db_ok else "degraded", "database": "up" if db_ok else "down"}


if __name__ == "__main__":
    # Import string + app_dir so --reload works no matter where this is launched from.
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True,
                app_dir=str(Path(__file__).resolve().parent.parent))