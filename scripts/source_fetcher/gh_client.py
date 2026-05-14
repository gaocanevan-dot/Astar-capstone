"""Minimal GitHub REST API client for c4 source fetching.

Authentication via `~/.config/claude/mcp.env` (`GITHUB_PERSONAL_ACCESS_TOKEN`).
PAT value is never logged or returned by any public function.

Provides:
- get_repo_tree(owner, repo, ref="main") -> list[{"path": str, "type": "blob"|"tree", "size": int}]
- get_file_raw(owner, repo, path, ref="main") -> str
- get_issue(owner, repo, number) -> {"body": str, "title": str, "comments": list[str]}

Rate-limit aware: each call records remaining quota; if remaining < 50, sleep
until x-ratelimit-reset.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

API_BASE = "https://api.github.com"
TOKEN_FILE = Path.home() / ".config" / "claude" / "mcp.env"
MIN_REMAINING_BEFORE_SLEEP = 50

_token_cache: str | None = None


def _load_token() -> str:
    global _token_cache
    if _token_cache is not None:
        return _token_cache
    if not TOKEN_FILE.is_file():
        raise RuntimeError(f"Token file missing: {TOKEN_FILE}")
    for line in TOKEN_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("GITHUB_PERSONAL_ACCESS_TOKEN="):
            _token_cache = line.split("=", 1)[1].strip()
            return _token_cache
    raise RuntimeError(f"GITHUB_PERSONAL_ACCESS_TOKEN= not found in {TOKEN_FILE}")


@dataclass
class RateState:
    limit: int = 0
    remaining: int = 0
    reset_epoch: int = 0

    def maybe_sleep(self) -> None:
        if self.remaining and self.remaining < MIN_REMAINING_BEFORE_SLEEP:
            sleep_for = max(0, self.reset_epoch - int(time.time()) + 5)
            if sleep_for > 0:
                print(f"[gh_client] rate-limit low ({self.remaining}); sleeping {sleep_for}s")
                time.sleep(sleep_for)


_rate = RateState()


def _request(url: str, *, accept: str = "application/vnd.github+json") -> tuple[bytes, dict]:
    _rate.maybe_sleep()
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {_load_token()}",
            "Accept": accept,
            "User-Agent": "capstone-c4-fetcher/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            headers = dict(resp.headers)
    except urllib.error.HTTPError as e:
        body = e.read()
        headers = dict(e.headers) if e.headers else {}
        try:
            msg = json.loads(body).get("message", "")
        except Exception:
            msg = body[:200].decode("utf-8", errors="replace")
        raise GhApiError(e.code, msg, url) from None

    if "X-RateLimit-Limit" in headers:
        _rate.limit = int(headers["X-RateLimit-Limit"])
        _rate.remaining = int(headers.get("X-RateLimit-Remaining", _rate.remaining))
        _rate.reset_epoch = int(headers.get("X-RateLimit-Reset", _rate.reset_epoch))
    return body, headers


class GhApiError(RuntimeError):
    def __init__(self, status: int, message: str, url: str) -> None:
        super().__init__(f"GitHub API {status}: {message} [{url}]")
        self.status = status
        self.message = message
        self.url = url


def rate_state() -> RateState:
    return _rate


@lru_cache(maxsize=64)
def get_repo_tree(owner: str, repo: str, ref: str = "main") -> tuple[dict, ...]:
    """Return all entries (recursive). Each entry: {path, type, size?}."""
    url = f"{API_BASE}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1"
    body, _ = _request(url)
    data = json.loads(body)
    if data.get("truncated"):
        print(f"[gh_client] WARNING repo tree truncated for {owner}/{repo}@{ref}")
    return tuple(data.get("tree", []))


def get_default_branch(owner: str, repo: str) -> str:
    """Returns 'main' / 'master' / etc."""
    url = f"{API_BASE}/repos/{owner}/{repo}"
    body, _ = _request(url)
    data = json.loads(body)
    return data.get("default_branch", "main")


def get_file_raw(owner: str, repo: str, path: str, ref: str = "main") -> str:
    """Return file contents (UTF-8 text). Uses Accept: vnd.github.raw."""
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}?ref={ref}"
    body, _ = _request(url, accept="application/vnd.github.raw")
    return body.decode("utf-8", errors="replace")


def get_issue(owner: str, repo: str, number: int) -> dict[str, Any]:
    """Return {title, body, state, html_url}."""
    url = f"{API_BASE}/repos/{owner}/{repo}/issues/{number}"
    body, _ = _request(url)
    data = json.loads(body)
    return {
        "title": data.get("title", ""),
        "body": data.get("body", "") or "",
        "state": data.get("state", ""),
        "html_url": data.get("html_url", ""),
    }
