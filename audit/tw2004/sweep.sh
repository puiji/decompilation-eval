#!/bin/bash
# tw2004: compile every Matching unit with its own settings and with library defaults
# (ffcc/sweep.py, variants project + default). Runs in reveval-gc:arm64:
#   /src repo (ro)   /audit audit/ffcc scripts (ro)   /mnt out/tw2004 (has units.jsonl)
# Compilers are the project's pin (compilers_20251118.zip, files.decomp.dev), unmodified.
# The 5 ProDG units go through the project's own stage-by-stage driver: ngccc.exe refuses to run
# without an installed sn.ini, so cpp -> cc1 -> NgcAs is the only way to run that compiler.
set -uo pipefail
rm -rf /w && cp -a /src /w && cd /w
mkdir -p build/compilers build/tools /res
curl -sSfL https://files.decomp.dev/compilers_20251118.zip -o /tmp/c.zip && unzip -q /tmp/c.zip -d build/compilers || exit 1
curl -sSfL https://github.com/decompals/wibo/releases/download/1.2.0/wibo-i686 -o build/tools/wibo && chmod +x build/tools/wibo || exit 1
sha1sum build/compilers/GC/{1.2.5n,1.3,1.3.2,2.5}/mwcceppc.exe build/compilers/ProDG/3.5/cc1.exe
cp /mnt/units.jsonl /res/units.jsonl
VARIANTS="project default" python3 /audit/sweep.py /res/units.jsonl build/compilers build/tools/wibo /res
printf '#!/bin/sh\nexec qemu-i386 /w/build/tools/wibo "$@"\n' > /usr/local/bin/wq && chmod +x /usr/local/bin/wq
python3 - <<'EOF'
import json, subprocess, os
for u in map(json.loads, open("/res/units.jsonl")):
    if u["matching"] and u["mw_version"].startswith("ProDG/"):
        out = f"/res/project/{os.path.dirname(u['src'])}"
        flags = [f for f in u["flags"] if not f.startswith("-lang")]
        r = subprocess.run(["python3", "tools/build/prodg/prodgcc.py", "--wrapper", "wq", "build/compilers",
                            u["mw_version"], *" ".join(flags).split(), "-c", u["src"], "-o", out], capture_output=True, text=True)
        print("prodg", u["src"], "ok" if r.returncode == 0 else (r.stdout + r.stderr)[-300:])
EOF
cp -a /res/. /mnt/ && echo done
