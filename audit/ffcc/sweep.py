"""Compile a dtk project's Matching MWCC units under several compiler/flag variants.

    python sweep.py <units.jsonl> <compilers_dir> <wibo> <res_dir>     (inside a native arm64 container, cwd = repo copy)

VARIANTS (env, space-separated), per Matching unit:
  project   the unit's own compiler and flags (CI ties this to the retail hash)
  stock     own flags, patched compiler -> its stock base (GC/2.0p1x -> GC/2.0p1); only for patched units
  default   stock base of the *library's* compiler, unit codegen overrides swapped for the library's
            (-O, -opt, -schedule, -inline, -use_lmw_stmw, as in studies/colosseum/flags.py); only where that differs
  p1a p1g p1h p1i   own flags on an intermediate patch stage; only for patched units
  any       own flags on every stock GC compiler in the bundle; only for patched units
ONLY (env) = file of src paths to restrict to.  JOBS (env) = parallel compiles.
A variant that would repeat the project's exact (compiler, flags) is skipped: identical by construction.
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CODEGEN = re.compile(r"-(O|opt |schedule |inline |use_lmw_stmw )")
PATCHED = re.compile(r"GC/2\.0p1[a-z]$")


def stock_of(v):
    return "GC/2.0p1" if PATCHED.match(v) else v


def default_flags(u):
    return [f for f in u["flags"] if not CODEGEN.match(f)] + [f for f in u["lib_flags"] if CODEGEN.match(f)]


def jobs_for(u, variants, stock_all):
    own = (u["mw_version"], u["flags"])
    patched = bool(PATCHED.match(u["mw_version"]))
    for v in variants:
        if v == "project":
            yield v, own
        elif v == "stock" and patched:
            yield v, (stock_of(u["mw_version"]), u["flags"])
        elif v == "default":
            d = (stock_of(u["lib_mw_version"]), default_flags(u))
            if d != (stock_of(u["mw_version"]), u["flags"]):
                yield v, d
        elif v in ("p1a", "p1g", "p1h", "p1i") and patched:
            yield v, ("GC/2.0" + v, u["flags"])
        elif v == "any" and patched:
            for s in stock_all:
                yield "any_" + s.replace("/", "_"), (s, u["flags"])


def main(units_path, compilers, wibo, res):
    variants = os.environ.get("VARIANTS", "project stock default").split()
    only = set(Path(os.environ["ONLY"]).read_text().split()) if os.environ.get("ONLY") else None
    stock_all = sorted(f"GC/{d.parent.name}" for d in Path(compilers, "GC").glob("*/mwcceppc.exe")
                       if not PATCHED.match(f"GC/{d.parent.name}"))
    units = [u for u in map(json.loads, open(units_path)) if u["matching"] and u["mw_version"].startswith("GC/")
             and (only is None or u["src"] in only)]
    jobs = [(u, name, spec) for u in units for name, spec in jobs_for(u, variants, stock_all)]

    def run(job):
        u, name, (mw, flags) = job
        out = Path(res, name, os.path.dirname(u["src"]))
        out.mkdir(parents=True, exist_ok=True)
        cmd = f"qemu-i386 {wibo} {compilers}/{mw}/mwcceppc.exe {' '.join(flags)} -c {u['src']} -o {out}"
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return r.returncode == 0 or f"{name} {mw} {u['src']}: {(r.stdout + r.stderr).strip()[-300:]}"

    ok = 0
    with ThreadPoolExecutor(int(os.environ.get("JOBS", 3))) as pool, open(Path(res, "failures.log"), "a") as log:
        for r in pool.map(run, jobs):
            if r is True:
                ok += 1
            else:
                log.write(r.replace("\n", " ") + "\n")
    print(f"{len(units)} units, {len(jobs)} compiles ({' '.join(variants)}): {ok} ok")
    # Record exactly what each variant was, so the comparison knows what was skipped as identical.
    with open(Path(res, "jobs.jsonl"), "a") as fh:
        for u, name, (mw, flags) in jobs:
            fh.write(json.dumps({"src": u["src"], "variant": name, "mw": mw, "flags": flags}) + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    main(*sys.argv[1:5])
