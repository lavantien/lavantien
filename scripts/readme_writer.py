"""Idempotent, marker-based README rewrite.

Replaces the workflow heredoc that re-inserted content against an anchor
string that no longer matched, dropping badge rows on every run and
accumulating leading blank lines. All regions are keyed on stable
markers or structural spans, so a second pass is a byte-identical no-op.
"""

import re
from typing import Protocol, Sequence

from scripts import config

# hoist into scripts/config.py when that file is editable in this effort
REPO_URL_BASE = "https://github.com/lavantien"

_TABLE_RE = re.compile(r"<table>.*?</table>", re.DOTALL)
_STRAY_MARKERS = frozenset((config.MARKER_START, config.MARKER_END))


class RepoLike(Protocol):
    name: str
    stars: int
    description: str
    year: int


def build_languages_block() -> str:
    img = (
        f'<p align="center"><img src="{config.README_IMG_SRC}"'
        f' alt="{config.README_ALT_TEXT}"'
        f' width="{config.README_IMG_WIDTH}"></p>'
    )
    return "\n".join((config.MARKER_START, img, config.MARKER_END))


def render_repo_table(rows: Sequence[RepoLike]) -> str:
    lines = ["<table>"]
    for i in range(0, len(rows), 2):
        cells = "".join(_repo_cell(row) for row in rows[i : i + 2])
        lines.append(f"<tr>{cells}</tr>")
    lines.append("</table>")
    return "\n".join(lines)


def _repo_cell(row: RepoLike) -> str:
    link = (
        f'<td><a href="{REPO_URL_BASE}/{row.name}">{row.name}</a>'
        f" (<i>{row.year}</i>) (<b>{row.stars}⭐</b>)</td>"
    )
    return f"{link}<td>{row.description}</td>"


def normalize(content: str) -> str:
    lines = content.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def replace_between(content: str, start_marker: str, end_marker: str, block: str) -> str:
    span = _find_span(content, start_marker, end_marker)
    if span is None:
        return content
    start, end = span
    return content[:start] + block + content[end:]


def _find_span(content: str, start_marker: str, end_marker: str) -> tuple[int, int] | None:
    start = content.find(start_marker)
    if start == -1:
        return None
    end = content.find(end_marker, start + len(start_marker))
    if end == -1:
        return None
    return start, end + len(end_marker)


def rewrite_readme(
    content: str,
    *,
    languages_block: str,
    repo_table: str,
    updated_line: str,
) -> str:
    content = normalize(content)
    content = _apply_languages(content, languages_block)
    content = _apply_table(content, repo_table)
    content = _apply_updated(content, updated_line)
    return normalize(content)


def _apply_languages(content: str, languages_block: str) -> str:
    if _find_span(content, config.MARKER_START, config.MARKER_END) is not None:
        return replace_between(
            content, config.MARKER_START, config.MARKER_END, languages_block
        )
    kept = [ln for ln in content.split("\n") if ln.strip() not in _STRAY_MARKERS]
    return languages_block + "\n\n" + "\n".join(kept)


def _apply_table(content: str, repo_table: str) -> str:
    match = _TABLE_RE.search(content)
    if match is not None:
        return content[: match.start()] + repo_table + content[match.end() :]
    lines = content.split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith(config.UPDATED_PREFIX):
            lines[i:i] = repo_table.split("\n") + [""]
            return "\n".join(lines)
    return content.rstrip("\n") + "\n\n" + repo_table + "\n"


def _apply_updated(content: str, updated_line: str) -> str:
    lines = content.split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith(config.UPDATED_PREFIX):
            lines[i] = updated_line
            return "\n".join(lines)
    return content.rstrip("\n") + "\n\n" + updated_line + "\n"
