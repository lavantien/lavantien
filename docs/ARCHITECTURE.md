# languages strip generator

Pipeline behind the profile README. Every constant lives in `scripts/config.py`.

## flow

1. `scripts/github_client.py` lists repos through the `gh` CLI with the GraphQL field set pinned in `GH_JSON_FIELDS`, reading `GH_TOKEN` from the environment.
2. `scripts/aggregate.py` keeps public, non-fork, non-archived repos, sums language bytes across them, and applies the star table selection rules.
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
- `make mutate` swaps token-level mutants into `scripts/` against the suite and requires a clean `scripts/` tree so restores stay verifiable.
- Two expressions avoid comparison operators because the equality boundary they would need is unreachable, which leaves any `<=`/`<` form with a structurally equivalent mutant: `tag.rpartition("}")[-1]` for namespace stripping and `m.end() in range(updated.start())` for the owned-table bound in `readme_writer`.
