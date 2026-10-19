"""One-off backfill: add a `scope` column (game | sdk) to label CSVs written before runners emitted it.

    python audit/add_scope.py

SDK means vendor libraries (console SDK, C runtime, middleware such as RedSound or m4a), whichever
compiler built them. Rules per project, from each project's build files and the run's own split:
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = Path(__file__).parent / "labels"
SDK_RE = {  # file-column regex -> sdk
    "bushido": r"main/psxsdk/",
    "boktai2": r"lib_",
    "knidl": r"(agb_sram|m4a_c1|m4a_cgb|m4a_ctrl)$",
    "dcb_decomp": r"psyq/",
    "parasite-eve": r"main_psyq",
    "klonoa": r"src/(m4a|eeprom)",
}
TSV = {"ffcc": ["ffcc/GCCJGC", "ffcc/GCCP01"], "tw2004": ["tw2004"],  # runs that recorded a category
       "tww": ["tww/run/GZLE01"], "melee": ["melee/run/GALE01"]}
GAME = {"game", "core"}  # TWW "core" = framework, m_Do, SSystem: the game's own engine code


def tsv_scope(dirs):
    out = {}
    for d in dirs:
        for r in csv.DictReader(open(ROOT / "out" / d / "functions.tsv"), delimiter="\t"):
            out[(r["src"], r["function"])] = "game" if r["category"] in GAME else "sdk"
    return out


def main():
    for path in sorted(LABELS.glob("*.csv")):
        rows = list(csv.DictReader(open(path)))
        if not rows or "scope" in rows[0]:
            continue
        name = path.stem
        lookup = tsv_scope(TSV[name]) if name in TSV else None
        for r in rows:
            if lookup is not None:
                r["scope"] = lookup.get((r["file"], r["symbol"]), "game")  # tw2004's ProDG rows are game
            elif name in SDK_RE and re.search(SDK_RE[name], r["file"]):
                r["scope"] = "sdk"
            else:
                r["scope"] = "game"
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, [*rows[0].keys()])
            w.writeheader()
            w.writerows(rows)
        print(f"{name}: {sum(r['scope'] == 'sdk' for r in rows)} sdk / {len(rows)}")


if __name__ == "__main__":
    main()
