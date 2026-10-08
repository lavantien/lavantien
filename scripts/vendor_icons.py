"""Vendor icon SVGs from pinned upstream refs into assets/devicons.

Each icon named by config.DEVICON_MAP is resolved through
config.ICON_SOURCES, downloaded from its pinned upstream ref,
validated as inert SVG (parses, svg root, no scripts, no external URL
attributes), and written under its slug-variant filename, so languages
sharing an icon dedupe to one file. Existing files that still validate
are skipped, keeping `make icons` cheap and usable offline once the
assets are vendored. ATTRIBUTION.md embeds every source repository,
pinned ref, and license fetched from the same refs verbatim.
"""

import argparse
import datetime
import pathlib
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts import config

TIMEOUT_SECONDS = 30
USER_AGENT = "lavantien-profile-icons/1.0"
MAX_SVG_BYTES = 100 * 1024
SVG_ROOT_TAGS = ("svg", "{http://www.w3.org/2000/svg}svg")
ATTRIBUTION_NAME = "ATTRIBUTION.md"


def resolve_source(slug):
    return config.ICON_SOURCE_OVERRIDES.get(slug, config.DEFAULT_ICON_SOURCE)


def _source_url(source_name, path):
    source = config.ICON_SOURCES[source_name]
    return f"{source['raw_base']}/{source['pinned_ref']}/{path}"


def icon_url(slug, variant):
    source_name = resolve_source(slug)
    template = config.ICON_SOURCES[source_name]["icon_path"]
    return _source_url(source_name, template.format(slug=slug, variant=variant))


def license_url(source_name):
    return _source_url(source_name, config.ICON_SOURCES[source_name]["license_path"])


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read()


def validate_svg(data, language):
    if not data:
        raise ValueError(f"{language}: empty file")
    if len(data) >= MAX_SVG_BYTES:
        raise ValueError(f"{language}: {len(data)} bytes is not under {MAX_SVG_BYTES}")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"{language}: not valid XML ({exc})") from exc
    if root.tag not in SVG_ROOT_TAGS:
        raise ValueError(f"{language}: root element is {root.tag}, not svg")
    for element in root.iter():
        tag = element.tag.rpartition("}")[-1]
        if tag == "script":
            raise ValueError(f"{language}: contains a script element")
        for value in element.attrib.values():
            if value.startswith("http"):
                raise ValueError(
                    f"{language}: attribute value {value!r} references an external URL"
                )


def fetch_or_skip(path, url, language, force):
    if path.exists() and not force:
        try:
            validate_svg(path.read_bytes(), language)
            return "skipped"
        except ValueError:
            pass
    try:
        data = fetch(url)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"{language}: HTTP {exc.code} fetching {url}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"{language}: cannot fetch {url} ({exc.reason})") from exc
    validate_svg(data, language)
    path.write_bytes(data)
    return "fetched"


def _fetch_license(source_name):
    url = license_url(source_name)
    try:
        license_text = fetch(url).decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ValueError(f"{ATTRIBUTION_NAME}: HTTP {exc.code} fetching {url}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(
            f"{ATTRIBUTION_NAME}: cannot fetch {url} ({exc.reason})"
        ) from exc
    if not license_text.strip():
        raise ValueError(
            f"{ATTRIBUTION_NAME}: {source_name} license fetched from {url} is empty"
        )
    return license_text


def write_attribution(files, force, downloaded_any):
    path = config.DEVICON_DIR / ATTRIBUTION_NAME
    if path.exists() and not force and not downloaded_any:
        print(f"skipped {ATTRIBUTION_NAME}")
        return
    sources = sorted({source_name for _, source_name in files})
    lines = [
        "# Vendored icons",
        "",
        f"Vendored: {datetime.date.today().isoformat()}",
        "",
        "Sources:",
        "",
    ]
    lines.extend(
        f"- {name}: {config.ICON_SOURCES[name]['repo']} "
        f"@ {config.ICON_SOURCES[name]['pinned_ref']}"
        for name in sources
    )
    lines.extend(["", "Files:", ""])
    lines.extend(f"- {filename} ({source})" for filename, source in files)
    lines.extend([
        "",
        "Icons are vendored from each source repository at the pinned",
        "ref above so the languages strip in the profile README is",
        "self-contained and needs no external service at render time.",
        "Re-vendor with `make icons`; add `--force` to redownload.",
    ])
    for name in sources:
        lines.extend(["", f"## {name} license", "", _fetch_license(name)])
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"fetched {ATTRIBUTION_NAME}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Vendor icon SVGs into assets/devicons."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="redownload files that already exist and validate",
    )
    args = parser.parse_args(argv)
    config.DEVICON_DIR.mkdir(parents=True, exist_ok=True)

    targets = {}
    for language, (slug, variant) in config.DEVICON_MAP.items():
        targets.setdefault((slug, variant), language)
    files = [
        (f"{slug}-{variant}.svg", resolve_source(slug)) for slug, variant in targets
    ]

    downloaded_any = False
    for (slug, variant), language in sorted(targets.items()):
        filename = f"{slug}-{variant}.svg"
        try:
            status = fetch_or_skip(
                config.DEVICON_DIR / filename,
                icon_url(slug, variant),
                language,
                args.force,
            )
        except ValueError as exc:
            print(f"rejected {filename}: {exc}")
            raise
        if status == "fetched":
            downloaded_any = True
        print(f"{status} {filename}")

    write_attribution(files, args.force, downloaded_any)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
