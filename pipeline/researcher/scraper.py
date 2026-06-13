"""Scrape a prospect's public pages → clean text. httpx + BeautifulSoup, with a
Firecrawl fallback for JS-heavy sites. Every fetch is cached by URL hash so
re-runs cost nothing and are reproducible offline.
"""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pipeline import cache
from pipeline.config import settings
from pipeline.models import ScrapedPage

# Pages most likely to carry ICP / pricing / trigger signal.
CANDIDATE_PATHS = ["", "/about", "/about-us", "/pricing", "/product", "/customers", "/blog", "/careers"]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; gtmer-research/0.1; +https://github.com)"}
MAX_CHARS = 12_000  # per page, keeps brief context (and cost) bounded


def _clean(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "noscript", "svg"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:MAX_CHARS]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=10),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True,
)
def _fetch_httpx(url: str) -> str:
    resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _fetch_firecrawl(url: str) -> str | None:
    if not settings.firecrawl_enabled:
        return None
    try:
        resp = httpx.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {settings.firecrawl_api_key}"},
            json={"url": url, "formats": ["markdown"]},
            timeout=40,
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("markdown")
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def scrape_url(url: str) -> ScrapedPage | None:
    cached = cache.get(url)
    if cached is not None:
        return ScrapedPage(url=url, text=cached, fetched_via="cache")

    text: str | None = None
    via: str = "httpx"
    try:
        html = _fetch_httpx(url)
        text = _clean(html)
        # JS-heavy site: almost no extractable text → try Firecrawl.
        if len(text) < 200:
            fc = _fetch_firecrawl(url)
            if fc:
                text, via = fc[:MAX_CHARS], "firecrawl"
    except httpx.HTTPError:
        fc = _fetch_firecrawl(url)
        if fc:
            text, via = fc[:MAX_CHARS], "firecrawl"

    if not text:
        return None
    cache.put(url, text)
    return ScrapedPage(url=url, text=text, fetched_via=via)  # type: ignore[arg-type]


def scrape_site(domain: str) -> list[ScrapedPage]:
    """Fetch the candidate pages for a domain; skip-and-continue on failures."""
    base = domain if domain.startswith("http") else f"https://{domain.rstrip('/')}"
    pages: list[ScrapedPage] = []
    seen_text: set[int] = set()
    for path in CANDIDATE_PATHS:
        page = scrape_url(base + path)
        if page and hash(page.text) not in seen_text:
            seen_text.add(hash(page.text))
            pages.append(page)
    return pages
