"""On-disk cache for scraped pages, keyed by sha256(url).

Makes re-runs free and offline-reproducible: re-scraping a lead costs nothing
and the pipeline is safe to re-run on any stage. Stored under data/cache/
(gitignored).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def _key(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def get(url: str) -> str | None:
    path = _key(url)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))["text"]
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def put(url: str, text: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _key(url).write_text(
        json.dumps({"url": url, "text": text}, ensure_ascii=False),
        encoding="utf-8",
    )
