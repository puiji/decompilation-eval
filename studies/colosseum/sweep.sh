#!/bin/bash
# Pokemon Colosseum: compile every Matching unit with each MWCC version the project uses,
# so one_compiler.py can ask whether any single compiler reproduces a whole library.
# Runs in a throwaway native (arm64) container:
#   /src  the project (read-only)   /audit  our scripts (read-only)   /out  results
# Tools are the project's own pins (compilers_20251118.zip from files.decomp.dev);
# wibo runs under qemu-i386 because Docker Desktop's Rosetta rejects its 32-bit segments.
set -uo pipefail
apt-get update -qq && apt-get install -y -qq python3 curl unzip qemu-user ca-certificates >/dev/null
rm -rf /work && cp -a /src /work && cd /work
mkdir -p build/compilers build/tools /res/logs
curl -sSfL https://files.decomp.dev/compilers_20251118.zip -o /tmp/c.zip && unzip -q /tmp/c.zip -d build/compilers || exit 1
curl -sSfL https://github.com/decompals/wibo/releases/download/1.2.0/wibo-i686 -o build/tools/wibo && chmod +x build/tools/wibo || exit 1
python3 /audit/bfbb/units.py > /res/units.jsonl || exit 1
python3 - <<'EOF'
import json, os, re, subprocess
from concurrent.futures import ThreadPoolExecutor
VERSIONS = os.environ.get("VERSIONS", "GC/1.1p1 GC/1.2.5n GC/1.3 GC/1.3.2 GC/2.0 GC/2.5 GC/2.6").split()
units = [u for u in map(json.loads, open("/res/units.jsonl")) if u["matching"] and u["mw_version"].startswith("GC/")
         and u["src"].startswith(os.environ.get("PREFIX", "src/"))]
# DEFAULT_FLAGS=1 swaps per-unit codegen overrides (-O, -opt, -schedule, -inline, -use_lmw_stmw)
# for the game default; data-layout (-sdata, -str, -rostr) and selection (-D, -i) flags stay.
CODEGEN = re.compile(r"-(O|opt |schedule |inline |use_lmw_stmw )")
if os.environ.get("DEFAULT_FLAGS"):
    for u in units:
        u["flags"] = [f for f in u["flags"] if not CODEGEN.match(f)] + ["-O4,p", "-inline auto", "-use_lmw_stmw on"]
if os.environ.get("SMOKE"):
    units = units[:3]
def run(job):
    u, v = job
    out = f"/res/{v.replace('/', '_')}/{os.path.dirname(u['src'])}"
    os.makedirs(out, exist_ok=True)
    cmd = f"qemu-i386 build/tools/wibo build/compilers/{v}/mwcceppc.exe {' '.join(u['flags'])} -c {u['src']} -o {out}"
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.returncode == 0 or f"{v} {u['src']}: {(r.stdout + r.stderr).strip()[-300:]}"
jobs = [(u, v) for u in units for v in VERSIONS]
with ThreadPoolExecutor(10) as pool, open("/res/logs/failures.log", "w") as log:
    ok = 0
    for res in pool.map(run, jobs):
        if res is True:
            ok += 1
        else:
            log.write(res.replace("\n", " ") + "\n")
print(f"{len(units)} units x {len(VERSIONS)} compilers: {ok} of {len(jobs)} compiled")
EOF
cp -a /res/. /out/ && echo done
