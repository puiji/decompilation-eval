"""labels/colosseum.csv from the Colosseum runs already on disk, plus the community-patch tier.

    REPO=repos/colosseum python colosseum_labels.py out/colosseum <commit> > labels/colosseum.csv   (needs powerpc objdump)

  out/colosseum/sweep/<GC_v>/      every Matching unit on each version, own flags (own version = retail code)
  out/colosseum/defflags/<GC_v>/   game units with codegen overrides swapped for the game default (flags.py)
  out/colosseum/community/base/project/   1.2.5n units rebuilt on released GC/1.2.5 (tier.py rewrite)
Scope: game = src/game/ except src/game/gba/ (the GBA-link SDK), as in flags.py. Settings dependence
exists only for game units (defflags was game-only). Hand-written asm functions are excluded (convention);
the stderr summary also gives the counts with them, to check against the findings (6,352 / 1,717).
"""
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ffcc"))
sys.path.insert(0, str(HERE.parent / "bfbb"))
from compare import ASM_FUNC  # noqa: E402
from compare_obj import functions  # noqa: E402


def main(out, commit):
    out = Path(out)
    repo = Path(os.environ["REPO"])
    units = [u for u in map(json.loads, open(out / "sweep" / "units.jsonl"))
             if u["matching"] and u["mw_version"].startswith("GC/")]
    w = csv.writer(sys.stdout)
    w.writerow(["project", "label", "category", "file", "symbol", "commit", "scope"])
    tally, raw, missing = Counter(), Counter(), Counter()
    for u in units:
        src, v = u["src"], u["mw_version"].replace("/", "_")
        o = Path(src).with_suffix(".o")
        proj_p = out / "sweep" / v / o
        if not proj_p.exists():
            missing["project"] += 1
            continue
        proj = functions(proj_p)
        game = src.startswith("src/game/") and "/gba/" not in src
        dflt_p, base_p = out / "defflags" / v / o, out / "community" / "base" / "project" / o
        dflt = functions(dflt_p) if dflt_p.exists() else None
        base = functions(base_p) if u["mw_version"] == "GC/1.2.5n" and base_p.exists() else None
        if u["mw_version"] == "GC/1.2.5n" and base is None:
            missing["base"] += 1
        if game and dflt is None:
            missing["defflags"] += 1
        asm = set(ASM_FUNC.findall((repo / src).read_text(errors="replace")))
        for fn, code in proj.items():
            sett = game and dflt is not None and dflt.get(fn) != code
            comm = base is not None and base.get(fn) != code
            if game:
                raw["game functions"] += 1
                raw["game settings_dependent"] += sett
            if fn in asm:
                tally["asm excluded"] += 1
                continue
            cat = "settings_dependent" if sett else "community_patch_dependent" if comm else "stock_match"
            if sett and comm:
                tally["also community (settings_dependent)"] += 1
            scope = "game" if game else "sdk"
            tally[(scope, cat)] += 1
            w.writerow(["colosseum", "assisted" if sett else "stock", cat, src, fn, commit, scope])
    print(f"missing objects: {dict(missing)}; with asm, as in flags.py: {dict(raw)}", file=sys.stderr)
    for k, n in sorted(tally.items(), key=str):
        print(f"  {k}: {n}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
