import contextlib
import io
import json
import pathlib
import re
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
    def test_no_artifacts_written_when_readme_render_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            readme = pathlib.Path(tmp) / "README.md"
            svg = pathlib.Path(tmp) / "s.svg"
            icons = pathlib.Path(tmp) / "icons"
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
                            "--icons-dir", str(icons),
                        ]
                    )
            self.assertFalse(svg.exists())
            self.assertFalse(icons.exists())
            self.assertEqual(readme.read_text(encoding="utf-8"), "seed")

SVG_NS = "http://www.w3.org/2000/svg"
SENTINEL_README = "sentinel readme\n"
SENTINEL_SVG = "sentinel svg\n"
CLEAN_FAILURES = (GhError, KeyError, TypeError, ValueError, AttributeError, IndexError)

EXPECTED_LANGS = [
    ("Typst", 10304702), ("Go", 2221713), ("Java", 480000),
    ("JavaScript", 168384), ("Python", 140000), ("C", 120000),
    ("TypeScript", 95000), ("Kotlin", 75000), ("Ruby", 75000),
    ("Lua", 50000),
]

BADGE_IMG = (
    f'<img src="{config.NO_AI_IMG_SRC}" alt="{config.NO_AI_ALT_TEXT}"'
    f' width="{config.NO_AI_IMG_WIDTH}" height="{config.NO_AI_IMG_HEIGHT}">'
)
NBSP_JOIN = "&nbsp;"


def item(name="svc", stars=5, langs=(("Go", 100),), created="2024-01-01T00:00:00Z",
         description="d", fork=False, archived=False, visibility="public"):
    return {
        "name": name,
        "stargazerCount": stars,
        "description": description,
        "createdAt": created,
        "isFork": fork,
        "isArchived": archived,
        "visibility": visibility,
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
                                   "--readme", str(readme), "--svg", str(svg),
                                   "--icons-dir", str(root / "icons")])
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
                                   "--readme", str(readme), "--svg", str(svg),
                                   "--icons-dir", str(root / "icons")])
            self._assert_untouched(readme, svg)


class TestMalformedPayloadFuzz(unittest.TestCase):
    def test_variants_never_partially_write(self):
        for label, payload in FUZZ_VARIANTS:
            with self.subTest(variant=label):
                self._run_variant(json.dumps(payload))

    def _run_variant(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            readme = root / "README.md"
            svg = root / "languages.svg"
            icons = root / "icons"
            readme.write_text(SENTINEL_README, encoding="utf-8")
            svg.write_text(SENTINEL_SVG, encoding="utf-8")
            src = root / "repos.json"
            src.write_text(text, encoding="utf-8")
            args = ["--from-json", str(src),
                    "--readme", str(readme), "--svg", str(svg),
                    "--icons-dir", str(icons)]
            try:
                with silence():
                    rc = generate.main(args)
            except CLEAN_FAILURES:
                self._assert_untouched(readme, svg)
            else:
                self.assertEqual(rc, 0)
                self._assert_wellformed(readme, svg, icons)

    def _assert_untouched(self, readme, svg):
        self.assertEqual(readme.read_text(encoding="utf-8"), SENTINEL_README)
        self.assertEqual(svg.read_text(encoding="utf-8"), SENTINEL_SVG)

    def _assert_wellformed(self, readme, svg, icons):
        svg_text = svg.read_text(encoding="utf-8")
        ET.fromstring(svg_text)
        self.assertNotIn("\r", svg_text)
        for path in sorted(icons.glob("*.svg")):
            ET.fromstring(path.read_text(encoding="utf-8"))
        content = readme.read_text(encoding="utf-8")
        self.assertTrue(content.startswith(config.MARKER_START))
        self.assertEqual(content.count("<table"), 1)
        self.assertEqual(content.count("</table>"), 1)
        for chip_src in set(re.findall(r'src="([^"]+)"', content)):
            if chip_src.startswith(config.LANG_ICONS_SRC_DIR):
                self.assertTrue((icons / pathlib.PurePosixPath(chip_src).name)
                                .is_file(), chip_src)
        updated = [ln for ln in content.split("\n")
                   if ln.startswith(config.UPDATED_PREFIX)]
        self.assertEqual(len(updated), 1)


class TestEndToEndFromFixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.readme = pathlib.Path(tmp.name) / "README.md"
        self.svg = pathlib.Path(tmp.name) / "languages.svg"
        self.icons = pathlib.Path(tmp.name) / "icons"
        self.readme.write_bytes(config.FIXTURE_README_MESSY.read_bytes())
        self.args = ["--from-json", str(config.FIXTURE_SAMPLE),
                     "--readme", str(self.readme), "--svg", str(self.svg),
                     "--icons-dir", str(self.icons)]

    def _artifact_total(self):
        return 2 + len(list(self.icons.glob("*.svg")))

    def test_happy_path_rewrites_readme_and_writes_strip(self):
        with silence() as out:
            rc = generate.main(self.args)
        self.assertEqual(rc, 0)
        total = self._artifact_total()
        self.assertIn(f"done: {total} changed, 0 unchanged", out.getvalue())

        svg_text = self.svg.read_text(encoding="utf-8")
        root = ET.fromstring(svg_text)
        expected_aria = "Top languages: " + ", ".join(
            f"{name} {svg_strip.format_bytes(size)}" for name, size in EXPECTED_LANGS
        )
        self.assertEqual(root.get("aria-label"), expected_aria)
        self.assertEqual(root.find(f"{{{SVG_NS}}}title").text, expected_aria)
        self.assertTrue(expected_aria.startswith("Top languages: Typst 10.3M"))

        content = self.readme.read_text(encoding="utf-8")
        self.assertTrue(content.startswith(config.MARKER_START))
        self.assertEqual(content[0], "<")
        self.assertEqual(content.count("<table"), 1)
        self.assertEqual(content.count("</table>"), 1)
        self.assertIn(f'<table width="{config.TABLE_WIDTH}">', content)
        self.assertEqual(
            content.count(f'<td width="{config.TABLE_CELL_WIDTH}">'), 40
        )
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        updated = [ln for ln in content.split("\n")
                   if ln.startswith(config.UPDATED_PREFIX)]
        self.assertEqual(
            updated, [f"{config.UPDATED_PREFIX}{today}{config.UPDATED_SUFFIX}"]
        )
        self.assertIn(
            '<a href="https://github.com/lavantien/modern-swe-library">'
            "modern-swe-library</a><br>(<i>2023</i>)&nbsp;(<b>200+9⭐</b>)"
            + NBSP_JOIN + BADGE_IMG
            + '<br><img src="assets/lang-icons/go-plain.svg" alt="Go"'
              ' width="14" height="14">&nbsp;Go&nbsp;400K'
              ' <img src="assets/lang-icons/python-plain.svg" alt="Python"'
              ' width="14" height="14">&nbsp;Python&nbsp;50K',
            content,
        )
        self.assertIn(
            '<a href="https://github.com/lavantien/dotfiles">dotfiles</a>'
            "<br>(<i>2023</i>)&nbsp;(<b>42⭐</b>)" + NBSP_JOIN + BADGE_IMG
            + '<br><img src="assets/lang-icons/typst-original.svg" alt="Typst"'
              ' width="14" height="14">&nbsp;Typst&nbsp;10.3M'
              ' <img src="assets/lang-icons/lua-plain.svg" alt="Lua"'
              ' width="14" height="14">&nbsp;Lua&nbsp;50K',
            content,
        )
        self.assertNotIn(
            '<a href="https://github.com/lavantien/caro-ai-pvp">caro-ai-pvp</a>'
            "<br>(<i>2025</i>)&nbsp;(<b>15⭐</b>)" + NBSP_JOIN + BADGE_IMG,
            content,
        )
        self.assertEqual(content.count(BADGE_IMG), 15)
        icon_names = sorted(p.name for p in self.icons.glob("*.svg"))
        self.assertEqual(icon_names, [
            "bash-plain.svg", "c-original.svg", "go-plain.svg", "java-plain.svg",
            "javascript-plain.svg", "kotlin-plain.svg", "lua-plain.svg",
            "perl-plain.svg", "python-plain.svg", "ruby-plain.svg",
            "typescript-plain.svg", "typst-original.svg",
        ])
        self.assertIn(
            '<a href="https://github.com/lavantien/tied-zebra">tied-zebra</a>'
            "<br>(<i>2022</i>)&nbsp;(<b>7⭐</b>)"
            + NBSP_JOIN + BADGE_IMG
            + '<br><img src="assets/lang-icons/bash-plain.svg" alt="Shell"'
              ' width="14" height="14">&nbsp;Shell&nbsp;526',
            content,
        )

    def test_second_run_is_byte_identical_noop(self):
        with silence() as first:
            self.assertEqual(generate.main(self.args), 0)
        total = self._artifact_total()
        readme_once = self.readme.read_bytes()
        svg_once = self.svg.read_bytes()
        icons_once = {p.name: p.read_bytes() for p in self.icons.glob("*.svg")}
        with silence() as second:
            self.assertEqual(generate.main(self.args), 0)
        self.assertEqual(self.readme.read_bytes(), readme_once)
        self.assertEqual(self.svg.read_bytes(), svg_once)
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.icons.glob("*.svg")}, icons_once
        )
        self.assertIn(f"done: {total} changed, 0 unchanged", first.getvalue())
        self.assertIn("0 changed", second.getvalue())
        self.assertIn("unchanged", second.getvalue())

    def test_final_summary_line_is_exact(self):
        with silence() as first:
            self.assertEqual(generate.main(self.args), 0)
        total = self._artifact_total()
        with silence() as second:
            self.assertEqual(generate.main(self.args), 0)
        self.assertEqual(
            first.getvalue().splitlines()[-1],
            f"done: {total} changed, 0 unchanged",
        )
        self.assertEqual(
            second.getvalue().splitlines()[-1],
            f"done: 0 changed, {total} unchanged",
        )

    @mock.patch("scripts.github_client.fetch_repo_snapshot",
                side_effect=AssertionError("network snapshot fetch in --from-json mode"))
    def test_from_json_mode_uses_stub_not_the_network(self, _snapshot_fetch):
        with silence():
            rc = generate.main(self.args)
        self.assertEqual(rc, 0)

    @mock.patch("scripts.github_client.fetch_repo_snapshot",
                side_effect=AssertionError("network snapshot fetch in --from-json mode"))
    def test_stub_returns_snapshot_for_archived_pinned_repo(self, _snapshot_fetch):
        src_items = [
            dict(item(name="modern-swe-library", stars=17, langs=()), archived=True),
            item(name="other", stars=3, langs=()),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp) / "repos.json"
            src.write_text(json.dumps(src_items), encoding="utf-8")
            readme = pathlib.Path(tmp) / "README.md"
            svg = pathlib.Path(tmp) / "languages.svg"
            icons = pathlib.Path(tmp) / "icons"
            with silence():
                rc = generate.main(["--from-json", str(src),
                                    "--readme", str(readme), "--svg", str(svg),
                                    "--icons-dir", str(icons)])
            content = readme.read_text(encoding="utf-8")
        self.assertEqual(rc, 0)
        self.assertIn(
            '<a href="https://github.com/lavantien/modern-swe-library">'
            "modern-swe-library</a><br>(<i>2023</i>)&nbsp;(<b>200+17⭐</b>)"
            + NBSP_JOIN + BADGE_IMG,
            content,
        )
        self.assertIn("(<b>0⭐</b>)", content)

    def test_fixture_snapshot_fetch_normalizes_descriptions(self):
        items = [
            dict(item(name="described", stars=3,
                      langs=(("Go", 400000), ("HTML", 5)),
                      created="2024-02-02T00:00:00Z"),
                 description="live description"),
            dict(item(name="nullish", stars=1, langs=()), description=None),
        ]
        fetch = generate._fixture_snapshot_fetch(items)
        self.assertEqual(
            fetch("lavantien/described"),
            {"stars": 3, "description": "live description",
             "createdAt": "2024-02-02T00:00:00Z",
             "langs": (("Go", 400000),)},
        )
        self.assertEqual(fetch("lavantien/nullish")["description"], "")
        self.assertEqual(fetch("lavantien/nullish")["langs"], ())
        self.assertIsNone(fetch("lavantien/absent"))

    @mock.patch("scripts.github_client.fetch_repo_snapshot",
                return_value={"stars": 9, "description": "lib",
                              "createdAt": "2023-01-01T00:00:00Z",
                              "langs": (("Go", 400000), ("Python", 50000))})
    @mock.patch("scripts.github_client.fetch_repos")
    def test_live_mode_wires_gh_client(self, fetch_repos, snapshot_fetch):
        fetch_repos.return_value = json.loads(
            config.FIXTURE_SAMPLE.read_text(encoding="utf-8"))
        with silence():
            rc = generate.main(["--live", "--readme", str(self.readme),
                                "--svg", str(self.svg),
                                "--icons-dir", str(self.icons)])
        self.assertEqual(rc, 0)
        fetch_repos.assert_called_once_with()
        snapshot_fetch.assert_called_once_with("lavantien/modern-swe-library")
        content = self.readme.read_text(encoding="utf-8")
        self.assertIn(
            '<a href="https://github.com/lavantien/modern-swe-library">'
            "modern-swe-library</a><br>(<i>2023</i>)&nbsp;(<b>200+9⭐</b>)"
            + NBSP_JOIN + BADGE_IMG
            + '<br><img src="assets/lang-icons/go-plain.svg" alt="Go"'
              ' width="14" height="14">&nbsp;Go&nbsp;400K'
              ' <img src="assets/lang-icons/python-plain.svg" alt="Python"'
              ' width="14" height="14">&nbsp;Python&nbsp;50K',
            content,
        )

    def test_icons_dir_defaults_to_config_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            icons = pathlib.Path(tmp) / "from-config"
            with mock.patch.object(config, "LANG_ICONS_DIR", icons), silence():
                rc = generate.main([
                    "--from-json", str(config.FIXTURE_SAMPLE),
                    "--readme", str(self.readme), "--svg", str(self.svg),
                ])
            self.assertEqual(rc, 0)
            self.assertGreater(len(list(icons.glob("*.svg"))), 0)

    def test_bootstrap_outranks_shadowing_scripts_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            decoy = pathlib.Path(tmp)
            (decoy / "scripts").mkdir()
            (decoy / "scripts" / "__init__.py").write_text(
                "raise AssertionError('decoy scripts package imported')\n",
                encoding="utf-8",
            )
            script = str(config.REPO_ROOT / "scripts" / "generate.py")
            runner = (
                "import sys, runpy\n"
                f"sys.path.insert(0, {str(decoy)!r})\n"
                "sys.argv = ['generate.py', '--help']\n"
                f"runpy.run_path({script!r}, run_name='__main__')\n"
            )
            proc = subprocess.run(
                [sys.executable, "-c", runner],
                capture_output=True, text=True, cwd=str(decoy),
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("decoy scripts package imported", proc.stderr)

    def test_script_entry_direct_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            readme = pathlib.Path(tmp) / "README.md"
            svg = pathlib.Path(tmp) / "languages.svg"
            icons = pathlib.Path(tmp) / "icons"
            proc = subprocess.run(
                [sys.executable, str(config.REPO_ROOT / "scripts" / "generate.py"),
                 "--from-json", str(config.FIXTURE_SAMPLE),
                 "--readme", str(readme), "--svg", str(svg),
                 "--icons-dir", str(icons)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("changed", proc.stdout)
            self.assertTrue(svg.is_file())
            self.assertTrue(any(icons.glob("*.svg")))
            self.assertTrue(readme.read_text(encoding="utf-8")
                            .startswith(config.MARKER_START))


class TestWorkflow(unittest.TestCase):
    def test_cron_commits_every_artifact_family(self):
        lines = config.WORKFLOW_PATH.read_text(encoding="utf-8").splitlines()
        add_line = next(ln for ln in lines if "git add" in ln)
        for artifact in ("README.md", "assets/languages.svg", "assets/lang-icons"):
            self.assertIn(artifact, add_line)


if __name__ == "__main__":
    unittest.main()
