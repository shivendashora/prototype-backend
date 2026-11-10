import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent


@lru_cache
def load(name: str) -> list[dict]:
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))
