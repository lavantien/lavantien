"""Artifact writes and standalone recolored language icon files.

write_if_changed is the shared byte-exact artifact writer (bytes mode
keeps every artifact LF on every platform). ensure_icons materializes
one standalone svg per table language under the icons directory, so
README img tags never dangle and dark-theme-invisible brand fills get
the same recolor treatment as the strip.
"""

import pathlib
import xml.etree.ElementTree as ET

from scripts import config, svg_strip


def write_if_changed(path: pathlib.Path, content: str) -> bool:
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return True


def render_icons(langs, directory) -> tuple[dict[str, str], list]:
    """Pure pass: language to img-src mapping plus (path, content)
    pairs, every document parsed and validated, nothing written. A
    language without a vendored icon is absent from the mapping, so
    its chip renders text-only instead of dangling."""
    mapping: dict[str, str] = {}
    planned: list[tuple[pathlib.Path, str]] = []
    for name in sorted(langs):
        content = svg_strip.render_icon_svg(name)
        if content is None:
            continue
        ET.fromstring(content)
        slug, variant = config.DEVICON_MAP[name]
        mapping[name] = f"{config.LANG_ICONS_SRC_DIR}/{slug}-{variant}.svg"
        planned.append((pathlib.Path(directory) / f"{slug}-{variant}.svg", content))
    return mapping, planned


def ensure_icons(langs, directory) -> tuple[dict[str, str], int]:
    """render_icons plus the writes: only missing or stale files change
    on disk, and the written count feeds the generator summary."""
    mapping, planned = render_icons(langs, directory)
    changed = sum(write_if_changed(path, content) for path, content in planned)
    return mapping, changed
