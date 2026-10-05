import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from unittest import mock

from scripts import config, generate, svg_strip
from scripts.aggregate import aggregate, top_languages
from scripts.github_client import GhError


class TestWriteOrdering(unittest.TestCase):
    def test_no_svg_written_when_readme_render_fails(self):
        # both artifacts render fully before the first byte hits disk
        with tempfile.TemporaryDirectory() as tmp:
            readme = pathlib.Path(tmp) / "README.md"
            svg = pathlib.Path(tmp) / "s.svg"
            readme.write_text("seed", encoding="utf-8")
            with mock.patch(
                "scripts.readme_writer.rewrite_readme",
                side_effect=RuntimeError("boom"),
            ):
                with self.assertRaises(RuntimeError):
                    generate.main(
                        [
                            "--from-json", str(config.FIXTURE_SAMPLE),
                            "--readme", str(readme),
                            "--svg", str(svg),
                        ]
                    )
            self.assertFalse(svg.exists())
            self.assertEqual(readme.read_text(encoding="utf-8"), "seed")

SVG_NS = "http://www.w3.org/2000/svg"
SENTINEL_README = "sentinel readme\n"
SENTINEL_SVG = "sentinel svg\n"
# what counts as a clean data failure: raised by load or aggregate before
# the first write, never a hang or an interpreter-level crash
CLEAN_FAILURES = (GhError, KeyError, TypeError, ValueError, AttributeError, IndexError)

EXPECTED_LANGS = [
    ("Go", 2221713), ("Java", 480000), ("JavaScript", 168384),
    ("Python", 140000), ("C", 120000), ("TypeScript", 95000),
    ("Kotlin", 75000), ("Ruby", 75000), ("Lua", 50000), ("F#", 13000),
]


def item(name="svc", stars=5, langs=(("Go", 100),), created="2024-01-01T00:00:00Z",
         description="d", fork=False, archived=False):
    return {
        "name": name,
        "stargazerCount": stars,
        "description": description,
        "createdAt": created,
        "isFork": fork,
        "isArchived": archived,
        "languages": [{"size": size, "node": {"name": lang}} for lang, size in langs],
    }


def drop(d, key):
    return {k: v for k, v in d.items() if k != key}


FUZZ_VARIANTS = [
    ("array of ints", [1, 2, 3]),
    ("array of strings", ["a", "b"]),
    ("array of nulls", [None, None]),
    ("array of booleans", [True]),
    ("array of empty arrays", [[]]),
    ("top-level object", {"name": "x"}),
    ("null description", [dict(item(), description=None)]),
    ("null languages", [dict(item(), languages=None)]),
    ("missing languages", [drop(item(), "languages")]),
    ("null createdAt", [dict(item(), createdAt=None)]),
    ("missing createdAt on non-fork", [drop(item(), "createdAt")]),
    ("missing name", [drop(item(), "name")]),
    ("null name", [dict(item(), name=None)]),
    ("missing stargazerCount", [drop(item(), "stargazerCount")]),
    ("truthy non-bool isFork", [dict(item(), isFork=1)]),
    ("truthy non-bool isArchived", [dict(item(), isArchived="yes")]),
    ("language entry missing size",
     [dict(item(), languages=[{"node": {"name": "Go"}}])]),
    ("language entry missing node",
     [dict(item(), languages=[{"size": 100}])]),
    ("language entry null node",
     [dict(item(), languages=[{"size": 100, "node": None}])]),
    ("language entry node is string",
     [dict(item(), languages=[{"size": 100, "node": "Go"}])]),
    ("language entry size is string",
     [dict(item(), languages=[{"size": "100", "node": {"name": "Go"}}])]),
]


@contextlib.contextmanager
def silence():
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        yield out


class TestArgParsing(unittest.TestCase):
    def test_both_sources_at_once_rejected(self):
        with self.assertRaises(SystemExit) as ctx, silence():
            generate.main(["--from-json", "repos.json", "--live"])
        self.assertNotEqual(ctx.exception.code, 0)

    def test_no_source_rejected(self):
        with self.assertRaises(SystemExit) as ctx, silence():
            generate.main([])
        self.assertNotEqual(ctx.exception.code, 0)


class TestSourceFailures(unittest.TestCase):
    def _seed(self, root):
        readme = root / "README.md"
        svg = root / "languages.svg"
        readme.write_text(SENTINEL_README, encoding="utf-8")
        svg.write_text(SENTINEL_SVG, encoding="utf-8")
        return readme, svg

    def _assert_untouched(self, readme, svg):
        self.assertEqual(readme.read_text(encoding="utf-8"), SENTINEL_README)
        self.assertEqual(svg.read_text(encoding="utf-8"), SENTINEL_SVG)

    def test_missing_from_json_file_raises_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            readme, svg = self._seed(root)
            missing = root / "missing.json"
            with silence():
                with self.assertRaises(GhError) as ctx:
                    generate.main(["--from-json", str(missing),
                                   "--readme", str(readme), "--svg", str(svg)])
            self.assertIn(str(missing), str(ctx.exception))
            self._assert_untouched(readme, svg)

    def test_malformed_json_raises_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            readme, svg = self._seed(root)
            src = root / "repos.json"
            src.write_text("{not json", encoding="utf-8")
            with silence():
                with self.assertRaises(GhError):
                    generate.main(["--from-json", str(src),
                                   "--readme", str(readme), "--svg", str(svg)])
            self._assert_untouched(readme, svg)


class TestMalformedPayloadFuzz(unittest.TestCase):
    # invariant per variant: main() either completes and leaves well-formed
    # artifacts, or raises a clean data error with both artifacts untouched
    def test_variants_never_partially_write(self):
        for label, payload in FUZZ_VARIANTS:
            with self.subTest(variant=label):
                self._run_variant(json.dumps(payload))

    def _run_variant(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            readme = root / "README.md"
            svg = root / "languages.svg"
            readme.write_text(SENTINEL_README, encoding="utf-8")
            svg.write_text(SENTINEL_SVG, encoding="utf-8")
            src = root / "repos.json"
            src.write_text(text, encoding="utf-8")
            args = ["--from-json", str(src),
                    "--readme", str(readme), "--svg", str(svg)]
            try:
                with silence():
                    rc = generate.main(args)
            except CLEAN_FAILURES:
                self._assert_untouched(readme, svg)
            else:
                self.assertEqual(rc, 0)
                self._assert_wellformed(readme, svg)

    def _assert_untouched(self, readme, svg):
        self.assertEqual(readme.read_text(encoding="utf-8"), SENTINEL_README)
        self.assertEqual(svg.read_text(encoding="utf-8"), SENTINEL_SVG)

    def _assert_wellformed(self, readme, svg):
        svg_text = svg.read_text(encoding="utf-8")
        ET.fromstring(svg_text)
        self.assertNotIn("\r", svg_text)
        content = readme.read_text(encoding="utf-8")
        self.assertTrue(content.startswith(config.MARKER_START))
        self.assertEqual(content.count("<table>"), 1)
        self.assertEqual(content.count("</table>"), 1)
        updated = [ln for ln in content.split("\n")
                   if ln.startswith(config.UPDATED_PREFIX)]
        self.assertEqual(len(updated), 1)


class TestEndToEndFromFixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.readme = pathlib.Path(tmp.name) / "README.md"
        self.svg = pathlib.Path(tmp.name) / "languages.svg"
        self.readme.write_bytes(config.FIXTURE_README_MESSY.read_bytes())
        self.args = ["--from-json", str(config.FIXTURE_SAMPLE),
                     "--readme", str(self.readme), "--svg", str(self.svg)]

    def test_happy_path_rewrites_readme_and_writes_strip(self):
        with silence() as out:
            rc = generate.main(self.args)
        self.assertEqual(rc, 0)
        self.assertIn("2 changed", out.getvalue())

        svg_text = self.svg.read_text(encoding="utf-8")
        root = ET.fromstring(svg_text)
        expected_aria = "Top languages: " + ", ".join(
            f"{name} {svg_strip.format_bytes(size)}" for name, size in EXPECTED_LANGS
        )
        self.assertEqual(root.get("aria-label"), expected_aria)
        self.assertEqual(root.find(f"{{{SVG_NS}}}title").text, expected_aria)
        self.assertTrue(expected_aria.startswith("Top languages: Go 2.2M"))

        content = self.readme.read_text(encoding="utf-8")
        self.assertTrue(content.startswith(config.MARKER_START))
        self.assertEqual(content[0], "<")
        self.assertEqual(content.count("<table>"), 1)
        self.assertEqual(content.count("</table>"), 1)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        updated = [ln for ln in content.split("\n")
                   if ln.startswith(config.UPDATED_PREFIX)]
        self.assertEqual(updated, [f"{config.UPDATED_PREFIX}{today}"])
        # stub star wiring: the fixed repo is absent from the fixture so its
        # lookup falls back to 0, fixture repos carry their own counts
        self.assertIn(
            '<a href="https://github.com/lavantien/modern-swe-library">'
            "modern-swe-library</a> (<i>2023</i>) (<b>0⭐</b>)",
            content,
        )
        self.assertIn(
            '<a href="https://github.com/lavantien/dotfiles">dotfiles</a>'
            " (<i>2023</i>) (<b>42⭐</b>)",
            content,
        )

    def test_second_run_is_byte_identical_noop(self):
        with silence() as first:
            self.assertEqual(generate.main(self.args), 0)
        readme_once = self.readme.read_bytes()
        svg_once = self.svg.read_bytes()
        with silence() as second:
            self.assertEqual(generate.main(self.args), 0)
        self.assertEqual(self.readme.read_bytes(), readme_once)
        self.assertEqual(self.svg.read_bytes(), svg_once)
        self.assertIn("2 changed", first.getvalue())
        self.assertIn("0 changed", second.getvalue())
        self.assertIn("unchanged", second.getvalue())

    def test_final_summary_line_is_exact(self):
        # byte-exact last line, both on the fresh run and the idempotent
        # rerun, so wording or count changes in the summary cannot survive
        with silence() as first:
            self.assertEqual(generate.main(self.args), 0)
        with silence() as second:
            self.assertEqual(generate.main(self.args), 0)
        self.assertEqual(
            first.getvalue().splitlines()[-1], "done: 2 changed, 0 unchanged"
        )
        self.assertEqual(
            second.getvalue().splitlines()[-1], "done: 0 changed, 2 unchanged"
        )

    @mock.patch("scripts.github_client.fetch_star_count",
                side_effect=AssertionError("network star fetch in --from-json mode"))
    def test_from_json_mode_uses_stub_not_the_network(self, _star_fetch):
        with silence():
            rc = generate.main(self.args)
        self.assertEqual(rc, 0)

    @mock.patch("scripts.github_client.fetch_star_count",
                side_effect=AssertionError("network star fetch in --from-json mode"))
    def test_stub_returns_own_stars_for_fixed_repo_in_items(self, _star_fetch):
        # select_rows consults star_fetch only for the fixed first repo;
        # its recorded item is archived, so the aggregate filters it out
        # and the stub must still resolve its stargazerCount from the raw
        # loaded items instead of falling back to 0 or the network
        src_items = [
            dict(item(name="modern-swe-library", stars=17, langs=()), archived=True),
            item(name="other", stars=3, langs=()),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp) / "repos.json"
            src.write_text(json.dumps(src_items), encoding="utf-8")
            readme = pathlib.Path(tmp) / "README.md"
            svg = pathlib.Path(tmp) / "languages.svg"
            with silence():
                rc = generate.main(["--from-json", str(src),
                                    "--readme", str(readme), "--svg", str(svg)])
            content = readme.read_text(encoding="utf-8")
        self.assertEqual(rc, 0)
        # the fixed row keeps its config-pinned year and description; only
        # the stars come from the loaded items via the stub
        self.assertIn(
            '<a href="https://github.com/lavantien/modern-swe-library">'
            "modern-swe-library</a> (<i>2023</i>) (<b>17⭐</b>)",
            content,
        )
        self.assertNotIn("(<b>0⭐</b>)", content)

    @mock.patch("scripts.github_client.fetch_star_count", return_value=9)
    @mock.patch("scripts.github_client.fetch_repos")
    def test_live_mode_wires_gh_client(self, fetch_repos, star_count):
        fetch_repos.return_value = json.loads(
            config.FIXTURE_SAMPLE.read_text(encoding="utf-8"))
        with silence():
            rc = generate.main(["--live", "--readme", str(self.readme),
                                "--svg", str(self.svg)])
        self.assertEqual(rc, 0)
        fetch_repos.assert_called_once_with()
        star_count.assert_called_once_with(
            f"{config.GH_OWNER}/{config.FIXED_FIRST_REPO['name']}")
        content = self.readme.read_text(encoding="utf-8")
        self.assertIn(
            '<a href="https://github.com/lavantien/modern-swe-library">'
            "modern-swe-library</a> (<i>2023</i>) (<b>9⭐</b>)",
            content,
        )

    def test_script_entry_direct_execution(self):
        # the Makefile invokes the file by path, not via -m scripts.generate;
        # direct execution must bootstrap the repo root itself
        with tempfile.TemporaryDirectory() as tmp:
            readme = pathlib.Path(tmp) / "README.md"
            svg = pathlib.Path(tmp) / "languages.svg"
            proc = subprocess.run(
                [sys.executable, str(config.REPO_ROOT / "scripts" / "generate.py"),
                 "--from-json", str(config.FIXTURE_SAMPLE),
                 "--readme", str(readme), "--svg", str(svg)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("2 changed", proc.stdout)
            self.assertTrue(svg.is_file())
            self.assertTrue(readme.read_text(encoding="utf-8")
                            .startswith(config.MARKER_START))


if __name__ == "__main__":
    unittest.main()
