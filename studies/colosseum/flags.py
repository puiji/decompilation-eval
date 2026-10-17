"""How much of Colosseum's matched game code depends on per-unit codegen flags?

    python flags.py <sweep_dir> <defflags_dir> <splits.txt>   (inside a container with powerpc objdump)

sweep_dir:    sweep.sh output (each unit with its own compiler and flags = the retail code)
defflags_dir: sweep.sh with DEFAULT_FLAGS=1 PREFIX=src/game/ (overrides swapped for the game default)

1. Control: units with no override must come out identical (proves the flag swap is sound).
2. Functions that change without their unit's overrides, by override signature.
3. Layout: a flag set is per translation unit, so it should cover contiguous stretches of
   .text. An "island" is one unit whose compiler/flags differ from both neighbours while the
   neighbours agree; inside one original file that can't happen.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "audit" / "bfbb"))
from compare_obj import functions  # noqa: E402

CODEGEN = re.compile(r"-(O|opt |schedule |inline |use_lmw_stmw )")
DEFAULT = ["-inline auto", "-O4,p", "-use_lmw_stmw on"]


def text_ranges(splits):
    out = {}
    for m in re.finditer(r"^(\S[^\n]*?):\n((?:\t[^\n]*\n)+)", Path(splits).read_text(), re.M):
        t = re.search(r"^\t\.text\s+start:(0x[0-9A-Fa-f]+)\s+end:(0x[0-9A-Fa-f]+)", m.group(2), re.M)
        if t:
            out["src/" + m.group(1)] = (int(t.group(1), 16), int(t.group(2), 16))
    return out


def main(sweep, defflags, splits):
    sweep, defflags = Path(sweep), Path(defflags)
    units = [u for u in map(json.loads, open(sweep / "units.jsonl"))
             if u["matching"] and u["src"].startswith("src/game/") and "/gba/" not in u["src"]]
    control, dep_by_sig, units_by_sig, dep = [0, 0], Counter(), Counter(), {}
    for u in units:
        obj, v = Path(u["src"]).with_suffix(".o"), u["mw_version"].replace("/", "_")
        ref, got = functions(sweep / v / obj), functions(defflags / v / obj)
        changed = sum(got.get(k) != b for k, b in ref.items())
        dep[u["src"]] = (changed, len(ref))
        extra = sorted(f for f in u["flags"] if CODEGEN.match(f) and f not in DEFAULT)
        missing = sorted(f for f in DEFAULT if f not in u["flags"])
        if not extra and not missing:
            control[0] += len(ref)
            control[1] += changed
        else:
            key = " ".join(extra) + (" | lacks " + " ".join(missing) if missing else "")
            dep_by_sig[key] += changed
            units_by_sig[key] += 1
    total = sum(n for _, n in dep.values())
    print(f"{len(units)} Matching game units, {total} functions")
    print(f"control: {control[1]} of {control[0]} functions in units without overrides change (expect 0)")
    print(f"functions that need their unit's flag overrides: {sum(dep_by_sig.values())} ({sum(dep_by_sig.values()) / total:.1%})")
    for k, n in dep_by_sig.most_common(8):
        print(f"  {n:5}  ({units_by_sig[k]:3} units)  {k}")

    ranges = text_ranges(splits)
    rows = sorted((ranges[u["src"]], u["src"], (u["mw_version"], tuple(sorted(f for f in u["flags"] if CODEGEN.match(f)))))
                  for u in units if u["src"] in ranges)
    islands = [rows[i] for i in range(1, len(rows) - 1)
               if rows[i - 1][2] == rows[i + 1][2] != rows[i][2] and rows[i + 1][0][0] - rows[i - 1][0][1] < 0x2000]
    print(f"\nislands: {len(islands)} units, {sum(dep[r[1]][0] for r in islands)} flag-dependent functions in them")
    with open(sweep.parent / "islands.tsv", "w") as fh:
        fh.write("start\tsize\tsrc\tcompiler\tcodegen_flags\tneighbour_flags\tflag_dependent_functions\n")
        for i, r in enumerate(rows[1:-1], 1):
            if r in islands:
                fh.write(f"{r[0][0]:#x}\t{r[0][1] - r[0][0]:#x}\t{r[1]}\t{r[2][0]}\t{' '.join(r[2][1])}\t"
                         f"{rows[i - 1][2][0]} {' '.join(rows[i - 1][2][1])}\t{dep[r[1]][0]}\n")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
