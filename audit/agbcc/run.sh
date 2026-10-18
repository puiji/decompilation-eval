#!/bin/bash
# Runs INSIDE a throwaway container. Generic agbcc stock-rebuild for any GBA project.
# Compiles every src C file three ways and writes <variant>/<file>.s:
#   project        the project's agbcc build (FORK@FORK_SHA) with its per-file settings
#   stock          stock pret agbcc (STOCK_SHA) with the same per-file settings
#   stock_default  stock pret agbcc, default CFLAGS for every file (no per-file overrides)
# Env: PROJ, FORK (dirs under /src), FORK_SHA, CFLAGS, OVERRIDES ("relpath|cc|flags" lines),
#      PREPROC=1 to pipe through the project's tools/preproc with charmap.txt.
# agbcc_arm files are skipped (its i386 configure doesn't build here); they're listed as SKIP.
set -euo pipefail
STOCK_SHA=${STOCK_SHA:-da598c1d918402c42c0c0d7128ba14567f3175e9}

apt-get update -qq && apt-get install -y -qq gcc g++ make gcc-arm-none-eabi git libpng-dev >/dev/null
build() {  # $1 name, $2 repo, $3 commit
  git clone -q "/src/$2" "/work/$1" && git -C "/work/$1" -c advice.detachedHead=false checkout -q "$3"
  make -C "/work/$1/gcc" old -j1 >/dev/null 2>&1 && mv "/work/$1/gcc/old_agbcc" "/work/$1/"
  make -C "/work/$1/gcc" clean >/dev/null && make -C "/work/$1/gcc" -j1 >/dev/null 2>&1
  mv "/work/$1/gcc/agbcc" "/work/$1/"
}
build project "$FORK" "$FORK_SHA"
build stock agbcc-pret "$STOCK_SHA"

INC=/work/inc; mkdir -p $INC; cp -R /work/project/libc/include/. $INC/; cp /work/project/ginclude/* $INC/
cp -R "/src/$PROJ" /work/proj && cd /work/proj
[ "${PREPROC:-0}" = 1 ] && make -C tools/preproc >/dev/null

mkdir -p /work/i
find src -name '*.c' | sort > /work/files
while read -r c; do
  n=$(echo "${c#src/}" | tr / _ | sed 's/\.c$//')
  arm-none-eabi-cpp -nostdinc -undef -std=gnu89 -DMODERN=0 -I $INC -I include -iquote include "$c" -o "/work/i/$n.i" 2>/dev/null \
    || { echo "CPPFAIL $c"; continue; }
  if [ "${PREPROC:-0}" = 1 ]; then tools/preproc/preproc "/work/i/$n.i" charmap.txt > "/work/i/$n.p" && mv "/work/i/$n.p" "/work/i/$n.i"; fi
done < /work/files

setting() {  # $1 relpath -> "cc|flags" (override or default)
  local o; o=$(printf '%s\n' "${OVERRIDES:-}" | awk -F'|' -v f="$1" '$1==f {print $2"|"$3}')
  echo "${o:-agbcc|$CFLAGS}"
}
run() {  # $1 variant, $2 compiler dir, $3 use_overrides
  mkdir -p "/out/$1"
  while read -r c; do
    n=$(echo "${c#src/}" | tr / _ | sed 's/\.c$//')
    [ -f "/work/i/$n.i" ] || continue
    if [ "$3" = 1 ]; then s=$(setting "$c"); else s="agbcc|$CFLAGS"; fi
    cc=${s%%|*}; flags=${s#*|}
    [ "$cc" = agbcc_arm ] && { echo "SKIP $1 $c (agbcc_arm)"; continue; }
    (cd /tmp && "/work/$2/$cc" $flags -o "/out/$1/$n.s" "/work/i/$n.i" 2>/dev/null) || echo "FAIL $1 $c"
  done < /work/files
}
run project project 1
run stock stock 1
run stock_default stock 0
echo done
