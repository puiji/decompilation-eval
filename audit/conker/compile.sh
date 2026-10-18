#!/bin/bash
# Runs INSIDE a throwaway arm64 container. Conker's Bad Fur Day (DevOldSchool/conkers-bfd-decomp).
# The project compiler is the released ido-static-recomp v1.2 asset (SHA-256 pinned), so "stock"
# is the same binary; what's measured is per-file settings and the object post-passes.
#   /src  read-only: conker, ultralib-conker (its submodule, for headers)
#   /ido  read-only: the release tarballs (hash-checked on the host)
#   /out  results
# Variants (one .o per mapped C source, GLOBAL_ASM pragmas stripped as the project's no-ROM CI does):
#   project   pinned flags, minus -g3 where a CONKER_COMPILE_WITHOUT directive says so
#   default   pinned flags for every file, and `#pragma loop` lines removed
#   postpass  project objects after prepare_main_library_object.py / split_game_rodata.py
#   mut       project with one instruction word flipped in one object (sanity check)
set -euo pipefail
apt-get update -qq && apt-get install -y -qq binutils-mips-linux-gnu python3 python3-yaml >/dev/null
mkdir -p /opt/ido && tar -xzf /ido/ido-5.3-recomp-linux-arm.tar.gz -C /opt/ido
cp -a /src/conker /work && rm -rf /work/lib/ultralib && cp -a /src/ultralib-conker /work/lib/ultralib
cd /work

{ python3 scripts/list_integrated_sources.py --overlay main --profile us
  python3 scripts/list_integrated_sources.py --profile-segment debugger --profile us
  python3 scripts/list_integrated_sources.py --overlay game --profile us; } 2>/out/list.err \
  | tr ' ' '\n' | grep '\.c$' | sort -u > /out/sources.txt || true
echo "mapped sources: $(wc -l < /out/sources.txt)"

BASE="-c -32 -G 0 -Xfullwarn -Xcpluscomm -signed -nostdinc -non_shared -Wab,-r4300_mul -D_LANGUAGE_C -D_FINALROM -D_MIPS_SZLONG=32 -DPROFILE_US=1 -I include -I lib/ultralib/include -O2 -g3 -mips2"
: > /out/globalasm.tsv; : > /out/fail.txt
while read -r c; do
  [ -f "$c" ] || { echo "nofile $c" >> /out/fail.txt; continue; }
  grep -oE '#pragma[ \t]+GLOBAL_ASM\("[^"]+"\)' "$c" | sed -E 's|.*/([^/"]+)\.s"\)|\1|' \
    | sed "s|^|$c\t|" >> /out/globalasm.tsv || true
  o=${c%.c}.o; s=/work/strip/$c; mkdir -p "$(dirname "$s")" /out/project/"$(dirname "$o")" /out/default/"$(dirname "$o")"
  sed -E '/^[ \t]*#pragma[ \t]+GLOBAL_ASM\(/d' "$c" > "$s"
  pflags=$BASE
  grep -qE 'CONKER_COMPILE_WITHOUT:[ \t]*-g3' "$c" && pflags=${BASE/ -g3/}
  /opt/ido/cc $pflags -o "/out/project/$o" "$s" 2>>/out/cc.err || { echo "project $c" >> /out/fail.txt; continue; }
  sed -E '/^[ \t]*#pragma[ \t]+loop\b/d' "$s" > "$s.d.c"
  /opt/ido/cc $BASE -o "/out/default/$o" "$s.d.c" 2>>/out/cc.err || echo "default $c" >> /out/fail.txt
done < /out/sources.txt

cp -a /out/project /out/postpass
for u in init_2E50:7 init_11FA0:5; do
  o=/out/postpass/src/done/main/${u%:*}.o
  [ -f "$o" ] && python3 scripts/prepare_main_library_object.py "$o" "$o.p" --delta=-0x70000000 --expected-relocations "${u#*:}" \
    && mv "$o.p" "$o" || echo "postpass ${u%:*}" >> /out/fail.txt
done
for u in game_B4080 game_16EE20 game_1C1150; do
  o=$(find /out/postpass -name "$u.o" | head -1)
  [ -n "$o" ] && python3 scripts/split_game_rodata.py "$o" || echo "postpass $u" >> /out/fail.txt
done

cp -a /out/project /out/mut
m=$(find /out/mut -name '*.o' | sort | head -1); python3 /a/compare.py --mutate "$m" "$m.x" && mv "$m.x" "$m"
echo "mutated: $m" > /out/mutated.txt

for v in default postpass mut; do python3 /a/compare.py /out project $v /out/globalasm.tsv; done | tee /out/summary.txt
echo done
