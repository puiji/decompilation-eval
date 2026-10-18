"""Community-patch tier for dtk/MWCC projects: which Matching functions need GC/1.2.5n (over released
GC/1.2.5) or GC/2.0p1 (over released GC/2.0) to match.

    python tier.py rewrite <units.jsonl> > units_base.jsonl
        Matching units on a community-patched compiler (or a chain built on 2.0p1), with mw_version
        swapped for the released base. Compile it with ffcc/sweep.sh VARIANTS=project.
    REPO=<checkout> python tier.py labels <resA> <resB> <project> <commit> [game_src_prefix] > labels.csv
        resA = an ffcc/sweep.py result dir (project, stock, default); resB = the rewritten-units run.
        Categories: compiler_dependent (project patch) > settings_dependent > community_patch_dependent
        (labelled stock) > stock_match. Scope from the unit's progress category (game/core = game), or,
        when a project has none, from game_src_prefix; SDK_RE (env) marks matching src paths sdk regardless.  (needs powerpc objdump)
    python tier.py selftest          (the released-base mapping)
    python tier.py diff <resA> <resB> > dependent.tsv        (needs powerpc objdump)
        Functions of the rewritten units whose released-base code differs from the project build.
    python tier.py apply <labels.csv> <dependent.tsv> [project]   (project: only rows of that project, e.g. ffcc-GCCJGC)
        Mark stock_match rows listed in an already-measured TSV (column `function` = "src:symbol", as in
        out/tww/125n_dependent.tsv and out/melee/125n_dependent.tsv) as community_patch_dependent, in place.
"""
import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ffcc"))
sys.path.insert(0, str(HERE.parent / "bfbb"))
from compare import score  # noqa: E402
from compare_obj import functions  # noqa: E402

BASE = [(re.compile(r"GC/1\.2\.5n$"), "GC/1.2.5"), (re.compile(r"GC/2\.0p1[a-z]?$"), "GC/2.0")]


def base_of(mw):
    return next((b for pat, b in BASE if pat.match(mw)), None)


def rewrite(units_path):
    for u in map(json.loads, open(units_path)):
        if u["matching"] and base_of(u["mw_version"]):
            print(json.dumps({**u, "mw_version": base_of(u["mw_version"])}))


def labels(res_a, res_b, project, commit, game_prefix=None):
    rows, failed = score(res_a)
    rewritten = {u["src"] for u in map(json.loads, open(Path(res_b, "units.jsonl")))}
    cache = {}

    def funcs(res, src):
        if (res, src) not in cache:
            p = Path(res, "project", src).with_suffix(".o")
            cache[res, src] = functions(p) if p.exists() else None
        return cache[res, src]

    w = csv.writer(sys.stdout)
    w.writerow(["project", "label", "category", "file", "symbol", "commit", "scope"])
    tally, missing = Counter(), Counter()
    for r in rows:
        src, fn = r["src"], r["function"]
        community = False
        if src in rewritten:
            base = funcs(res_b, src)
            if base is None:
                missing[src] += 1
            else:
                community = base.get(fn) != funcs(res_a, src)[fn]
        cat = ("compiler_dependent" if r["compiler_dependent"] else "settings_dependent" if r["settings_dependent"]
               else "community_patch_dependent" if community else "stock_match")
        if community and cat != "community_patch_dependent":
            tally[f"also community ({cat})"] += 1
        if os.environ.get("SDK_RE") and re.search(os.environ["SDK_RE"], src):  # target override of the project's category
            scope = "sdk"
        elif r["category"]:
            scope = "game" if r["category"] in ("game", "core") else "sdk"
        else:
            scope = "game" if game_prefix and src.startswith(game_prefix) else "sdk"
        tally[(scope, cat)] += 1
        label = "assisted" if cat in ("compiler_dependent", "settings_dependent") else "stock"
        w.writerow([project, label, cat, src, fn, commit, scope])
    print(f"{project}: not counted {dict(failed)}; base object missing for {len(missing)} units", file=sys.stderr)
    for k, n in sorted(tally.items(), key=str):
        print(f"  {k}: {n}", file=sys.stderr)


def diff(res_a, res_b):
    print("category\tfunction")
    units = list(map(json.loads, open(Path(res_b, "units.jsonl"))))
    missing = 0
    for u in units:
        p_a, p_b = (Path(r, "project", u["src"]).with_suffix(".o") for r in (res_a, res_b))
        if not (p_a.exists() and p_b.exists()):
            missing += 1
            continue
        a, b = functions(p_a), functions(p_b)
        for fn, code in a.items():
            if b.get(fn) != code:
                print(f"{u.get('category')}\t{u['src']}:{fn}")
    print(f"{len(units)} rewritten units, {missing} without both objects", file=sys.stderr)


def apply(labels_csv, tsv, project=None):
    dep = {line.split("\t")[1].strip() for line in open(tsv).readlines()[1:]}
    rows = list(csv.DictReader(open(labels_csv)))
    seen, tally = set(), Counter()
    for r in rows:
        key = f"{r['file']}:{r['symbol']}"
        if key in dep and project in (None, r["project"]):
            seen.add(key)
            if r["category"] == "stock_match":
                r["category"] = "community_patch_dependent"
            tally[(r["scope"], r["category"])] += 1
    with open(labels_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{labels_csv}: {len(dep)} listed, {len(seen)} matched label rows, {len(dep - seen)} not in labels", file=sys.stderr)
    for k, n in sorted(tally.items(), key=str):
        print(f"  {k}: {n}", file=sys.stderr)


if __name__ == "__main__":
    if sys.argv[1:2] == ["rewrite"]:
        rewrite(sys.argv[2])
    elif sys.argv[1:2] == ["diff"]:
        diff(*sys.argv[2:4])
    elif sys.argv[1:2] == ["apply"]:
        apply(*sys.argv[2:5])
    elif sys.argv[1:2] == ["labels"]:
        labels(*sys.argv[2:8])
    elif sys.argv[1:2] == ["selftest"]:
        assert [base_of(v) for v in ("GC/1.2.5n", "GC/2.0p1", "GC/2.0p1g", "GC/2.0p1j", "GC/1.2.5", "GC/2.0", "GC/2.6")] == \
            ["GC/1.2.5", "GC/2.0", "GC/2.0", "GC/2.0", None, None, None]
        print("ok")
    else:
        sys.exit(__doc__)
