import contextlib
import datetime
import io
import pathlib
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

from scripts import config, vendor_icons

GOOD_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'
    b'<path d="M2 2h124v124H2z"/></svg>'
)
OTHER_SVG = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
LICENSE_BYTES = b"MIT license text\n"
ICON_URL = "https://example.com/icons/go/go-plain.svg"
LICENSE_URL = vendor_icons.RAW_BASE + "/LICENSE"


def fake_urlopen(url_map):
    def open_(request, timeout=None):
        data = url_map[request.full_url]  # unexpected url fails the test
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = data
        return response

    return mock.Mock(side_effect=open_)


def no_network():
    urlopen = mock.Mock(side_effect=AssertionError("network access in test"))
    return mock.patch("urllib.request.urlopen", new=urlopen), urlopen


@contextlib.contextmanager
def captured():
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        yield out


class TestIconUrl(unittest.TestCase):
    def test_exact_url(self):
        self.assertEqual(
            vendor_icons.icon_url("go", "plain"),
            "https://raw.githubusercontent.com/devicons/devicon/"
            + config.PINNED_DEVICON_REF
            + "/icons/go/go-plain.svg",
        )


class TestValidateSvg(unittest.TestCase):
    def test_accepts_minimal_well_formed_svg(self):
        self.assertIsNone(vendor_icons.validate_svg(GOOD_SVG, "Go"))

    def test_rejects_empty_file(self):
        with self.assertRaises(ValueError) as ctx:
            vendor_icons.validate_svg(b"", "Go")
        self.assertEqual(str(ctx.exception), "Go: empty file")

    def test_rejects_non_xml_garbage(self):
        with self.assertRaises(ValueError) as ctx:
            vendor_icons.validate_svg(b"this is not xml <", "Go")
        self.assertEqual(
            str(ctx.exception),
            f"Go: not valid XML ({ctx.exception.__cause__})",
        )

    def test_rejects_wrong_root_tag(self):
        with self.assertRaises(ValueError) as ctx:
            vendor_icons.validate_svg(b"<g/>", "Go")
        self.assertEqual(str(ctx.exception), "Go: root element is g, not svg")

    def test_rejects_script_element(self):
        bad = (
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b"<script>alert(1)</script></svg>"
        )
        with self.assertRaises(ValueError) as ctx:
            vendor_icons.validate_svg(bad, "Go")
        self.assertEqual(str(ctx.exception), "Go: contains a script element")

    def test_rejects_external_url_attribute(self):
        bad = (
            b'<svg xmlns="http://www.w3.org/2000/svg"'
            b' data-x="http://evil.example"/>'
        )
        with self.assertRaises(ValueError) as ctx:
            vendor_icons.validate_svg(bad, "Go")
        self.assertEqual(
            str(ctx.exception),
            "Go: attribute value 'http://evil.example' "
            "references an external URL",
        )

    def test_rejects_exactly_max_bytes(self):
        # boundary: a file of exactly the vendoring cap that is otherwise a
        # valid svg must still be rejected. The cap is pinned as a literal
        # here so a mutated MAX_SVG_BYTES cannot resize the probe with it
        cap = 100 * 1024
        pad = cap - len(b"<svg/>") - len(b"<!--") - len(b"-->")
        data = b"<svg/>" + b"<!--" + b" " * pad + b"-->"
        self.assertEqual(len(data), cap)
        with self.assertRaises(ValueError) as ctx:
            vendor_icons.validate_svg(data, "Go")
        self.assertEqual(
            str(ctx.exception),
            f"Go: {cap} bytes is not under {vendor_icons.MAX_SVG_BYTES}",
        )


class TestFetchOrSkip(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = pathlib.Path(tmp.name) / "go-plain.svg"

    def test_existing_valid_file_skips_without_network(self):
        self.path.write_bytes(GOOD_SVG)
        patch, urlopen = no_network()
        with patch:
            status = vendor_icons.fetch_or_skip(
                self.path, ICON_URL, "Go", force=False
            )
        self.assertEqual(status, "skipped")
        urlopen.assert_not_called()

    def test_missing_file_downloads_and_writes(self):
        with mock.patch(
            "urllib.request.urlopen", new=fake_urlopen({ICON_URL: GOOD_SVG})
        ) as urlopen:
            status = vendor_icons.fetch_or_skip(
                self.path, ICON_URL, "Go", force=False
            )
        self.assertEqual(status, "fetched")
        self.assertEqual(self.path.read_bytes(), GOOD_SVG)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, ICON_URL)
        # literal pin: the module contract is a 30 second fetch timeout
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 30)

    def test_corrupt_existing_file_redownloads(self):
        self.path.write_bytes(b"<svg><script>x</script></svg>")
        with mock.patch(
            "urllib.request.urlopen", new=fake_urlopen({ICON_URL: GOOD_SVG})
        ):
            status = vendor_icons.fetch_or_skip(
                self.path, ICON_URL, "Go", force=False
            )
        self.assertEqual(status, "fetched")
        self.assertEqual(self.path.read_bytes(), GOOD_SVG)

    def test_force_redownloads_valid_existing_file(self):
        self.path.write_bytes(GOOD_SVG)
        with mock.patch(
            "urllib.request.urlopen", new=fake_urlopen({ICON_URL: OTHER_SVG})
        ):
            status = vendor_icons.fetch_or_skip(
                self.path, ICON_URL, "Go", force=True
            )
        self.assertEqual(status, "fetched")
        self.assertEqual(self.path.read_bytes(), OTHER_SVG)

    def test_rejected_download_raises_and_writes_nothing(self):
        with mock.patch(
            "urllib.request.urlopen", new=fake_urlopen({ICON_URL: b"garbage"})
        ):
            with self.assertRaises(ValueError):
                vendor_icons.fetch_or_skip(
                    self.path, ICON_URL, "Go", force=False
                )
        self.assertFalse(self.path.exists())

    def test_http_error_becomes_value_error(self):
        error = urllib.error.HTTPError(ICON_URL, 404, "Not Found", None, None)
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ValueError) as ctx:
                vendor_icons.fetch_or_skip(
                    self.path, ICON_URL, "Go", force=False
                )
        self.assertEqual(str(ctx.exception), f"Go: HTTP 404 fetching {ICON_URL}")

    def test_url_error_becomes_value_error(self):
        error = urllib.error.URLError("dns gone")
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ValueError) as ctx:
                vendor_icons.fetch_or_skip(
                    self.path, ICON_URL, "Go", force=False
                )
        self.assertEqual(
            str(ctx.exception), f"Go: cannot fetch {ICON_URL} (dns gone)"
        )


class TestWriteAttribution(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        self.path = self.dir / "ATTRIBUTION.md"
        patcher = mock.patch.object(config, "DEVICON_DIR", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _expected_content(self, filenames):
        return "\n".join([
            "# Vendored devicon icons",
            "",
            "Source: https://github.com/devicons/devicon",
            f"Pinned ref: {config.PINNED_DEVICON_REF}",
            f"Vendored: {datetime.date.today().isoformat()}",
            "",
            "Files:",
            "",
            *[f"- {name}" for name in filenames],
            "",
            "These SVGs are vendored from the devicon repository at the pinned",
            "ref above so the languages strip in the profile README is",
            "self-contained and needs no external service at render time.",
            "Re-vendor with `make icons`; add `--force` (or edit the Makefile",
            "target's invocation) to redownload.",
            "",
            "## LICENSE",
            "",
            LICENSE_BYTES.decode("utf-8"),
            "",
        ])

    def test_skips_when_present_and_nothing_downloaded(self):
        self.path.write_text("existing", encoding="utf-8")
        patch, urlopen = no_network()
        with patch, captured() as out:
            vendor_icons.write_attribution(
                ["go-plain.svg"], force=False, downloaded_any=False
            )
        self.assertEqual(self.path.read_text(encoding="utf-8"), "existing")
        self.assertEqual(out.getvalue(), "skipped ATTRIBUTION.md\n")
        urlopen.assert_not_called()

    def test_writes_attribution_when_missing(self):
        with mock.patch(
            "urllib.request.urlopen",
            new=fake_urlopen({LICENSE_URL: LICENSE_BYTES}),
        ) as urlopen:
            with captured() as out:
                vendor_icons.write_attribution(
                    ["go-plain.svg", "php-plain.svg"],
                    force=False,
                    downloaded_any=False,
                )
        self.assertEqual(
            self.path.read_text(encoding="utf-8"),
            self._expected_content(["go-plain.svg", "php-plain.svg"]),
        )
        self.assertEqual(out.getvalue(), "fetched ATTRIBUTION.md\n")
        self.assertEqual(urlopen.call_args.args[0].full_url, LICENSE_URL)

    def test_force_refetches_existing_attribution(self):
        self.path.write_text("stale", encoding="utf-8")
        with mock.patch(
            "urllib.request.urlopen",
            new=fake_urlopen({LICENSE_URL: LICENSE_BYTES}),
        ):
            with captured():
                vendor_icons.write_attribution(
                    ["go-plain.svg"], force=True, downloaded_any=False
                )
        self.assertIn("## LICENSE", self.path.read_text(encoding="utf-8"))

    def test_downloads_refetch_existing_attribution(self):
        self.path.write_text("stale", encoding="utf-8")
        with mock.patch(
            "urllib.request.urlopen",
            new=fake_urlopen({LICENSE_URL: LICENSE_BYTES}),
        ):
            with captured():
                vendor_icons.write_attribution(
                    ["go-plain.svg"], force=False, downloaded_any=True
                )
        self.assertIn("## LICENSE", self.path.read_text(encoding="utf-8"))

    def test_blank_license_rejected_and_not_written(self):
        with mock.patch(
            "urllib.request.urlopen", new=fake_urlopen({LICENSE_URL: b"  \n"})
        ):
            with self.assertRaises(ValueError) as ctx:
                vendor_icons.write_attribution(
                    ["go-plain.svg"], force=False, downloaded_any=True
                )
        self.assertEqual(
            str(ctx.exception),
            f"ATTRIBUTION.md: LICENSE fetched from {LICENSE_URL} is empty",
        )
        self.assertFalse(self.path.exists())

    def test_http_error_becomes_value_error(self):
        error = urllib.error.HTTPError(LICENSE_URL, 403, "Forbidden", None, None)
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ValueError) as ctx:
                vendor_icons.write_attribution(
                    ["go-plain.svg"], force=False, downloaded_any=False
                )
        self.assertEqual(
            str(ctx.exception),
            f"ATTRIBUTION.md: HTTP 403 fetching {LICENSE_URL}",
        )

    def test_url_error_becomes_value_error(self):
        error = urllib.error.URLError("no dns")
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ValueError) as ctx:
                vendor_icons.write_attribution(
                    ["go-plain.svg"], force=False, downloaded_any=False
                )
        self.assertEqual(
            str(ctx.exception),
            f"ATTRIBUTION.md: cannot fetch {LICENSE_URL} (no dns)",
        )


class TestMain(unittest.TestCase):
    # PHP and Hack share php-plain, so this map must dedupe to two files
    ICON_MAP = {"PHP": ("php", "plain"), "Hack": ("php", "plain"),
                "Go": ("go", "plain")}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)

    def _urls(self, php_bytes=GOOD_SVG, go_bytes=GOOD_SVG):
        return {
            vendor_icons.icon_url("go", "plain"): go_bytes,
            vendor_icons.icon_url("php", "plain"): php_bytes,
            LICENSE_URL: LICENSE_BYTES,
        }

    def _run(self, urls, argv=()):
        with mock.patch.object(config, "DEVICON_DIR", self.dir), \
                mock.patch.object(config, "DEVICON_MAP", self.ICON_MAP), \
                mock.patch(
                    "urllib.request.urlopen", new=fake_urlopen(urls)
                ) as urlopen:
            with captured() as out:
                rc = vendor_icons.main(list(argv))
        return rc, out.getvalue(), urlopen

    def test_happy_path_fetches_dedupes_and_writes_attribution(self):
        rc, out, urlopen = self._run(self._urls())
        self.assertEqual(rc, 0)
        self.assertEqual(
            out.splitlines(),
            ["fetched go-plain.svg", "fetched php-plain.svg",
             "fetched ATTRIBUTION.md"],
        )
        self.assertEqual(
            sorted(p.name for p in self.dir.iterdir()),
            ["ATTRIBUTION.md", "go-plain.svg", "php-plain.svg"],
        )
        self.assertEqual((self.dir / "go-plain.svg").read_bytes(), GOOD_SVG)
        self.assertEqual((self.dir / "php-plain.svg").read_bytes(), GOOD_SVG)
        attribution = (self.dir / "ATTRIBUTION.md").read_text(encoding="utf-8")
        self.assertIn("\n- go-plain.svg\n- php-plain.svg\n", attribution)
        self.assertIn("## LICENSE", attribution)
        requested = {call.args[0].full_url for call in urlopen.call_args_list}
        self.assertEqual(
            requested,
            {vendor_icons.icon_url("go", "plain"),
             vendor_icons.icon_url("php", "plain"), LICENSE_URL},
        )

    def test_second_run_skips_everything_without_network(self):
        self._run(self._urls())
        patch, urlopen = no_network()
        with patch, mock.patch.object(config, "DEVICON_DIR", self.dir), \
                mock.patch.object(config, "DEVICON_MAP", self.ICON_MAP), \
                captured() as out:
            rc = vendor_icons.main([])
        self.assertEqual(rc, 0)
        self.assertEqual(
            out.getvalue().splitlines(),
            ["skipped go-plain.svg", "skipped php-plain.svg",
             "skipped ATTRIBUTION.md"],
        )
        urlopen.assert_not_called()

    def test_rejected_icon_raises_after_report(self):
        urls = self._urls(php_bytes=b"garbage")
        with mock.patch.object(config, "DEVICON_DIR", self.dir), \
                mock.patch.object(config, "DEVICON_MAP", self.ICON_MAP), \
                mock.patch("urllib.request.urlopen", new=fake_urlopen(urls)):
            with captured() as out:
                with self.assertRaises(ValueError):
                    vendor_icons.main([])
        self.assertTrue(
            out.getvalue().startswith(
                "fetched go-plain.svg\n"
                "rejected php-plain.svg: PHP: not valid XML ("
            ),
            out.getvalue(),
        )
        self.assertTrue((self.dir / "go-plain.svg").exists())
        self.assertFalse((self.dir / "php-plain.svg").exists())
        self.assertFalse((self.dir / "ATTRIBUTION.md").exists())

    def test_script_entry_direct_execution(self):
        # the Makefile invokes the file by path; --help exercises the import
        # bootstrap without touching the network or the devicon dir
        proc = subprocess.run(
            [sys.executable,
             str(config.REPO_ROOT / "scripts" / "vendor_icons.py"), "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--force", proc.stdout)


if __name__ == "__main__":
    unittest.main()
