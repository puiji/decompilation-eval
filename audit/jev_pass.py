"""Ask TypeSafe Jev whether an inline-asm function was originally hand-written asm.

Runs on the functions where scan.py can't tell assisted from stock (any inline asm),
caches answers by source hash, and scores them against the labels.

    python jev_pass.py <functions.jsonl> <cache.json>

API: POST {base}/v1/systemone with
{state, model, questions}; Bearer TYPESAFE_API_KEY (read from ../.env).
"""
import hashlib
import json
import os
import re
import ssl
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
MODEL = os.environ.get("TYPESAFE_MODEL", "jev-latest")
ASM = re.compile(r"\b(?:__)?asm(?:__)?\b")
CONTEXT = ("This is one function from a matching decompilation of a PlayStation 2 game, written in C/C++ "
           "so that it compiles to exactly the original bytes. Inline assembly is legitimate only for "
           "instructions a C compiler cannot emit, such as VU0/COP2 vector ops, COP0 or other special "
           "registers, or sync/cache instructions.")
QUESTIONS = {
    "asm_in_all_but_name": {"type": "noul", "instructions": CONTEXT + " Is this function essentially a "
                            "hand-written assembly routine wrapped in a C function signature, rather than C code "
                            "that uses a little asm where the compiler has no equivalent?"},
    "asm_forces_match": {"type": "noul", "instructions": CONTEXT + " Does this function's inline assembly "
                         "do work that ordinary C could express (loads, stores, arithmetic, branches, register "
                         "moves), suggesting the asm is there to force a byte match rather than because it is needed?"},
}

# v2 targets what the ssx3 audit actually judged (PR #13): was the ORIGINAL hand-written asm,
# so the C is only a shell? Compared only on linked functions; static inline one-instruction
# helpers (abs.s, sqrt.s) are 657 of the 700 stock functions and all accepted, which made v1 unfair.
CONTEXT2 = ("This is one linked function from a matching decompilation of a PlayStation 2 game (EA, 2003). "
            "Decompilers write C/C++ that compiles to exactly the original bytes. Some original functions were "
            "written in C by EA and compiled; others were written by hand in MIPS/VU0 assembly. For a hand-written "
            "one, a C body made of inline asm is a disguise and should be kept as an asm file instead.")
QUESTIONS_V2 = {
    "origin": {"type": "choice", "instructions": CONTEXT2 + " How was the ORIGINAL function most likely written?",
               "criteria": {
                   "hand_written_asm": "A hand-written assembly routine. Signs: the work is done in the asm, not "
                       "in C; an interrupt or exception handler; saving or restoring FPU, COP0 or COP2 registers; a "
                       "VU0 microcode-style routine; a trap or break stub; a tiny stub whose only real work is special "
                       "instructions; code that touches registers directly instead of through C variables.",
                   "compiled_c": "Compiled C. Signs: real C logic (struct fields, loops, calls, arithmetic, "
                       "branches) carries the work, and inline asm supplies only one or a few instructions the "
                       "compiler cannot emit, such as sqrt.s, abs.s, ei/di, or a vector multiply in the middle of C math."}},
    "c_is_shell": {"type": "noul", "instructions": CONTEXT2 + " Is the C in this function only a shell around "
                   "assembly, so that deleting the inline asm would leave essentially nothing of the function's behavior?"},
}


def facts(src):
    """Plain-text header with the cheap structural features, for the v2 'facts' variant."""
    lines = [x for x in src.splitlines() if x.strip()]
    asm_lines = sum(1 for x in lines if re.match(r'\s*"', x) or ASM.search(x))
    c_stmts = sum(1 for x in lines if x.rstrip().endswith(";") and not ASM.search(x) and not re.match(r'\s*"', x))
    calls = len(re.findall(r"\b(?!if|for|while|switch|return|sizeof|asm|__asm__)\w+\s*\(", src.split("{", 1)[-1]))
    return (f"[facts] {len(lines)} non-blank lines; {asm_lines} are inline asm; {c_stmts} plain C statements; "
            f"about {calls} calls or casts outside asm.\n\n")


def is_linked(r):
    return not re.search(r"\b(inline|static)\b", r["source"].split("{", 1)[0])


def api_key():
    env = Path(__file__).resolve().parents[1] / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith("TYPESAFE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("TYPESAFE_API_KEY", "")


def ssl_ctx():
    try:
        import certifi  # python.org builds ship without system certs
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def classify(text, key, ctx, questions=QUESTIONS):
    body = json.dumps({"state": text, "model": MODEL, "questions": questions}).encode()
    req = urllib.request.Request(f"{BASE.rstrip('/')}/v1/systemone", data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "User-Agent": "decompilation-eval"})
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        return json.loads(r.read())


def auroc(pos, neg):
    """P(random positive scores above random negative), ties count half (Mann-Whitney, midranks)."""
    ranked = sorted([(x, 1) for x in pos] + [(x, 0) for x in neg])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        rank_sum += (i + j + 1) / 2 * sum(lab for _, lab in ranked[i:j])
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def asm_share(src):
    lines = [x for x in src.splitlines() if x.strip()]
    return sum(1 for x in lines if re.match(r'\s*"', x)) / len(lines)


def main(functions_path, cache_path):
    rows = [r for r in map(json.loads, open(functions_path))
            if ASM.search(r["source"]) and r["category"] in ("asm_shell", "stock_match")]
    cache_file = Path(cache_path)
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    h = lambda r: hashlib.sha256(r["source"].encode()).hexdigest()[:16]
    # Every (cache key, state, questions) we need; v1 keys stay as they were.
    jobs = {}
    for r in rows:
        jobs[h(r)] = (r, r["source"], QUESTIONS)
        if is_linked(r):
            jobs[f"v2raw:{h(r)}"] = (r, r["source"], QUESTIONS_V2)
            jobs[f"v2facts:{h(r)}"] = (r, facts(r["source"]) + r["source"], QUESTIONS_V2)
    todo = [k for k in jobs if k not in cache]
    if todo:
        key, ctx = api_key(), ssl_ctx()
        if not key:
            sys.exit("no TYPESAFE_API_KEY in the repo-root .env")
        print(f"querying Jev for {len(todo)} items...")
        with ThreadPoolExecutor(8) as pool:
            for k, out in zip(todo, pool.map(lambda k: classify(jobs[k][1], key, ctx, jobs[k][2]), todo)):
                cache[k] = {"symbol": jobs[k][0]["symbol"], **out}
        cache_file.write_text(json.dumps(cache))

    a = lambda k: cache[k]["answers"]
    v1 = {f"v1 {q}": (lambda r, q=q: a(h(r))[q]["noul"]) for q in QUESTIONS}
    v2 = {}
    for var in ("raw", "facts"):
        v2[f"v2 {var} origin"] = lambda r, var=var: a(f"v2{var}:{h(r)}")["origin"]["probabilities"]["hand_written_asm"]
        v2[f"v2 {var} c_is_shell"] = lambda r, var=var: a(f"v2{var}:{h(r)}")["c_is_shell"]["noul"]
    base = {"asm_share (no model)": lambda r: asm_share(r["source"])}

    def table(title, pop, signals):
        assisted = [r for r in pop if r["label"] == "assisted"]
        stock = [r for r in pop if r["label"] == "stock"]
        print(f"\n{title}: {len(assisted)} assisted vs {len(stock)} stock")
        print(f"{'signal':26} {'AUROC':>6}   flagged at 0.5      at 0.7      at 0.9")
        for name, f in signals.items():
            pos, neg = [f(r) for r in assisted], [f(r) for r in stock]
            cells = "  ".join(f"{sum(p >= t for p in pos):2}/{len(pos)} vs {sum(n >= t for n in neg):3}"
                              for t in (0.5, 0.7, 0.9))
            print(f"{name:26} {auroc(pos, neg):6.3f}   {cells}")

    table("All inline-asm functions (v1 setup)", rows, {**v1, **base})
    table("Linked functions only (fair comparison)", [r for r in rows if is_linked(r)], {**v1, **v2, **base})
    usage = [c.get("usage") or {} for c in cache.values()]
    tokens = sum(u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in usage)
    print(f"\nJev {cache and next(iter(cache.values())).get('model')}: {len(cache)} cached calls, "
          f"{tokens:,} tokens")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
