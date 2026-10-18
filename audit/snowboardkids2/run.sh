#!/bin/bash
# Runs INSIDE a throwaway linux/amd64 container. Snowboard Kids 2 (N64, KMC GCC 2.7.2).
# The project fetches decompals/mips-gcc-2.7.2 releases/latest (= v0.1, the stock release), so the
# project compiler IS the stock binary. What can differ is per-file settings (one -O0 file).
#   /src  read-only: snowboardkids2 (with lib/ submodules checked out)
#   /out  results: <variant>/<file>.s
# Variants: project (Makefile settings), stock (same, second compile: determinism check),
#           stock_default (-O2 everywhere).
set -uo pipefail
apt-get update -qq && apt-get install -y -qq curl ca-certificates python3 python3-yaml >/dev/null
mkdir -p /work/kmc && cd /work/kmc
curl -sSLO https://github.com/decompals/mips-gcc-2.7.2/releases/download/v0.1/gcc-2.7.2-linux.tar.gz
tar xf gcc-2.7.2-linux.tar.gz && sha256sum gcc-2.7.2-linux.tar.gz
cp -a /src/snowboardkids2 /work/p && cd /work/p
mkdir -p build/include/generated/course_definitions
python3 tools/generate_course_definitions.py --definitions config/courses --out build/include/generated/course_definitions \
  || echo "course definitions failed"

CC="env COMPILER_PATH=/work/kmc /work/kmc/gcc"
BASE="-mabi=32 -mgp32 -mfp32 -mno-abicalls -nostdinc -fno-PIC -G 0 -funsigned-char -w -mips3 -EB -fno-builtin -fno-common -fno-asm"
MACROS="-D_LANGUAGE_C -D_MIPS_SZLONG=32 -D_MIPS_SZINT=32 -D__USE_ISOC99 -DF3DEX_GBI_2 -DNDEBUG -D_FINALROM"
INC="-I include -I lib/ultralib/include -I lib/ultralib/include/PR -I lib/libmus/include/PR -I lib/libmus/src -I lib/f3dex2/PR"
for v in project stock stock_default; do mkdir -p /out/$v; done
find src -name '*.c' | sort > /work/files
while read -r c; do
  d=$(dirname "$c"); n=$(echo "${c#src/}" | tr / _ | sed 's/\.c$//')
  opt=-O2; [ "$c" = src/graphics/tiled_sprite_grid.c ] && opt=-O0
  python3 tools/textconv.py tools/charmap.txt "$c" - > /work/t.c 2>/dev/null || { echo "TEXTCONV $c"; continue; }
  for v in project stock stock_default; do
    o=$opt; [ $v = stock_default ] && o=-O2
    $CC $BASE $o -I $d $INC $MACROS -I src/ -I assets/courses -I assets/modelpayload -I build/include -I build/$d \
      -x c -S -o /out/$v/$n.s /work/t.c 2>/work/err || { echo "FAIL $v $c: $(grep -m1 -E 'error|No such' /work/err)"; rm -f /out/$v/$n.s; }
  done
done < /work/files
echo done
