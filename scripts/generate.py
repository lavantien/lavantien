"""Generator CLI: rebuild the languages SVG strip and the README stats.

Aggregation and rendering run to completion before the first byte hits
disk, so malformed data can never leave a half-updated artifact behind.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Callable
from datetime import datetime, timezone

# direct execution (make generate runs this file by path) puts scripts/
# on sys.path instead of the repo root, so the scripts package itself is
# unresolvable; bootstrap the root before importing it
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import config, github_client, readme_writer, svg_strip
from scripts.aggregate import aggregate, select_rows, top_languages


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
    return parser.parse_args(argv)


def _fixture_star_fetch(items: list[dict]) -> Callable[[str], int]:
    # offline stand-in for gh repo view: full-name star lookup over the
    # loaded items, including forked/archived ones the aggregate filters
    # out (the fixed first repo is archived yet still carries real stars)
    own = {
        f"{config.GH_OWNER}/{item['name']}": item["stargazerCount"]
        for item in items
    }

    def fetch(full_name: str) -> int:
        return own.get(full_name, 0)

    return fetch


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write_if_changed(path: pathlib.Path, content: str) -> bool:
    if path.is_file() and _read(path) == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    # bytes not text mode: artifacts stay LF on every platform
    path.write_bytes(content.encode("utf-8"))
    return True


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.live:
        items = github_client.fetch_repos()
    else:
        items = github_client.load_repos_json(args.from_json)
    agg = aggregate(items)
    star_fetch: Callable[[str], int] = (
        github_client.fetch_star_count if args.live else _fixture_star_fetch(items)
    )
    strip = svg_strip.render_strip(top_languages(agg.lang_sizes))
    updated_line = (
        f"{config.UPDATED_PREFIX}"
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    )
    readme_content = readme_writer.rewrite_readme(
        _read(args.readme),
        languages_block=readme_writer.build_languages_block(),
        repo_table=readme_writer.render_repo_table(
            select_rows(agg.repos, star_fetch=star_fetch)
        ),
        updated_line=updated_line,
    )
    svg_changed = _write_if_changed(args.svg, strip)
    readme_changed = _write_if_changed(args.readme, readme_content)
    for path, changed in ((args.svg, svg_changed), (args.readme, readme_changed)):
        print(f"{'changed' if changed else 'unchanged'}: {path}")
    changed_count = svg_changed + readme_changed
    print(f"done: {changed_count} changed, {2 - changed_count} unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
