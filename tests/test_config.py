import re
import unittest

from scripts import config

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

SOURCE_KEYS = {"repo", "raw_base", "pinned_ref", "icon_path", "license_path"}


class TestConfig(unittest.TestCase):
    def test_prog_langs_have_colors_and_icons(self):
        self.assertEqual(config.PROG_LANGS, frozenset(config.LANG_COLORS))
        self.assertEqual(config.PROG_LANGS, frozenset(config.DEVICON_MAP))

    def test_colors_are_hex(self):
        for lang, color in config.LANG_COLORS.items():
            self.assertRegex(color, HEX_RE, lang)
        for value in (config.DEFAULT_COLOR, config.TEXT_MAIN):
            self.assertRegex(value, HEX_RE)

    def test_devicon_pairs_shape(self):
        for lang, (slug, variant) in config.DEVICON_MAP.items():
            self.assertRegex(slug, r"^[a-z0-9]+$", lang)
            self.assertRegex(variant, r"^[a-z-]+$", lang)

    def test_repo_paths_resolve_to_real_files(self):
        self.assertTrue(config.READ_PATH.exists())
        self.assertTrue(config.FIXTURE_RECORDED.exists())
        self.assertTrue(config.FIXTURE_SAMPLE.exists())
        self.assertTrue(config.FIXTURE_README_MESSY.exists())


class TestIconSources(unittest.TestCase):
    def test_sources_have_full_shape(self):
        for name, source in config.ICON_SOURCES.items():
            self.assertEqual(set(source), SOURCE_KEYS, name)
            self.assertTrue(source["repo"].startswith("https://github.com/"), name)
            self.assertTrue(
                source["raw_base"].startswith("https://raw.githubusercontent.com/"),
                name,
            )
            self.assertRegex(source["pinned_ref"], r"^[0-9a-f]{40}$", name)
            self.assertTrue(source["icon_path"].startswith("icons/"), name)
            self.assertTrue(source["icon_path"].endswith(".svg"), name)
            self.assertTrue(source["license_path"], name)

    def test_default_source_exists(self):
        self.assertIn(config.DEFAULT_ICON_SOURCE, config.ICON_SOURCES)

    def test_overrides_target_configured_sources(self):
        self.assertLessEqual(
            set(config.ICON_SOURCE_OVERRIDES.values()), set(config.ICON_SOURCES)
        )

    def test_override_slugs_appear_in_devicon_map(self):
        slugs = {slug for slug, _ in config.DEVICON_MAP.values()}
        self.assertLessEqual(set(config.ICON_SOURCE_OVERRIDES), slugs)

    def test_every_map_slug_resolves_and_formats(self):
        for lang, (slug, variant) in config.DEVICON_MAP.items():
            name = config.ICON_SOURCE_OVERRIDES.get(slug, config.DEFAULT_ICON_SOURCE)
            self.assertIn(name, config.ICON_SOURCES, lang)
            path = config.ICON_SOURCES[name]["icon_path"].format(
                slug=slug, variant=variant
            )
            self.assertTrue(path.startswith("icons/") and path.endswith(".svg"), lang)

    def test_typst_pins(self):
        self.assertIn("Typst", config.PROG_LANGS)
        self.assertEqual(config.LANG_COLORS["Typst"], "#239dad")
        self.assertEqual(config.DEVICON_MAP["Typst"], ("typst", "original"))
        self.assertEqual(config.ICON_SOURCE_OVERRIDES["typst"], "simple-icons")


class TestLiteralPins(unittest.TestCase):
    def test_pinned_constants(self):
        self.assertEqual(config.GH_REPO_LIMIT, 300)
        self.assertEqual(config.TOP_N, 10)
        self.assertEqual(config.STRIP_HEIGHT, 28)
        self.assertEqual(config.ICON_SIZE, 16)
        self.assertEqual(config.PAD_X, 7)
        self.assertEqual(config.LABEL_GAP, 4)
        self.assertEqual(config.ENTRY_GAP, 14)
        self.assertEqual(config.CHAR_WIDTH_XWIDE, 9.6)
        self.assertEqual(config.CHAR_WIDTH_WIDE, 8.2)
        self.assertEqual(config.CHAR_WIDTH_NARROW, 3.8)
        self.assertEqual(config.CHAR_WIDTH_DEFAULT, 7.0)
        self.assertEqual(config.WIDTH_MARGIN, 8)
        self.assertEqual(config.FONT_SIZE, 13)
        self.assertEqual(config.TEXT_MAIN, "#6e7781")
        self.assertEqual(config.GH_TIMEOUT_SECONDS, 60)
        self.assertEqual(
            config.RECOLOR_FILLS,
            frozenset({"#000", "#000000", "#000080", "black"}),
        )


if __name__ == "__main__":
    unittest.main()
