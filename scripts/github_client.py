"""Thin gh CLI client: repo listing, fixture loading, snapshot lookups.

gh reads GH_TOKEN from the inherited environment automatically.
"""

from __future__ import annotations

import json
import subprocess
import sys

from scripts import config
from scripts.aggregate import item_top_langs

_EXCERPT_LEN = 200
_SNAPSHOT_ATTEMPTS = 2


class GhError(RuntimeError):
    pass


def _excerpt(text: str) -> str:
    return text.strip()[:_EXCERPT_LEN]


def _run(gh_exec: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [gh_exec, *args],
        capture_output=True,
        text=True,
        timeout=config.GH_TIMEOUT_SECONDS,
    )


def fetch_repos(gh_exec: str = "gh") -> list[dict]:
    try:
        proc = _run(gh_exec, [
            "repo", "list", "--limit", str(config.GH_REPO_LIMIT),
            "--json", config.GH_JSON_FIELDS,
        ])
    except OSError as exc:
        raise GhError(f"cannot run gh repo list via {gh_exec!r}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GhError(
            f"gh repo list timed out after {config.GH_TIMEOUT_SECONDS}s"
        ) from exc
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


def fetch_repo_snapshot(full_name: str, gh_exec: str = "gh") -> dict | None:
    """Live repo snapshot for a pinned repo missing from the aggregate.

    One retry: a transient gh failure must not strip a day of live data
    from the fixed repo (the readme commits whatever we return). A
    payload without an int stargazerCount or forkCount, or missing any
    of the other fields, is a total failure and yields None, so callers
    fall back to config values instead of half-built data.
    """
    for _ in range(_SNAPSHOT_ATTEMPTS):
        try:
            proc = _run(gh_exec, [
                "repo", "view", full_name,
                "--json", "stargazerCount,forkCount,description,"
                          "createdAt,languages",
            ])
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode != 0:
            continue
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        stars = data.get("stargazerCount")
        if isinstance(stars, bool) or not isinstance(stars, int):
            return None
        forks = data.get("forkCount")
        if isinstance(forks, bool) or not isinstance(forks, int):
            return None
        if "description" not in data or "createdAt" not in data:
            return None
        return {
            "stars": stars,
            "forks": forks,
            "description": data["description"] or "",
            "createdAt": data["createdAt"],
            "langs": item_top_langs(data),
        }
    return None


def _record_main() -> int:
    """`make record` entry: print the public, non-fork repo items as json
    so the committed fixture never carries private repo metadata,
    whatever credential records it. Archived public repos stay: the
    offline snapshot stub needs them (pinned repos can be archived)."""
    items = [
        item
        for item in fetch_repos()
        if not item["isFork"]
        and str(item.get("visibility", "")).upper() == "PUBLIC"
    ]
    sys.stdout.write(json.dumps(items, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_record_main())
