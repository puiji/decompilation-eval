"""Jev triage against rebuild labels: can source-only review flag what the stock rebuild found?

    python jev_rebuild.py extract <out_dir>        # function text + fixed-seed sample (no Jev calls)
    python jev_rebuild.py run <out_dir>            # Jev calls (cached) + scores
    python jev_rebuild.py selftest

Positives: game functions the rebuild labels assisted (compiler- or settings-dependent).
Negatives: stock game functions from the same files, so file, author and style are held fixed.
Pre-registered before any call; result in findings.md, Oct 18 "Jev vs rebuild labels".
"""
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bushido.jev_heldout import ci  # noqa: E402
from jev_pass import api_key, auroc, classify, ssl_ctx  # noqa: E402
from labels import DEF, KEYWORDS  # noqa: E402
from scan import IDIOMS, scan_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LABELS = Path(__file__).parent / "labels"
PROJECTS = {"bfbb": ("bfbb", "bfbb"), "ffcc": ("ffcc", "ffcc"), "colosseum": ("colosseum", "colosseum")}  # csv -> repo
CAP, NEG_CAP, SEED = 300, 900, 20261018  # extra negatives so length matching has a pool
OPERATOR = re.compile(r"^__(?!ct$|dt$)[a-z]{2,3}$")  # __as, __pl, __adv ...: operators, skipped

CONTEXT = ("This is one function from a matching decompilation of a Nintendo GameCube game. The C/C++ is "
           "built with Metrowerks CodeWarrior and must compile to exactly the original game's bytes.")
QUESTIONS = {
    "needs_special_build": {"type": "noul", "instructions": CONTEXT + " Is this function likely to match only "
                            "with a non-standard build, such as a patched compiler, or a compiler version or "
                            "optimization flags that differ from the rest of the project, rather than with the "
                            "project's standard compiler and settings?"},
    "shaped": {"type": "noul", "instructions": CONTEXT + " Does this C look shaped to force a byte match rather "
               "than written the way a programmer naturally would? Signs: odd temporaries or redundant casts, "
               "statements in an unnatural order, do-while(0) or goto used for codegen, volatile or register "
               "tricks, dead code, or comments about matching."},
}


def demangle(sym):
    """CodeWarrior symbol -> (class or None, name), or None for operators. Plain C names pass through."""
    m = re.match(r"^(__\w+?|\w+?)__(?=[0-9QFC])(.*)$", sym)
    if not m:
        return None, sym
    name, rest = m.groups()
    if OPERATOR.match(name):
        return None
    cls = None
    if rest[:1] == "Q":
        rest = rest[2:]
        for _ in range(int(m.group(2)[1])):
            n = re.match(r"\d+", rest).group()
            cls, rest = rest[len(n):len(n) + int(n)], rest[len(n) + int(n):]
    elif rest[:1].isdigit():
        n = re.match(r"\d+", rest).group()
        cls = rest[len(n):len(n) + int(n)]
    if name in ("__ct", "__dt"):
        if cls is None:
            return None
        name = ("~" if name == "__dt" else "") + cls
    return cls, name


def definitions(text):
    """[(qualifier or None, name, source)] for top-level definitions; `~X` for destructors."""
    out = []
    for m in DEF.finditer(text):
        name = m.group(1)
        if name in KEYWORDS:
            continue
        head = text[m.start():m.start(1)]
        if head.endswith("~"):
            name, head = "~" + name, head[:-1]
        q = re.search(r"(\w+)::$", head)
        depth = 0
        for i in range(m.end() - 1, len(text)):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            if depth == 0:
                break
        out.append((q and q.group(1), name, text[m.start():i + 1]))
    return out


def unit_text(repo, f, depth=0):
    """A file plus the .c files it #includes (Colosseum's split units include a range file under #defines)."""
    text = (ROOT / "repos" / repo / f).read_text(errors="replace")
    inc = [i for i in re.findall(r'^#include\s+"([^"]+\.c)"', text, re.M) if (ROOT / "repos" / repo / i).exists()]
    return text + "".join("\n" + unit_text(repo, i, depth + 1) for i in inc if depth < 3)


def extract(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(SEED)
    rows, cover = [], Counter()
    for csv_name, (project, repo) in PROJECTS.items():
        labels = [r for r in csv.DictReader(open(LABELS / f"{csv_name}.csv")) if r["scope"] == "game"]
        pos_files = {r["file"] for r in labels if r["label"] == "assisted"}
        defs = {f: definitions(unit_text(repo, f)) for f in pos_files}
        seen = {}  # FFCC JP and PAL share sources: one row per text, conflicting labels dropped
        for r in labels:
            if r["file"] not in pos_files:
                continue
            want = demangle(r["symbol"])
            hits = [s for q, n, s in defs[r["file"]] if want and (q, n) == want]
            ok = "found" if len(hits) == 1 else "operator" if want is None else "missing" if not hits else "ambiguous"
            cover[project, r["label"], ok] += 1
            if ok != "found":
                continue
            prev = seen.setdefault(hits[0], {"project": project, "label": r["label"], "category": r["category"],
                                             "file": r["file"], "symbol": r["symbol"], "source": hits[0]})
            if prev["label"] != r["label"]:
                prev["label"] = "conflict"
        group = [r for r in seen.values() if r["label"] != "conflict"]
        cover[project, "conflict", "dropped"] += len(seen) - len(group)
        for lab in ("assisted", "stock"):
            g = sorted((r for r in group if r["label"] == lab), key=lambda r: (r["file"], r["symbol"]))
            rows += rnd.sample(g, min(CAP if lab == "assisted" else NEG_CAP, len(g)))
    with open(out_dir / "functions.jsonl", "w") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in rows)
    for k, v in sorted(cover.items()):
        print(" ".join(k), v)
    print(Counter((r["project"], r["label"]) for r in rows))


def baselines(src):
    lines = [x for x in src.splitlines() if x.strip()]
    hits = scan_text(src)
    return {"lines (no model)": len(lines), "scanner idioms (no model)": sum(hits.get(t, 0) for t in IDIOMS)}


def length_matched(pop):
    """Each positive paired with the unused same-project negative nearest in line count (greedy, fixed order)."""
    n_lines = lambda r: sum(1 for x in r["source"].splitlines() if x.strip())
    out = []
    for p in PROJECTS:
        neg = [r for r in pop if r["project"] == p and r["label"] == "stock"]
        for r in sorted((r for r in pop if r["project"] == p and r["label"] == "assisted"), key=n_lines):
            if neg:
                best = min(neg, key=lambda x: (abs(n_lines(x) - n_lines(r)), x["symbol"]))
                neg.remove(best)
                out += [r, best]
    return out


def run(out_dir):
    out_dir = Path(out_dir)
    rows = [json.loads(l) for l in open(out_dir / "functions.jsonl")]
    cache_file = out_dir / "jev_cache.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    h = lambda r: hashlib.sha256(r["source"].encode()).hexdigest()[:16]
    todo = sorted({h(r): r["source"] for r in rows if h(r) not in cache}.items())
    if todo:
        key, ctx = api_key(), ssl_ctx()
        if not key:
            sys.exit("no TYPESAFE_API_KEY in the repo-root .env")
        print(f"querying Jev for {len(todo)} functions...")
        with ThreadPoolExecutor(8) as pool:
            for (k, _), out in zip(todo, pool.map(lambda t: classify(t[1], key, ctx, QUESTIONS), todo)):
                cache[k] = out
        cache_file.write_text(json.dumps(cache))
    signals = {q: (lambda r, q=q: cache[h(r)]["answers"][q]["noul"]) for q in QUESTIONS}
    signals.update({b: (lambda r, b=b: baselines(r["source"])[b]) for b in baselines("x")})
    pops = {"pooled": rows, **{p: [r for r in rows if r["project"] == p] for p in PROJECTS},
            "pooled, length-matched pairs": length_matched(rows)}
    for name, pop in pops.items():
        pos = [r for r in pop if r["label"] == "assisted"]
        neg = [r for r in pop if r["label"] == "stock"]
        print(f"\n{name}: {len(pos)} assisted vs {len(neg)} stock (same files)")
        for s, f in signals.items():
            p, n = [f(r) for r in pos], [f(r) for r in neg]
            lo, hi = ci(p, n)
            print(f"  {s:28} AUROC {auroc(p, n):.3f} ({lo:.2f}-{hi:.2f})")
    usage = [c.get("usage") or {} for c in cache.values()]
    tokens = sum(u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in usage)
    print(f"\nJev: {len(cache)} cached calls, {tokens:,} tokens (~${tokens * 42 / 1e9:.4f})")


def selftest():
    assert demangle("GetNextChunk__10CChunkFileFRQ210CChunkFile6CChunk") == ("CChunkFile", "GetNextChunk")
    assert demangle("__ct__10CChunkFileFPv") == ("CChunkFile", "CChunkFile")
    assert demangle("__dt__5CFontFv") == ("CFont", "~CFont")
    assert demangle("xCameraExit__FP7xCamera") == (None, "xCameraExit")
    assert demangle("foo__Q23Out2InFv") == ("In", "foo")
    assert demangle("__as__5xQuatFRC5xQuat") is None
    assert demangle("DVDLowSeek") == (None, "DVDLowSeek")
    src = "CFont::~CFont()\n{\n}\nvoid CFont::GetWidth(char* s)\n{\n    if (s) { x(); }\n}\nint f(void)\n{\n    return 1;\n}\n"
    assert [(q, n) for q, n, _ in definitions(src)] == [("CFont", "~CFont"), ("CFont", "GetWidth"), (None, "f")]
    assert definitions(src)[1][2].endswith("x(); }\n}")
    print("selftest ok")


if __name__ == "__main__":
    cmd = sys.argv[1:2]
    if cmd == ["selftest"]:
        selftest()
    elif cmd in (["extract"], ["run"]) and len(sys.argv) > 2:
        {"extract": extract, "run": run}[cmd[0]](sys.argv[2])
    else:
        sys.exit(__doc__)
