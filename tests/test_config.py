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
        for value in (config.DEFAULT_COLOR, config.TEXT_DARK, config.TEXT_LIGHT):
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


if __name__ == "__main__":
    unittest.main()
