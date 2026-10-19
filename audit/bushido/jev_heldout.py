"""Held-out Jev v2 test on BushidoBlade 2 (pre-registered; result in findings.md, Oct 16).

    python jev_heldout.py <heldout.jsonl> <cache.json>

Same questions and criteria as jev_pass.QUESTIONS_V2; only the platform sentence of the
context changes. Positives are `hand_written`, negatives `compiled`.
"""
import hashlib
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev_pass import ASM, CONTEXT2, QUESTIONS_V2, api_key, asm_share, auroc, classify, facts, ssl_ctx  # noqa: E402

CONTEXT_PS1 = (CONTEXT2.replace("PlayStation 2 game (EA, 2003)", "PlayStation game (Bushido Blade 2, 1998)")
               .replace("in C by EA", "in C by the developers or Sony's SDK")
               .replace("MIPS/VU0 assembly", "MIPS/GTE assembly"))
assert CONTEXT_PS1.count("Bushido") == 1 and "VU0 assembly" not in CONTEXT_PS1
QUESTIONS = json.loads(json.dumps(QUESTIONS_V2).replace(json.dumps(CONTEXT2)[1:-1], json.dumps(CONTEXT_PS1)[1:-1]))
assert all(CONTEXT_PS1 in q["instructions"] for q in QUESTIONS.values())


def asm_line_share(src):
    lines = [x for x in src.splitlines() if x.strip()]
    return sum(1 for x in lines if re.match(r'\s*"', x) or ASM.search(x)) / len(lines)


def ci(pos, neg, n=2000, seed=0):
    rnd = random.Random(seed)
    stats = sorted(auroc([rnd.choice(pos) for _ in pos], [rnd.choice(neg) for _ in neg]) for _ in range(n))
    return stats[int(0.025 * n)], stats[int(0.975 * n)]


def main(path, cache_path):
    rows = [json.loads(l) for l in open(path)]
    cache_file = Path(cache_path)
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    h = lambda r: hashlib.sha256(r["source"].encode()).hexdigest()[:16]
    jobs = {}
    for r in rows:
        jobs[f"raw:{h(r)}"] = r["source"]
        jobs[f"facts:{h(r)}"] = facts(r["source"]) + r["source"]
    todo = [k for k in jobs if k not in cache]
    if todo:
        key, ctx = api_key(), ssl_ctx()
        if not key:
            sys.exit("no TYPESAFE_API_KEY in the repo-root .env")
        print(f"querying Jev for {len(todo)} items...")
        with ThreadPoolExecutor(8) as pool:
            for k, out in zip(todo, pool.map(lambda k: classify(jobs[k], key, ctx, QUESTIONS), todo)):
                cache[k] = out
        cache_file.write_text(json.dumps(cache))

    a = lambda k: cache[k]["answers"]
    signals = {}
    for var in ("raw", "facts"):
        signals[f"{var} origin"] = lambda r, v=var: a(f"{v}:{h(r)}")["origin"]["probabilities"]["hand_written_asm"]
        signals[f"{var} c_is_shell"] = lambda r, v=var: a(f"{v}:{h(r)}")["c_is_shell"]["noul"]
    signals["asm_share (no model)"] = lambda r: asm_share(r["source"])
    signals["asm_line_share (no model)"] = lambda r: asm_line_share(r["source"])
    def table(title, pos, neg):
        print(f"\n{title}: {len(pos)} hand_written vs {len(neg)} compiled")
        print(f"{'signal':26} {'AUROC':>6} {'95% CI':>13}   flagged at 0.5      at 0.7      at 0.9")
        for name, f in signals.items():
            p, n = [f(r) for r in pos], [f(r) for r in neg]
            lo, hi = ci(p, n)
            cells = "  ".join(f"{sum(x >= t for x in p):2}/{len(p)} vs {sum(x >= t for x in n):3}" for t in (0.5, 0.7, 0.9))
            print(f"{name:26} {auroc(p, n):6.3f} ({lo:.2f}-{hi:.2f})   {cells}")

    pos = [r for r in rows if r["label"] == "hand_written"]
    neg = [r for r in rows if r["label"] == "compiled"]
    table("Pre-registered labels", pos, neg)
    # Post hoc: the canonical list's own tag says gte_psyq_macro_call rows are compiled C with GTE macros.
    gte = [r for r in pos if r.get("canon_tag") == "gcc-cannot-emit:gte_psyq_macro_call"]
    table("POST HOC, canonical gte_psyq_macro_call rows moved to compiled", [r for r in pos if r not in gte], neg + gte)
    usage = [c.get("usage") or {} for c in cache.values()]
    tokens = sum(u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in usage)
    print(f"\nJev {next(iter(cache.values())).get('model')}: {len(cache)} cached calls, {tokens:,} tokens")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
