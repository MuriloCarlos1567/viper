from __future__ import annotations

import hashlib
import re


def service_name_for_repo(repo: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", repo.lower()).strip("-")
    if not base:
        base = "repo"
    if base[0].isdigit():
        base = f"r-{base}"
    return base


def unique_service_name(repo: str, existing: set[str]) -> str:
    candidate = service_name_for_repo(repo)
    if candidate not in existing:
        return candidate
    suffix = hashlib.md5(repo.encode("utf-8"), usedforsecurity=False).hexdigest()[:6]
    return f"{candidate}-{suffix}"
