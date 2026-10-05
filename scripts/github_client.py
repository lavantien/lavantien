"""Thin gh CLI client: repo listing, fixture loading, star lookups.

gh reads GH_TOKEN from the inherited environment automatically.
"""

from __future__ import annotations

import json
import subprocess

from scripts import config

_EXCERPT_LEN = 200


class GhError(RuntimeError):
    pass


def _excerpt(text: str) -> str:
    return text.strip()[:_EXCERPT_LEN]


def _run(gh_exec: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([gh_exec, *args], capture_output=True, text=True)


def fetch_repos(gh_exec: str = "gh") -> list[dict]:
    try:
        proc = _run(gh_exec, [
            "repo", "list", "--limit", str(config.GH_REPO_LIMIT),
            "--json", config.GH_JSON_FIELDS,
        ])
    except OSError as exc:
        raise GhError(f"cannot run gh repo list via {gh_exec!r}: {exc}") from exc
    if proc.returncode != 0:
        detail = _excerpt(proc.stderr) or _excerpt(proc.stdout)
        raise GhError(f"gh repo list exited {proc.returncode}: {detail}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise GhError(f"gh repo list returned invalid json: {_excerpt(proc.stdout)}") from exc


def load_repos_json(path) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise GhError(f"cannot load repos json from {path}: {exc}") from exc


def fetch_star_count(full_name: str, gh_exec: str = "gh") -> int:
    try:
        proc = _run(gh_exec, [
            "repo", "view", full_name,
            "--json", "stargazerCount", "--jq", ".stargazerCount",
        ])
    except OSError:
        return 0
    if proc.returncode != 0:
        return 0
    count = proc.stdout.strip()
    return int(count) if count.isdigit() else 0
