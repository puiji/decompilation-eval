#!/bin/bash
# Runs INSIDE a throwaway container. Klonoa as of fe933e4 (2026-04-03), when the build still
# used the patched compiler: -fno-fold-addr on every C file, -ftst on the m4a TST units.
# Compiles each file the project's way (patched fork + patch flags) and the stock way
# (pret agbcc, same flags minus the patch-only ones).
set -euo pipefail
KLONOA=fe933e4
FORK=86a2006   # agbcc pin at fe933e4: has -ftst, -fcmp-elim, -fno-fold-addr
STOCK=da598c1d918402c42c0c0d7128ba14567f3175e9

apt-get update -qq && apt-get install -y -qq gcc make gcc-arm-none-eabi git >/dev/null
build() {
  git clone -q "/src/$2" "/work/$1" && git -C "/work/$1" -c advice.detachedHead=false checkout -q "$3"
  make -C "/work/$1/gcc" old -j1 >/dev/null 2>&1 && mv "/work/$1/gcc/old_agbcc" "/work/$1/"
  make -C "/work/$1/gcc" clean >/dev/null && make -C "/work/$1/gcc" -j1 >/dev/null 2>&1
  mv "/work/$1/gcc/agbcc" "/work/$1/"
}
build fork agbcc-fork "$FORK"
build stock agbcc-pret "$STOCK"
git clone -q /src/kl-eod-decomp /work/k && git -C /work/k -c advice.detachedHead=false checkout -q "$KLONOA"

INC=/work/inc; mkdir -p $INC; cp -R /work/fork/libc/include/. $INC/; cp /work/fork/ginclude/* $INC/
cd /work/k; mkdir -p /work/i
for c in src/*.c; do arm-none-eabi-cpp -nostdinc -I $INC -iquote include "$c" -o "/work/i/$(basename "$c" .c).i"; done

BASE="-mthumb-interwork -Wimplicit -Wparentheses -O2 -fhex-asm -fprologue-bugfix"
mkdir -p /out/project /out/stock
for i in /work/i/*.i; do
  n=$(basename "$i" .i)
  case $n in
    m4a_1|m4a_tst_*)  # TST units: old_agbcc -ftst
      /work/fork/old_agbcc  -mthumb-interwork -O2 -ftst -o /out/project/$n.s "$i"
      /work/stock/old_agbcc -mthumb-interwork -O2       -o /out/stock/$n.s   "$i" ;;
    m4a|m4a_nopush_*)
      /work/fork/old_agbcc  -mthumb-interwork -O2 -o /out/project/$n.s "$i"
      /work/stock/old_agbcc -mthumb-interwork -O2 -o /out/stock/$n.s   "$i" ;;
    *)
      /work/fork/agbcc  $BASE -fno-fold-addr -o /out/project/$n.s "$i" 2>/dev/null
      /work/stock/agbcc $BASE                -o /out/stock/$n.s   "$i" 2>/dev/null ;;
  esac || echo "FAIL $n"
done
echo done
