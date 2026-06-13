"""Versioned prompt loader.

Each prompt lives in `prompts/{version}/{task}.md`. On load we hash it and (best
effort) register the version in the `prompt_versions` table, so every brief /
email / eval row can carry the exact prompt_version it came from. The active
version is just the directory name passed in (default "v1").
"""

from __future__ import annotations

import functools
import hashlib
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent
DEFAULT_VERSION = "v1"


TASKS = ("brief", "email_sequence", "grounding", "judge_rubric")


@functools.lru_cache(maxsize=64)
def _read(task: str, version: str) -> tuple[str, str]:
    """Return (text, resolved_version).

    A new prompt version only needs to ship the files it actually changes — e.g.
    v2 changes only `email_sequence`, so a v2 run reuses v1's brief/grounding/
    judge prompts (holding the judge constant across the A/B is exactly what you
    want). Falls back to DEFAULT_VERSION when a task has no file for `version`.
    """
    path = PROMPTS_DIR / version / f"{task}.md"
    if path.exists():
        return path.read_text(encoding="utf-8"), version
    fallback = PROMPTS_DIR / DEFAULT_VERSION / f"{task}.md"
    if fallback.exists():
        return fallback.read_text(encoding="utf-8"), DEFAULT_VERSION
    raise FileNotFoundError(f"prompt not found: {path} (no {DEFAULT_VERSION} fallback either)")


class PromptHandle:
    def __init__(self, task: str, version: str) -> None:
        self.task = task
        self.version = version
        self.text, self.resolved_version = _read(task, version)
        self.sha256 = hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def pv_id(self) -> str:
        # Requested version, so version-keyed lookups stay consistent. When this
        # falls back to v1 the sha256 will match v1's row — correctly recording
        # that the prompt was unchanged for this version.
        return f"{self.task}:{self.version}"

    def register(self) -> None:
        """Best-effort DB registration; never blocks a pipeline run."""
        try:
            from pipeline import db

            db.register_prompt(self.pv_id, self.task, self.version, self.sha256)
        except Exception:  # noqa: BLE001 — observability, not correctness
            pass


def load(task: str, version: str = DEFAULT_VERSION, register: bool = False) -> PromptHandle:
    h = PromptHandle(task, version)
    if register:
        h.register()
    return h


def ensure_prompts(version: str = DEFAULT_VERSION, tasks: tuple[str, ...] = TASKS) -> None:
    """Preflight: fail fast (before any lead/API call) if `version` is bad —
    beats lazily dead-lettering every lead deep in the graph. A version is valid
    if its directory exists (it may ship only the prompts it changes; the rest
    fall back to v1). A typo'd `--version` with no directory fails here."""
    if version != DEFAULT_VERSION and not (PROMPTS_DIR / version).is_dir():
        raise FileNotFoundError(
            f"prompt version '{version}' has no directory at {PROMPTS_DIR / version}"
        )
    missing = [t for t in tasks if not _resolves(t, version)]
    if missing:
        raise FileNotFoundError(
            f"missing prompt(s) for version '{version}': {', '.join(missing)}"
        )


def _resolves(task: str, version: str) -> bool:
    try:
        _read(task, version)
        return True
    except FileNotFoundError:
        return False


def register_all(version: str = DEFAULT_VERSION, tasks: tuple[str, ...] = TASKS) -> None:
    """Best-effort: record every active prompt version in `prompt_versions`."""
    for t in tasks:
        try:
            load(t, version, register=True)
        except Exception:  # noqa: BLE001 — observability only
            pass
