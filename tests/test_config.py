import re
import unittest
import xml.etree.ElementTree as ET

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


class TestPinnedRepos(unittest.TestCase):
    def test_pinned_repos_exact(self):
        self.assertEqual(config.PINNED_REPOS, (
            {"name": "dotfiles", "year": 2023},
            {"name": "modern-swe-library", "year": 2023, "stars_prefix": 200,
             "no_ai": True,
             "description": "Open knowledge library: curated resources for modern software engineering"},
            {"name": "FlowerShop", "year": 2018},
            {"name": "caro-ai-pvp", "year": 2025},
            {"name": "blind-trainer", "year": 2026},
            {"name": "quotes-manager", "year": 2026},
            {"name": "dota-helper", "year": 2026},
            {"name": "llm-tournament", "year": 2024},
            {"name": "genetic-cpp", "year": 2016},
            {"name": "SumoBot", "year": 2017},
            {"name": "go-edge-mesh", "year": 2021},
            {"name": "order-demo", "year": 2021},
            {"name": "go-flutter-microservices-skeleton", "year": 2022},
        ))

    def test_table_and_updated_line(self):
        self.assertEqual(config.TABLE_REPO_LIMIT, 20)
        self.assertEqual(config.UPDATED_PREFIX, "*Last updated: ")
        self.assertEqual(config.UPDATED_SUFFIX, "*")

    def test_table_layout_constants(self):
        self.assertEqual(config.TABLE_WIDTH, "100%")
        self.assertEqual(config.TABLE_CELL_WIDTH, "25%")
        self.assertEqual(config.META_JOIN, "&nbsp;")

    def test_excluded_repo_names(self):
        self.assertEqual(
            config.EXCLUDED_REPO_NAMES, frozenset({"lavantien", "neovim"})
        )

    def test_no_ai_badge_constants(self):
        self.assertEqual(config.NO_AI_REFERENCE_REPO, "llm-tournament")
        self.assertEqual(config.NO_AI_FALLBACK_CUTOFF, "2025-01-01T20:30:10Z")
        self.assertEqual(config.NO_AI_IMG_SRC, "assets/no-ai.svg")
        self.assertEqual(config.NO_AI_ALT_TEXT, "no AI")
        self.assertEqual(config.NO_AI_IMG_WIDTH, 14)
        self.assertEqual(config.NO_AI_IMG_HEIGHT, 14)
        self.assertEqual(config.NO_AI_BORDER_COLOR, "#ff0000")
        self.assertEqual(config.NO_AI_TEXT_COLOR, "#008000")


class TestNoAiBadgeAsset(unittest.TestCase):
    def test_single_logo_red_border_green_text(self):
        path = config.REPO_ROOT / config.NO_AI_IMG_SRC
        root = ET.parse(path).getroot()
        paths = root.findall("{http://www.w3.org/2000/svg}path")
        fills = {p.get("fill") for p in paths}
        self.assertEqual(len(paths), 2)
        self.assertEqual(fills, {config.NO_AI_BORDER_COLOR, config.NO_AI_TEXT_COLOR})
        self.assertTrue(all(p.get("d") for p in paths))


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
