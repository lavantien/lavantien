import re
import unittest

from scripts import config

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


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


class TestLiteralPins(unittest.TestCase):
    # deliberate literal pins for mutation coverage: these values are the
    # public contract of the config hub, and asserts elsewhere that derive
    # expectations from config would mutate in lockstep and pass silently
    def test_pinned_constants(self):
        self.assertEqual(config.GH_REPO_LIMIT, 300)
        self.assertEqual(config.TOP_N, 10)
        self.assertEqual(config.STRIP_HEIGHT, 28)
        self.assertEqual(config.ICON_SIZE, 16)
        self.assertEqual(config.PAD_X, 7)
        self.assertEqual(config.LABEL_GAP, 4)
        self.assertEqual(config.ENTRY_GAP, 14)
        self.assertEqual(config.CHAR_WIDTH, 7.0)
        self.assertEqual(config.FONT_SIZE, 13)
        self.assertEqual(config.TEXT_MAIN, "#6e7781")


if __name__ == "__main__":
    unittest.main()
