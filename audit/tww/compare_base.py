"""Community-patched compiler vs its stock base (GC/1.2.5n vs GC/1.2.5), per function.

    REPO=<checkout> python compare_base.py <project_dir> <base_dir> <units.jsonl>     (needs powerpc objdump)

<project_dir>/<src>.o is the project build (1.2.5n), <base_dir>/<src>.o the same unit and flags on 1.2.5.
Prints per category: functions, how many differ, and the differing names. TSV (env) = also write
every differing function to that file.
"""
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bfbb"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ffcc"))
from compare_obj import functions  # noqa: E402
from compare import ASM_FUNC  # noqa: E402


def main(proj, base, units):
    n, diff, names = Counter(), Counter(), defaultdict(list)
    for u in map(json.loads, open(units)):
        o = Path(u["src"]).with_suffix(".o")
        a, b = Path(proj, o), Path(base, o)
        if not (a.exists() and b.exists()):
            print("missing", u["src"])
            continue
        asm = set(ASM_FUNC.findall(Path(os.environ["REPO"], u["src"]).read_text(errors="replace")))
        fa, fb = functions(a), functions(b)
        for k, code in fa.items():
            if k in asm:
                continue
            n[u["category"]] += 1
            if fb.get(k) != code:
                diff[u["category"]] += 1
                names[u["category"]].append(f"{u['src']}:{k}")
    if os.environ.get("TSV"):
        Path(os.environ["TSV"]).write_text("category\tfunction\n" + "".join(
            f"{c}\t{x}\n" for c, xs in names.items() for x in xs))
    for c in n:
        print(f"{c!s:10} functions {n[c]:5}  differ on stock 1.2.5 {diff[c]:4}")
        for x in names[c][:10]:
            print("   ", x)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
