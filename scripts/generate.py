"""Generator CLI: rebuild the languages SVG strip and the README stats.

Aggregation and rendering run to completion before the first byte hits
disk, so malformed data can never leave a half-updated artifact behind.
Direct execution (make generate runs this file by path) puts scripts/
on sys.path instead of the repo root, so the scripts package itself is
unresolvable; the root is bootstrapped onto sys.path before importing it.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Callable
from datetime import datetime, timezone

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import config, github_client, lang_icons, readme_writer, svg_strip
from scripts.aggregate import (
    aggregate,
    item_top_langs,
    select_rows,
    top_languages,
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenerate the top-languages SVG strip and README stats."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--from-json", metavar="PATH", type=pathlib.Path,
        help="read repo items from a recorded gh repo-list json file",
    )
    source.add_argument(
        "--live", action="store_true",
        help="fetch repo items live via the gh cli",
    )
    parser.add_argument(
        "--readme", type=pathlib.Path, default=config.READ_PATH,
        help="readme file to rewrite (default: %(default)s)",
    )
    parser.add_argument(
        "--svg", type=pathlib.Path, default=config.SVG_PATH,
        help="svg artifact to write (default: %(default)s)",
    )
    parser.add_argument(
        "--icons-dir", type=pathlib.Path, default=config.LANG_ICONS_DIR,
        help="directory for standalone language icons (default: %(default)s)",
    )
    return parser.parse_args(argv)


def _fixture_snapshot_fetch(items: list[dict]) -> Callable[[str], dict | None]:
    """Offline stand-in for gh repo view: full-name snapshot lookup over
    the loaded items, including forked/archived ones the aggregate
    filters out (an archived pinned repo still carries real data)."""
    own = {
        f"{config.GH_OWNER}/{item['name']}": {
            "stars": item["stargazerCount"],
            "description": item.get("description") or "",
            "createdAt": item["createdAt"],
            "langs": item_top_langs(item),
        }
        for item in items
    }

    def fetch(full_name: str) -> dict | None:
        return own.get(full_name)

    return fetch


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.live:
        items = github_client.fetch_repos()
    else:
        items = github_client.load_repos_json(args.from_json)
    agg = aggregate(items)
    snapshot_fetch: Callable[[str], dict | None] = (
        github_client.fetch_repo_snapshot if args.live
        else _fixture_snapshot_fetch(items)
    )
    rows = select_rows(
        agg.repos, snapshot_fetch=snapshot_fetch, cutoff=agg.no_ai_cutoff
    )
    icon_srcs, icon_plans, skipped_icons = lang_icons.render_icons(
        {name for row in rows for name, _ in row.top_langs}, args.icons_dir
    )
    for name in skipped_icons:
        print(f"warning: no vendored icon for {name}; chip renders text-only")
    strip = svg_strip.render_strip(top_languages(agg.lang_sizes))
    updated_line = (
        f"{config.UPDATED_PREFIX}"
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        f"{config.UPDATED_SUFFIX}"
    )
    readme_content = readme_writer.rewrite_readme(
        _read(args.readme),
        languages_block=readme_writer.build_languages_block(),
        repo_table=readme_writer.render_repo_table(rows, icon_srcs=icon_srcs),
        updated_line=updated_line,
    )
    reports = [(args.svg, strip), (args.readme, readme_content), *icon_plans]
    changed_count = 0
    for path, content in reports:
        changed = lang_icons.write_if_changed(path, content)
        changed_count += changed
        print(f"{'changed' if changed else 'unchanged'}: {path}")
    print(f"done: {changed_count} changed, {len(reports) - changed_count} unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
