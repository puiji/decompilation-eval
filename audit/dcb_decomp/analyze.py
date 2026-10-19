"""Score the dcb_decomp rebuild (rebuild.sh output) and write its labels.

    python audit/dcb_decomp/analyze.py out/dcb_decomp <commit> > audit/labels/dcb_decomp.csv

Game C: the project's compiler is stock old-gcc 2.95.2 with one flag set for every file, so
stock and stock_default are the project build by construction. PsyQ objects (left out of the
project's progress): patched vs unpatched compiler, and per-object flags vs the base flags.
"""
import csv
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "klonoa"))
from compare import functions, is_asm, load  # noqa: E402


def c_only(funcs):
    return {k: b for k, b in funcs.items() if not is_asm(b)}


def sanity(variant_dir):
    """A one-instruction change in one function must show up as exactly one difference."""
    s = next(p for p in sorted(variant_dir.glob("*.s")) if c_only(functions(p)))
    lines = s.read_text().splitlines()
    i = next(n for n, l in enumerate(lines) if l.strip().startswith(("addu", "lw", "move", "sw")))
    lines[i] = lines[i].replace("$", "$t9_", 1) if "$" in lines[i] else lines[i] + "x"
    a = functions(s)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / s.name
        tmp.write_text("\n".join(lines) + "\n")
        b = functions(tmp)
    return sum(a[k] != b.get(k) for k in a)


def main(out, commit):
    out = Path(out)
    game = c_only(load(out / "game/project"))
    v = {n: c_only(load(out / "psyq" / n)) for n in ("project", "stock", "stock_default", "any_2.8.1", "any_2.95.2")}
    lane = dict(l.split() for l in open(out / "psyq_lanes.txt"))
    proj = v["project"]
    cats, by_lane, reproduced = {}, Counter(), Counter()
    for k, b in proj.items():
        obj = k.split(":", 1)[0]
        if v["stock"].get(k) != b:
            cats[k] = "compiler_dependent"
            alt = [n for n in ("stock_default", "any_2.8.1", "any_2.95.2") if v[n].get(k) == b]
            reproduced["by an unpatched release" if alt else "by no unpatched release tried"] += 1
        elif v["stock_default"].get(k) != b:
            cats[k] = "settings_dependent"
        else:
            cats[k] = "stock_match"
        by_lane[(lane[obj], cats[k])] += 1

    print(f"game C functions: {len(game)} (stock old-gcc 2.95.2, uniform flags)", file=sys.stderr)
    print(f"PsyQ C functions: {len(proj)}", file=sys.stderr)
    for c, n in Counter(cats.values()).most_common():
        print(f"  {c:20} {n}", file=sys.stderr)
    for (l, c), n in sorted(by_lane.items()):
        print(f"  lane {l:7} {c:20} {n}", file=sys.stderr)
    for r, n in reproduced.items():
        print(f"  compiler_dependent reproduced {r}: {n}", file=sys.stderr)
    print(f"sanity: one-instruction change detected as {sanity(out / 'psyq/project')} difference(s)", file=sys.stderr)

    w = csv.writer(sys.stdout)
    w.writerow(["project", "label", "category", "file", "symbol", "commit"])
    for k in sorted(game):
        f, sym = k.split(":", 1)
        w.writerow(["dcb_decomp", "stock", "stock_match", f"game/{f}", sym, commit])
    for k in sorted(proj):
        f, sym = k.split(":", 1)
        w.writerow(["dcb_decomp", "stock" if cats[k] == "stock_match" else "assisted", cats[k], f"psyq/{f}", sym, commit])


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
