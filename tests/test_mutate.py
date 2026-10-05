import pathlib
import tempfile
import unittest

from scripts import mutate

SAMPLE_PATH = pathlib.Path("scripts/sample.py")

SAMPLE = '''\
"""Module docstring with 10 numbers and a < b comparison inside."""

import math

TOP = 10
RATIO = 7.0
BIG = 1_000_000


def clip(value, lo, hi):
    # comment: 5 < 6 and 7 == 7
    if value < lo:
        return lo
    if value >= hi:
        return hi
    return value


def blend(a, b):
    return a and b or a - b if 2 + 3 else 0
'''


class TestPlanMutants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mutants = mutate.plan_mutants(SAMPLE, SAMPLE_PATH)

    def _one(self, kind, row):
        found = [m for m in self.mutants if m.kind == kind and m.row == row]
        self.assertEqual(len(found), 1, f"expected exactly one {kind} mutant on row {row}")
        return found[0]

    def test_numeric_constants_bumped(self):
        self.assertEqual(self._one("num", 5).replacement, "11")
        self.assertEqual(self._one("num", 6).replacement, "8.0")
        self.assertEqual(self._one("num", 7).replacement, "1000001")

    def test_comparisons_swapped_in_both_directions(self):
        self.assertEqual(self._one("cmp", 12).replacement, "<=")
        self.assertEqual(self._one("cmp", 14).replacement, ">")

    def test_boolean_operators_swapped(self):
        replacements = {m.replacement for m in self.mutants if m.kind == "bool" and m.row == 20}
        self.assertEqual(replacements, {"or", "and"})

    def test_arithmetic_only_between_numeric_neighbors(self):
        # 2 + 3 mutates, a - b does not (names around the minus)
        self.assertEqual(self._one("arith", 20).replacement, "-")

    def test_docstring_and_comment_rows_skipped(self):
        rows = {m.row for m in self.mutants}
        self.assertNotIn(1, rows)
        self.assertNotIn(11, rows)

    def test_import_rows_flagged(self):
        doc_rows, import_rows = mutate._excluded_rows(
            mutate._tokenize("from scripts import config\n")
        )
        self.assertEqual(import_rows, {1})
        self.assertEqual(doc_rows, set())

    def test_string_with_brace_appends_x(self):
        mutants = mutate.plan_mutants('frag = "pre {post}"\n', SAMPLE_PATH)
        self.assertEqual([m.replacement for m in mutants if m.kind == "str"],
                         ['"pre {post}X"'])

    def test_fstring_middle_appends_x(self):
        mutants = mutate.plan_mutants('label = f"val={name}!"\n', SAMPLE_PATH)
        self.assertEqual([m.replacement for m in mutants if m.kind == "fstr"],
                         ["val=X"])

    def test_imaginary_literal_skipped(self):
        self.assertEqual(mutate.plan_mutants("z = 2j\n", SAMPLE_PATH), [])

    def test_ids_stable_unique_and_position_ordered(self):
        self.assertEqual(self.mutants, mutate.plan_mutants(SAMPLE, SAMPLE_PATH))
        mids = [m.mid for m in self.mutants]
        self.assertEqual(len(mids), len(set(mids)))
        positions = [(m.row, m.col) for m in self.mutants]
        self.assertEqual(positions, sorted(positions))

    def test_mutant_id_format(self):
        first = self.mutants[0]
        self.assertEqual(
            first.mid,
            f"scripts/sample.py:{first.row}:{first.col}:{first.kind}",
        )

    def test_per_file_cap(self):
        source = "".join(f"v{i} = {i}\n" for i in range(mutate.MAX_MUTANTS_PER_FILE + 50))
        self.assertEqual(len(mutate.plan_mutants(source, SAMPLE_PATH)),
                         mutate.MAX_MUTANTS_PER_FILE)


class TestSplice(unittest.TestCase):
    def test_splice_replaces_only_the_target_span(self):
        source = "aa = 1\nbb = 22\ncc = 3\n"
        mutants = mutate.plan_mutants(source, SAMPLE_PATH)
        target = [m for m in mutants if m.row == 2][0]
        self.assertEqual(target.replacement, "23")
        self.assertEqual(mutate.splice(source, target), "aa = 1\nbb = 23\ncc = 3\n")


class TestSwapped(unittest.TestCase):
    def test_restores_after_success_and_after_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "sample.py"
            original = b"original = 1\n"
            path.write_bytes(original)
            mutate._ORIGINALS[path] = original
            self.addCleanup(mutate._ORIGINALS.pop, path, None)
            with mutate.swapped(path, "original = 2\n"):
                self.assertEqual(path.read_bytes(), b"original = 2\n")
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(RuntimeError):
                with mutate.swapped(path, "original = 3\n"):
                    raise RuntimeError("boom")
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
