"""Score scan.py's source-construct flags against a label set.

    python score_scan.py <functions.jsonl>
"""
import json
import sys
from collections import Counter, defaultdict

from scan import IDIOMS, scan_text


def main(path):
    total, flagged, fired = Counter(), Counter(), defaultdict(Counter)
    for line in open(path):
        r = json.loads(line)
        key = (r["label"], r["category"])
        c = scan_text(r["source"])
        hits = [t for t in IDIOMS if c[t]]
        total[key] += 1
        if hits:
            flagged[key] += 1
            fired[key].update(hits)
    print(f"{'label':8} {'category':15} {'flagged':>13}  patterns")
    for key in sorted(total):
        n, k = total[key], flagged[key]
        pats = ", ".join(f"{p} {v}" for p, v in fired[key].most_common(4))
        print(f"{key[0]:8} {key[1]:15} {k:5}/{n:<6} {k / n:5.1%}  {pats}")
    assisted = sum(v for (l, _), v in total.items() if l == "assisted")
    hits_assisted = sum(v for (l, _), v in flagged.items() if l == "assisted")
    stock_flag = sum(v for (l, _), v in flagged.items() if l == "stock")
    print(f"\nrecall on assisted {hits_assisted}/{assisted}; flagged stock {stock_flag} "
          f"(precision {hits_assisted / max(1, hits_assisted + stock_flag):.1%})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
