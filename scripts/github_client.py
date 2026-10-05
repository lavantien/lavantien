"""Thin gh CLI client: repo listing, fixture loading, star lookups.

gh reads GH_TOKEN from the inherited environment automatically.
"""

from __future__ import annotations

import json
import subprocess
import sys

from scripts import config

_EXCERPT_LEN = 200
_STAR_ATTEMPTS = 2


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


def fetch_star_count(full_name: str, gh_exec: str = "gh") -> int:
    # one retry: a transient gh failure must not zero the fixed repo's
    # stars for a day (the readme commits whatever we return)
    for _ in range(_STAR_ATTEMPTS):
        try:
            proc = _run(gh_exec, [
                "repo", "view", full_name,
                "--json", "stargazerCount", "--jq", ".stargazerCount",
            ])
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0:
            count = proc.stdout.strip()
            return int(count) if count.isdigit() else 0
    return 0


def _record_main() -> int:
    # `make record` entry: print the public, non-fork repo items as json
    # so the committed fixture never carries private repo metadata,
    # whatever credential records it. Archived public repos stay: the
    # offline star stub needs them (the fixed first repo is archived).
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
