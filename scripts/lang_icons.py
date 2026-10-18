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
    data = content.encode("utf-8")
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def render_icons(langs, directory) -> tuple[dict[str, str], list, list]:
    """Pure pass: language to img-src mapping plus (path, content)
    pairs, every document parsed and validated, nothing written. A
    language without a vendored icon is absent from the mapping (its
    chip renders text-only instead of dangling) and lands in the
    returned skipped list so the caller can trace the degradation.
    Two languages sharing one vendored icon (Hack and PHP both ride
    the php mark) get language-suffixed files so their brand colors
    never collapse onto one overwritten image."""
    names = sorted(name for name in langs if name in config.DEVICON_MAP)
    bases = {
        name: f"{config.DEVICON_MAP[name][0]}-{config.DEVICON_MAP[name][1]}.svg"
        for name in names
    }
    counts: dict[str, int] = {}
    for base in bases.values():
        counts[base] = counts.get(base, 0) + 1
    mapping: dict[str, str] = {}
    planned: list[tuple[pathlib.Path, str]] = []
    for name in names:
        content = svg_strip.render_icon_svg(name)
        if content is None:
            continue
        ET.fromstring(content)
        base = bases[name]
        if counts[base] > 1:
            suffix = "".join(ch for ch in name.lower() if ch.isalnum())
            base = f"{base[:-4]}-{suffix}.svg"
        mapping[name] = f"{config.LANG_ICONS_SRC_DIR}/{base}"
        planned.append((pathlib.Path(directory) / base, content))
    return mapping, planned, sorted(set(langs) - set(mapping))


def ensure_icons(langs, directory) -> tuple[dict[str, str], int]:
    """render_icons plus the writes: only missing or stale files change
    on disk, and the written count feeds the generator summary."""
    mapping, planned, _skipped = render_icons(langs, directory)
    changed = sum(write_if_changed(path, content) for path, content in planned)
    return mapping, changed
