import json
import unittest

from scripts import config
from scripts.aggregate import Aggregation, aggregate, select_rows, top_languages


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
        self.assertEqual(aggregate([]), Aggregation(repos=[], lang_sizes={}))

    def test_filters_fork_and_archived(self):
        agg = aggregate([
            item("forked", stars=3, langs=[("Rust", 999999)], fork=True),
            item("legacy", stars=50, langs=[("Python", 800000)], archived=True),
            item("kept", stars=1, langs=[("Go", 10)]),
        ])
        self.assertEqual([r.name for r in agg.repos], ["kept"])
        self.assertEqual(agg.lang_sizes, {"Go": 10})

    def test_private_repositories_excluded(self):
        # profile stats cover public work only: private bytes must vanish
        agg = aggregate([
            item("secret", stars=9, langs=[("Go", 5000000)], visibility="private"),
            item("open", stars=1, langs=[("Go", 10)]),
        ])
        self.assertEqual([r.name for r in agg.repos], ["open"])
        self.assertEqual(agg.lang_sizes, {"Go": 10})

    def test_missing_visibility_treated_as_private(self):
        unknown = item("mystery", langs=[("JavaScript", 400000)])
        del unknown["visibility"]
        self.assertEqual(aggregate([unknown]), Aggregation(repos=[], lang_sizes={}))

    def test_sums_bytes_across_repos(self):
        agg = aggregate([
            item("svc-a", langs=[("Go", 300000), ("HTML", 10)]),
            item("svc-b", langs=[("Go", 260000), ("Go", 5)]),
        ])
        self.assertEqual(agg.lang_sizes, {"Go": 560005, "HTML": 10})

    def test_year_overrides_applied(self):
        agg = aggregate([
            item("SumoBot", created="2019-04-01T00:00:00Z"),
            item("FlowerShop", created="2020-06-15T00:00:00Z"),
            item("plain", created="2025-03-10T11:22:33Z"),
        ])
        years = {r.name: r.year for r in agg.repos}
        self.assertEqual(years, {"SumoBot": 2017, "FlowerShop": 2018, "plain": 2025})

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
            cls.repos = aggregate(json.load(fh)).repos

    def test_fixture_row_order_and_limit(self):
        calls = []

        def star_fetch(full_name):
            calls.append(full_name)
            return 99

        rows = select_rows(self.repos, star_fetch=star_fetch)
        self.assertEqual(calls, ["lavantien/modern-swe-library"])
        self.assertEqual([r.name for r in rows], [
            "modern-swe-library", "dotfiles", "llm-tournament", "caro-ai-pvp",
            "FlowerShop", "go-web-service", "go-worker-pool", "SumoBot",
            "ruby-perl-migrator", "kotlin-android-lab",
        ])
        self.assertEqual(len(rows), config.TABLE_ROW_LIMIT)
        self.assertEqual(rows[0].stars, 99)

    def test_excluded_names_absent_and_no_duplicates(self):
        rows = select_rows(self.repos, star_fetch=lambda full_name: 1)
        names = [r.name for r in rows]
        self.assertNotIn("lavantien", names)
        self.assertEqual(len(names), len(set(names)))

    def test_falsy_star_fetch_stays_zero(self):
        repos = aggregate([item("only", stars=5)]).repos
        rows = select_rows(repos, star_fetch=lambda full_name: None)
        self.assertEqual(rows[0].name, config.FIXED_FIRST_REPO["name"])
        self.assertEqual(rows[0].stars, 0)
        self.assertEqual([r.name for r in rows[1:]], ["only"])

    def test_no_pinned_matches_leaves_short_list(self):
        rows = select_rows([], star_fetch=lambda full_name: 7)
        self.assertEqual([r.name for r in rows], [config.FIXED_FIRST_REPO["name"]])
        self.assertEqual(rows[0].year, config.FIXED_FIRST_REPO["year"])
        self.assertEqual(rows[0].description, config.FIXED_FIRST_REPO["description"])


class TestFixtureIntegration(unittest.TestCase):
    # position 10 is F#, not Perl: at equal 13000 bytes the alphabetical
    # tie-break orders F# before Perl, so Perl is the entry cut at n=10.
    # All byte totals verified against the fixture by hand before encoding.
    EXPECTED = [
        ("Go", 2221713), ("Java", 480000), ("JavaScript", 168384),
        ("Python", 140000), ("C", 120000), ("TypeScript", 95000),
        ("Kotlin", 75000), ("Ruby", 75000), ("Lua", 50000), ("F#", 13000),
    ]

    def test_sample_fixture_top_languages(self):
        with open(config.FIXTURE_SAMPLE, encoding="utf-8") as fh:
            agg = aggregate(json.load(fh))
        self.assertEqual(top_languages(agg.lang_sizes), self.EXPECTED)


if __name__ == "__main__":
    unittest.main()
