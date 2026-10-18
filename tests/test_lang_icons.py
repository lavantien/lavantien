import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

from scripts import config, svg_strip
from scripts.lang_icons import ensure_icons, write_if_changed


class TestRenderIconSvg(unittest.TestCase):
    def test_recolor_applies_brand_color(self):
        content = svg_strip.render_icon_svg("Lua")
        fills = {e.get("fill") for e in ET.fromstring(content).iter()}
        self.assertIn(config.LANG_COLORS["Lua"], fills)
        self.assertNotIn("#000080", fills)

    def test_document_head_and_tail_exact(self):
        content = svg_strip.render_icon_svg("Go")
        self.assertTrue(content.startswith(
            f'<svg xmlns="{svg_strip.SVG_NS}" viewBox="0 0 128 128" '
            f'width="{config.TABLE_LANG_ICON_SIZE}" '
            f'height="{config.TABLE_LANG_ICON_SIZE}">'
        ))
        self.assertTrue(content.endswith("</svg>\n"))

    def test_size_attributes_come_from_config(self):
        content = svg_strip.render_icon_svg("Go")
        root = ET.fromstring(content)
        self.assertEqual(
            (root.get("width"), root.get("height")),
            (str(config.TABLE_LANG_ICON_SIZE), str(config.TABLE_LANG_ICON_SIZE)),
        )

    def test_unmapped_language_returns_none(self):
        self.assertIsNone(svg_strip.render_icon_svg("HTML"))

    def test_missing_icon_file_returns_none(self):
        with mock.patch.object(config, "DEVICON_MAP", {"Ghost": ("ghost", "plain")}):
            self.assertIsNone(svg_strip.render_icon_svg("Ghost"))


class TestEnsureIcons(unittest.TestCase):
    def test_writes_valid_svgs_and_returns_src_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp) / "nested"
            mapping, changed = ensure_icons({"Go", "Lua"}, directory)
            self.assertEqual(mapping, {
                "Go": f"{config.LANG_ICONS_SRC_DIR}/go-plain.svg",
                "Lua": f"{config.LANG_ICONS_SRC_DIR}/lua-plain.svg",
            })
            self.assertEqual(changed, 2)
            self.assertEqual(
                sorted(p.name for p in directory.glob("*.svg")),
                ["go-plain.svg", "lua-plain.svg"],
            )
            for rel in mapping.values():
                ET.fromstring((directory / pathlib.PurePosixPath(rel).name)
                              .read_text(encoding="utf-8"))

    def test_second_run_rewrites_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            first = ensure_icons({"Go"}, directory)
            second = ensure_icons({"Go"}, directory)
            self.assertEqual(first[0], second[0])
            self.assertEqual(second[1], 0)

    def test_unmapped_language_is_absent_from_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            mapping, changed = ensure_icons({"HTML", "Go"}, directory)
            self.assertEqual(list(mapping), ["Go"])
            self.assertEqual(changed, 1)
            self.assertEqual(
                [p.name for p in directory.glob("*.svg")], ["go-plain.svg"]
            )

    def test_empty_language_set_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp) / "icons"
            self.assertEqual(ensure_icons(set(), directory), ({}, 0))
            self.assertFalse(directory.exists())


class TestWriteIfChanged(unittest.TestCase):
    def test_writes_and_reports_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "sub" / "f.svg"
            self.assertTrue(write_if_changed(path, "a\n"))
            self.assertEqual(path.read_text(encoding="utf-8"), "a\n")

    def test_same_content_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "f.svg"
            write_if_changed(path, "a\n")
            self.assertFalse(write_if_changed(path, "a\n"))


if __name__ == "__main__":
    unittest.main()
