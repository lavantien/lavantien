import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import config
from scripts.github_client import GhError, fetch_repos, fetch_star_count, load_repos_json


def gh_result(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestLoadReposJson(unittest.TestCase):
    def test_round_trip_sample_fixture(self):
        with open(config.FIXTURE_SAMPLE, encoding="utf-8") as fh:
            expected = json.load(fh)
        self.assertEqual(load_repos_json(config.FIXTURE_SAMPLE), expected)

    def test_malformed_json_raises_with_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = pathlib.Path(tmp) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            with self.assertRaises(GhError) as ctx:
                load_repos_json(bad)
            self.assertIn(str(bad), str(ctx.exception))

    def test_missing_file_raises_with_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = pathlib.Path(tmp) / "missing.json"
            with self.assertRaises(GhError) as ctx:
                load_repos_json(missing)
            self.assertIn(str(missing), str(ctx.exception))


class TestFetchRepos(unittest.TestCase):
    @mock.patch("scripts.github_client.subprocess.run")
    def test_invokes_gh_with_configured_flags(self, run):
        run.return_value = gh_result(stdout="[]")
        self.assertEqual(fetch_repos(), [])
        run.assert_called_once_with(
            ["gh", "repo", "list", "--limit", str(config.GH_REPO_LIMIT),
             "--json", config.GH_JSON_FIELDS],
            capture_output=True, text=True,
        )

    @mock.patch("scripts.github_client.subprocess.run")
    def test_returns_parsed_items(self, run):
        items = [{"name": "x", "stargazerCount": 1}]
        run.return_value = gh_result(stdout=json.dumps(items))
        self.assertEqual(fetch_repos(gh_exec="stub"), items)

    @mock.patch("scripts.github_client.subprocess.run")
    def test_nonzero_exit_raises_with_stderr(self, run):
        run.return_value = gh_result(stderr="gh: auth failure", returncode=1)
        with self.assertRaises(GhError) as ctx:
            fetch_repos()
        self.assertIn("gh: auth failure", str(ctx.exception))

    @mock.patch("scripts.github_client.subprocess.run")
    def test_invalid_json_raises_with_stdout_excerpt(self, run):
        run.return_value = gh_result(stdout="<html>502</html>")
        with self.assertRaises(GhError) as ctx:
            fetch_repos()
        self.assertIn("<html>502</html>", str(ctx.exception))

    @mock.patch("scripts.github_client.subprocess.run")
    def test_missing_executable_raises(self, run):
        run.side_effect = FileNotFoundError("no gh")
        with self.assertRaises(GhError):
            fetch_repos()


class TestFetchStarCount(unittest.TestCase):
    @mock.patch("scripts.github_client.subprocess.run")
    def test_parses_digit_stdout(self, run):
        run.return_value = gh_result(stdout="1234\n")
        self.assertEqual(fetch_star_count("lavantien/modern-swe-library"), 1234)
        run.assert_called_once_with(
            ["gh", "repo", "view", "lavantien/modern-swe-library",
             "--json", "stargazerCount", "--jq", ".stargazerCount"],
            capture_output=True, text=True,
        )

    @mock.patch("scripts.github_client.subprocess.run")
    def test_nondigit_stdout_returns_zero(self, run):
        run.return_value = gh_result(stdout="null")
        self.assertEqual(fetch_star_count("x/y"), 0)

    @mock.patch("scripts.github_client.subprocess.run")
    def test_empty_stdout_returns_zero(self, run):
        run.return_value = gh_result(stdout="")
        self.assertEqual(fetch_star_count("x/y"), 0)

    @mock.patch("scripts.github_client.subprocess.run")
    def test_nonzero_exit_returns_zero(self, run):
        run.return_value = gh_result(stderr="not found", returncode=1)
        self.assertEqual(fetch_star_count("x/y"), 0)

    @mock.patch("scripts.github_client.subprocess.run")
    def test_subprocess_failure_returns_zero(self, run):
        run.side_effect = OSError("no gh")
        self.assertEqual(fetch_star_count("x/y"), 0)


if __name__ == "__main__":
    unittest.main()
