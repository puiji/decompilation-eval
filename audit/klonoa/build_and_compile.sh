#!/bin/bash
# Runs INSIDE a throwaway container. Builds the Klonoa agbcc fork and stock pret agbcc
# (the fork's merge base), then compiles every Klonoa C file with each under several flag
# sets. No ROM is needed: we compare compiler output, not the linked ROM.
#   /src  read-only: kl-eod-decomp, agbcc-fork, agbcc-pret
#   /out  results: <variant>/<file>.s
set -euo pipefail
FORK=61b9c52f16ae9bce3b36cee6917e72d1494e2b09   # what kl-eod-decomp pins
STOCK=da598c1d918402c42c0c0d7128ba14567f3175e9  # merge base with pret/agbcc

apt-get update -qq && apt-get install -y -qq gcc make gcc-arm-none-eabi git >/dev/null

build() {  # $1 name, $2 repo, $3 commit
  git clone -q "/src/$2" "/work/$1" && git -C "/work/$1" -c advice.detachedHead=false checkout -q "$3"
  make -C "/work/$1/gcc" old -j1 >/dev/null 2>&1 && mv "/work/$1/gcc/old_agbcc" "/work/$1/"
  make -C "/work/$1/gcc" clean >/dev/null && make -C "/work/$1/gcc" -j1 >/dev/null 2>&1
  mv "/work/$1/gcc/agbcc" "/work/$1/"
}
build fork agbcc-fork "$FORK"
build stock agbcc-pret "$STOCK"

# Preprocess once with the fork's headers, so only the compiler differs between variants.
INC=/work/inc; mkdir -p $INC; cp -R /work/fork/libc/include/. $INC/; cp /work/fork/ginclude/* $INC/
cd /src/kl-eod-decomp
BASE="-mthumb-interwork -Wimplicit -Wparentheses -O2 -fhex-asm -fprologue-bugfix"
INSTR="-finstrument-src-locs -fdump-function-size -fdump-reg-lifetimes -fdump-pool-literals"
mkdir -p /work/i
for c in src/*.c; do
  n=$(basename "$c" .c)
  arm-none-eabi-cpp -nostdinc -I $INC -iquote include "$c" -o "/work/i/$n.i"
done

run() {  # $1 variant, $2 compiler dir, rest = flags (old_agbcc files use their Makefile flags)
  local v=$1 cc=$2; shift 2; mkdir -p "/out/$v"
  for i in /work/i/*.i; do
    n=$(basename "$i" .i)
    case $n in
      m4a)    "/work/$cc/old_agbcc" -mthumb-interwork -O2 -o "/out/$v/$n.s" "$i" ;;
      eeprom) "/work/$cc/old_agbcc" -mthumb-interwork -O1 -fhex-asm -o "/out/$v/$n.s" "$i" ;;
      *)      "/work/$cc/agbcc" "$@" -o "/out/$v/$n.s" "$i" 2>/dev/null ;;
    esac || echo "FAIL $v $n"
  done
}
run fork_full  fork  $BASE -g $INSTR   # exactly what the project builds with
run fork_base  fork  $BASE
run fork_g     fork  $BASE -g
run fork_instr fork  $BASE $INSTR
run stock_base stock $BASE
run stock_g    stock $BASE -g
echo done
