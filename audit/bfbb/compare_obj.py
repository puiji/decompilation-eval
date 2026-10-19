"""Per-function diff of PowerPC objects compiled by two compilers (from compile.sh).

    python compare_obj.py <out_dir> <ref_variant> <variant> [units.jsonl]
    python compare_obj.py <out_dir> --any <diff.tsv> <variant> ...

The --any form takes the Matching rows of a diff TSV and asks, per function, which of
the given variants (stock compilers) reproduce the ref variant's code exactly.

Disassembles with powerpc-linux-gnu-objdump (run it inside the Docker image; the
host has no PPC binutils), normalizes addresses, and lists functions whose code or
relocations differ. With units.jsonl (from units.py), splits counts by the unit's Matching flag.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ADDR = re.compile(r"^\s*[0-9a-f]+:\s*")
TARGET = re.compile(r"\b[0-9a-f]+ <([^>+]+)(\+0x[0-9a-f]+)?>")
# Limitation: MWCC's numbered locals (@123) are collapsed, so a swapped literal reference
# between two pooled constants is missed. Map by content if that ever matters.
NUMBERED = re.compile(r"@\d+")
SYM = re.compile(r"^[0-9a-f]+ <(.+)>:$")


def functions(obj):
    text = subprocess.run(["powerpc-linux-gnu-objdump", "-dr", "--no-show-raw-insn", str(obj)],
                          capture_output=True, text=True).stdout
    out, name = {}, None
    for line in text.splitlines():
        m = SYM.match(line)
        if m:
            name = m.group(1)
            out[name] = []
        elif name and line.strip() and not line.startswith("Disassembly"):
            line = TARGET.sub(lambda t: f"<{t.group(1)}{t.group(2) or ''}>", ADDR.sub("", line))
            out[name].append(NUMBERED.sub("@N", line.strip()))
    return {k: tuple(v) for k, v in out.items()}


def matching_flags(units):
    """{'src/SB/Core/x/xBase': 'Matching', ...}: linked (SHA1-checked) or not."""
    rows = map(json.loads, open(units))
    return {str(Path(r["src"]).with_suffix("")): "Matching" if r["matching"] else "NonMatching" for r in rows}


def main(out_dir, ref, var, units=None):
    out = Path(out_dir)
    flags = matching_flags(units) if units else {}
    tally, differ = {}, []
    for a in sorted((out / ref).rglob("*.o")):
        rel = a.relative_to(out / ref)
        b = out / var / rel
        flag = flags.get(str(rel.with_suffix("")), "?")
        t = tally.setdefault(flag, [0, 0, 0])
        if not b.exists():
            t[2] += 1
            continue
        fa, fb = functions(a), functions(b)
        for k in fa:
            t[0] += 1
            if fa[k] != fb.get(k):
                t[1] += 1
                differ.append((flag, str(rel), k, len(fa[k]), len(fb.get(k, ()))))
    print(f"{ref} vs {var}")
    for flag, (n, d, missing) in sorted(tally.items()):
        print(f"  {flag:22} functions {n:6}  differ {d:5}  objects missing in {var}: {missing}")
    with open(out / f"diff_{ref}_vs_{var}.tsv", "w") as fh:
        fh.write("flag\tobject\tfunction\tref_lines\tvar_lines\n")
        for row in differ:
            fh.write("\t".join(map(str, row)) + "\n")


def any_stock(out_dir, tsv, *variants):
    out = Path(out_dir)
    rows = [l.rstrip("\n").split("\t") for l in open(tsv)][1:]
    rows = [r for r in rows if r[0] == "Matching"]
    ref = Path(tsv).stem.split("_vs_")[0].removeprefix("diff_")
    cache = {}
    def funcs(v, obj):
        if (v, obj) not in cache:
            f = out / v / obj
            cache[v, obj] = functions(f) if f.exists() else {}
        return cache[v, obj]
    hits, compiled = {}, {v: 0 for v in variants}
    for _, obj, fn, *_ in rows:
        want = funcs(ref, obj)[fn]
        hits[obj, fn] = [v for v in variants if funcs(v, obj).get(fn) == want]
        for v in variants:
            compiled[v] += bool(funcs(v, obj))
    print(f"{len(rows)} Matching functions that differ from stock 2.0p1 under {ref}")
    print("  reproduced by at least one stock compiler:", sum(bool(h) for h in hits.values()))
    for v in variants:
        print(f"  {v:10} reproduces {sum(v in h for h in hits.values()):4}   (object compiled for {compiled[v]} of {len(rows)})")
    with open(out / f"any_stock_{ref}.tsv", "w") as fh:
        fh.write("object\tfunction\treproduced_by\n")
        for (obj, fn), h in sorted(hits.items()):
            fh.write(f"{obj}\t{fn}\t{','.join(h)}\n")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    if sys.argv[2] == "--any":
        any_stock(sys.argv[1], *sys.argv[3:])
    else:
        main(*sys.argv[1:5])
