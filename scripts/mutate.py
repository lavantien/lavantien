"""Mutation testing harness for the scripts/ package.

Plans deterministic token-level mutants (numeric constants, comparison
operators, boolean operators, arithmetic between adjacent numbers,
format-fragment strings), swaps each one into the real source file,
reruns the unittest suite in a subprocess, and restores the original
bytes no matter how the run ends: per-mutant finally, an atexit hook,
and a git-cleanliness check before and after the sweep. A mutant the
suite does not kill is behavior the suite fails to pin down; every
survivor is reported with its exact location and the change that went
unnoticed.

Exit codes: 0 all mutants killed, 1 at least one survivor, 2 harness
misuse (bad arguments, dirty scripts/ tree, failed restore).
"""

from __future__ import annotations

import argparse
import atexit
import io
import os
import subprocess
import sys
import tokenize
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = REPO_ROOT / "scripts"
SELF_NAME = "mutate.py"
PACKAGE_INIT = "__init__.py"
MAX_MUTANTS_PER_FILE = 200
DEFAULT_TIMEOUT_S = 120.0

CMP_SWAPS = {"<": "<=", ">": ">=", "<=": "<", ">=": ">", "==": "!=", "!=": "=="}
BOOL_SWAPS = {"and": "or", "or": "and"}
ARITH_SWAPS = {"+": "-", "-": "+", "*": "//"}

KILLED, SURVIVED, TIMEOUT, INVALID = "killed", "survived", "timeout", "invalid"
PROGRESS = {KILLED: ".", SURVIVED: "S", TIMEOUT: "T", INVALID: "i"}

EXIT_OK, EXIT_SURVIVOR, EXIT_MISUSE = 0, 1, 2

_TRIVIA = frozenset(
    {tokenize.NL, tokenize.COMMENT, tokenize.ENCODING, tokenize.ENDMARKER}
)
# a STRING directly after one of these starts a statement, so it is a
# docstring (or an inert bare string expression) and is never mutated
_BOUNDARY_TYPES = frozenset({tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT})
_BOUNDARY_OPS = frozenset({":", ";"})


@dataclass(frozen=True)
class Mutant:
    path: Path
    kind: str
    row: int
    col: int
    start: int  # character offset of the mutated token in the planned source
    end: int
    original: str
    replacement: str
    line: str

    @property
    def mid(self) -> str:
        return f"{_relpath(self.path)}:{self.row}:{self.col}:{self.kind}"


def _relpath(path: Path) -> str:
    if path.is_absolute():
        try:
            path = path.relative_to(REPO_ROOT)
        except ValueError:
            pass
    return path.as_posix()


def _tokenize(source: str) -> list[tokenize.TokenInfo]:
    return list(tokenize.generate_tokens(io.StringIO(source).readline))


def _excluded_rows(tokens: list[tokenize.TokenInfo]) -> tuple[set[int], set[int]]:
    """Rows of docstrings and of import statements, both never mutated."""
    doc_rows: set[int] = set()
    import_rows: set[int] = set()
    prev: tokenize.TokenInfo | None = None
    for tok in tokens:
        if tok.type in _TRIVIA:
            continue
        if tok.type == tokenize.NAME and tok.string == "import":
            import_rows.update(range(tok.start[0], tok.end[0] + 1))
        if tok.type == tokenize.STRING and (
            prev is None
            or prev.type in _BOUNDARY_TYPES
            or prev.string in _BOUNDARY_OPS
        ):
            doc_rows.update(range(tok.start[0], tok.end[0] + 1))
        prev = tok
    return doc_rows, import_rows


def _bump_number(text: str) -> str | None:
    if text[-1:] in ("j", "J"):
        return None
    body = text.replace("_", "")
    try:
        if any(ch in body for ch in ".eE") and not body.lower().startswith("0x"):
            return repr(float(body) + 1.0)
        return str(int(body, 0) + 1)
    except ValueError:
        return None


def _append_x(string_token: str) -> str:
    return string_token[:-1] + "X" + string_token[-1]


def plan_mutants(source: str, path: Path) -> list[Mutant]:
    lines = source.splitlines(keepends=True)
    tokens = _tokenize(source)
    doc_rows, import_rows = _excluded_rows(tokens)
    code = [
        t for t in tokens
        if t.type not in _TRIVIA and t.type not in _BOUNDARY_TYPES
    ]
    line_starts = [0]
    for ln in lines:
        line_starts.append(line_starts[-1] + len(ln))
    mutants: list[Mutant] = []
    for i, tok in enumerate(code):
        row = tok.start[0]
        if row in import_rows or row in doc_rows:
            continue
        replacement: str | None = None
        kind = ""
        if tok.type == tokenize.NUMBER:
            replacement, kind = _bump_number(tok.string), "num"
        elif tok.type == tokenize.OP:
            if tok.string in CMP_SWAPS:
                replacement, kind = CMP_SWAPS[tok.string], "cmp"
            elif (
                tok.string in ARITH_SWAPS
                and code[i - 1].type == tokenize.NUMBER
                and i + 1 < len(code)
                and code[i + 1].type == tokenize.NUMBER
            ):
                replacement, kind = ARITH_SWAPS[tok.string], "arith"
        elif tok.type == tokenize.NAME and tok.string in BOOL_SWAPS:
            replacement, kind = BOOL_SWAPS[tok.string], "bool"
        elif tok.type == tokenize.STRING and "{" in tok.string:
            replacement, kind = _append_x(tok.string), "str"
        elif tok.type == tokenize.FSTRING_MIDDLE and any(
            c.isalpha() for c in tok.string
        ):
            replacement, kind = tok.string + "X", "fstr"
        if replacement is not None and replacement != tok.string:
            mutants.append(Mutant(
                path=path,
                kind=kind,
                row=row,
                col=tok.start[1],
                start=line_starts[row - 1] + tok.start[1],
                end=line_starts[tok.end[0] - 1] + tok.end[1],
                original=tok.string,
                replacement=replacement,
                line=lines[row - 1].rstrip("\r\n"),
            ))
    return mutants[:MAX_MUTANTS_PER_FILE]


def splice(source: str, mutant: Mutant) -> str:
    return source[: mutant.start] + mutant.replacement + source[mutant.end :]


# authoritative originals for the running sweep; the atexit hook uses
# them so a crash of any kind still leaves the tree byte-identical
_ORIGINALS: dict[Path, bytes] = {}


def _restore_all() -> None:
    for path, data in _ORIGINALS.items():
        path.write_bytes(data)


atexit.register(_restore_all)


@contextmanager
def swapped(path: Path, mutated_source: str) -> Iterator[None]:
    try:
        path.write_bytes(mutated_source.encode("utf-8"))
        yield
    finally:
        path.write_bytes(_ORIGINALS[path])


def run_suite(timeout_s: float) -> str:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"]
    try:
        proc = subprocess.run(
            command, cwd=REPO_ROOT, env=env, capture_output=True, timeout=timeout_s
        )
    except subprocess.TimeoutExpired:
        return TIMEOUT
    return SURVIVED if proc.returncode == 0 else KILLED


def discover_sources() -> list[Path]:
    return sorted(
        p for p in SOURCES_DIR.glob("*.py")
        if p.name not in (SELF_NAME, PACKAGE_INIT)
    )


def git_porcelain(*pathspecs: str) -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", *pathspecs],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"mutate: git status failed: {proc.stderr.strip()}", file=sys.stderr)
        raise SystemExit(EXIT_MISUSE)
    return proc.stdout.splitlines()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mutation-test scripts/ against the unittest suite."
    )
    parser.add_argument(
        "--limit", type=int,
        help="run at most N mutants (deterministic order)",
    )
    parser.add_argument(
        "--file",
        help="restrict the sweep to one source, e.g. scripts/svg_strip.py",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="print mutant ids only, without running anything",
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_S,
        help="per-mutant suite timeout in seconds (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.timeout <= 0:
        print("mutate: --timeout must be positive", file=sys.stderr)
        return EXIT_MISUSE
    sources = discover_sources()
    if args.file is not None:
        target = Path(args.file)
        if not target.is_absolute():
            target = REPO_ROOT / target
        if target.resolve() not in sources:
            print(
                f"mutate: {args.file!r} is not a mutable source "
                f"(expected one of: {', '.join(_relpath(p) for p in sources)})",
                file=sys.stderr,
            )
            return EXIT_MISUSE
        sources = [target.resolve()]
    plans = [(p, p.read_text(encoding="utf-8")) for p in sources]
    if args.limit is not None:
        remaining = args.limit
        capped = []
        for p, source in plans:
            take = plan_mutants(source, p)[:max(remaining, 0)]
            remaining -= len(take)
            capped.append((p, source))
            if remaining <= 0:
                break
        plans = capped
    if args.list:
        for p, source in plans:
            for mutant in plan_mutants(source, p):
                print(mutant.mid)
        return EXIT_OK

    dirty = git_porcelain("scripts")
    if dirty:
        print(
            "mutate: scripts/ tree is dirty; commit or stash first so "
            "restores are verifiable:",
            file=sys.stderr,
        )
        for entry in dirty:
            print(f"  {entry}", file=sys.stderr)
        return EXIT_MISUSE
    baseline = set(git_porcelain())
    for p, _ in plans:
        _ORIGINALS[p] = p.read_bytes()

    counts = {KILLED: 0, SURVIVED: 0, TIMEOUT: 0, INVALID: 0}
    survivors: list[Mutant] = []
    try:
        for path, source in plans:
            mutants = plan_mutants(source, path)
            if not mutants:
                print(f"{path.as_posix()}: no mutants", flush=True)
                continue
            print(f"{path.as_posix()}: {len(mutants)} mutants", flush=True)
            for mutant in mutants:
                mutated = splice(source, mutant)
                try:
                    compile(mutated, str(path), "exec")
                except SyntaxError:
                    counts[INVALID] += 1
                    print(PROGRESS[INVALID], end="", flush=True)
                    continue
                with swapped(path, mutated):
                    status = run_suite(args.timeout)
                counts[status] += 1
                if status == SURVIVED:
                    survivors.append(mutant)
                print(PROGRESS[status], end="", flush=True)
            print(flush=True)
    except KeyboardInterrupt:
        print("\nmutate: interrupted; sources restored", file=sys.stderr)
        return 130
    finally:
        _restore_all()

    unrestored = [p for p, data in _ORIGINALS.items() if p.read_bytes() != data]
    _ORIGINALS.clear()
    new_dirty = [ln for ln in git_porcelain() if ln not in baseline]
    if unrestored or new_dirty:
        print("mutate: RESTORE FAILURE, tree left dirty:", file=sys.stderr)
        for p in unrestored:
            print(f"  bytes differ from original: {p}", file=sys.stderr)
        for ln in new_dirty:
            print(f"  new git entry: {ln}", file=sys.stderr)
        return EXIT_MISUSE

    total = counts[KILLED] + counts[SURVIVED] + counts[TIMEOUT]
    kill_rate = (
        (counts[KILLED] + counts[TIMEOUT]) / total if total else 1.0
    )
    print()
    print(f"total: {total} runnable, {counts[INVALID]} invalid (excluded)")
    print(
        f"killed: {counts[KILLED]}  survived: {counts[SURVIVED]}  "
        f"timeout: {counts[TIMEOUT]}"
    )
    print(f"kill rate: {kill_rate:.1%}")
    if survivors:
        print("survivors:")
        for mutant in survivors:
            print(
                f"  {mutant.mid}  {mutant.line.strip()}    "
                f"[{mutant.original} -> {mutant.replacement}]"
            )
    return EXIT_SURVIVOR if survivors else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
