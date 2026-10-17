"""Can one compiler build each library? Reads sweep.sh output.

    python one_compiler.py <sweep_out_dir> [ref_dir]   (inside a container with powerpc objdump)

With ref_dir (the first sweep), the reference comes from there, so a second sweep built
with different flags (DEFAULT_FLAGS=1) is scored against the project's real build.

Reference = each Matching unit compiled with the compiler the project assigns it. The
build is SHA1-checked, so that output is the retail code. A prebuilt library (MetroTRK,
an SDK .a, MusyX) was compiled in one go, so one compiler should reproduce all of it.
Per group: the best single compiler, and the functions only another version reproduces.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "audit" / "bfbb"))
from compare_obj import functions  # noqa: E402

VERSIONS = ["GC/1.1p1", "GC/1.2.5n", "GC/1.3", "GC/1.3.2", "GC/2.0", "GC/2.5", "GC/2.6"]


def group(src):
    # THP and the GBA-link SDK are their own libraries even where the project files them elsewhere.
    parts = src.split("/")
    return "/".join(parts[1:3]) if parts[1:3] in (["dolphin", "thp"], ["game", "gba"]) else parts[1]


def main(out_dir, ref_dir=None):
    out = Path(out_dir)
    ref_out = Path(ref_dir or out_dir)
    versions = [v for v in VERSIONS if (out / v.replace("/", "_")).exists()]
    units = [u for u in map(json.loads, open(out / "units.jsonl"))
             if u["matching"] and u["mw_version"] in VERSIONS and (out / versions[0].replace("/", "_") / u["src"]).parent.exists()]
    groups = defaultdict(list)
    for u in units:
        obj = Path(u["src"]).with_suffix(".o")
        code = {v: functions(out / v.replace("/", "_") / obj) if (out / v.replace("/", "_") / obj).exists() else {}
                for v in versions}
        ref_obj = ref_out / u["mw_version"].replace("/", "_") / obj
        ref = functions(ref_obj) if ref_dir else code[u["mw_version"]]
        for fn, body in ref.items():
            groups[group(u["src"])].append((u["src"], fn, u["mw_version"],
                                           {v for v in versions if code[v].get(fn) == body}))
    rows = []
    print(f"{'group':12} {'funcs':>5} {'informative':>11}  {'assigned versions':40} best single   not reproduced by it")
    for g, fns in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        informative = [f for f in fns if len(f[3]) < len(versions)]
        best = max(versions, key=lambda v: sum(v in f[3] for f in fns))
        missed = [f for f in fns if best not in f[3]]
        assigned = dict(Counter(f[2] for f in fns).most_common())
        print(f"{g:12} {len(fns):5} {len(informative):11}  {str(assigned):40} {best:10} {len(missed):5}")
        rows += [(g, best, *f[:3], ",".join(sorted(f[3]))) for f in missed]
        print(" " * 14 + "misses per compiler: " + ", ".join(f"{v[3:]} {sum(v not in f[3] for f in fns)}" for v in versions))
    with open(out / "needs_other_compiler.tsv", "w") as fh:
        fh.write("group\tbest_single\tsrc\tfunction\tassigned\treproduced_by\n")
        fh.writelines("\t".join(r) + "\n" for r in rows)
    print(f"\n{len(rows)} Matching functions are not reproduced by their group's best single compiler")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
