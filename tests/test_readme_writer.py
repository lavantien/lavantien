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
UPDATED_NEW = config.UPDATED_PREFIX + "2026-10-06" + config.UPDATED_SUFFIX
BADGE_IMG = (
    f'<img src="{config.NO_AI_IMG_SRC}" alt="{config.NO_AI_ALT_TEXT}"'
    f' width="{config.NO_AI_IMG_WIDTH}" height="{config.NO_AI_IMG_HEIGHT}">'
)
NBSP_JOIN = "&nbsp;&nbsp;&nbsp;&nbsp;"

_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
_CELL_RE = re.compile(
    r'<td width="[^"]*"><a href="https://github\.com/lavantien/(?P<name>[^"]+)">'
    r"(?P=name)</a>"
    r"<br>\(<i>(?P<year>\d{4})</i>\)"
    r"&nbsp;&nbsp;&nbsp;&nbsp;<b>(?P<stars>[^<]*)✪</b>"
    r"&nbsp;&nbsp;&nbsp;&nbsp;<b>(?P<forks>\d+)♆</b>"
    r"(?P<badge>&nbsp;&nbsp;&nbsp;&nbsp;<img [^>]+>)?"
    r"(?P<langsrow>(?:<br>(?:(?!</td>).)*))?"
    r'</td><td width="[^"]*">(?P<desc>.*?)</td>'
)
_CHIP_RE = re.compile(
    r'<img src="(?P<src>[^"]+)" alt="(?P<alt>[A-Za-z][A-Za-z0-9+#-]*)"'
    r' width="\d+" height="\d+">'
    r"&nbsp;(?P<isize>\d+(?:\.\d+)?[MK]?)"
    r"|(?P<lang>[A-Za-z][A-Za-z0-9+#-]*)&nbsp;(?P<tsize>\d+(?:\.\d+)?[MK]?)"
)


def size_bytes(text):
    if text.endswith("M"):
        return round(float(text[:-1]) * 1_000_000)
    if text.endswith("K"):
        return round(float(text[:-1]) * 1_000)
    return int(text)


def parse_langs(langsrow):
    if not langsrow:
        return (), {}
    text = langsrow.removeprefix("<br>")
    chips = []
    icon_srcs = {}
    pos = 0
    for match in _CHIP_RE.finditer(text):
        expected = "" if pos == 0 else config.LANG_CHIP_JOIN
        gap = text[pos:match.start()]
        if gap != expected:
            raise ValueError(f"unexpected content between chips: {gap!r}")
        pos = match.end()
        if match["src"] is not None:
            lang, size = match["alt"], match["isize"]
            icon_srcs[lang] = match["src"]
        else:
            lang, size = match["lang"], match["tsize"]
        chips.append((lang, size_bytes(size)))
    if text[pos:]:
        raise ValueError(f"trailing content after chips: {text[pos:]!r}")
    return tuple(chips), icon_srcs


def repo(name, year, stars, description, stars_display="", no_ai=False,
         top_langs=(), forks=0):
    return types.SimpleNamespace(
        name=name, year=year, stars=stars, description=description,
        stars_display=stars_display, no_ai=no_ai, top_langs=top_langs,
        forks=forks,
    )


def load_messy():
    return config.FIXTURE_README_MESSY.read_text(encoding="utf-8")


def parse_fixture_table(messy):
    start = messy.index("<table")
    end = messy.index("</table>") + len("</table>")
    table = messy[start:end]
    rows = []
    icon_srcs: dict[str, str] = {}
    for tr in _ROW_RE.findall(table):
        for match in _CELL_RE.finditer(tr):
            stars_text = match["stars"]
            top_langs, srcs = parse_langs(match["langsrow"])
            icon_srcs.update(srcs)
            rows.append(
                repo(
                    match["name"],
                    int(match["year"]),
                    int(stars_text.rsplit("+", 1)[-1]),
                    match["desc"],
                    stars_display=stars_text if "+" in stars_text else "",
                    no_ai=match["badge"] is not None,
                    top_langs=top_langs,
                    forks=int(match["forks"]),
                )
            )
    return table, rows, icon_srcs


def rewrite_kwargs():
    _, rows, icon_srcs = parse_fixture_table(load_messy())
    return {
        "languages_block": build_languages_block(),
        "repo_table": render_repo_table(rows, icon_srcs=icon_srcs),
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
    ICONS = {
        "Go": "assets/lang-icons/go-plain.svg",
        "Python": "assets/lang-icons/python-plain.svg",
        "Kotlin": "assets/lang-icons/kotlin-plain.svg",
    }

    def test_odd_rows_last_row_alone(self):
        table = render_repo_table(
            [
                repo("alpha", 2020, 1, "first"),
                repo("beta", 2021, 2, "second"),
                repo("gamma", 2022, 3, "third"),
            ],
            icon_srcs={},
        )
        expected = "\n".join(
            (
                '<table width="100%">',
                '<tr><td width="25%"><a href="https://github.com/lavantien/alpha">'
                "alpha</a><br>(<i>2020</i>)&nbsp;&nbsp;&nbsp;&nbsp;<b>1✪</b>"
                "&nbsp;&nbsp;&nbsp;&nbsp;<b>0♆</b>"
                '</td><td width="25%">first</td>'
                '<td width="25%"><a href="https://github.com/lavantien/beta">'
                "beta</a><br>(<i>2021</i>)&nbsp;&nbsp;&nbsp;&nbsp;<b>2✪</b>"
                "&nbsp;&nbsp;&nbsp;&nbsp;<b>0♆</b>"
                '</td><td width="25%">second</td></tr>',
                '<tr><td width="25%"><a href="https://github.com/lavantien/gamma">'
                "gamma</a><br>(<i>2022</i>)&nbsp;&nbsp;&nbsp;&nbsp;<b>3✪</b>"
                "&nbsp;&nbsp;&nbsp;&nbsp;<b>0♆</b>"
                '</td><td width="25%">third</td></tr>',
                "</table>",
            )
        )
        self.assertEqual(table, expected)

    def test_empty_rows(self):
        self.assertEqual(
            render_repo_table([], icon_srcs={}), '<table width="100%">\n</table>'
        )

    def test_badged_prefixed_cell_exact(self):
        table = render_repo_table([
            repo("modern-swe-library", 2023, 9, "lib",
                 stars_display="200+9", no_ai=True, forks=1),
        ], icon_srcs={})
        self.assertEqual(
            table,
            '<table width="100%">\n'
            '<tr><td width="25%">'
            '<a href="https://github.com/lavantien/modern-swe-library">'
            "modern-swe-library</a><br>(<i>2023</i>)"
            "&nbsp;&nbsp;&nbsp;&nbsp;<b>200+9✪</b>&nbsp;&nbsp;&nbsp;&nbsp;<b>1♆</b>"
            + NBSP_JOIN
            + BADGE_IMG
            + '</td><td width="25%">lib</td></tr>\n</table>',
        )

    def test_plain_cell_exact_without_img(self):
        table = render_repo_table([repo("plain", 2020, 3, "doc")], icon_srcs={})
        self.assertEqual(
            table,
            '<table width="100%">\n'
            '<tr><td width="25%">'
            '<a href="https://github.com/lavantien/plain">plain</a>'
            "<br>(<i>2020</i>)&nbsp;&nbsp;&nbsp;&nbsp;<b>3✪</b>"
            "&nbsp;&nbsp;&nbsp;&nbsp;<b>0♆</b>"
            '</td><td width="25%">doc</td></tr>\n</table>',
        )

    def test_two_lang_chips_row_exact(self):
        table = render_repo_table([
            repo("svc", 2024, 8, "doc",
                 top_langs=(("Go", 2221713), ("Python", 140000))),
        ], icon_srcs=self.ICONS)
        self.assertEqual(
            table,
            '<table width="100%">\n'
            '<tr><td width="25%">'
            '<a href="https://github.com/lavantien/svc">svc</a>'
            "<br>(<i>2024</i>)&nbsp;&nbsp;&nbsp;&nbsp;<b>8✪</b>"
            "&nbsp;&nbsp;&nbsp;&nbsp;<b>0♆</b>"
            "<br>"
            '<img src="assets/lang-icons/go-plain.svg" alt="Go"'
            ' width="14" height="14">'
            "&nbsp;2.2M"
            "&nbsp;&nbsp;&nbsp; "
            '<img src="assets/lang-icons/python-plain.svg" alt="Python"'
            ' width="14" height="14">'
            "&nbsp;140K"
            '</td><td width="25%">doc</td></tr>\n</table>',
        )

    def test_lang_chip_text_only_without_icon(self):
        table = render_repo_table([
            repo("svc", 2024, 8, "doc", top_langs=(("Kotlin", 75000),)),
        ], icon_srcs={})
        self.assertEqual(
            table,
            '<table width="100%">\n'
            '<tr><td width="25%">'
            '<a href="https://github.com/lavantien/svc">svc</a>'
            "<br>(<i>2024</i>)&nbsp;&nbsp;&nbsp;&nbsp;<b>8✪</b>"
            "&nbsp;&nbsp;&nbsp;&nbsp;<b>0♆</b>"
            "<br>Kotlin&nbsp;75K"
            '</td><td width="25%">doc</td></tr>\n</table>',
        )

    def test_empty_langs_omit_the_row(self):
        table = render_repo_table([
            repo("svc", 2024, 8, "doc", top_langs=()),
        ], icon_srcs=self.ICONS)
        self.assertNotIn("<br>K", table)
        self.assertNotIn("lang-icons", table)

    def test_hostile_name_and_description_are_escaped(self):
        table = render_repo_table([
            repo("a&b<c>", 2020, 3, 'uses <algorithm> & "quotes"'),
        ], icon_srcs={})
        self.assertIn(
            '<a href="https://github.com/lavantien/a&amp;b&lt;c&gt;">a&amp;b&lt;c&gt;'
            "</a>",
            table,
        )
        self.assertIn("<td width=\"25%\">uses &lt;algorithm&gt; &amp; "
                      "\"quotes\"</td>", table)
        self.assertNotIn("<algorithm>", table)

    def test_chip_parser_accepts_hyphenated_language(self):
        chips, srcs = parse_langs(
            '<br><img src="assets/lang-icons/objectivec-plain.svg"'
            ' alt="Objective-C" width="14" height="14">&nbsp;12K'
        )
        self.assertEqual(chips, (("Objective-C", 12000),))
        self.assertEqual(
            srcs, {"Objective-C": "assets/lang-icons/objectivec-plain.svg"}
        )
        self.assertEqual(parse_langs("<br>Objective-C&nbsp;12K"), ((("Objective-C", 12000),), {}))

    def test_hostile_lang_is_escaped_in_chips(self):
        hostile = ('a&b<c>"', 5000)
        table = render_repo_table(
            [repo("svc", 2024, 8, "doc", top_langs=(hostile,))],
            icon_srcs={'a&b<c>"': "assets/lang-icons/go-plain.svg"},
        )
        self.assertIn('alt="a&amp;b&lt;c&gt;&quot;"', table)
        self.assertIn("&nbsp;5K", table)
        self.assertNotIn('alt="a&b', table)
        text_only = render_repo_table(
            [repo("svc", 2024, 8, "doc", top_langs=(hostile,))], icon_srcs={}
        )
        self.assertIn("<br>a&amp;b&lt;c&gt;&quot;&nbsp;5K", text_only)
        self.assertNotIn("<br>a&b", text_only)

    def test_byte_matches_fixture_table(self):
        messy = load_messy()
        table, rows, icon_srcs = parse_fixture_table(messy)
        self.assertEqual(len(rows), 20)
        self.assertEqual(sum(1 for r in rows if r.no_ai), 15)
        self.assertEqual(sum(1 for r in rows if r.top_langs), 10)
        self.assertGreater(len(icon_srcs), 0)
        self.assertEqual(render_repo_table(rows, icon_srcs=icon_srcs), table)


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
        """End marker present but past the offset a missing start marker
        would search from: the span lookup must bail out, not replace."""
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
        self.assertEqual(lines[4], config.MARKER_REPOS_START)
        self.assertEqual(lines[5], '<table width="100%">')

    def test_idempotent_on_messy_and_clean(self):
        kwargs = rewrite_kwargs()
        once = rewrite_readme(load_messy(), **kwargs)
        twice = rewrite_readme(once, **kwargs)
        self.assertEqual(once, twice)
        self.assertEqual(rewrite_readme(twice, **kwargs), twice)

    def test_exactly_one_table(self):
        result = rewrite_readme(load_messy(), **rewrite_kwargs())
        self.assertEqual(result.count("<table"), 1)
        self.assertEqual(result.count("</table>"), 1)
        self.assertIn('href="https://github.com/lavantien/modern-swe-library"', result)

    def test_timestamp_replaced_not_appended(self):
        result = rewrite_readme(load_messy(), **rewrite_kwargs())
        found = [
            ln for ln in result.split("\n") if ln.startswith(config.UPDATED_PREFIX)
        ]
        self.assertEqual(found, [UPDATED_NEW])
        self.assertNotIn(config.UPDATED_PREFIX + "2026-10-05*", result)

    def test_suffixless_legacy_updated_line_replaced(self):
        content = (
            "## Notes\n\n<table>\n<tr>junk</tr>\n</table>\n\n"
            + config.UPDATED_PREFIX
            + "2026-01-01\n"
        )
        result = rewrite_readme(content, **rewrite_kwargs())
        found = [
            ln for ln in result.split("\n") if ln.startswith(config.UPDATED_PREFIX)
        ]
        self.assertEqual(found, [UPDATED_NEW])
        self.assertNotIn(config.UPDATED_PREFIX + "2026-01-01", result)

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
        self.assertLess(result.index("## Notes"), result.index("<table"))
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
        self.assertEqual(lines[i_close + 1], config.MARKER_REPOS_END)
        self.assertEqual(lines[i_close + 2], "")
        self.assertEqual(i_updated, i_close + 3)
        self.assertEqual(lines[i_updated], UPDATED_NEW)

    def test_table_and_updated_appended_when_both_absent(self):
        result = rewrite_readme("## Notes\n", **rewrite_kwargs())
        lines = result.split("\n")
        self.assertEqual(lines[0], config.MARKER_START)
        i_close = lines.index("</table>")
        i_updated = next(
            i for i, ln in enumerate(lines) if ln.startswith(config.UPDATED_PREFIX)
        )
        self.assertEqual(lines[i_close + 1], config.MARKER_REPOS_END)
        self.assertEqual(lines[i_close + 2], "")
        self.assertEqual(i_updated, i_close + 3)
        self.assertEqual(lines[i_updated], UPDATED_NEW)
        self.assertEqual(lines[-1], "")

    def test_empty_content(self):
        kwargs = rewrite_kwargs()
        expected = (
            kwargs["languages_block"]
            + "\n\n"
            + config.MARKER_REPOS_START
            + "\n"
            + kwargs["repo_table"]
            + "\n"
            + config.MARKER_REPOS_END
            + "\n\n"
            + UPDATED_NEW
            + "\n"
        )
        self.assertEqual(rewrite_readme("", **kwargs), expected)


class TestRepoTableMarkers(unittest.TestCase):
    LANGS_BLOCK = "\n".join((config.MARKER_START, EXPECTED_IMG, config.MARKER_END))
    USER_TABLE = "<table>\n<tr><td>mine</td></tr>\n</table>"
    FOREIGN_ATTRIBUTED_TABLE = (
        '<table align="center">\n<tr><td>stats</td></tr>\n</table>'
    )
    OLD_GEN_TABLE = "<table>\n<tr><td>old gen</td></tr>\n</table>"
    GEN_TABLE = "<table>\n<tr><td>gen</td></tr>\n</table>"

    def rewrite(self, content):
        return rewrite_readme(
            content,
            languages_block=self.LANGS_BLOCK,
            repo_table=self.GEN_TABLE,
            updated_line=UPDATED_NEW,
        )

    def test_user_table_before_markers_survives(self):
        marked = "\n".join(
            (config.MARKER_REPOS_START, self.GEN_TABLE, config.MARKER_REPOS_END)
        )
        content = "\n\n".join(
            (self.USER_TABLE, marked, "*Last updated: 2026-01-01*")
        ) + "\n"
        result = self.rewrite(content)
        self.assertIn(self.USER_TABLE, result)
        self.assertEqual(result.count("<table>"), 2)
        self.assertEqual(result.count(config.MARKER_REPOS_START), 1)
        self.assertIn(config.MARKER_REPOS_START + "\n" + self.GEN_TABLE, result)
        self.assertEqual(self.rewrite(result), result)

    def test_foreign_attributed_table_survives_markerless_adoption(self):
        content = "\n\n".join(
            (self.OLD_GEN_TABLE, self.FOREIGN_ATTRIBUTED_TABLE,
             "*Last updated: 2026-01-01*")
        ) + "\n"
        result = self.rewrite(content)
        self.assertIn(self.FOREIGN_ATTRIBUTED_TABLE, result)
        self.assertNotIn(self.OLD_GEN_TABLE, result)
        self.assertIn(config.MARKER_REPOS_START + "\n" + self.GEN_TABLE, result)
        self.assertEqual(self.rewrite(result), result)

    def test_attributed_generator_table_is_adopted(self):
        attributed_old = (
            f'<table width="{config.TABLE_WIDTH}">\n<tr><td>old gen</td></tr>\n'
            "</table>"
        )
        content = "\n\n".join(
            (self.FOREIGN_ATTRIBUTED_TABLE, attributed_old,
             "*Last updated: 2026-01-01*")
        ) + "\n"
        result = self.rewrite(content)
        self.assertIn(self.FOREIGN_ATTRIBUTED_TABLE, result)
        self.assertNotIn(attributed_old, result)
        self.assertIn(config.MARKER_REPOS_START + "\n" + self.GEN_TABLE, result)
        self.assertEqual(self.rewrite(result), result)

    def test_adoption_targets_table_adjacent_to_updated_line(self):
        """No markers yet: the generator-owned table is the one sitting
        right before the updated line; a user table above must survive."""
        content = "\n\n".join(
            (self.USER_TABLE, self.OLD_GEN_TABLE, "*Last updated: 2026-01-01*")
        ) + "\n"
        result = self.rewrite(content)
        self.assertIn(self.USER_TABLE, result)
        self.assertNotIn(self.OLD_GEN_TABLE, result)
        self.assertIn(config.MARKER_REPOS_START + "\n" + self.GEN_TABLE, result)
        self.assertEqual(result.count("<table>"), 2)
        self.assertEqual(self.rewrite(result), result)

    def test_stray_repos_marker_dropped(self):
        content = "\n".join(
            (config.MARKER_REPOS_END, "*Last updated: 2026-01-01*")
        ) + "\n"
        result = self.rewrite(content)
        self.assertNotIn(config.MARKER_REPOS_END + "\n", result[: result.find("<table>")])
        self.assertIn(config.MARKER_REPOS_START, result)
        self.assertEqual(self.rewrite(result), result)

    def test_tables_after_updated_replace_last(self):
        """No owned table before the updated line: the last table is the
        generator's, an earlier one is left alone."""
        table_a = "<table>\n<tr><td>first</td></tr>\n</table>"
        table_b = "<table>\n<tr><td>second</td></tr>\n</table>"
        content = "*Last updated: 2026-01-01*\n\n" + table_a + "\n\n" + table_b + "\n"
        result = self.rewrite(content)
        self.assertIn(table_a, result)
        self.assertNotIn(table_b, result)
        self.assertEqual(self.rewrite(result), result)

    def test_two_tables_no_updated_replaces_last(self):
        table_a = "<table>\n<tr><td>first</td></tr>\n</table>"
        table_b = "<table>\n<tr><td>second</td></tr>\n</table>"
        content = table_a + "\n\n" + table_b + "\n"
        result = self.rewrite(content)
        self.assertIn(table_a, result)
        self.assertNotIn(table_b, result)
        self.assertIn(UPDATED_NEW, result)
        self.assertEqual(self.rewrite(result), result)


if __name__ == "__main__":
    unittest.main()
