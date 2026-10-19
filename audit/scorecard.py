"""Build the scorecard table from the per-project label CSVs.

    python audit/scorecard.py [labels_dir]   # prints a markdown table

Every number in the table comes from audit/labels/*.csv, so anyone with the CSVs can regenerate it.
Layout-only and community-patch functions count as stock (see Method in WRITEUP.md). Rows with scope=sdk are left out of the game columns. A project whose CSV lists only assisted functions (no stock rows) would be marked partial.
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

COMPILER = {"compiler_dependent", "compiler_patch", "compiler_patch_stock_reproducible"}
SETTINGS = {"settings_dependent"}


def main(labels_dir=Path(__file__).parent / "labels"):
    counts, all_code = defaultdict(Counter), defaultdict(Counter)
    for path in sorted(Path(labels_dir).glob("*.csv")):
        for row in csv.DictReader(open(path)):
            all_code[row["project"]][row["label"]] += 1
            if row.get("scope", "game") == "game":
                counts[row["project"]][row["category"]] += 1
    print("Game code (the headline); the last column includes SDK/library code.\n")
    print("| Project | Game functions | Compiler-dependent | Settings-dependent | Other assisted | Layout-only | Community-patch | Stock match rate | All code |")
    print("|---|---|---|---|---|---|---|---|---|")
    for project, c in sorted(counts.items()):
        a = all_code[project]
        n = sum(c.values())
        comp = sum(c[k] for k in COMPILER)
        sett = sum(c[k] for k in SETTINGS)
        community = c["community_patch_dependent"]
        other = n - comp - sett - c["stock_match"] - c["layout_dependent"] - community
        stock = c["stock_match"] + c["layout_dependent"] + community
        rate = f"{stock / n:.1%}" if stock else "partial (no stock rows)"
        whole = f"{a['stock'] / sum(a.values()):.1%}" if a["stock"] else "partial"
        print(f"| {project} | {n:,} | {comp:,} | {sett:,} | {other:,} | {c['layout_dependent']:,} | {community:,} | {rate} | {whole} |")


if __name__ == "__main__":
    main(*sys.argv[1:2])
