# languages strip generator

Pipeline behind the profile README. Every constant lives in `scripts/config.py`.

## flow

1. `scripts/github_client.py` lists repos through the `gh` CLI with the GraphQL field set pinned in `GH_JSON_FIELDS`, reading `GH_TOKEN` from the environment.
2. `scripts/aggregate.py` keeps public, non-fork, non-archived repos, sums language bytes, and builds table rows as `PINNED_REPOS` in config order at their fixed years (a pinned repo missing from aggregation, e.g. the archived modern-swe-library, falls back to a live `gh repo view` snapshot of stars, description, and createdAt, with the config description as last resort and the no-AI cutoff resolving from the batch reference repo or `NO_AI_FALLBACK_CUTOFF`, plus an optional per-entry `no_ai` override), then free-market repos sorted by stars descending with an alphabetical tie-break, skipping `EXCLUDED_REPO_NAMES` (the profile repo and neovim), filled up to `TABLE_REPO_LIMIT = 20` entries.
3. `top_languages` filters the sums to `PROG_LANGS`, sorts by bytes descending with an alphabetical tie-break, and cuts at `TOP_N`.
4. `scripts/svg_strip.py` renders one icon plus a `Name Size` label per language into a self-contained SVG at natural width. Icons load from `assets/devicons/<slug>-<variant>.svg`; a missing file or unmapped language falls back to a gray letter tile.
5. `scripts/readme_writer.py` rewrites the marker regions of `README.md` and writes `assets/languages.svg`. Both artifacts render fully before the first byte hits disk, so malformed data can never leave a half-updated artifact.
6. `make icons` re-vendors icons, `make generate` rebuilds from the recorded fixture, `make update` goes live, `make record` refreshes the fixture with public repos only.

## icon sources

Icons come from two pinned upstreams, resolved per slug through `ICON_SOURCES` and `ICON_SOURCE_OVERRIDES`.

- `devicons/devicon` @ `7330accdbc47e2dc0c19789a48533c4a3c50fe58`, fetched 2026-10-05 via `gh api repos/devicons/devicon/commits/master --jq .sha`.
- `simple-icons/simple-icons` @ `ac1bf3df4e3d4cd1ce03cedb96d6165d2e98fe99`, fetched 2026-10-09 the same way. Devicon ships no typst icon, checked at the pinned ref and at master, so the Typst mark comes from simple-icons.

Variant and stand-in caveats, all verified against the `icons/` tree of devicon at the pinned ref: Rust and C ship no plain variant, only original and line, so they use original. Blade has no devicon and rides the Laravel mark. Hack has no devicon and rides the PHP mark. Lua brand navy `#000080`, Rust brand black, and any default black fill vanish on the GitHub dark theme, so `RECOLOR_FILLS` replaces them with the language brand hex at embed time.

Color sources: shields.io ported hexes for the original workflow set, MathWorks orange for MATLAB per linguist, gray for Hack per linguist, Typst teal `#239dad` per `lib/linguist/languages.yml` in `github-linguist/linguist`.

## invariants under test

- `PROG_LANGS`, `LANG_COLORS`, and `DEVICON_MAP` share one key set, so every allowlisted language has a color and an icon entry.
- Every mapped slug resolves to a configured icon source and its `icon_path` template formats into an `icons/` path.
- The golden SVG pins the exact rendered bytes of the sample top 10, which transitively pins the vendored icon files themselves.
- Pinned repos render live data while public and non-archived. A pinned repo absent from aggregation (archived, private, or forked) falls back to a live `gh repo view` snapshot of stars, description, and createdAt, with the config description as last resort and the `no_ai` entry override taking precedence, so it keeps its badge and description instead of silently degrading. The cutoff resolves from the batch reference repo with `NO_AI_FALLBACK_CUTOFF` as the fixed fallback.
- modern-swe-library renders its star count as `200+<live count>` via `stars_prefix`.
- Every repo created strictly before the creation timestamp of `NO_AI_REFERENCE_REPO` (llm-tournament) shows the `assets/no-ai.svg` badge next to its star count, derived at aggregation time from the same batch or from `NO_AI_FALLBACK_CUTOFF` when the reference repo is absent, and the reference repo itself is never badged.
- The table spans the full width (`TABLE_WIDTH`) with four equal `TABLE_CELL_WIDTH` columns, so both name lanes and both description lanes share identical widths. `META_JOIN` glues year, star count, and badge into one unbreakable line, so the meta row never wraps under the link. The badge svg holds a single logo cut from the original artwork: red ring (`NO_AI_BORDER_COLOR`), green AI letters (`NO_AI_TEXT_COLOR`).
- The updated line is fully config-driven, `UPDATED_PREFIX` + UTC date + `UPDATED_SUFFIX`, and `_UPDATED_LINE_RE` derives from `re.escape(UPDATED_PREFIX)` so writer and format cannot drift.
- `make mutate` swaps token-level mutants into `scripts/` against the suite and requires a clean `scripts/` tree so restores stay verifiable.
- Two expressions avoid comparison operators because the equality boundary they would need is unreachable, which leaves any `<=`/`<` form with a structurally equivalent mutant: `tag.rpartition("}")[-1]` for namespace stripping and `m.end() in range(updated.start())` for the owned-table bound in `readme_writer`.
