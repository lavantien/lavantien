"""Aggregation of gh repo-list items into table rows and language byte sums.

Ported from the inline python of .github/workflows/update-readme.yml.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, replace

from scripts import config


@dataclass(frozen=True)
class Repo:
    name: str
    stars: int
    description: str
    year: int
    stars_display: str = ""
    no_ai: bool = False


@dataclass(frozen=True)
class Aggregation:
    repos: list[Repo]
    lang_sizes: dict[str, int]


def aggregate(items: Iterable[dict]) -> Aggregation:
    """Fold gh repo-list items into table rows and language byte sums.

    Profile stats cover public work only; gh reports the GraphQL enum
    ("PUBLIC"), a missing visibility is treated as private so a shape
    change can never leak it. The no-AI cutoff is the creation timestamp
    of the reference repo in this batch: ISO 8601 Z strings compare
    correctly as text, and strictly-before wins so the reference repo
    itself is never badged.
    """
    items = list(items)
    repos: list[Repo] = []
    lang_sizes: dict[str, int] = {}
    cutoff = next(
        (i["createdAt"] for i in items if i["name"] == config.NO_AI_REFERENCE_REPO),
        None,
    )
    for item in items:
        if item["isFork"] or item["isArchived"]:
            continue
        if str(item.get("visibility", "")).upper() != "PUBLIC":
            continue
        repos.append(Repo(
            name=item["name"],
            stars=item["stargazerCount"],
            description=item.get("description") or "",
            year=int(item["createdAt"][:4]),
            no_ai=cutoff is not None and item["createdAt"] < cutoff,
        ))
        for lang in item.get("languages") or []:
            name = lang["node"]["name"]
            lang_sizes[name] = lang_sizes.get(name, 0) + lang.get("size", 0)
    return Aggregation(repos=repos, lang_sizes=lang_sizes)


def top_languages(
    lang_sizes: Mapping[str, int],
    *,
    allow: Collection[str] = config.PROG_LANGS,
    n: int = config.TOP_N,
) -> list[tuple[str, int]]:
    return sorted(
        ((name, size) for name, size in lang_sizes.items() if name in allow and size > 0),
        key=lambda pair: (-pair[1], pair[0]),
    )[:n]


def select_rows(
    repos: list[Repo],
    *,
    star_fetch: Callable[[str], int],
) -> list[Repo]:
    """Build the table rows: pinned entries first at their fixed years
    (a pinned repo missing from the aggregate is rebuilt from its config
    entry with a live star fetch, so it never drops), then the free
    market sorted by stars filling up to the table limit. Pinned years
    always win over createdAt; stars and the derived no-AI flag stay
    live from the snapshot unless the config entry pins them."""
    by_name = {r.name: r for r in repos}
    rows: list[Repo] = []
    for entry in config.PINNED_REPOS:
        match = by_name.get(entry["name"])
        if match is not None:
            row = replace(match, year=entry["year"])
        else:
            row = Repo(
                name=entry["name"],
                stars=star_fetch(f"{config.GH_OWNER}/{entry['name']}") or 0,
                description=entry.get("description", ""),
                year=entry["year"],
            )
        if "no_ai" in entry:
            row = replace(row, no_ai=entry["no_ai"])
        if "stars_prefix" in entry:
            row = replace(row, stars_display=f"{entry['stars_prefix']}+{row.stars}")
        rows.append(row)
    pinned_names = {entry["name"] for entry in config.PINNED_REPOS}
    remaining = sorted(
        (r for r in repos
         if r.name not in config.EXCLUDED_REPO_NAMES and r.name not in pinned_names),
        key=lambda r: (-r.stars, r.name),
    )[: max(0, config.TABLE_REPO_LIMIT - len(rows))]
    rows.extend(remaining)
    return rows
