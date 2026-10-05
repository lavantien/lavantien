"""Render the top-languages strip as a self-contained SVG document.

Everything render-affecting comes from scripts.config; the only local
values are the renderer's own structural constants (namespace, icon
viewBox fallback, clip id, aria prefix).
"""

import math
import xml.etree.ElementTree as ET
from collections.abc import Sequence

from scripts import config

SVG_NS = "http://www.w3.org/2000/svg"
FALLBACK_VIEWBOX = "0 0 128 128"
CLIP_ID = "strip-corners"
ARIA_PREFIX = "Top languages: "


def format_bytes(b):
    # ported verbatim from .github/workflows/update-readme.yml
    if b >= 1_000_000:
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
    return math.ceil(len(text) * config.CHAR_WIDTH)


def _channel(v):
    c = v / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color):
    r = _channel(int(hex_color[1:3], 16))
    g = _channel(int(hex_color[3:5], 16))
    b = _channel(int(hex_color[5:7], 16))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(a, b):
    lo, hi = sorted((a, b))
    return (hi + 0.05) / (lo + 0.05)


def pick_text_color(hex_color):
    # WCAG 2.x: compute the contrast ratio of both text tokens against the
    # fill and keep the higher, instead of a fixed 0.179 luminance split,
    # which mispicks mid-tone fills.
    fill = _relative_luminance(hex_color)
    light = _relative_luminance(config.TEXT_LIGHT)
    dark = _relative_luminance(config.TEXT_DARK)
    if _contrast_ratio(fill, light) > _contrast_ratio(fill, dark):
        return config.TEXT_LIGHT
    return config.TEXT_DARK


def compute_widths(sizes, total=config.TOTAL_WIDTH, minimum=config.MIN_SEGMENT_WIDTH):
    n = len(sizes)
    if n == 0:
        return []
    scale = sum(sizes)
    if scale <= 0:
        widths = [total / n] * n
    else:
        widths = [total * s / scale for s in sizes]
    widths = [max(w, minimum) for w in widths]
    # floor grants pushed the sum past total; take the excess back from the
    # segments with headroom, in proportion to that headroom
    overflow = sum(widths) - total
    headroom = sum(w - minimum for w in widths)
    if overflow > 0 and headroom > 0:
        widths = [w - overflow * (w - minimum) / headroom for w in widths]
        widths = [max(w, minimum) for w in widths]
    # largest-remainder rounding keeps the sum exact
    bases = [math.floor(w) for w in widths]
    remaining = total - sum(bases)
    order = sorted(range(n), key=lambda i: (-(widths[i] - bases[i]), i))
    for i in order[:remaining]:
        bases[i] += 1
    bases[-1] += total - sum(bases)  # residual, 0 in exact arithmetic
    return bases


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
        "  <defs>",
        f'    <clipPath id="{CLIP_ID}">',
        f'      <rect width="{width}" height="{height}" rx="{config.CORNER_RADIUS}"/>',
        "    </clipPath>",
        "  </defs>",
        f'  <g clip-path="url(#{CLIP_ID})">',
    ]


def _render_empty():
    width, height = config.TOTAL_WIDTH, config.STRIP_HEIGHT
    fill = config.DEFAULT_COLOR
    font = escape_xml(config.FONT_FAMILY)
    esc = escape_xml(config.EMPTY_LABEL)
    lines = _document_open(config.EMPTY_LABEL, width, height)
    lines.append(
        f'    <rect x="0" y="0" width="{width}" height="{height}" fill="{fill}"/>'
    )
    lines.append(
        f'    <text x="{width // 2}" y="{height // 2}" text-anchor="middle" '
        f'dominant-baseline="central" font-family="{font}" '
        f'font-size="{config.FONT_SIZE}" fill="{pick_text_color(fill)}">{esc}</text>'
    )
    lines.append("  </g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_strip(langs: Sequence[tuple[str, int]]) -> str:
    langs = list(langs)
    if not langs:
        return _render_empty()
    width_total, height = config.TOTAL_WIDTH, config.STRIP_HEIGHT
    widths = compute_widths([size for _, size in langs])
    aria = ARIA_PREFIX + ", ".join(
        f"{name} {format_bytes(size)}" for name, size in langs
    )
    lines = _document_open(aria, width_total, height)
    font = escape_xml(config.FONT_FAMILY)
    icon_y = (height - config.ICON_SIZE) // 2
    x = 0
    for (name, size), width in zip(langs, widths):
        fill = config.LANG_COLORS.get(name, config.DEFAULT_COLOR)
        lines.append(
            f'    <rect x="{x}" y="0" width="{width}" height="{height}" fill="{fill}"/>'
        )
        icon = load_icon(name)
        if icon is None:
            center = x + config.PAD_X + config.ICON_SIZE // 2
            lines.append(
                f'    <text x="{center}" y="{height // 2}" text-anchor="middle" '
                f'dominant-baseline="central" font-family="{font}" '
                f'font-size="{config.ICON_SIZE}" '
                f'fill="{pick_text_color(fill)}">{escape_xml(name[:1])}</text>'
            )
        else:
            inner, view_box = icon
            lines.append(
                f'    <svg x="{x + config.PAD_X}" y="{icon_y}" '
                f'width="{config.ICON_SIZE}" height="{config.ICON_SIZE}" '
                f"viewBox=\"{escape_xml(view_box)}\">{inner}</svg>"
            )
        label = f"{name} {format_bytes(size)}"
        needed = (
            2 * config.PAD_X + config.ICON_SIZE + config.LABEL_GAP + estimate_text_width(label)
        )
        if width >= needed:
            lines.append(
                f'    <text x="{x + config.PAD_X + config.ICON_SIZE + config.LABEL_GAP}" '
                f'y="{height // 2}" dominant-baseline="central" '
                f'font-family="{font}" font-size="{config.FONT_SIZE}" '
                f'fill="{pick_text_color(fill)}">{escape_xml(label)}</text>'
            )
        x += width
    lines.append("  </g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"
