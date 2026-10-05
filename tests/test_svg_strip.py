import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from scripts import config, svg_strip

SAMPLE = [
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

SVG_NS = "{http://www.w3.org/2000/svg}"


def parse(svg):
    return ET.fromstring(svg)


def strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


def iter_all(root):
    return list(root.iter())


def nested_icons(root):
    # root itself is an <svg>; icons are the nested ones
    return [e for e in root.iter() if strip_ns(e.tag) == "svg" and e is not root]


class TestFormatBytes(unittest.TestCase):
    def test_boundaries(self):
        # literals, not config-derived, so constant mutants cannot hide
        self.assertEqual(svg_strip.format_bytes(0), "0")
        self.assertEqual(svg_strip.format_bytes(999), "999")
        self.assertEqual(svg_strip.format_bytes(1000), "1K")
        self.assertEqual(svg_strip.format_bytes(999_999), "1000K")
        self.assertEqual(svg_strip.format_bytes(1_000_000), "1.0M")
        self.assertEqual(svg_strip.format_bytes(1_050_000), "1.1M")
        self.assertEqual(svg_strip.format_bytes(480_000), "480K")
        self.assertEqual(svg_strip.format_bytes(2_221_713), "2.2M")


class TestEstimateTextWidth(unittest.TestCase):
    def test_literals(self):
        # CHAR_WIDTH is 7.0: expectations are literal so a config mutant fails
        self.assertEqual(svg_strip.estimate_text_width(""), 0)
        self.assertEqual(svg_strip.estimate_text_width("Go"), 14)
        self.assertEqual(svg_strip.estimate_text_width("No language data"), 112)
        self.assertEqual(svg_strip.estimate_text_width("Go 2.2M"), 49)


class TestEscapeXml(unittest.TestCase):
    def test_all_specials(self):
        self.assertEqual(
            svg_strip.escape_xml('a<b>&"c\''),
            "a&lt;b&gt;&amp;&quot;c&apos;",
        )

    def test_plain_passthrough(self):
        self.assertEqual(svg_strip.escape_xml("Go 2.2M"), "Go 2.2M")


class TestLoadIcon(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        patcher = mock.patch.object(config, "DEVICON_DIR", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def write(self, name, content):
        (self.dir / name).write_text(content, encoding="utf-8")

    def test_known_icon_loads_with_viewbox(self):
        self.write(
            "go-plain.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'
            '<path d="M0 0h1v1z"/></svg>',
        )
        inner, view_box = svg_strip.load_icon("Go")
        self.assertEqual(view_box, "0 0 128 128")
        self.assertIn("<path", inner)
        # nested markup must re-parse under the strip namespace
        ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{inner}</svg>')

    def test_viewbox_synthesized_from_width_height(self):
        self.write(
            "go-plain.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">'
            '<rect width="24" height="24"/></svg>',
        )
        _, view_box = svg_strip.load_icon("Go")
        self.assertEqual(view_box, "0 0 24 24")

    def test_viewbox_fallback_when_neither(self):
        self.write(
            "go-plain.svg",
            '<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>',
        )
        _, view_box = svg_strip.load_icon("Go")
        self.assertEqual(view_box, "0 0 128 128")

    def test_viewbox_fallback_when_only_one_dimension(self):
        # width without height (and vice versa) cannot synthesize a viewBox
        self.write(
            "go-plain.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" width="24"><rect/></svg>',
        )
        self.assertEqual(svg_strip.load_icon("Go")[1], "0 0 128 128")
        self.write(
            "go-plain.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" height="24"><rect/></svg>',
        )
        self.assertEqual(svg_strip.load_icon("Go")[1], "0 0 128 128")

    def test_missing_file_returns_none(self):
        self.assertIsNone(svg_strip.load_icon("Go"))

    def test_unknown_language_returns_none(self):
        self.assertIsNone(svg_strip.load_icon("Solidity"))

    def test_parse_error_returns_none(self):
        self.write("go-plain.svg", "<svg><path")
        self.assertIsNone(svg_strip.load_icon("Go"))

    def test_wrong_root_tag_returns_none(self):
        self.write("go-plain.svg", '<g xmlns="http://www.w3.org/2000/svg"/>')
        self.assertIsNone(svg_strip.load_icon("Go"))

    def test_script_element_returns_none(self):
        self.write(
            "go-plain.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'
            "<script>alert(1)</script></svg>",
        )
        self.assertIsNone(svg_strip.load_icon("Go"))

    def test_http_attribute_returns_none(self):
        self.write(
            "go-plain.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'
            '<image href="http://evil.example/x.png"/></svg>',
        )
        self.assertIsNone(svg_strip.load_icon("Go"))

    def test_namespaced_children_are_stripped(self):
        self.write(
            "go-plain.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'
            '<ns:path xmlns:ns="http://example.com/ns" d="M0 0"/></svg>',
        )
        inner, _ = svg_strip.load_icon("Go")
        self.assertIn("<path", inner)
        self.assertNotIn("ns:", inner)


class TestRenderStrip(unittest.TestCase):
    def test_parses_as_xml(self):
        for langs in (SAMPLE, [("Go", 2221713)], []):
            with self.subTest(n=len(langs)):
                parse(svg_strip.render_strip(langs))

    def test_no_external_references(self):
        root = parse(svg_strip.render_strip(SAMPLE))
        for elem in iter_all(root):
            for key, value in elem.attrib.items():
                if "http" in value:
                    self.assertEqual(
                        (strip_ns(key), value),
                        ("xmlns", "http://www.w3.org/2000/svg"),
                    )
            self.assertNotEqual(strip_ns(elem.tag), "script")

    def test_no_background_shapes(self):
        # plain text row: no segment rects, no clip paths, no defs
        root = parse(svg_strip.render_strip(SAMPLE))
        tags = {strip_ns(elem.tag) for elem in iter_all(root)}
        self.assertNotIn("rect", tags)
        self.assertNotIn("defs", tags)
        self.assertNotIn("clipPath", tags)

    def test_one_icon_and_label_per_language(self):
        root = parse(svg_strip.render_strip(SAMPLE))
        self.assertEqual(len(nested_icons(root)), len(SAMPLE))
        texts = [
            e for e in iter_all(root)
            if strip_ns(e.tag) == "text" and e.text and " " in e.text
        ]
        self.assertEqual(len(texts), len(SAMPLE))

    def test_layout_literals(self):
        # PAD_X=7, ICON_SIZE=16, LABEL_GAP=4, ENTRY_GAP=14: literal expectations
        svg = svg_strip.render_strip([("Go", 2221713)])
        root = parse(svg)
        self.assertEqual(root.get("width"), "83")  # 7 + 16 + 4 + 49 + 7
        self.assertEqual(root.get("height"), "28")
        self.assertEqual(root.get("viewBox"), "0 0 83 28")
        icon = nested_icons(root)[0]
        self.assertEqual(icon.get("x"), "7")
        label = next(e for e in iter_all(root) if strip_ns(e.tag) == "text")
        self.assertEqual(label.get("x"), "27")
        self.assertEqual(label.text, "Go 2.2M")
        self.assertEqual(label.get("fill"), config.TEXT_MAIN)

    def test_second_entry_offset(self):
        # entry 1 advance is 69, then ENTRY_GAP 14: icon 2 lands at x=90
        root = parse(svg_strip.render_strip([("Go", 2221713), ("C", 120000)]))
        icons = nested_icons(root)
        self.assertEqual(icons[1].get("x"), "90")
        texts = [e for e in iter_all(root) if strip_ns(e.tag) == "text"]
        self.assertEqual(texts[1].text, "C 120K")

    def test_title_matches_aria(self):
        root = parse(svg_strip.render_strip([("Go", 2221713)]))
        expected = "Top languages: Go 2.2M"
        self.assertEqual(root.get("aria-label"), expected)
        title = next(e for e in iter_all(root) if strip_ns(e.tag) == "title")
        self.assertEqual(title.text, expected)

    def test_unknown_language_letter_tile(self):
        svg = svg_strip.render_strip([("Solidity", 42000)])
        root = parse(svg)
        texts = [e for e in iter_all(root) if strip_ns(e.tag) == "text"]
        self.assertEqual(
            [(t.text, t.get("fill")) for t in texts],
            [("S", config.DEFAULT_COLOR), ("Solidity 42K", config.TEXT_MAIN)],
        )
        icons = nested_icons(root)
        self.assertEqual(icons, [])

    def test_letter_tile_document_exact_bytes(self):
        # full literal pin of the fallback path: tile centered in the icon
        # slot at 7 + 16//2 = 15, label at 27, entry width 7+16+4+84+7 = 118
        font = (
            "ui-sans-serif, system-ui, -apple-system, &apos;Segoe UI&apos;, "
            "Helvetica, Arial, sans-serif"
        )
        expected = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="118" height="28" '
            'viewBox="0 0 118 28" role="img" aria-label="Top languages: Solidity 42K">\n'
            "  <title>Top languages: Solidity 42K</title>\n"
            f'  <text x="15" y="14" text-anchor="middle" '
            f'dominant-baseline="central" font-family="{font}" '
            f'font-size="16" fill="#8b949e">S</text>\n'
            f'  <text x="27" y="14" dominant-baseline="central" '
            f'font-family="{font}" font-size="13" '
            f'fill="#6e7781">Solidity 42K</text>\n'
            "</svg>\n"
        )
        self.assertEqual(svg_strip.render_strip([("Solidity", 42000)]), expected)

    def test_deterministic(self):
        self.assertEqual(svg_strip.render_strip(SAMPLE), svg_strip.render_strip(SAMPLE))

    def test_empty_renders_placeholder(self):
        svg = svg_strip.render_strip([])
        root = parse(svg)
        self.assertEqual(root.get("width"), "126")  # 7 + 112 + 7
        self.assertEqual(root.get("height"), "28")
        text = next(e for e in iter_all(root) if strip_ns(e.tag) == "text")
        self.assertEqual(text.text, config.EMPTY_LABEL)
        self.assertEqual(text.get("text-anchor"), "middle")
        self.assertEqual(int(text.get("x")), 126 // 2)

    def test_empty_document_exact_bytes(self):
        # full literal pin: kills attribute/format mutants in the shared
        # document-open and empty-render paths
        expected = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="126" height="28" '
            'viewBox="0 0 126 28" role="img" aria-label="No language data">\n'
            "  <title>No language data</title>\n"
            '  <text x="63" y="14" text-anchor="middle" '
            'dominant-baseline="central" font-family="ui-sans-serif, system-ui, '
            "-apple-system, &apos;Segoe UI&apos;, Helvetica, Arial, sans-serif\" "
            'font-size="13" fill="#6e7781">No language data</text>\n'
            "</svg>\n"
        )
        self.assertEqual(svg_strip.render_strip([]), expected)

    def test_aria_and_label_escape_specials(self):
        svg = svg_strip.render_strip([('A"B&Co', 5)])
        self.assertIn(
            'aria-label="Top languages: A&quot;B&amp;Co 5"', svg
        )
        root = parse(svg)
        self.assertEqual(root.get("aria-label"), 'Top languages: A"B&Co 5')
        texts = [
            (t.text, t.get("fill")) for t in iter_all(root) if strip_ns(t.tag) == "text"
        ]
        self.assertEqual(
            texts,
            [("A", config.DEFAULT_COLOR), ('A"B&Co 5', config.TEXT_MAIN)],
        )

    def test_matches_golden_svg(self):
        svg = svg_strip.render_strip(SAMPLE)
        if os.environ.get("UPDATE_GOLDEN"):
            config.GOLDEN_SVG.write_bytes(svg.encode("utf-8"))
        self.assertEqual(svg, config.GOLDEN_SVG.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
