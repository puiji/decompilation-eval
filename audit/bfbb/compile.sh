#!/bin/bash
# BFBB duplotron: compile every source unit with the project's compiler choice and
# with stock GC/2.0p1 (and GC/2.0p1a), so compare_obj.py can count functions whose
# code depends on the patch. Runs in a throwaway native (arm64) container:
#   /src/bfbb  the project (read-only)   /audit  our scripts (read-only)   /out  results
# Downloads the same pinned tools the project's ninja rules fetch (compilers zip from
# files.decomp.dev, wibo, sjiswrap) and derives the patched compilers with the
# project's own SHA-1-pinned patch scripts.
set -uo pipefail
apt-get update -qq && apt-get install -y -qq python3 curl unzip jq qemu-user ca-certificates >/dev/null
rm -rf /work && cp -a /src/bfbb /work && cd /work
CC=build/compilers T=build/tools
mkdir -p $CC $T
if [ -d /out/compilers/GC/2.0p1g ]; then cp -a /out/compilers/. $CC/; else
  curl -sSfL https://files.decomp.dev/compilers_20250812.zip -o /tmp/c.zip && unzip -q /tmp/c.zip -d $CC || exit 1
  python3 tools/patch_compiler.py $CC/GC/2.0p1a/mwcceppc.exe || exit 1
  python3 tools/patch_compiler_rw.py $CC/GC/2.0p1g/mwcceppc.exe || exit 1
  cp -a $CC /out/compilers
fi
# wibo sets up 32-bit x86 segments, which Docker Desktop's Rosetta rejects
# ("invalid gdt selector"), so run its i686 build under qemu-user in an arm64 container.
curl -sSfL https://github.com/decompals/wibo/releases/download/1.2.0/wibo-i686 -o $T/wibo || exit 1
chmod +x $T/wibo
sha1sum $CC/GC/2.0p1/mwcceppc.exe $CC/GC/2.0p1a/mwcceppc.exe $CC/GC/2.0p1g/mwcceppc.exe

mkdir -p /res/logs  # results stay off the bind mount until the end (Docker Desktop file sharing dropped writes)
python3 /audit/units.py > /res/units.jsonl || exit 1
echo "$(wc -l < /res/units.jsonl) source units"

compile() {  # compile <variant> <compiler version or "own">
  while read -r u; do
    src=$(jq -r .src <<<"$u"); mw=$(jq -r .mw_version <<<"$u")
    case $mw in GC/2.0p1?) ;; *) continue;; esac  # only units the project builds with a patched compiler
    [ "$2" != own ] && mw=$2
    # sjiswrap (UTF-8 -> Shift-JIS) fails under wibo+qemu (GetProcAddressFail). Skipping it
    # changes only non-ASCII string bytes, the same way for every compiler compared.
    sj=""
    dir=/res/$1/$(dirname "$src"); mkdir -p "$dir"
    eval "qemu-i386 $T/wibo $sj $CC/$mw/mwcceppc.exe $(jq -r '.flags | join(" ")' <<<"$u") -c $src -o $dir" \
      >/dev/null 2>>/res/logs/$1.log || echo "$1 failed: $src"
  done < /res/units.jsonl
}
[ -n "${SMOKE:-}" ] && { head -1 /res/units.jsonl > /tmp/u && mv /tmp/u /res/units.jsonl; }
# Second pass: ONLY=<file of src paths> narrows the units; VARIANTS="name=GC/x ..." picks compilers.
[ -n "${ONLY:-}" ] && { grep -F -f "$ONLY" /res/units.jsonl > /tmp/u; mv /tmp/u /res/units.jsonl; }
for v in ${VARIANTS:-project=own stock_p1=GC/2.0p1 p1a=GC/2.0p1a}; do compile "${v%%=*}" "${v#*=}"; done
cp -a /res/. /out/ && echo done
