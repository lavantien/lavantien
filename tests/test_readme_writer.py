import re
import types
import unittest

from scripts import config
from scripts.readme_writer import (
    build_languages_block,
    normalize,
    render_repo_table,
    replace_between,
    rewrite_readme,
)

EXPECTED_IMG = (
    '<p align="center"><img src="assets/languages.svg"'
    ' alt="Top languages by code volume"></p>'
)
UPDATED_NEW = config.UPDATED_PREFIX + "2026-10-06*"

_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
_CELL_RE = re.compile(
    r'<td><a href="https://github\.com/lavantien/(?P<name>[^"]+)">(?P=name)</a>'
    r" \(<i>(?P<year>\d{4})</i>\) \(<b>(?P<stars>\d+)⭐</b>\)</td><td>(?P<desc>.*?)</td>"
)


def repo(name, year, stars, description):
    return types.SimpleNamespace(
        name=name, year=year, stars=stars, description=description
    )


def load_messy():
    return config.FIXTURE_README_MESSY.read_text(encoding="utf-8")


def parse_fixture_table(messy):
    start = messy.index("<table>")
    end = messy.index("</table>") + len("</table>")
    table = messy[start:end]
    rows = []
    for tr in _ROW_RE.findall(table):
        for match in _CELL_RE.finditer(tr):
            rows.append(
                repo(
                    match["name"],
                    int(match["year"]),
                    int(match["stars"]),
                    match["desc"],
                )
            )
    return table, rows


def rewrite_kwargs():
    _, rows = parse_fixture_table(load_messy())
    return {
        "languages_block": build_languages_block(),
        "repo_table": render_repo_table(rows),
        "updated_line": UPDATED_NEW,
    }


class TestBuildLanguagesBlock(unittest.TestCase):
    def test_exact_block(self):
        expected = (
            f"{config.MARKER_START}\n{EXPECTED_IMG}\n{config.MARKER_END}"
        )
        self.assertEqual(build_languages_block(), expected)

    def test_no_trailing_newline(self):
        self.assertFalse(build_languages_block().endswith("\n"))


class TestRenderRepoTable(unittest.TestCase):
    def test_odd_rows_last_row_alone(self):
        table = render_repo_table(
            [
                repo("alpha", 2020, 1, "first"),
                repo("beta", 2021, 2, "second"),
                repo("gamma", 2022, 3, "third"),
            ]
        )
        expected = "\n".join(
            (
                "<table>",
                "<tr><td><a href=\"https://github.com/lavantien/alpha\">alpha</a>"
                " (<i>2020</i>) (<b>1⭐</b>)</td><td>first</td>"
                "<td><a href=\"https://github.com/lavantien/beta\">beta</a>"
                " (<i>2021</i>) (<b>2⭐</b>)</td><td>second</td></tr>",
                "<tr><td><a href=\"https://github.com/lavantien/gamma\">gamma</a>"
                " (<i>2022</i>) (<b>3⭐</b>)</td><td>third</td></tr>",
                "</table>",
            )
        )
        self.assertEqual(table, expected)

    def test_empty_rows(self):
        self.assertEqual(render_repo_table([]), "<table>\n</table>")

    def test_byte_matches_fixture_table(self):
        messy = load_messy()
        table, rows = parse_fixture_table(messy)
        self.assertEqual(len(rows), 10)
        self.assertEqual(render_repo_table(rows), table)


class TestNormalize(unittest.TestCase):
    def test_strips_leading_and_trailing_blanks(self):
        self.assertEqual(normalize("\n\n\na\n\nb\n\n\n\n"), "a\n\nb\n")

    def test_adds_single_trailing_newline(self):
        self.assertEqual(normalize("a"), "a\n")
        self.assertEqual(normalize("a\n\n"), "a\n")

    def test_empty_and_blank_only(self):
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize("\n"), "")
        self.assertEqual(normalize(" \n\t\n"), "")

    def test_interior_blank_runs_preserved(self):
        self.assertEqual(normalize("a\n\n\nb\n"), "a\n\n\nb\n")
        self.assertEqual(normalize("a\n \nb\n"), "a\n \nb\n")


class TestReplaceBetween(unittest.TestCase):
    def test_replaces_inclusive_span(self):
        content = "x\nSTART\nold\nEND\ny"
        self.assertEqual(
            replace_between(content, "START", "END", "NEW"), "x\nNEW\ny"
        )

    def test_unchanged_when_both_markers_absent(self):
        content = "no markers here"
        self.assertIs(replace_between(content, "START", "END", "NEW"), content)

    def test_unchanged_when_only_one_marker(self):
        self.assertIs(
            replace_between("START only", "START", "END", "NEW"),
            "START only",
        )
        self.assertIs(
            replace_between("END only", "START", "END", "NEW"),
            "END only",
        )

    def test_unchanged_when_start_absent_and_end_beyond_offset(self):
        # end marker present but past the offset a missing start marker
        # would search from: the span lookup must bail out, not replace
        content = "x" * 30 + config.MARKER_END
        self.assertIs(
            replace_between(content, config.MARKER_START, config.MARKER_END, "NEW"),
            content,
        )

    def test_replaces_when_start_marker_leads_content(self):
        content = config.MARKER_START + "\nold\n" + config.MARKER_END
        self.assertEqual(
            replace_between(content, config.MARKER_START, config.MARKER_END, "NEW"),
            "NEW",
        )


class TestRewriteReadme(unittest.TestCase):
    def test_messy_readme_gets_block_at_top(self):
        messy = load_messy()
        leading = len(messy) - len(messy.lstrip("\n"))
        self.assertEqual(leading, 181)
        result = rewrite_readme(messy, **rewrite_kwargs())
        lines = result.split("\n")
        self.assertFalse(result.startswith("\n"))
        self.assertEqual(lines[0], config.MARKER_START)
        self.assertEqual(lines[1], EXPECTED_IMG)
        self.assertEqual(lines[2], config.MARKER_END)
        self.assertEqual(lines[3], "")
        self.assertEqual(lines[4], "<table>")

    def test_idempotent_on_messy_and_clean(self):
        kwargs = rewrite_kwargs()
        once = rewrite_readme(load_messy(), **kwargs)
        twice = rewrite_readme(once, **kwargs)
        self.assertEqual(once, twice)
        self.assertEqual(rewrite_readme(twice, **kwargs), twice)

    def test_exactly_one_table(self):
        result = rewrite_readme(load_messy(), **rewrite_kwargs())
        self.assertEqual(result.count("<table>"), 1)
        self.assertEqual(result.count("</table>"), 1)
        self.assertIn('href="https://github.com/lavantien/modern-swe-library"', result)

    def test_timestamp_replaced_not_appended(self):
        result = rewrite_readme(load_messy(), **rewrite_kwargs())
        found = [
            ln for ln in result.split("\n") if ln.startswith(config.UPDATED_PREFIX)
        ]
        self.assertEqual(found, [UPDATED_NEW])
        self.assertNotIn(config.UPDATED_PREFIX + "2026-10-05*", result)

    def test_unrelated_content_preserved(self):
        content = (
            "## Notes\n\nkeep me\n\n<table>\n<tr>junk</tr>\n</table>\n\n"
            + config.UPDATED_PREFIX
            + "old*\n"
        )
        result = rewrite_readme(content, **rewrite_kwargs())
        self.assertIn("## Notes", result)
        self.assertIn("keep me", result)
        self.assertNotIn("junk", result)
        self.assertLess(result.index("## Notes"), result.index("<table>"))
        self.assertLess(result.index("</table>"), result.index(UPDATED_NEW))

    def test_stray_start_marker_dropped_and_idempotent(self):
        content = (
            config.MARKER_START
            + "\n\n## Notes\n\n<table>\n<tr>junk</tr>\n</table>\n\n"
            + config.UPDATED_PREFIX
            + "old*\n"
        )
        kwargs = rewrite_kwargs()
        once = rewrite_readme(content, **kwargs)
        self.assertEqual(once.count(config.MARKER_START), 1)
        self.assertEqual(once.count(config.MARKER_END), 1)
        self.assertEqual(once.count(EXPECTED_IMG), 1)
        self.assertEqual(rewrite_readme(once, **kwargs), once)

    def test_stray_end_marker_dropped_and_idempotent(self):
        content = (
            "## Notes\n\n"
            + config.MARKER_END
            + "\n\n<table>\n<tr>junk</tr>\n</table>\n\n"
            + config.UPDATED_PREFIX
            + "old*\n"
        )
        kwargs = rewrite_kwargs()
        once = rewrite_readme(content, **kwargs)
        self.assertEqual(once.count(config.MARKER_START), 1)
        self.assertEqual(once.count(config.MARKER_END), 1)
        self.assertEqual(rewrite_readme(once, **kwargs), once)

    def test_table_inserted_before_updated_when_no_table(self):
        content = "## Notes\n\n" + config.UPDATED_PREFIX + "old*\n"
        result = rewrite_readme(content, **rewrite_kwargs())
        lines = result.split("\n")
        i_close = lines.index("</table>")
        i_updated = next(
            i for i, ln in enumerate(lines) if ln.startswith(config.UPDATED_PREFIX)
        )
        self.assertEqual(i_updated, i_close + 2)
        self.assertEqual(lines[i_close + 1], "")
        self.assertEqual(lines[i_updated], UPDATED_NEW)

    def test_table_and_updated_appended_when_both_absent(self):
        result = rewrite_readme("## Notes\n", **rewrite_kwargs())
        lines = result.split("\n")
        self.assertEqual(lines[0], config.MARKER_START)
        i_close = lines.index("</table>")
        i_updated = next(
            i for i, ln in enumerate(lines) if ln.startswith(config.UPDATED_PREFIX)
        )
        self.assertEqual(i_updated, i_close + 2)
        self.assertEqual(lines[i_updated], UPDATED_NEW)
        self.assertEqual(lines[-1], "")

    def test_empty_content(self):
        kwargs = rewrite_kwargs()
        expected = (
            kwargs["languages_block"]
            + "\n\n"
            + kwargs["repo_table"]
            + "\n\n"
            + UPDATED_NEW
            + "\n"
        )
        self.assertEqual(rewrite_readme("", **kwargs), expected)


if __name__ == "__main__":
    unittest.main()
