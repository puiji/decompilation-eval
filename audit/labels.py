"""Build the ssx3 label set from its stock-tools audit (PR #13).

Ground truth is objective: the audit rebuilt with the unmodified SN compiler and
diffed every function against the retail executable.
  assisted/compiler_patch  72 functions that matched only with a binary-patched cc1plus
  assisted/asm_shell       27 functions whose C body is inline asm
  assisted/wrapped_c   C kept under #ifdef SKIP_ASM next to INCLUDE_ASM (never compiled)
  stock/stock_match    every C function still linked after the PR, which matches on stock tools

    python labels.py <ssx3_repo> <out_dir>

Writes labels.csv (no code; safe to commit) and functions.jsonl (the C text; keep
gitignored, it's the ssx3 project's code).
"""
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

PATCH_COMMIT, ASM_COMMIT, MERGE = "3abb77ada", "7f8da5b46", "dff0e7750c"
INCLUDE = re.compile(r'^\+\s*INCLUDE_ASM\(\s*"[^"]*"\s*,\s*(\w+)\s*\)', re.M)
# Limitation: regex + brace matching, not a C++ parser. Misses macros-as-definitions
# and braces inside string/char literals; fine for decomp code, swap for tree-sitter if it bites.
DEF = re.compile(r"^(?![\s#/])[^;{}()]*?\b(\w+)\s*\(([^;{}]*)\)\s*(?:const\s*)?\{", re.M)
KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof"}
# `void foo_impl(...) __asm__("func_X")` binds a C name to the linker symbol func_X.
ASM_LABEL = re.compile(r"\b(\w+)\s*\([^;{}]*\)\s*__asm__\s*\(\s*\"(\w+)\"\s*\)")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, check=True).stdout


def functions(text):
    """{name: source} for top-level function definitions in one file."""
    out = {}
    for m in DEF.finditer(text):
        name = m.group(1)
        if name in KEYWORDS:
            continue
        depth, i = 0, m.end() - 1
        for i in range(m.end() - 1, len(text)):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            if depth == 0:
                break
        out.setdefault(name, text[m.start():i + 1])
    for alias, sym in ASM_LABEL.findall(text):
        if alias in out:
            out.setdefault(sym, out[alias])
    return out


def lookup(funcs, sym):
    return funcs.get(sym) or funcs.get(re.sub(r"__F\w*$", "", sym))


def unique(funcs):
    """One (name, source) per definition; asm-label aliases share a source."""
    seen = set()
    for name, src in funcs.items():
        if src not in seen:
            seen.add(src)
            yield name, src


def strip_skip_asm(text):
    return re.sub(r"^#ifdef SKIP_ASM\n.*?^#endif[^\n]*\n", "", text, flags=re.M | re.S)


def changed_src(repo, commit):
    return [f for f in git(repo, "diff", "--name-only", f"{commit}^", commit, "--", "src").split()
            if f.endswith((".c", ".cpp"))]


def build(repo):
    rows, assisted = [], set()
    for commit, category in [(PATCH_COMMIT, "compiler_patch"), (ASM_COMMIT, "asm_shell")]:
        for f in changed_src(repo, commit):
            diff = git(repo, "show", commit, "--", f)
            before = functions(strip_skip_asm(git(repo, "show", f"{commit}^:{f}")))
            for sym in INCLUDE.findall(diff):
                rows.append(("assisted", category, f, sym, commit, lookup(before, sym)))
                assisted.add(sym)
            if commit == ASM_COMMIT:
                for block in re.findall(r"^#ifdef SKIP_ASM\n(.*?)^#endif", git(repo, "show", f"{commit}^:{f}"), re.M | re.S):
                    for sym, src in unique(functions(block)):
                        rows.append(("assisted", "wrapped_c", f, sym, commit, src))
    for f in git(repo, "ls-tree", "-r", "--name-only", MERGE, "src").split():
        if f.endswith((".c", ".cpp")):
            for sym, src in unique(functions(strip_skip_asm(git(repo, "show", f"{MERGE}:{f}")))):
                if sym not in assisted and re.sub(r"__F\w*$", "", sym) not in assisted:
                    rows.append(("stock", "stock_match", f, sym, MERGE, src))
    return rows


def main(repo, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = build(repo)
    with open(out / "labels.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["project", "label", "category", "file", "symbol", "commit", "lines", "extracted"])
        for label, cat, f, sym, commit, src in rows:
            w.writerow(["ssx3", label, cat, f, sym, commit, src.count("\n") + 1 if src else 0, bool(src)])
    with open(out / "functions.jsonl", "w") as fh:
        for label, cat, f, sym, commit, src in rows:
            if src:
                fh.write(json.dumps({"project": "ssx3", "symbol": sym, "label": label,
                                     "category": cat, "file": f, "source": src}) + "\n")
    from collections import Counter
    c = Counter((r[0], r[1], bool(r[5])) for r in rows)
    for (label, cat, ok), n in sorted(c.items()):
        print(f"{label:8} {cat:15} {'extracted' if ok else 'MISSING  '} {n}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
