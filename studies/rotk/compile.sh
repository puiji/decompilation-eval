#!/bin/bash
# Runs INSIDE a throwaway container. lotr-gba-re/rotk builds its matched C with an agbcc fork
# (613cad3d = pret + 4 "tracing for LLM agents" commits touching regmove/reload1/combine).
# Compile every src/c file with the fork (tracing off, tracing on) and stock pret agbcc.
set -euo pipefail
FORK=613cad3d3afb54c516f1b222e7d54a3fb7bb28f3
STOCK=da598c1d918402c42c0c0d7128ba14567f3175e9

apt-get update -qq && apt-get install -y -qq gcc make gcc-arm-none-eabi git python3 python3-pip curl >/dev/null
build() {
  git clone -q "/src/$2" "/work/$1" && git -C "/work/$1" -c advice.detachedHead=false checkout -q "$3"
  make -C "/work/$1/gcc" -j1 >/dev/null 2>&1 && mv "/work/$1/gcc/agbcc" "/work/$1/"
}
build fork agbcc-lotr "$FORK"
build stock agbcc-pret "$STOCK"

# Generated header (from config/*.cfg, no ROM) via the project's own tool.
git clone -q /src/rotk /work/rotk && cd /work/rotk
pip install -q --break-system-packages uv >/dev/null 2>&1
uv run rotkit build variables >/dev/null

INC=/work/inc; mkdir -p $INC; cp -R /work/fork/libc/include/. $INC/; cp /work/fork/ginclude/* $INC/
mkdir -p /work/i
for c in $(find src/c -name '*.c' | sort); do
  n=$(echo "${c#src/c/}" | tr / _ | sed 's/\.c$//')
  arm-none-eabi-cpp -nostdinc -DAGBCC -Iinclude -Icarved/include -Ibuild/include -I$INC "$c" -o "/work/i/$n.i"
done

FLAGS="-O2 -mthumb-interwork -Wall -W -Wmissing-prototypes"
run() {  # $1 variant, $2 compiler dir, rest = extra flags
  local v=$1 cc=$2; shift 2; mkdir -p "/out/$v"
  for i in /work/i/*.i; do
    n=$(basename "$i" .i)
    (cd /tmp && "/work/$cc/agbcc" "$i" -o "/out/$v/$n.s" $FLAGS "$@" 2>/dev/null) || echo "FAIL $v $n"
  done
}
run fork_base  fork
AGBCC_TRACE_ALLOC=1 AGBCC_TRACE_LOOP=1 AGBCC_TRACE_XJUMP=1 AGBCC_TRACE_RELOAD=1 AGBCC_TRACE_COMBINE=1 \
  run fork_trace fork -dp -da
run stock_base stock
echo done
