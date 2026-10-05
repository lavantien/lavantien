import math
import os
import unittest
import xml.etree.ElementTree as ET

from scripts import config, svg_strip

SVG_NS = "http://www.w3.org/2000/svg"

GOLDEN_LANGS = [
    ("Go", 2221713),
    ("Java", 480000),
    ("JavaScript", 168384),
    ("Python", 140000),
    ("C", 120000),
    ("TypeScript", 95000),
    ("Kotlin", 75000),
    ("Ruby", 75000),
    ("Lua", 50000),
    ("F#", 13000),
]

NORMAL = [("Go", 2221713), ("JavaScript", 168384), ("Lua", 50000)]


def strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


def parse(text):
    return ET.fromstring(text)


def segments(root, local):
    group = root.find(f"{{{SVG_NS}}}g")
    return [e for e in group if strip_ns(e.tag) == local]


def iter_local(root):
    for elem in root.iter():
        yield strip_ns(elem.tag), elem


def icon_path(name):
    slug, variant = config.DEVICON_MAP[name]
    return config.DEVICON_DIR / f"{slug}-{variant}.svg"


class TestFormatBytes(unittest.TestCase):
    def test_ported_boundaries(self):
        cases = [
            (0, "0"),
            (999, "999"),
            (1000, "1K"),
            (12000, "12K"),
            (480000, "480K"),
            (999999, "1000K"),
            (1000000, "1.0M"),
            (2221713, "2.2M"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(svg_strip.format_bytes(value), expected)


class TestHelpers(unittest.TestCase):
    def test_escape_xml(self):
        self.assertEqual(
            svg_strip.escape_xml('a&b<c>d"e\'f'),
            "a&amp;b&lt;c&gt;d&quot;e&apos;f",
        )

    def test_estimate_text_width(self):
        self.assertEqual(
            svg_strip.estimate_text_width("Go 2.2M"), math.ceil(7 * config.CHAR_WIDTH)
        )
        self.assertEqual(
            svg_strip.estimate_text_width("abc"), math.ceil(3 * config.CHAR_WIDTH)
        )

    def test_pick_text_color(self):
        # higher-contrast rule: Go #00ADD8 is a mid-tone (L~0.35) where dark
        # text wins 6.3:1 over white 2.6:1, so it maps to TEXT_DARK
        cases = [
            (config.LANG_COLORS["JavaScript"], config.TEXT_DARK),
            (config.LANG_COLORS["Go"], config.TEXT_DARK),
            (config.LANG_COLORS["Java"], config.TEXT_LIGHT),
            ("#FFFFFF", config.TEXT_DARK),
            ("#000000", config.TEXT_LIGHT),
        ]
        for fill, expected in cases:
            with self.subTest(fill=fill):
                self.assertEqual(svg_strip.pick_text_color(fill), expected)


class TestComputeWidths(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(svg_strip.compute_widths([]), [])

    def test_sum_exact_and_floored(self):
        cases = [
            [5000, 3000, 2000],
            [1000000, 500, 400, 300, 200, 100],
            [7],
        ]
        for sizes in cases:
            with self.subTest(sizes=sizes):
                widths = svg_strip.compute_widths(sizes)
                self.assertEqual(len(widths), len(sizes))
                self.assertEqual(sum(widths), config.TOTAL_WIDTH)
                self.assertTrue(all(w >= config.MIN_SEGMENT_WIDTH for w in widths))

    def test_proportional_in_headroom(self):
        sizes = [5000, 3000, 2000]
        widths = svg_strip.compute_widths(sizes)
        denom = sum(sizes)
        for size, width in zip(sizes, widths):
            self.assertLessEqual(
                abs(width - config.TOTAL_WIDTH * size / denom), 2, (size, width)
            )

    def test_floor_grants_come_from_headroom(self):
        sizes = [1000000, 500, 400, 300, 200, 100]
        widths = svg_strip.compute_widths(sizes)
        ideal_head = config.TOTAL_WIDTH * sizes[0] / sum(sizes)
        self.assertLess(widths[0], ideal_head)
        self.assertGreater(widths[0], ideal_head - 6 * config.MIN_SEGMENT_WIDTH)
        self.assertEqual(widths[1:], [config.MIN_SEGMENT_WIDTH] * 5)


class TestLoadIcon(unittest.TestCase):
    def test_go_icon(self):
        icon = svg_strip.load_icon("Go")
        self.assertIsNotNone(icon)
        inner, view_box = icon
        source = ET.parse(icon_path("Go")).getroot()
        self.assertEqual(view_box, source.get("viewBox"))
        self.assertIn("<path", inner)
        ET.fromstring(f'<svg xmlns="{SVG_NS}">{inner}</svg>')

    def test_unknown_language_returns_none(self):
        self.assertIsNone(svg_strip.load_icon("Solidity"))

    def test_go_icon_inner_has_no_namespace_prefixes(self):
        inner, _ = svg_strip.load_icon("Go")
        self.assertNotIn("ns0:", inner)
        self.assertNotIn("http", inner)


class TestRenderStrip(unittest.TestCase):
    def test_parses_for_normal_single_and_empty(self):
        for langs in (NORMAL, [("Go", 2221713)], []):
            with self.subTest(langs=langs):
                root = parse(svg_strip.render_strip(langs))
                self.assertEqual(strip_ns(root.tag), "svg")
                self.assertEqual(root.get("width"), str(config.TOTAL_WIDTH))
                self.assertEqual(root.get("height"), str(config.STRIP_HEIGHT))
                self.assertEqual(
                    root.get("viewBox"),
                    f"0 0 {config.TOTAL_WIDTH} {config.STRIP_HEIGHT}",
                )
                self.assertEqual(root.get("role"), "img")

    def test_title_matches_aria_label(self):
        root = parse(svg_strip.render_strip([("Go", 2221713), ("Lua", 50000)]))
        expected = "Top languages: Go 2.2M, Lua 50K"
        self.assertEqual(root.get("aria-label"), expected)
        title = root.find(f"{{{SVG_NS}}}title")
        self.assertIsNotNone(title)
        self.assertEqual(title.text, expected)

    def test_no_external_references(self):
        text = svg_strip.render_strip(
            [("Go", 2221713), ("Solidity", 60000), ("JavaScript", 168384)]
        )
        root = parse(text)
        for local, elem in iter_local(root):
            self.assertNotEqual(local, "script")
            for value in elem.attrib.values():
                self.assertNotIn("http", value, local)
            if elem.text:
                self.assertNotIn("http", elem.text, local)
        self.assertEqual(text.count("http"), 1)
        self.assertIn(f'xmlns="{SVG_NS}"', text)

    def test_clip_path_rounds_ends(self):
        root = parse(svg_strip.render_strip(NORMAL))
        clip = root.find(f"{{{SVG_NS}}}defs/{{{SVG_NS}}}clipPath")
        self.assertIsNotNone(clip)
        clip_rect = clip.find(f"{{{SVG_NS}}}rect")
        self.assertEqual(clip_rect.get("rx"), str(config.CORNER_RADIUS))
        self.assertEqual(clip_rect.get("width"), str(config.TOTAL_WIDTH))
        group = root.find(f"{{{SVG_NS}}}g")
        self.assertTrue(group.get("clip-path", "").startswith("url(#"))

    def test_segment_count_matches_input(self):
        root = parse(svg_strip.render_strip(NORMAL))
        self.assertEqual(len(segments(root, "rect")), len(NORMAL))

    def test_widths_cumulative_and_exact(self):
        cases = [
            NORMAL,
            [("Go", 1000000), ("Lua", 1000), ("Java", 5000), ("C", 3000), ("F#", 2000)],
        ]
        for langs in cases:
            with self.subTest(langs=langs):
                root = parse(svg_strip.render_strip(langs))
                x = 0
                for rect in segments(root, "rect"):
                    self.assertEqual(rect.get("x"), str(x))
                    width = int(rect.get("width"))
                    self.assertGreaterEqual(width, config.MIN_SEGMENT_WIDTH)
                    x += width
                self.assertEqual(x, config.TOTAL_WIDTH)

    def test_fills_follow_language(self):
        root = parse(svg_strip.render_strip(NORMAL))
        rects = segments(root, "rect")
        for (name, _), rect in zip(NORMAL, rects):
            self.assertEqual(rect.get("fill"), config.LANG_COLORS[name])
        self.assertEqual(rects[0].get("height"), str(config.STRIP_HEIGHT))
        self.assertEqual(rects[0].get("y"), "0")

    def test_empty_input_renders_default_segment(self):
        root = parse(svg_strip.render_strip([]))
        rects = segments(root, "rect")
        self.assertEqual(len(rects), 1)
        self.assertEqual(rects[0].get("x"), "0")
        self.assertEqual(rects[0].get("width"), str(config.TOTAL_WIDTH))
        self.assertEqual(rects[0].get("fill"), config.DEFAULT_COLOR)
        texts = segments(root, "text")
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0].text, config.EMPTY_LABEL)
        self.assertEqual(texts[0].get("text-anchor"), "middle")
        self.assertEqual(root.get("aria-label"), config.EMPTY_LABEL)

    def test_icon_embedded_with_own_viewbox(self):
        langs = [("Go", 2221713), ("Java", 480000)]
        root = parse(svg_strip.render_strip(langs))
        icons = segments(root, "svg")
        self.assertEqual(len(icons), len(langs))
        go_source = ET.parse(icon_path("Go")).getroot()
        self.assertEqual(icons[0].get("viewBox"), go_source.get("viewBox"))
        self.assertEqual(icons[0].get("x"), str(config.PAD_X))
        self.assertEqual(
            icons[0].get("y"), str((config.STRIP_HEIGHT - config.ICON_SIZE) // 2)
        )
        self.assertEqual(icons[0].get("width"), str(config.ICON_SIZE))
        self.assertEqual(icons[0].get("height"), str(config.ICON_SIZE))
        self.assertGreater(len(list(icons[0])), 0)

    def test_label_content_and_position(self):
        root = parse(svg_strip.render_strip([("Go", 2221713)]))
        texts = segments(root, "text")
        self.assertEqual([t.text for t in texts], ["Go 2.2M"])
        label = texts[0]
        self.assertEqual(label.get("font-size"), str(config.FONT_SIZE))
        self.assertEqual(label.get("font-family"), config.FONT_FAMILY)
        self.assertEqual(label.get("dominant-baseline"), "central")
        self.assertEqual(label.get("y"), str(config.STRIP_HEIGHT // 2))
        icon_right = config.PAD_X + config.ICON_SIZE + svg_strip.LABEL_GAP
        self.assertEqual(label.get("x"), str(icon_right))
        self.assertEqual(
            label.get("fill"), svg_strip.pick_text_color(config.LANG_COLORS["Go"])
        )

    def test_label_dropped_when_segment_too_narrow(self):
        root = parse(svg_strip.render_strip([("Go", 1000000), ("Lua", 1000)]))
        rects = segments(root, "rect")
        self.assertEqual(len(rects), 2)
        self.assertEqual(rects[1].get("width"), str(config.MIN_SEGMENT_WIDTH))
        texts = segments(root, "text")
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0].text, "Go 1.0M")

    def test_missing_icon_falls_back_to_letter_tile(self):
        root = parse(svg_strip.render_strip([("Solidity", 60000)]))
        self.assertEqual(segments(root, "svg"), [])
        rects = segments(root, "rect")
        self.assertEqual(rects[0].get("fill"), config.DEFAULT_COLOR)
        texts = segments(root, "text")
        tiles = [t for t in texts if t.get("font-size") == str(config.ICON_SIZE)]
        self.assertEqual(len(tiles), 1)
        tile = tiles[0]
        self.assertEqual(tile.text, "S")
        self.assertEqual(tile.get("text-anchor"), "middle")
        center = config.PAD_X + config.ICON_SIZE // 2
        self.assertEqual(tile.get("x"), str(center))
        self.assertEqual(tile.get("y"), str(config.STRIP_HEIGHT // 2))
        # the label logic is independent of the icon fallback
        labels = [t for t in texts if t.get("font-size") == str(config.FONT_SIZE)]
        self.assertEqual([t.text for t in labels], ["Solidity 60K"])

    def test_deterministic_bytes(self):
        first = svg_strip.render_strip(NORMAL)
        second = svg_strip.render_strip(list(NORMAL))
        self.assertEqual(first, second)
        self.assertNotIn("\r", first)
        self.assertTrue(first.endswith("\n"))
        self.assertFalse(first.endswith("\n\n"))


class TestGolden(unittest.TestCase):
    def test_matches_golden_file(self):
        actual = svg_strip.render_strip(GOLDEN_LANGS).encode("utf-8")
        if os.environ.get("UPDATE_GOLDEN"):
            config.GOLDEN_SVG.parent.mkdir(parents=True, exist_ok=True)
            config.GOLDEN_SVG.write_bytes(actual)
            return
        self.assertTrue(
            config.GOLDEN_SVG.exists(),
            "golden file missing; run UPDATE_GOLDEN=1 make test",
        )
        self.assertEqual(actual, config.GOLDEN_SVG.read_bytes())


if __name__ == "__main__":
    unittest.main()
