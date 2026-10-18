import json
import unittest
from unittest import mock

from scripts import config
from scripts.aggregate import (
    Aggregation,
    aggregate,
    item_top_langs,
    select_rows,
    top_languages,
)


def item(name, stars=0, langs=(), created="2024-01-01T00:00:00Z",
         description="", fork=False, archived=False, visibility="public"):
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


class TestAggregate(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(
            aggregate([]),
            Aggregation(repos=[], lang_sizes={},
                        no_ai_cutoff=config.NO_AI_FALLBACK_CUTOFF),
        )

    def test_filters_fork_and_archived(self):
        agg = aggregate([
            item("forked", stars=3, langs=[("Rust", 999999)], fork=True),
            item("legacy", stars=50, langs=[("Python", 800000)], archived=True),
            item("kept", stars=1, langs=[("Go", 10)]),
        ])
        self.assertEqual([r.name for r in agg.repos], ["kept"])
        self.assertEqual(agg.lang_sizes, {"Go": 10})

    def test_private_repositories_excluded(self):
        agg = aggregate([
            item("secret", stars=9, langs=[("Go", 5000000)], visibility="private"),
            item("open", stars=1, langs=[("Go", 10)]),
        ])
        self.assertEqual([r.name for r in agg.repos], ["open"])
        self.assertEqual(agg.lang_sizes, {"Go": 10})

    def test_missing_visibility_treated_as_private(self):
        unknown = item("mystery", langs=[("JavaScript", 400000)])
        del unknown["visibility"]
        self.assertEqual(
            aggregate([unknown]),
            Aggregation(repos=[], lang_sizes={},
                        no_ai_cutoff=config.NO_AI_FALLBACK_CUTOFF),
        )

    def test_sums_bytes_across_repos(self):
        agg = aggregate([
            item("svc-a", langs=[("Go", 300000), ("HTML", 10)]),
            item("svc-b", langs=[("Go", 260000), ("Go", 5)]),
        ])
        self.assertEqual(agg.lang_sizes, {"Go": 560005, "HTML": 10})

    def test_top_langs_per_repo(self):
        agg = aggregate([
            item("svc", langs=[("Go", 300), ("HTML", 999), ("Python", 200)]),
            item("plain", langs=[]),
        ])
        by_name = {r.name: r.top_langs for r in agg.repos}
        self.assertEqual(by_name, {
            "svc": (("Go", 300), ("Python", 200)),
            "plain": (),
        })

    def test_year_taken_from_created_at(self):
        agg = aggregate([
            item("SumoBot", created="2019-04-01T00:00:00Z"),
            item("FlowerShop", created="2020-06-15T00:00:00Z"),
            item("plain", created="2025-03-10T11:22:33Z"),
        ])
        years = {r.name: r.year for r in agg.repos}
        self.assertEqual(years, {"SumoBot": 2019, "FlowerShop": 2020, "plain": 2025})

    def test_description_none_becomes_empty(self):
        agg = aggregate([dict(item("x"), description=None)])
        self.assertEqual(agg.repos[0].description, "")

    def test_missing_languages_key_and_empty_list(self):
        no_key = item("no-key")
        del no_key["languages"]
        agg = aggregate([no_key, item("empty-list", langs=[])])
        self.assertEqual(agg.lang_sizes, {})
        self.assertEqual(len(agg.repos), 2)

    def test_missing_size_key_contributes_zero_bytes(self):
        one = item("svc")
        one["languages"] = [{"node": {"name": "Go"}}]
        self.assertEqual(aggregate([one]).lang_sizes, {"Go": 0})

    def test_missing_required_keys_raise(self):
        no_created = item("x")
        del no_created["createdAt"]
        with self.assertRaises(KeyError):
            aggregate([no_created])
        no_name = item("x")
        del no_name["name"]
        with self.assertRaises(KeyError):
            aggregate([no_name])


class TestNoAiFlag(unittest.TestCase):
    def test_cutoff_derived_from_reference_repo(self):
        agg = aggregate([
            item("llm-tournament", created="2025-03-10T11:22:33Z"),
            item("older", created="2025-03-10T11:22:32Z"),
            item("same", created="2025-03-10T11:22:33Z"),
            item("newer", created="2025-03-10T11:22:34Z"),
        ])
        self.assertEqual(agg.no_ai_cutoff, "2025-03-10T11:22:33Z")
        flags = {r.name: r.no_ai for r in agg.repos}
        self.assertEqual(flags, {
            "llm-tournament": False,
            "older": True,
            "same": False,
            "newer": False,
        })

    def test_missing_reference_repo_falls_back_to_config_cutoff(self):
        agg = aggregate([
            item("ancient", created="2024-12-31T23:59:59Z"),
            item("equal", created=config.NO_AI_FALLBACK_CUTOFF),
            item("modern", created="2025-06-01T00:00:00Z"),
        ])
        self.assertEqual(agg.no_ai_cutoff, config.NO_AI_FALLBACK_CUTOFF)
        flags = {r.name: r.no_ai for r in agg.repos}
        self.assertEqual(flags, {"ancient": True, "equal": False, "modern": False})


class TestItemTopLangs(unittest.TestCase):
    def test_sums_duplicate_edges_filters_and_orders(self):
        entry = lambda name, size: {"size": size, "node": {"name": name}}
        self.assertEqual(
            item_top_langs({"languages": [
                entry("Go", 10), entry("Go", 5), entry("TypeScript", 50),
                entry("C", 30), entry("HTML", 999),
            ]}),
            (("TypeScript", 50), ("C", 30)),
        )

    def test_single_language(self):
        self.assertEqual(
            item_top_langs({"languages": [{"size": 7, "node": {"name": "Go"}}]}),
            (("Go", 7),),
        )

    def test_missing_null_or_empty_languages(self):
        no_key = {}
        self.assertEqual(item_top_langs(no_key), ())
        self.assertEqual(item_top_langs({"languages": None}), ())
        self.assertEqual(item_top_langs({"languages": []}), ())

    def test_zero_size_edges_dropped(self):
        self.assertEqual(
            item_top_langs({"languages": [
                {"node": {"name": "Go"}},
                {"size": 0, "node": {"name": "Python"}},
            ]}),
            (),
        )


class TestTopLanguages(unittest.TestCase):
    def test_prog_only_and_positive_sizes(self):
        sizes = {"HTML": 999999, "Go": 10, "Rust": 0}
        self.assertEqual(top_languages(sizes), [("Go", 10)])

    def test_desc_order_with_alphabetical_tie_break(self):
        sizes = {"Ruby": 75000, "Kotlin": 75000, "F#": 13000, "Perl": 13000, "Go": 2221713}
        self.assertEqual(top_languages(sizes), [
            ("Go", 2221713), ("Kotlin", 75000), ("Ruby", 75000),
            ("F#", 13000), ("Perl", 13000),
        ])

    def test_respects_n(self):
        self.assertEqual(
            top_languages({"Go": 3, "Java": 2, "C": 1}, n=2),
            [("Go", 3), ("Java", 2)],
        )

    def test_custom_allow(self):
        self.assertEqual(top_languages({"HTML": 5}, allow={"HTML"}), [("HTML", 5)])

    def test_single_byte_language_kept(self):
        self.assertEqual(top_languages({"Go": 1}), [("Go", 1)])

    def test_zero_size_language_excluded(self):
        self.assertEqual(top_languages({"Go": 0}), [])

    def test_empty(self):
        self.assertEqual(top_languages({}), [])


class TestSelectRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(config.FIXTURE_SAMPLE, encoding="utf-8") as fh:
            cls.agg = aggregate(json.load(fh))
        cls.repos = cls.agg.repos
        cls.cutoff = cls.agg.no_ai_cutoff

    def test_fixture_row_order_and_limit(self):
        calls = []

        def snapshot_fetch(full_name):
            calls.append(full_name)
            return {"stars": 9, "description": "lib",
                    "createdAt": "2025-01-01T20:30:10Z",
                    "langs": (("Go", 400000), ("Python", 50000))}

        rows = select_rows(
            self.repos, snapshot_fetch=snapshot_fetch, cutoff=self.cutoff
        )
        self.assertEqual(calls, ["lavantien/modern-swe-library"])
        self.assertEqual([(r.name, r.year) for r in rows], [
            ("dotfiles", 2023),
            ("modern-swe-library", 2023),
            ("FlowerShop", 2018),
            ("caro-ai-pvp", 2025),
            ("blind-trainer", 2026),
            ("quotes-manager", 2026),
            ("dota-helper", 2026),
            ("llm-tournament", 2024),
            ("genetic-cpp", 2016),
            ("SumoBot", 2017),
            ("go-edge-mesh", 2021),
            ("order-demo", 2021),
            ("go-flutter-microservices-skeleton", 2022),
            ("high-alpha", 2020),
            ("runner-beta", 2021),
            ("go-web-service", 2023),
            ("go-worker-pool", 2024),
            ("tied-zebra", 2022),
            ("ruby-perl-migrator", 2022),
            ("kotlin-android-lab", 2022),
        ])
        self.assertEqual(len(rows), config.TABLE_REPO_LIMIT)
        self.assertEqual(rows[1].stars, 9)
        self.assertEqual(rows[1].stars_display, "200+9")
        self.assertEqual(rows[1].top_langs, (("Go", 400000), ("Python", 50000)))
        by_name = {r.name: r.top_langs for r in rows}
        self.assertEqual(by_name["dotfiles"], (("Typst", 10304702), ("Lua", 50000)))
        self.assertEqual(by_name["go-worker-pool"], (("Go", 260000), ("Python", 140000)))
        self.assertEqual(by_name["blind-trainer"], ())
        badged = {r.name for r in rows if r.no_ai}
        self.assertEqual(badged, {
            "dotfiles", "modern-swe-library", "FlowerShop", "genetic-cpp",
            "SumoBot", "go-edge-mesh", "order-demo",
            "go-flutter-microservices-skeleton", "high-alpha", "runner-beta",
            "go-web-service", "go-worker-pool", "tied-zebra",
            "ruby-perl-migrator", "kotlin-android-lab",
        })
        self.assertNotIn("sandbox-notes", [r.name for r in rows])

    def test_excluded_names_absent_and_no_duplicates(self):
        rows = select_rows(
            self.repos,
            snapshot_fetch=lambda full_name: {"stars": 1, "description": "",
                                              "createdAt": self.cutoff,
                                              "langs": ()},
            cutoff=self.cutoff,
        )
        names = [r.name for r in rows]
        self.assertNotIn("lavantien", names)
        self.assertEqual(len(names), len(set(names)))

    def test_neovim_skipped_free_market_fills_next(self):
        repos = aggregate([
            item("neovim", stars=5, langs=()),
            item("zz-next", stars=3, langs=()),
        ]).repos
        with mock.patch.object(config, "PINNED_REPOS", ()):
            rows = select_rows(
                repos, snapshot_fetch=lambda full_name: None,
                cutoff=config.NO_AI_FALLBACK_CUTOFF,
            )
        self.assertEqual([r.name for r in rows], ["zz-next"])
        only_excludes_lavantien = frozenset({"lavantien"})
        with mock.patch.object(config, "PINNED_REPOS", ()), \
                mock.patch.object(config, "EXCLUDED_REPO_NAMES",
                                  only_excludes_lavantien):
            rows = select_rows(
                repos, snapshot_fetch=lambda full_name: None,
                cutoff=config.NO_AI_FALLBACK_CUTOFF,
            )
        self.assertEqual([r.name for r in rows], ["neovim", "zz-next"])

    def test_none_snapshot_fetch_yields_zero_stars(self):
        rows = select_rows(
            [], snapshot_fetch=lambda full_name: None,
            cutoff=config.NO_AI_FALLBACK_CUTOFF,
        )
        self.assertEqual(len(rows), len(config.PINNED_REPOS))
        self.assertTrue(all(r.stars == 0 for r in rows))
        modern = next(r for r in rows if r.name == "modern-swe-library")
        self.assertEqual(modern.stars_display, "200+0")

    def test_no_pinned_matches_builds_rows_from_config(self):
        snap = {"stars": 7, "description": "", "createdAt": "2030-01-01T00:00:00Z",
                "langs": (("Zig", 1),)}
        rows = select_rows(
            [], snapshot_fetch=lambda full_name: snap,
            cutoff=config.NO_AI_FALLBACK_CUTOFF,
        )
        self.assertEqual(
            [(r.name, r.year) for r in rows],
            [(e["name"], e["year"]) for e in config.PINNED_REPOS],
        )
        self.assertTrue(all(r.stars == 7 for r in rows))
        self.assertTrue(all(r.top_langs == (("Zig", 1),) for r in rows))
        modern = next(r for r in rows if r.name == "modern-swe-library")
        self.assertEqual(
            modern.description,
            "Open knowledge library: curated resources for modern software engineering",
        )
        self.assertTrue(modern.no_ai)
        others = [r for r in rows if r.name != "modern-swe-library"]
        self.assertTrue(all(r.description == "" for r in others))

    def test_archived_pinned_repo_rebuilds_from_snapshot(self):
        items = [
            item("llm-tournament", created="2025-03-10T11:22:33Z"),
            item("legacy", created="2024-06-01T00:00:00Z", archived=True),
        ]
        agg = aggregate(items)
        snaps = {
            "lavantien/legacy": {"stars": 21, "description": "batch description",
                                 "createdAt": "2024-06-01T00:00:00Z",
                                 "langs": (("Java", 90),)},
            "lavantien/fresh": {"stars": 3, "description": "fresh batch description",
                                "createdAt": "2026-01-01T00:00:00Z",
                                "langs": ()},
        }
        entries = ({"name": "legacy", "year": 2024}, {"name": "fresh", "year": 2026})
        with mock.patch.object(config, "PINNED_REPOS", entries):
            rows = select_rows(agg.repos, snapshot_fetch=snaps.__getitem__,
                               cutoff=agg.no_ai_cutoff)
        by_name = {r.name: r for r in rows}
        self.assertEqual(
            (by_name["legacy"].stars, by_name["legacy"].description,
             by_name["legacy"].year, by_name["legacy"].no_ai,
             by_name["legacy"].top_langs),
            (21, "batch description", 2024, True, (("Java", 90),)),
        )
        self.assertEqual(
            (by_name["fresh"].stars, by_name["fresh"].description,
             by_name["fresh"].year, by_name["fresh"].no_ai),
            (3, "fresh batch description", 2026, False),
        )

    def test_snapshot_none_keeps_config_description_and_zero_stars(self):
        entries = (
            {"name": "plain", "year": 2020},
            {"name": "described", "year": 2021, "description": "config description"},
        )
        with mock.patch.object(config, "PINNED_REPOS", entries):
            rows = select_rows(
                [], snapshot_fetch=lambda full_name: None,
                cutoff=config.NO_AI_FALLBACK_CUTOFF,
            )
        by_name = {r.name: (r.stars, r.description, r.no_ai) for r in rows}
        self.assertEqual(by_name, {
            "plain": (0, "", False),
            "described": (0, "config description", False),
        })

    def test_snapshot_empty_description_falls_back_to_config(self):
        entries = ({"name": "described", "year": 2021,
                    "description": "config description"},)
        snap = {"stars": 4, "description": "", "createdAt": "2020-01-01T00:00:00Z",
                "langs": ()}
        with mock.patch.object(config, "PINNED_REPOS", entries):
            rows = select_rows(
                [], snapshot_fetch=lambda full_name: snap,
                cutoff=config.NO_AI_FALLBACK_CUTOFF,
            )
        self.assertEqual(rows[0].description, "config description")

    def test_snapshot_created_exactly_at_cutoff_is_not_badged(self):
        items = [item("llm-tournament", created="2025-03-10T11:22:33Z")]
        agg = aggregate(items)
        snap = {"stars": 2, "description": "same moment",
                "createdAt": "2025-03-10T11:22:33Z", "langs": ()}
        entries = ({"name": "twin", "year": 2025},)
        with mock.patch.object(config, "PINNED_REPOS", entries):
            rows = select_rows(
                [], snapshot_fetch=lambda full_name: snap,
                cutoff=agg.no_ai_cutoff,
            )
        self.assertEqual((rows[0].stars, rows[0].description), (2, "same moment"))
        self.assertFalse(rows[0].no_ai)

    def test_pinned_no_ai_override_wins(self):
        repos = aggregate([
            item("llm-tournament", created="2025-03-10T11:22:33Z"),
            item("older", created="2024-01-01T00:00:00Z"),
            item("newer", created="2026-01-01T00:00:00Z"),
        ]).repos
        entries = (
            {"name": "older", "year": 2024, "no_ai": False},
            {"name": "newer", "year": 2026, "no_ai": True},
        )
        with mock.patch.object(config, "PINNED_REPOS", entries):
            rows = select_rows(
                repos, snapshot_fetch=lambda full_name: None,
                cutoff="2025-03-10T11:22:33Z",
            )
        flags = {r.name: r.no_ai for r in rows}
        self.assertFalse(flags["older"])
        self.assertTrue(flags["newer"])

    def test_pinned_saturation_appends_no_remaining_rows(self):
        pinned = [{"name": f"pinned-{i}", "year": 2000 + i} for i in range(20)]
        repos = aggregate(
            [item(e["name"], stars=i) for i, e in enumerate(pinned)]
            + [item("leftover", stars=99)]
        ).repos
        with mock.patch.object(config, "PINNED_REPOS", pinned):
            rows = select_rows(
                repos, snapshot_fetch=lambda full_name: None,
                cutoff=config.NO_AI_FALLBACK_CUTOFF,
            )
        self.assertEqual([r.name for r in rows], [e["name"] for e in pinned])
        self.assertEqual(len(rows), config.TABLE_REPO_LIMIT)

    def test_more_pinned_than_limit_keeps_all(self):
        pinned = [{"name": f"pinned-{i}", "year": 2000 + i} for i in range(22)]
        repos = aggregate(
            [item(e["name"], stars=i) for i, e in enumerate(pinned)]
        ).repos
        with mock.patch.object(config, "PINNED_REPOS", pinned):
            rows = select_rows(
                repos, snapshot_fetch=lambda full_name: None,
                cutoff=config.NO_AI_FALLBACK_CUTOFF,
            )
        self.assertEqual([r.name for r in rows], [e["name"] for e in pinned])

    def test_free_market_tie_break_is_byte_order(self):
        repos = aggregate([
            item("beta", stars=5, langs=()),
            item("Zeta", stars=5, langs=()),
            item("alpha", stars=5, langs=()),
        ]).repos
        with mock.patch.object(config, "PINNED_REPOS", ()):
            rows = select_rows(
                repos, snapshot_fetch=lambda full_name: None,
                cutoff=config.NO_AI_FALLBACK_CUTOFF,
            )
        self.assertEqual([r.name for r in rows], ["Zeta", "alpha", "beta"])


class TestFixtureIntegration(unittest.TestCase):
    EXPECTED = [
        ("Typst", 10304702), ("Go", 2221713), ("Java", 480000),
        ("JavaScript", 168384), ("Python", 140000), ("C", 120000),
        ("TypeScript", 95000), ("Kotlin", 75000), ("Ruby", 75000),
        ("Lua", 50000),
    ]

    def test_sample_fixture_top_languages(self):
        with open(config.FIXTURE_SAMPLE, encoding="utf-8") as fh:
            agg = aggregate(json.load(fh))
        self.assertEqual(top_languages(agg.lang_sizes), self.EXPECTED)


class TestRecordedFixtureCoverage(unittest.TestCase):
    def test_recorded_fixture_covers_pinned_repos(self):
        with open(config.FIXTURE_RECORDED, encoding="utf-8") as fh:
            recorded = {entry["name"] for entry in json.load(fh)}
        for entry in config.PINNED_REPOS:
            self.assertIn(entry["name"], recorded, entry["name"])
        self.assertIn(config.NO_AI_REFERENCE_REPO, recorded)


if __name__ == "__main__":
    unittest.main()
