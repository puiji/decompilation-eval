"""Score a sweep.py result dir: compiler- and settings-dependence per function.

    python compare.py <res_dir> <project> <commit> [labels.csv]       (needs powerpc-linux-gnu-objdump)
    python compare.py <res_dir> --any                                  (after a VARIANTS=any pass)
    python compare.py --selftest <some.o>
REPO (env) = the project checkout, to exclude hand-written MWCC asm functions by name.

Per Matching unit, functions from the project build are compared with
  stock    the stock base compiler, same flags          -> compiler_dependent
  default  library default compiler/codegen flags       -> settings_dependent (vs stock)
Variants sweep.py skipped are identical by construction. For patched units the earliest patch
stage (p1a, p1g, p1h, p1i, else p1j) that already reproduces the project's code is recorded.
"""
import csv
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bfbb"))
from compare_obj import functions  # noqa: E402

CODEGEN = re.compile(r"-(O|opt |schedule |inline |use_lmw_stmw )")
# MWCC `asm void f(...) { ... }`: hand-written asm in a C file, identical under any compiler, so
# excluded from the counts (like asm includes elsewhere). By name: C++ mangled asm functions slip through.
ASM_FUNC = re.compile(r"^\s*(?:static\s+|extern\s+)*(?:inline\s+)?(?:asm|ASM)\s+[\w\s\*&:<>,]+?\b(\w+)\s*\(", re.M)
STAGES = ["p1a", "p1g", "p1h", "p1i"]


def obj(res, variant, src):
    return Path(res, variant, src).with_suffix(".o")


def load(res):
    res = Path(res)
    units = [u for u in map(json.loads, open(res / "units.jsonl")) if u["matching"]
             and (u["mw_version"].startswith("GC/") or u["mw_version"].startswith("ProDG/"))]
    ran = defaultdict(set)
    for j in map(json.loads, open(res / "jobs.jsonl")):
        ran[j["src"]].add(j["variant"])
    return units, ran


def score(res):
    units, ran = load(res)
    rows, failed = [], Counter()
    cache = {}
    repo = os.environ.get("REPO")
    asm_names = lambda src: set(ASM_FUNC.findall(Path(repo, src).read_text(errors="replace"))) if repo else set()
    def funcs(variant, src):
        p = obj(res, variant, src)
        if (variant, src) not in cache:
            cache[variant, src] = functions(p) if p.exists() else None
        return cache[variant, src]
    for u in units:
        src = u["src"]
        proj = funcs("project", src)
        if proj is None:
            failed["project"] += 1
            continue
        stock = funcs("stock", src) if "stock" in ran[src] else proj
        default = funcs("default", src) if "default" in ran[src] else stock
        if stock is None or default is None:
            failed["stock" if stock is None else "default"] += 1
            continue
        overrides = (u["mw_version"] != u["lib_mw_version"]
                     or sorted(f for f in u["flags"] if CODEGEN.match(f)) != sorted(f for f in u["lib_flags"] if CODEGEN.match(f)))
        stage_funcs = {s: funcs(s, src) for s in STAGES if s in ran[src]}
        asm = asm_names(src)
        failed["asm functions excluded"] += sum(n in asm for n in proj)
        for name, code in proj.items():
            if name in asm:
                continue
            comp = stock.get(name) != code
            sett = default.get(name) != stock.get(name)
            stage = ""
            if comp and stage_funcs:
                stage = next((s for s in STAGES if (stage_funcs.get(s) or {}).get(name) == code), "p1j")
            rows.append({"src": src, "function": name, "category": u["category"], "compiler": u["mw_version"],
                         "overrides": overrides, "compiler_dependent": comp, "settings_dependent": sett, "stage": stage})
    return rows, failed


def report(rows, failed):
    print(f"not counted: {dict(failed) or 'nothing'}")
    by = defaultdict(Counter)
    for r in rows:
        c = by[r["category"]]
        c["functions"] += 1
        c["compiler_dependent"] += r["compiler_dependent"]
        c["settings_dependent"] += r["settings_dependent"] and not r["compiler_dependent"]
        c["either"] += r["compiler_dependent"] or r["settings_dependent"]
    for cat, c in sorted(by.items(), key=str):
        print(f"  {cat!s:10} functions {c['functions']:6}  compiler-dependent {c['compiler_dependent']:5}  "
              f"settings-dependent {c['settings_dependent']:5}  stock match {1 - c['either'] / c['functions']:.1%}")
    ctrl = [r for r in rows if not r["overrides"]]
    print(f"control: {sum(r['settings_dependent'] for r in ctrl)} of {len(ctrl)} functions in units without "
          f"version/codegen overrides change under the default rebuild (expect 0)")
    stages = Counter(r["stage"] for r in rows if r["stage"])
    if stages:
        print("compiler-dependent functions by earliest patch stage that reproduces them:", dict(sorted(stages.items())))


def write_labels(rows, project, commit, path):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["project", "label", "category", "file", "symbol", "commit"])
        for r in rows:
            cat = ("compiler_dependent" if r["compiler_dependent"] else
                   "settings_dependent" if r["settings_dependent"] else "stock_match")
            w.writerow([project, "stock" if cat == "stock_match" else "assisted", cat, r["src"], r["function"], commit])


def any_stock(res):
    """Which released compilers reproduce the compiler-dependent functions? (cf. bfbb --any)"""
    res = Path(res)
    rows, _ = score(res)
    dep = [r for r in rows if r["compiler_dependent"]]
    variants = sorted(d.name for d in res.iterdir() if d.name.startswith("any_"))
    hit, compiled = Counter(), Counter()
    with open(res / "any_stock.tsv", "w") as fh:
        fh.write("src\tfunction\treproduced_by\n")
        for r in dep:
            want = functions(obj(res, "project", r["src"]))[r["function"]]
            by = []
            for v in variants:
                p = obj(res, v, r["src"])
                if p.exists():
                    compiled[v] += 1
                    if functions(p).get(r["function"]) == want:
                        by.append(v)
                        hit[v] += 1
            fh.write(f"{r['src']}\t{r['function']}\t{','.join(by)}\n")
            r["by"] = by
    print(f"{len(dep)} compiler-dependent functions; reproduced by at least one released compiler: "
          f"{sum(bool(r['by']) for r in dep)}")
    for v in variants:
        print(f"  {v:16} reproduces {hit[v]:4}  (object compiled for {compiled[v]} of {len(dep)})")


def selftest(path):
    """A one-instruction change in .text must show up as exactly one differing function."""
    sample = "asm void foo(int a) {\n}\nstatic asm u32 bar(void)\n{}\nvoid baz(void) { asm { nop } }\n"
    assert ASM_FUNC.findall(sample + "static ASM void DCEnable(void) {\n") == ["foo", "bar", "DCEnable"], ASM_FUNC.findall(sample)
    data = bytearray(Path(path).read_bytes())
    shoff, = struct.unpack(">I", data[0x20:0x24])
    shentsize, shnum, shstrndx = struct.unpack(">HHH", data[0x2E:0x34])
    sh = lambda i: struct.unpack(">IIIIIIIIII", data[shoff + i * shentsize: shoff + (i + 1) * shentsize])
    strtab = sh(shstrndx)[4]
    name = lambda h: data[strtab + h[0]: data.index(0, strtab + h[0])].decode()
    text = next(sh(i) for i in range(shnum) if name(sh(i)).startswith(".text") and sh(i)[5] >= 8)
    off = text[4] + 4  # second instruction word
    word, = struct.unpack(">I", data[off:off + 4])
    data[off:off + 4] = struct.pack(">I", word ^ 0x00200000)  # flip one bit of the rD/rS field
    with tempfile.NamedTemporaryFile(suffix=".o") as t:
        t.write(data)
        t.flush()
        a, b = functions(path), functions(t.name)
    changed = [k for k in a if a[k] != b.get(k)]
    assert len(changed) == 1, changed
    print(f"selftest ok: one flipped instruction -> 1 differing function ({changed[0]})")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
    elif sys.argv[2] == "--any":
        any_stock(sys.argv[1])
    else:
        rows, failed = score(sys.argv[1])
        report(rows, failed)
        if len(sys.argv) > 4:
            write_labels(rows, sys.argv[2], sys.argv[3], sys.argv[4])
            with open(Path(sys.argv[1], "functions.tsv"), "w") as fh:
                fh.write("\t".join(rows[0]) + "\n")
                fh.writelines("\t".join(map(str, r.values())) + "\n" for r in rows)
