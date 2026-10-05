"""Aggregation of gh repo-list items into table rows and language byte sums.

Ported from the inline python of .github/workflows/update-readme.yml.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass

from scripts import config


@dataclass(frozen=True)
class Repo:
    name: str
    stars: int
    description: str
    year: int


@dataclass(frozen=True)
class Aggregation:
    repos: list[Repo]
    lang_sizes: dict[str, int]


def aggregate(items: Iterable[dict]) -> Aggregation:
    repos: list[Repo] = []
    lang_sizes: dict[str, int] = {}
    for item in items:
        if item["isFork"] or item["isArchived"]:
            continue
        repos.append(Repo(
            name=item["name"],
            stars=item["stargazerCount"],
            description=item.get("description") or "",
            year=config.YEAR_OVERRIDES.get(item["name"], int(item["createdAt"][:4])),
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
    fixed = config.FIXED_FIRST_REPO
    rows = [Repo(
        name=fixed["name"],
        stars=star_fetch(f"{config.GH_OWNER}/{fixed['name']}") or 0,
        description=fixed["description"],
        year=fixed["year"],
    )]
    seen = {rows[0].name}
    for pinned in config.PINNED_REPOS:
        match = next((r for r in repos if r.name == pinned), None)
        if match is not None:
            rows.append(match)
            seen.add(match.name)
    remaining = sorted(
        (r for r in repos
         if r.name not in config.EXCLUDED_REPO_NAMES and r.name not in seen),
        key=lambda r: (-r.stars, r.name),
    )[: max(0, config.TABLE_ROW_LIMIT - len(rows))]
    rows.extend(remaining)
    return rows
