#!/bin/bash
# Bushido Blade 2: does the project's cc1 match the upstream release binary?
# Runs in a throwaway linux/amd64 container:
#   /src/bushido      the project (read-only)
#   /src/gcc          decompals/mips-gcc-2.7.2 at 43d1cdb (read-only)
#   /stock/cc1        upstream v0.1 release cc1 (same source, 32-bit static)
#   /out              results: one dir of .s per variant
# Variants:
#   project  64-bit host, the project's recipe (combine.o -O, rest -O0 -g) + crash-fix patch
#   nofix    same recipe without the patch, to see which TUs need the fix
#   stock    the upstream release binary
set -uo pipefail
apt-get update -qq && apt-get install -y -qq gcc make bison gperf git cpp-mipsel-linux-gnu >/dev/null

build() {  # build <name> <apply crash fix: 0|1>
  rm -rf /tmp/$1 && cp -a /src/gcc /tmp/$1 && cd /tmp/$1
  [ "$2" = 1 ] && git apply /src/bushido/tools/cc1-reorg-negate-rtx-decl.patch
  ./configure --target=mips-mips-gnu --prefix=/opt/cross --with-gnu-as --disable-gprof \
    --disable-gdb --host=i386-pc-linux --build=i386-pc-linux >/dev/null
  touch c-parse.c c-parse.h c-gperf.h objc-parse.c objc-parse.h
  make combine.o CFLAGS="-O -g -fgnu89-inline" >/tmp/$1.log 2>&1
  make cc1 CFLAGS="-g -fgnu89-inline" >>/tmp/$1.log 2>&1
  [ -x cc1 ] || { tail -20 /tmp/$1.log; exit 1; }
  echo "built $1: simplify_rtx $(nm -S cc1 | awk '$4=="simplify_rtx"{print $2}')"
}
build project 1
build nofix 0

cd /src/bushido
CPP="mipsel-linux-gnu-cpp -Iinclude -undef -Wall -lang-c -fno-builtin -Dmips -D__GNUC__=2 -D__OPTIMIZE__ -D__mips__ -D__mips -Dpsx -D__psx__ -D__psx -D_PSYQ -D__EXTENSIONS__ -D_MIPSEL -D_LANGUAGE_C -DLANGUAGE_C"
F="-O2 -G0 -funsigned-char -quiet -mcpu=3000 -mips1 -mno-abicalls -fno-builtin -w -mel -msoft-float"
GP=" $(sed -n 's/^GP_FILES *:= *//p' Makefile) "
NOSR=" $(sed -n 's/^NO_SR_FILES *:= *//p' Makefile) "
mkdir -p /out/i /out/project /out/nofix /out/stock
shopt -s globstar
n=0
for f in src/**/*.c; do
  id=${f#src/}; id=${id%.c}; key=${id//\//__}
  fl=$F
  case "$GP" in *" $id "*) fl=${F/-G0/-G8};; esac
  case "$NOSR" in *" $id "*) fl="$fl -fno-strength-reduce";; esac
  $CPP $f > /out/i/$key.i 2>/dev/null || echo "cpp failed: $id"
  for v in project nofix; do
    /tmp/$v/cc1 $fl /out/i/$key.i -o /out/$v/$key.s 2>/dev/null || echo "$v failed: $id (exit $?)"
  done
  /stock/cc1 $fl /out/i/$key.i -o /out/stock/$key.s 2>/dev/null || echo "stock failed: $id (exit $?)"
  n=$((n+1))
done
echo "compiled $n TUs"
