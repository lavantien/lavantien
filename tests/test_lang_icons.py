import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

from scripts import config, svg_strip
from scripts.lang_icons import ensure_icons, render_icons, write_if_changed


class TestRenderIconSvg(unittest.TestCase):
    def test_recolor_applies_brand_color(self):
        content = svg_strip.render_icon_svg("Lua")
        fills = {e.get("fill") for e in ET.fromstring(content).iter()}
        self.assertIn(config.LANG_COLORS["Lua"], fills)
        self.assertNotIn("#000080", fills)

    def test_document_head_and_tail_exact(self):
        content = svg_strip.render_icon_svg("Go")
        self.assertTrue(content.startswith(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" '
            'width="14" height="14">'
        ))
        self.assertTrue(content.endswith("</svg>\n"))

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

    def test_alias_collision_keeps_distinct_files_and_colors(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            mapping, changed = ensure_icons({"Hack", "PHP"}, directory)
            self.assertEqual(changed, 2)
            self.assertNotEqual(mapping["Hack"], mapping["PHP"])
            self.assertEqual(
                sorted(p.name for p in directory.glob("*.svg")),
                ["php-plain-hack.svg", "php-plain-php.svg"],
            )
            hack = (directory / "php-plain-hack.svg").read_text(encoding="utf-8")
            php = (directory / "php-plain-php.svg").read_text(encoding="utf-8")
            self.assertIn(config.LANG_COLORS["Hack"], hack)
            self.assertIn(config.LANG_COLORS["PHP"], php)
            self.assertNotEqual(hack, php)

    def test_empty_language_set_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp) / "icons"
            self.assertEqual(ensure_icons(set(), directory), ({}, 0))
            self.assertFalse(directory.exists())


    def test_render_icons_reports_skipped_languages(self):
        with tempfile.TemporaryDirectory() as tmp:
            mapping, planned, skipped = render_icons(
                {"HTML", "Go"}, pathlib.Path(tmp) / "icons"
            )
            self.assertEqual(skipped, ["HTML"])
            self.assertEqual(list(mapping), ["Go"])
            self.assertEqual(len(planned), 1)


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

    def test_overwrites_file_with_invalid_utf8_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "f.svg"
            path.write_bytes(b"\xff\xfe<svg")
            self.assertTrue(write_if_changed(path, "ok\n"))
            self.assertEqual(path.read_bytes(), b"ok\n")


if __name__ == "__main__":
    unittest.main()
