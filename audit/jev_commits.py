"""Jev commit triage: can Jev rank the scanner's history hits so lever-introducing commits come first?

    python jev_commits.py extract <out_dir>     # fetch build-file blobs, label by blame, sample (no Jev calls)
    python jev_commits.py run <out_dir>         # Jev calls (cached) + scores
    python jev_commits.py selftest

Population: commits scan.verifier_edits flags (they touch configure.py, Makefile, CI, checksums...).
Positive ("lever commit"), by effect, not by reading the commit: evaluating configure.py before and after
(in a network-less container; it is project code) shows the commit changed the compiler version or
codegen flags (compare.py's CODEGEN set; data-layout flags are not levers) of at least one C unit,
or it touched a compiler-patch script (BFBB, FFCC).
Pre-registered before any call; result in findings.md, Oct 18 "Jev commit triage".
"""
import hashlib
import io
import json
import random
import re
import subprocess
import tarfile
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bushido.jev_heldout import ci  # noqa: E402
from jev_pass import api_key, auroc, classify, ssl_ctx  # noqa: E402
from ffcc.compare import CODEGEN  # noqa: E402
from scan import verifier_edits  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LABELS = Path(__file__).parent / "labels"
AUDIT = Path(__file__).resolve().parent
# name -> (repo, configure.py --version values, has compiler-patch scripts)
PROJECTS = {"bfbb": ("bfbb", [""], True), "ffcc": ("ffcc", ["GCCJGC", "GCCP01"], True), "colosseum": ("colosseum", [""], False)}
CAP, SEED, MAX_CHARS = 500, 20261018, 12000
# The codegen settings compare.py resets (CODEGEN, plus the version); data-layout flags are not levers.
OVERRIDE = re.compile(r'mw_version|"-O\d|-opt |-inline |-schedule |-use_lmw_stmw')
COMPILER = re.compile(r"_COMPILER\b|GC/\d[\w.]*p1[a-j]")
PATCH_TOOL = re.compile(r"tools/patch_compiler\w*\.py$")

QUESTION = {"changes_levers": {"type": "noul", "instructions": (
    "This is one commit from a project that decompiles a game into C/C++ that must compile to exactly the "
    "original bytes. It is shown as its commit message and its changes to build, CI or checksum files. "
    "Does this commit change how some of the code gets compiled, by selecting a different compiler or "
    "compiler version for some files or libraries, changing their optimization or code-generation flags, or "
    "patching the compiler itself? Adding files with the existing settings, data-layout options, or changes "
    "that only move code between files or mark it as matching do not count.")}}
KEYWORDS = re.compile(r"match|flag|-O\d|compiler|mw_version|cflags|patch|version|\bopt", re.I)


def git(repo, *args, stdin=None):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, input=stdin, check=True).stdout


def prefetch(repo, oids):
    """Blobless clones: fetch the needed blobs in one batch instead of one round trip each."""
    oids = sorted({o for o in oids if o.strip("0")})
    if oids:
        git(repo, "-c", "fetch.negotiationAlgorithm=noop", "fetch", "-q", "--no-tags", "--no-write-fetch-head",
            "--recurse-submodules=no", "--filter=blob:none", "--stdin", "origin", stdin="\n".join(oids) + "\n")


def raw_oids(raw):
    return [w for line in raw.splitlines() if line.startswith(":") for w in line.split()[2:4]]


def tree_key(repo, rev):
    """configure.py blob + top-level tools/*.py blobs: everything units.py's output depends on."""
    ls = git(repo, "ls-tree", rev, "configure.py", "tools/").splitlines()
    return hashlib.sha256("".join(sorted(ls)).encode()).hexdigest()[:16], [l.split()[2] for l in ls if l.endswith(".py")]


def write_tree(repo, rev, dest):
    """Extract configure.py and tools/*.py of one revision (data only; nothing runs on the host)."""
    paths = [l.split("\t", 1)[1] for l in git(repo, "ls-tree", rev, "configure.py", "tools/").splitlines()
             if l.split()[1] == "blob" and re.fullmatch(r"configure\.py|tools/[\w.]+\.py", l.split("\t", 1)[1])]
    if not paths:
        return
    for attempt in range(3):  # a lazy blob fetch occasionally fails; retrying works
        r = subprocess.run(["git", "-C", str(repo), "archive", rev, *paths], capture_output=True)
        if r.returncode == 0:
            break
    r.check_returncode()
    tar = r.stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        members = [m for m in t.getmembers() if m.isfile() and (m.name == "configure.py" or re.fullmatch(r"tools/[\w.]+\.py", m.name))]
        for m in members:  # names already restricted to configure.py and tools/<name>.py
            (dest / m.name).parent.mkdir(parents=True, exist_ok=True)
            (dest / m.name).write_bytes(t.extractfile(m).read())


def evaluate(trees_dir, res_dir, versions):
    """Run units.py on every extracted tree in a throwaway container: no network, sources read-only."""
    script = ('cd /trees && ls | xargs -P 8 -I{} sh -c \'for v in ' + " ".join(v or "-" for v in versions) +
              '; do V=$v; [ "$V" = - ] && V=; (cd /trees/{} && VERSION=$V NO_SRC=1 PYTHONDONTWRITEBYTECODE=1 '
              'timeout 120 python3 /audit/ffcc/units.py > /tmp/res/{}.$v.jsonl 2>/tmp/res/{}.$v.err); done\' '
              '; cp -a /tmp/res/. /res/')
    res_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["docker", "run", "--rm", "--network", "none", "-v", f"{trees_dir}:/trees:ro", "-v", f"{AUDIT}:/audit:ro",
                    "-v", f"{res_dir}:/res", "reveval-gc:arm64", "sh", "-c", "mkdir -p /tmp/res && " + script], check=True)


def settings(path):
    """{src: (matching, mw_version, codegen flags, lib)} plus {("lib", name): default}, or None if the dump failed."""
    if not path.exists() or not path.stat().st_size:
        return None
    out = {}
    for u in map(json.loads, open(path)):
        cg = lambda fl: tuple(sorted(f for f in fl if CODEGEN.match(f)))
        out[u["src"]] = (u["matching"], u["mw_version"], cg(u["flags"]), u["lib"])
        out["lib", u["lib"]] = (u["lib_mw_version"], cg(u["lib_flags"]))
    return out


def changes_levers(before, after):
    """Did any C unit get a different compiler version or codegen flags? (Matching or not: the diff can't show which.)
    A new unit is compared with its library's settings before the commit (or after, for a new library),
    unless it takes the settings of a unit the same commit removed: a rename (Colosseum's range -> exact carves)."""
    removed = {before[k][1:3] for k in before if k[0] != "lib" and k not in after}
    for src, v in after.items():
        if src[0] == "lib":
            continue
        _, ver, cg, lib = v
        old = before[src][1:3] if src in before else before.get(("lib", lib), after["lib", lib])
        if (ver, cg) != tuple(old) and not (src not in before and (ver, cg) in removed):
            return True
    return False


def extract(out_dir):
    out_dir = Path(out_dir).resolve()  # docker -v needs absolute paths
    out_dir.mkdir(parents=True, exist_ok=True)
    rnd, rows = random.Random(SEED), []
    for name, (repo_name, versions, has_patch_tools) in PROJECTS.items():
        repo = ROOT / "repos" / repo_name
        hits = {}
        for h, _, _, f in verifier_edits(repo):
            hits.setdefault(h, []).append(f)
        full = dict(zip(hits, git(repo, "rev-parse", *hits).split()))
        sample = rnd.sample(sorted(hits), min(CAP, len(hits)))
        # Patch-script commits count as levers wherever they are; the scanner's file rules may not flag them.
        patch = set()
        if has_patch_tools:
            for c in git(repo, "log", "--format=%H", "--", "tools/").split():
                if any(PATCH_TOOL.search(f) for f in git(repo, "show", "--name-only", "--format=", c).split()):
                    patch.add(c)
        revs = {x for h in sample for x in (full[h], full[h] + "^")}
        keys, blobs = {}, []
        for x in revs:
            try:
                keys[x], b = tree_key(repo, x)
                blobs += b
            except subprocess.CalledProcessError:  # root commit has no parent
                keys[x] = None
        prefetch(repo, blobs)
        trees = out_dir / "trees" / name
        for x, k in keys.items():
            if k and not (trees / k).exists():
                write_tree(repo, x, trees / k)
        res = out_dir / "units" / name
        if not res.exists():
            evaluate(trees, res, versions)
        def label(h):
            c = full[h]
            if c in patch:
                return "lever"
            if keys[c + "^"] is None:
                return "unknown"
            pairs = [(settings(res / f"{keys[c + '^']}.{v or '-'}.jsonl"), settings(res / f"{keys[c]}.{v or '-'}.jsonl")) for v in versions]
            if any(b is None or a is None for b, a in pairs):
                return "unknown"
            return "lever" if any(changes_levers(b, a) for b, a in pairs) else "other"
        diffs = {}
        prefetch(repo, [o for h in sample for o in raw_oids(git(
            repo, "show", "--raw", "--no-renames", "--no-abbrev", "--format=", "-m", "--first-parent", h, "--", *hits[h]))])
        for h in sample:
            text = git(repo, "show", "--format=%B%n---", "--no-renames", "-m", "--first-parent", h, "--", *hits[h])
            diffs[h] = text[:MAX_CHARS] + ("\n[diff truncated]" if len(text) > MAX_CHARS else "")
        for h in sample:
            rows.append({"project": name, "commit": full[h], "label": label(h), "files": hits[h], "text": diffs[h]})
        print(f"{name}: {len(hits)} scanner hits; {len(patch)} patch-script commits, "
              f"{len(patch - set(full.values()))} of them never flagged by the scanner; "
              f"sampled {len(sample)}: {Counter(r['label'] for r in rows if r['project'] == name)}")
    with open(out_dir / "commits.jsonl", "w") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in rows)


def baselines(r):
    msg, _, diff = r["text"].partition("\n---\n")
    changed = [l for l in diff.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    return {"message keywords (no model)": len(KEYWORDS.findall(msg)),
            "diff override tokens (no model)": sum(bool(OVERRIDE.search(l) or COMPILER.search(l)) for l in changed),
            "diff size (no model)": len(changed)}


def run(out_dir):
    out_dir = Path(out_dir)
    rows = [r for r in map(json.loads, open(out_dir / "commits.jsonl")) if r["label"] != "unknown"]
    cache_file = out_dir / "jev_cache.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    h = lambda r: hashlib.sha256(r["text"].encode()).hexdigest()[:16]
    todo = sorted({h(r): r["text"] for r in rows if h(r) not in cache}.items())
    if todo:
        key, ctx = api_key(), ssl_ctx()
        if not key:
            sys.exit("no TYPESAFE_API_KEY in the repo-root .env")
        print(f"querying Jev for {len(todo)} commits...")
        with ThreadPoolExecutor(8) as pool:
            for (k, _), out in zip(todo, pool.map(lambda t: classify(t[1], key, ctx, QUESTION), todo)):
                cache[k] = out
        cache_file.write_text(json.dumps(cache))
    signals = {"jev changes_levers": lambda r: cache[h(r)]["answers"]["changes_levers"]["noul"]}
    signals.update({b: (lambda r, b=b: baselines(r)[b]) for b in baselines(rows[0])})
    silent = [r for r in rows if not baselines(r)["diff override tokens (no model)"]]
    for name, pop in {"pooled": rows, **{p: [r for r in rows if r["project"] == p] for p in PROJECTS},
                      "regex-silent (secondary)": silent}.items():
        pos = [r for r in pop if r["label"] == "lever"]
        neg = [r for r in pop if r["label"] == "other"]
        k = max(1, len(pop) // 10)
        print(f"\n{name}: {len(pos)} lever vs {len(neg)} other commits; recall = lever commits in the top 10% ({k})")
        for s, f in signals.items():
            p, n = [f(r) for r in pos], [f(r) for r in neg]
            lo, hi = ci(p, n)
            top = sorted(pop, key=lambda r: (-f(r), r["commit"]))[:k]  # ties broken by hash, not by label
            print(f"  {s:34} AUROC {auroc(p, n):.3f} ({lo:.2f}-{hi:.2f})   recall@10% {sum(r['label'] == 'lever' for r in top) / len(pos):.2f}")
    usage = [c.get("usage") or {} for c in cache.values()]
    tokens = sum(u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in usage)
    print(f"\nJev: {len(cache)} cached calls, {tokens:,} tokens (~${tokens * 42 / 1e9:.4f})")


def selftest():
    d = "game"
    before = {"a.c": (True, "GC/1.3.2", ("-O4,p",), d), "b.c": (False, "GC/2.6", ("-O4,p",), d),
              ("lib", d): ("GC/1.3.2", ("-O4,p",))}
    assert not changes_levers(before, {**before, "c.c": (True, "GC/1.3.2", ("-O4,p",), d)})  # new unit, default settings
    assert not changes_levers(before, {**before, "b.c": (True, "GC/2.6", ("-O4,p",), d)})  # marked matching, same override
    assert changes_levers(before, {**before, "a.c": (True, "GC/2.6", ("-O4,p",), d)})  # version swap
    assert changes_levers(before, {**before, "c.c": (True, "GC/1.3.2", ("-O3",), d)})  # new unit with its own flags
    r = {"text": "Use -O4 for match\n---\n+    Object(Matching, \"a.c\", mw_version=\"GC/1.3\"),\n+x"}
    assert baselines(r) == {"message keywords (no model)": 2, "diff override tokens (no model)": 1, "diff size (no model)": 2}
    lib_swap = {**before, ("lib", d): ("GC/2.0p1a", ("-O4,p",)), "c.c": (True, "GC/2.0p1a", ("-O4,p",), d)}
    assert changes_levers(before, lib_swap)  # new unit built on a library compiler the commit switched
    rename = {k: v for k, v in before.items() if k != "a.c"}
    assert not changes_levers(before, {**rename, "a2.c": (True, "GC/1.3.2", ("-O4,p",), d)})  # renamed unit keeps its settings
    print("selftest ok")


if __name__ == "__main__":
    cmd = sys.argv[1:2]
    if cmd == ["selftest"]:
        selftest()
    elif cmd in (["extract"], ["run"]) and len(sys.argv) > 2:
        {"extract": extract, "run": run}[cmd[0]](sys.argv[2])
    else:
        sys.exit(__doc__)
