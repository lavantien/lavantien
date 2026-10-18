import io
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import config, github_client
from scripts.github_client import (
    GhError,
    fetch_repo_snapshot,
    fetch_repos,
    load_repos_json,
)


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
            self.assertTrue(
                str(ctx.exception).startswith(f"cannot load repos json from {bad}: "),
                str(ctx.exception),
            )

    def test_missing_file_raises_with_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = pathlib.Path(tmp) / "missing.json"
            with self.assertRaises(GhError) as ctx:
                load_repos_json(missing)
            self.assertTrue(
                str(ctx.exception).startswith(f"cannot load repos json from {missing}: "),
                str(ctx.exception),
            )


class TestFetchRepos(unittest.TestCase):
    @mock.patch("scripts.github_client.subprocess.run")
    def test_invokes_gh_with_configured_flags(self, run):
        run.return_value = gh_result(stdout="[]")
        self.assertEqual(fetch_repos(), [])
        run.assert_called_once_with(
            ["gh", "repo", "list", "--limit", str(config.GH_REPO_LIMIT),
             "--json", config.GH_JSON_FIELDS],
            capture_output=True, text=True, timeout=60,
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
        self.assertEqual(
            str(ctx.exception), "gh repo list exited 1: gh: auth failure"
        )

    @mock.patch("scripts.github_client.subprocess.run")
    def test_nonzero_exit_excerpt_is_exactly_200_chars(self, run):
        """205 chars of stderr: the excerpt must keep exactly 200, so an
        off-by-one on the cap cannot slip the 201st char into the message."""
        run.return_value = gh_result(stderr="A" * 205, returncode=1)
        with self.assertRaises(GhError) as ctx:
            fetch_repos()
        self.assertEqual(
            str(ctx.exception), "gh repo list exited 1: " + "A" * 200
        )

    @mock.patch("scripts.github_client.subprocess.run")
    def test_nonzero_exit_falls_back_to_stdout_excerpt(self, run):
        run.return_value = gh_result(stdout="out detail", returncode=1)
        with self.assertRaises(GhError) as ctx:
            fetch_repos()
        self.assertEqual(
            str(ctx.exception), "gh repo list exited 1: out detail"
        )

    @mock.patch("scripts.github_client.subprocess.run")
    def test_invalid_json_raises_with_stdout_excerpt(self, run):
        run.return_value = gh_result(stdout="<html>502</html>")
        with self.assertRaises(GhError) as ctx:
            fetch_repos()
        self.assertEqual(
            str(ctx.exception),
            "gh repo list returned invalid json: <html>502</html>",
        )

    @mock.patch("scripts.github_client.subprocess.run")
    def test_missing_executable_raises(self, run):
        run.side_effect = FileNotFoundError("no gh")
        with self.assertRaises(GhError) as ctx:
            fetch_repos(gh_exec="stub")
        self.assertEqual(
            str(ctx.exception),
            "cannot run gh repo list via 'stub': no gh",
        )


class TestFetchRepoSnapshot(unittest.TestCase):
    @mock.patch("scripts.github_client.subprocess.run")
    def test_parses_all_fields(self, run):
        run.return_value = gh_result(stdout=json.dumps({
            "stargazerCount": 1234,
            "description": "curated resources",
            "createdAt": "2023-05-06T07:08:09Z",
            "languages": [{"size": 400000, "node": {"name": "Go"}},
                          {"size": 50000, "node": {"name": "Python"}}],
        }))
        self.assertEqual(
            fetch_repo_snapshot("lavantien/modern-swe-library"),
            {"stars": 1234, "description": "curated resources",
             "createdAt": "2023-05-06T07:08:09Z",
             "langs": (("Go", 400000), ("Python", 50000))},
        )
        run.assert_called_once_with(
            ["gh", "repo", "view", "lavantien/modern-swe-library",
             "--json", "stargazerCount,description,createdAt,languages"],
            capture_output=True, text=True, timeout=60,
        )

    @mock.patch("scripts.github_client.subprocess.run")
    def test_null_description_normalizes_to_empty(self, run):
        run.return_value = gh_result(stdout=json.dumps({
            "stargazerCount": 3,
            "description": None,
            "createdAt": "2024-01-01T00:00:00Z",
        }))
        self.assertEqual(
            fetch_repo_snapshot("x/y"),
            {"stars": 3, "description": "", "createdAt": "2024-01-01T00:00:00Z",
             "langs": ()},
        )

    @mock.patch("scripts.github_client.subprocess.run")
    def test_non_int_star_count_returns_none(self, run):
        for bad in ("12", True):
            with self.subTest(bad=bad):
                run.return_value = gh_result(stdout=json.dumps({
                    "stargazerCount": bad,
                    "description": "d",
                    "createdAt": "2024-01-01T00:00:00Z",
                }))
                self.assertIsNone(fetch_repo_snapshot("x/y"))

    @mock.patch("scripts.github_client.subprocess.run")
    def test_missing_fields_return_none(self, run):
        base = {
            "stargazerCount": 5,
            "description": "d",
            "createdAt": "2024-01-01T00:00:00Z",
        }
        for key in base:
            with self.subTest(missing=key):
                run.return_value = gh_result(
                    stdout=json.dumps({k: v for k, v in base.items() if k != key})
                )
                self.assertIsNone(fetch_repo_snapshot("x/y"))

    @mock.patch("scripts.github_client.subprocess.run")
    def test_non_object_json_returns_none(self, run):
        run.return_value = gh_result(stdout="null")
        self.assertIsNone(fetch_repo_snapshot("x/y"))

    @mock.patch("scripts.github_client.subprocess.run")
    def test_invalid_json_returns_none(self, run):
        run.return_value = gh_result(stdout="")
        self.assertIsNone(fetch_repo_snapshot("x/y"))

    @mock.patch("scripts.github_client.subprocess.run")
    def test_nonzero_exit_returns_none(self, run):
        run.return_value = gh_result(stderr="not found", returncode=1)
        self.assertIsNone(fetch_repo_snapshot("x/y"))

    @mock.patch("scripts.github_client.subprocess.run")
    def test_subprocess_failure_returns_none(self, run):
        run.side_effect = OSError("no gh")
        self.assertIsNone(fetch_repo_snapshot("x/y"))

    @mock.patch("scripts.github_client.subprocess.run")
    def test_retries_once_and_recovers(self, run):
        """Transient gh failure must not wipe the fixed repo's data."""
        run.side_effect = [
            gh_result(stderr="boom", returncode=1),
            gh_result(stdout=json.dumps({
                "stargazerCount": 7,
                "description": "d",
                "createdAt": "2024-01-01T00:00:00Z",
            })),
        ]
        self.assertEqual(
            fetch_repo_snapshot("x/y"),
            {"stars": 7, "description": "d", "createdAt": "2024-01-01T00:00:00Z",
             "langs": ()},
        )
        self.assertEqual(run.call_count, 2)

    @mock.patch("scripts.github_client.subprocess.run")
    def test_both_attempts_failing_returns_none(self, run):
        run.side_effect = [gh_result(returncode=1), gh_result(returncode=1)]
        self.assertIsNone(fetch_repo_snapshot("x/y"))
        self.assertEqual(run.call_count, 2)


class TestTimeouts(unittest.TestCase):
    @mock.patch("scripts.github_client.subprocess.run")
    def test_repo_list_timeout_raises_gherror(self, run):
        run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=60)
        with self.assertRaises(GhError) as ctx:
            fetch_repos()
        self.assertEqual(str(ctx.exception), "gh repo list timed out after 60s")

    @mock.patch("scripts.github_client.subprocess.run")
    def test_snapshot_timeout_returns_none(self, run):
        run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=60)
        self.assertIsNone(fetch_repo_snapshot("x/y"))


class TestRecordMain(unittest.TestCase):
    """`make record` entry: the committed fixture must never carry
    private repo metadata, whatever credential records it."""

    @mock.patch("scripts.github_client.fetch_repos")
    def test_records_public_unforked_only_archived_kept(self, fetch):
        fetch.return_value = [
            {"name": "open", "isFork": False, "isArchived": False,
             "visibility": "PUBLIC"},
            {"name": "secret", "isFork": False, "isArchived": False,
             "visibility": "PRIVATE"},
            {"name": "forked", "isFork": True, "isArchived": False,
             "visibility": "PUBLIC"},
            {"name": "old-but-public", "isFork": False, "isArchived": True,
             "visibility": "PUBLIC"},
            {"name": "lowercase-ok", "isFork": False, "isArchived": False,
             "visibility": "public"},
            {"name": "unknown", "isFork": False, "isArchived": False},
        ]
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            rc = github_client._record_main()
        self.assertEqual(rc, 0)
        expected = [fetch.return_value[0], fetch.return_value[3],
                    fetch.return_value[4]]
        self.assertEqual(
            out.getvalue(), json.dumps(expected, indent=2) + "\n"
        )
        self.assertEqual(json.loads(out.getvalue()), expected)


if __name__ == "__main__":
    unittest.main()
