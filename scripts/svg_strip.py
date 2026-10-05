"""Render the top-languages line as a self-contained SVG document.

Plain text row: one devicon and a `Name <byte-count>` label per
language, laid out left to right at natural width. No segment
backgrounds, no proportional widths. Everything render-affecting comes
from scripts.config; local values are structural constants only.
"""

import math
import xml.etree.ElementTree as ET
from collections.abc import Sequence

from scripts import config

SVG_NS = "http://www.w3.org/2000/svg"
FALLBACK_VIEWBOX = "0 0 128 128"
ARIA_PREFIX = "Top languages: "
# element tags whose fill is recolored when it would vanish on dark
_RECOLOR_TAGS = frozenset(
    {"path", "polygon", "circle", "rect", "ellipse", "line", "polyline", "g"}
)


def format_bytes(b):
    # ported from .github/workflows/update-readme.yml, with the K->M
    # boundary fixed: a K count that rounds up to 1000 promotes to M
    if b >= 999_500:
        return f"{b / 1_000_000:.1f}M"
    if b >= 1_000:
        return f"{b / 1_000:.0f}K"
    return str(b)


def escape_xml(s):
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def estimate_text_width(text):
    total = 0.0
    for ch in text:
        if ch in config.XWIDE_CHARS:
            total += config.CHAR_WIDTH_XWIDE
        elif ch in config.NARROW_CHARS:
            total += config.CHAR_WIDTH_NARROW
        elif ch.isupper() or ch.isdigit():
            total += config.CHAR_WIDTH_WIDE
        else:
            total += config.CHAR_WIDTH_DEFAULT
    return math.ceil(total)


def _strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


def load_icon(name):
    pair = config.DEVICON_MAP.get(name)
    if pair is None:
        return None
    slug, variant = pair
    path = config.DEVICON_DIR / f"{slug}-{variant}.svg"
    if not path.is_file():
        return None
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None
    if _strip_ns(root.tag) != "svg":
        return None
    elements = list(root.iter())
    for elem in elements:
        if _strip_ns(elem.tag) == "script":
            return None
        if any("http" in value for value in elem.attrib.values()):
            return None
    view_box = root.get("viewBox")
    if not view_box:
        icon_w, icon_h = root.get("width"), root.get("height")
        view_box = f"0 0 {icon_w} {icon_h}" if icon_w and icon_h else FALLBACK_VIEWBOX
    # strip namespaces so the markup nests under the strip's own xmlns
    for elem in elements:
        elem.tag = _strip_ns(elem.tag)
        elem.attrib = {_strip_ns(key): value for key, value in elem.attrib.items()}
    # recolor fills that vanish on the github dark theme (default black,
    # explicit black, lua navy) to the language's brand color
    color = config.LANG_COLORS.get(name, config.DEFAULT_COLOR)
    for elem in elements:
        if _strip_ns(elem.tag) not in _RECOLOR_TAGS:
            continue
        fill = elem.get("fill")
        if fill is None or fill.strip().lower() in config.RECOLOR_FILLS:
            elem.set("fill", color)
    inner = "".join(ET.tostring(child, encoding="unicode") for child in root)
    try:
        ET.fromstring(f'<svg xmlns="{SVG_NS}">{inner}</svg>')
    except ET.ParseError:
        return None
    return inner, view_box


def _document_open(aria, width, height):
    esc = escape_xml(aria)
    return [
        f'<svg xmlns="{SVG_NS}" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{esc}">',
        f"  <title>{esc}</title>",
    ]


def _render_empty():
    label = config.EMPTY_LABEL
    width = 2 * config.PAD_X + estimate_text_width(label) + config.WIDTH_MARGIN
    height = config.STRIP_HEIGHT
    font = escape_xml(config.FONT_FAMILY)
    lines = _document_open(label, width, height)
    lines.append(
        f'  <text x="{width // 2}" y="{height // 2}" text-anchor="middle" '
        f'dominant-baseline="central" font-family="{font}" '
        f'font-size="{config.FONT_SIZE}" fill="{config.TEXT_MAIN}">'
        f"{escape_xml(label)}</text>"
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_strip(langs: Sequence[tuple[str, int]]) -> str:
    langs = list(langs)
    if not langs:
        return _render_empty()
    height = config.STRIP_HEIGHT
    font = escape_xml(config.FONT_FAMILY)
    icon_y = (height - config.ICON_SIZE) // 2
    y_mid = height // 2
    aria = ARIA_PREFIX + ", ".join(
        f"{name} {format_bytes(size)}" for name, size in langs
    )
    # measure first, then emit: the width depends on the content
    entries = []
    x = config.PAD_X
    for name, size in langs:
        label = f"{name} {format_bytes(size)}"
        advance = config.ICON_SIZE + config.LABEL_GAP + estimate_text_width(label)
        entries.append((name, label, x, x + config.ICON_SIZE + config.LABEL_GAP))
        x += advance + config.ENTRY_GAP
    width = x - config.ENTRY_GAP + config.PAD_X + config.WIDTH_MARGIN
    lines = _document_open(aria, width, height)
    for name, label, icon_x, text_x in entries:
        icon = load_icon(name)
        if icon is None:
            center = icon_x + config.ICON_SIZE // 2
            lines.append(
                f'  <text x="{center}" y="{y_mid}" text-anchor="middle" '
                f'dominant-baseline="central" font-family="{font}" '
                f'font-size="{config.ICON_SIZE}" '
                f'fill="{config.DEFAULT_COLOR}">{escape_xml(name[:1])}</text>'
            )
        else:
            inner, view_box = icon
            lines.append(
                f'  <svg x="{icon_x}" y="{icon_y}" '
                f'width="{config.ICON_SIZE}" height="{config.ICON_SIZE}" '
                f"viewBox=\"{escape_xml(view_box)}\">{inner}</svg>"
            )
        lines.append(
            f'  <text x="{text_x}" y="{y_mid}" dominant-baseline="central" '
            f'font-family="{font}" font-size="{config.FONT_SIZE}" '
            f'fill="{config.TEXT_MAIN}">{escape_xml(label)}</text>'
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"
