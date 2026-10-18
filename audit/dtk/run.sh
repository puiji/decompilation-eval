#!/bin/bash
# Inside reveval-gc:arm64 (no host code runs). /src repo (ro)  /audit our scripts (ro)  /mnt results.
# 1. Fetch the project's pinned compiler bundle, run its own pre-compile steps (compiler patches).
# 2. Per VERSION: dump units, compile Matching units as project / stock / default (ffcc/sweep.py),
#    then the community-patch units on their released base (community/tier.py rewrite).
set -uo pipefail
rm -rf /w && cp -a /src /w && cd /w
mkdir -p build/compilers build/tools /res
V0=${VERSIONS%% *}
VERSION=$V0 TOOLCHAIN=1 python3 /audit/ffcc/units.py > /res/toolchain.json || { echo "toolchain dump failed"; exit 1; }
tag=$(jq -r .compilers_tag /res/toolchain.json)
curl -sSfL "https://files.decomp.dev/compilers_$tag.zip" -o /tmp/c.zip && unzip -q /tmp/c.zip -d build/compilers || exit 1
jq -r '.steps[].command' /res/toolchain.json | while read -r cmd; do echo "pre-compile: $cmd"; eval "$cmd" || echo "STEPFAIL $cmd"; done
# wibo is only the Win32 loader; 1.2.0 runs under qemu-i386 for every project (the project's own tag is in toolchain.json).
curl -sSfL "https://github.com/decompals/wibo/releases/download/${WIBO:-1.2.0}/wibo-i686" -o build/tools/wibo && chmod +x build/tools/wibo || exit 1
sha1sum build/compilers/GC/*/mwcceppc.exe > /res/compilers.sha1
for v in $VERSIONS; do
  mkdir -p /res/$v/base
  VERSION=$v python3 /audit/ffcc/units.py > /res/$v/units_declared.jsonl || { echo "units failed for $v"; continue; }
  python3 /audit/dtk/default.py < /res/$v/units_declared.jsonl > /res/$v/units.jsonl  # library default = its most common settings
  JOBS=${JOBS:-8} VARIANTS="project stock default" python3 /audit/ffcc/sweep.py /res/$v/units.jsonl build/compilers build/tools/wibo /res/$v
  python3 /audit/community/tier.py rewrite /res/$v/units.jsonl > /res/$v/base/units.jsonl
  JOBS=${JOBS:-8} VARIANTS=project python3 /audit/ffcc/sweep.py /res/$v/base/units.jsonl build/compilers build/tools/wibo /res/$v/base
done
cp -a /res/. /mnt/ && echo done
