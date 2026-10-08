"""Single config hub for the languages strip generator.

Every path, geometry constant, ported workflow value, color, and icon
source lives here. Downstream modules import from this file and
define no constants of their own.
"""

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
READ_PATH = REPO_ROOT / "README.md"
SVG_PATH = REPO_ROOT / "assets" / "languages.svg"
DEVICON_DIR = REPO_ROOT / "assets" / "devicons"
FIXTURE_RECORDED = REPO_ROOT / "fixtures" / "repos.recorded.json"
FIXTURE_SAMPLE = REPO_ROOT / "fixtures" / "repos.sample.json"
FIXTURE_README_MESSY = REPO_ROOT / "fixtures" / "readme.messy.md"
GOLDEN_SVG = REPO_ROOT / "fixtures" / "languages.golden.svg"

TOP_N = 10
STRIP_HEIGHT = 28
ICON_SIZE = 16
PAD_X = 7
LABEL_GAP = 4
ENTRY_GAP = 14
FONT_SIZE = 13
XWIDE_CHARS = frozenset("mwMW")
NARROW_CHARS = frozenset(" \tiljtfr.,:;!'|")
CHAR_WIDTH_XWIDE = 9.6
CHAR_WIDTH_WIDE = 8.2
CHAR_WIDTH_NARROW = 3.8
CHAR_WIDTH_DEFAULT = 7.0
WIDTH_MARGIN = 8
RECOLOR_FILLS = frozenset({"#000", "#000000", "#000080", "black"})
FONT_FAMILY = "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
EMPTY_LABEL = "No language data"

MARKER_START = "<!-- languages:start -->"
MARKER_END = "<!-- languages:end -->"
MARKER_REPOS_START = "<!-- repos:start -->"
MARKER_REPOS_END = "<!-- repos:end -->"
README_ALT_TEXT = "Top languages by code volume"
README_IMG_SRC = "assets/languages.svg"
UPDATED_PREFIX = "*Last updated: "

PROG_LANGS = frozenset({
    "Go", "Dart", "C#", "TypeScript", "Python", "Java", "JavaScript",
    "C++", "C", "Rust", "Swift", "Kotlin", "Ruby", "PHP", "Lua",
    "Blade", "Svelte", "Objective-C", "Hack", "Clojure", "Scala",
    "Haskell", "Elixir", "Julia", "R", "MATLAB", "Perl", "F#", "Typst",
})
YEAR_OVERRIDES = {"SumoBot": 2017, "FlowerShop": 2018}
PINNED_REPOS = ["dotfiles", "llm-tournament", "caro-ai-pvp"]
FIXED_FIRST_REPO = {
    "name": "modern-swe-library",
    "year": 2023,
    "description": "Open knowledge library: curated resources for modern software engineering",
}
TABLE_ROW_LIMIT = 10
EXCLUDED_REPO_NAMES = frozenset({"lavantien"})

GH_OWNER = "lavantien"
REPO_URL_BASE = f"https://github.com/{GH_OWNER}"
GH_JSON_FIELDS = (
    "name,stargazerCount,description,languages,isFork,isArchived,"
    "createdAt,visibility"
)
GH_REPO_LIMIT = 300
GH_TIMEOUT_SECONDS = 60

LANG_COLORS = {
    "Go": "#00ADD8",
    "Python": "#3776AB",
    "TypeScript": "#3178C6",
    "C#": "#239120",
    "Rust": "#DEA584",
    "C++": "#00599C",
    "Java": "#007396",
    "JavaScript": "#F7DF1E",
    "C": "#A8B9CC",
    "Swift": "#F05138",
    "Kotlin": "#7F52FF",
    "Ruby": "#CC342D",
    "PHP": "#777BB4",
    "Lua": "#5D7FA3",
    "Dart": "#0175C2",
    "Svelte": "#FF3E00",
    "Blade": "#F55247",
    "Objective-C": "#4388D0",
    "Hack": "#878787",
    "Clojure": "#5881D8",
    "Scala": "#DC322F",
    "Haskell": "#5D4F85",
    "Elixir": "#4B275F",
    "Julia": "#9558B2",
    "R": "#276DC3",
    "MATLAB": "#E16737",
    "Perl": "#0073A1",
    "F#": "#378BBA",
    "Typst": "#239dad",
}
DEFAULT_COLOR = "#8b949e"
TEXT_MAIN = "#6e7781"

DEVICON_MAP = {
    "Go": ("go", "plain"),
    "Python": ("python", "plain"),
    "TypeScript": ("typescript", "plain"),
    "C#": ("csharp", "plain"),
    "Rust": ("rust", "original"),
    "C++": ("cplusplus", "plain"),
    "Java": ("java", "plain"),
    "JavaScript": ("javascript", "plain"),
    "C": ("c", "original"),
    "Swift": ("swift", "plain"),
    "Kotlin": ("kotlin", "plain"),
    "Ruby": ("ruby", "plain"),
    "PHP": ("php", "plain"),
    "Lua": ("lua", "plain"),
    "Dart": ("dart", "plain"),
    "Svelte": ("svelte", "plain"),
    "Blade": ("laravel", "original"),
    "Objective-C": ("objectivec", "plain"),
    "Clojure": ("clojure", "original"),
    "Scala": ("scala", "plain"),
    "Haskell": ("haskell", "plain"),
    "Elixir": ("elixir", "plain"),
    "Julia": ("julia", "plain"),
    "R": ("r", "plain"),
    "MATLAB": ("matlab", "plain"),
    "Perl": ("perl", "plain"),
    "F#": ("fsharp", "plain"),
    "Hack": ("php", "plain"),
    "Typst": ("typst", "original"),
}

ICON_SOURCES = {
    "devicon": {
        "repo": "https://github.com/devicons/devicon",
        "raw_base": "https://raw.githubusercontent.com/devicons/devicon",
        "pinned_ref": "7330accdbc47e2dc0c19789a48533c4a3c50fe58",
        "icon_path": "icons/{slug}/{slug}-{variant}.svg",
        "license_path": "LICENSE",
    },
    "simple-icons": {
        "repo": "https://github.com/simple-icons/simple-icons",
        "raw_base": "https://raw.githubusercontent.com/simple-icons/simple-icons",
        "pinned_ref": "ac1bf3df4e3d4cd1ce03cedb96d6165d2e98fe99",
        "icon_path": "icons/{slug}.svg",
        "license_path": "LICENSE.md",
    },
}
DEFAULT_ICON_SOURCE = "devicon"
ICON_SOURCE_OVERRIDES = {"typst": "simple-icons"}
