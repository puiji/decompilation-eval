#!/bin/bash
# FFCC (and, with PROJECT_CC=bundle, any dtk MWCC project): compile Matching units under the
# sweep.py variants. Runs in the reveval-gc:arm64 image (python3, qemu-user, curl):
#   /src repo (ro)   /cc compilers dir (ro)   /audit our scripts (ro)   /mnt results
# FFCC derives its Japanese compiler GC/2.0p1j from GC/2.0p1 in five SHA-1-guarded steps. The
# first two (p1a, p1g) are BFBB's and produce the same hashes BFBB's chain did, so /cc can be
# out/bfbb/compilers; only FFCC's own three steps (p1h, p1i, p1j) are run here, with its scripts.
# RUNS = "VERSION:VARIANTS;..." e.g. "GCCJGC:project stock default p1a p1g p1h p1i;GCCP01:project default"
set -uo pipefail
rm -rf /w && cp -a /src /w && cd /w
mkdir -p build/tools /res
cp -a /cc build/compilers
if [ -f tools/patch_compiler_ffcc3.py ]; then
  for s in patch_compiler_ffcc patch_compiler_ffcc2 patch_compiler_ffcc3; do python3 tools/$s.py build/compilers || exit 1; done
  sha1sum build/compilers/GC/2.0p1{,a,g,h,i,j}/mwcceppc.exe
fi
curl -sSfL "https://github.com/decompals/wibo/releases/download/${WIBO:-1.0.3}/wibo-i686" -o build/tools/wibo && chmod +x build/tools/wibo || exit 1
IFS=';' read -ra runs <<<"$RUNS"
for r in "${runs[@]}"; do
  v=${r%%:*}; mkdir -p /res/$v
  [ -f /mnt/units_$v.jsonl ] && cp /mnt/units_$v.jsonl /res/$v/units.jsonl
  VARIANTS="${r#*:}" python3 /audit/sweep.py /res/$v/units.jsonl build/compilers build/tools/wibo /res/$v
done
cp -a /res/. /mnt/ && echo done
