#!/bin/bash
# Runs INSIDE a throwaway linux/amd64 container. Parasite Eve (PS1).
# The project's toolchain is already stock: decompals/old-gcc 0.17 release cc1 (2.7.2-psx, and
# 2.8.1-psx for files marked GCC_VERSION), upstream mkst/maspsx at a pinned rev, GNU as.
# What varies is per-file marker comments, resolved here by the project's own cc.sh
# (PE_CC_PRINT_FLAGS=1 prints the settings and compiles nothing).
#   /src  read-only: parasite-eve      /out  results
# cc1 layer (.s):  project | stock (same again: determinism) | stock_default (2.7.2, default flags)
# asm layer (.dis, objdump of .o, maspsx-backend files only):
#   asm_project (project .s, project maspsx/as settings) | asm_default (project .s, defaults)
set -uo pipefail
apt-get update -qq && apt-get install -y -qq curl ca-certificates git python3 binutils-mipsel-linux-gnu >/dev/null
ln -s "$(command -v mipsel-linux-gnu-as)" /usr/local/bin/mipsel-none-elf-as
REL=https://github.com/decompals/old-gcc/releases/download/0.17
mkdir -p /work/g272 /work/g281
curl -fsSL $REL/gcc-2.7.2-psx.tar.gz | tar xz -C /work/g272
curl -fsSL $REL/gcc-2.8.1-psx.tar.gz | tar xz -C /work/g281
C272=$(find /work/g272 -name cc1 -type f); C281=$(find /work/g281 -name cc1 -type f); CPP=$(find /work/g272 -name cpp -type f)
sha256sum "$C272" "$C281" "$CPP"
git clone -q --no-checkout https://github.com/mkst/maspsx.git /work/maspsx
git -C /work/maspsx checkout -q 42b862c988fe7a13fe4e7ac0ebec90ed6b9fb763
MASPSX=/work/maspsx/maspsx.py

cp -a /src/parasite-eve /work/p && cd /work/p
DEF_CC1="-w -O2 -G0 -funsigned-char -mips1 -mcpu=3000"
for v in project stock stock_default asm_project asm_default; do mkdir -p /out/$v; done
: > /out/settings.tsv
for c in $(find src -name '*.c' | sort); do
  n=$(echo "${c#src/}" | tr / _ | sed 's/\.c$//')
  s=$(PE_CC_PRINT_FLAGS=1 bash tools/scripts/cc.sh "$c" -) || { echo "RESOLVE $c"; continue; }
  get() { printf '%s\n' "$s" | sed -n "s/^$1: //p"; }
  cc1=$(get cc1); flags=$(get cc1_flags); backend=$(get backend); asg=$(get as_g)
  aver=$(get aspsx_version); mflags=$(get maspsx_flags)
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$c" "$cc1" "$flags" "$backend" "$asg" "$aver" "$mflags" >> /out/settings.tsv
  bin=$C272; case $cc1 in *281*) bin=$C281;; esac
  "$CPP" -undef -D__GNUC__=2 -D__OPTIMIZE__ -Dmips -D__mips__ -D__LITTLE_ENDIAN__ -Isdk/psyq-4.0/PSX/INCLUDE -Iinclude -Itools/m2c \
    "$c" -o /work/$n.i 2>/dev/null || { echo "CPP $c"; continue; }
  "$bin" $flags /work/$n.i -o /out/project/$n.s 2>/dev/null || echo "FAIL project $c"
  "$bin" $flags /work/$n.i -o /out/stock/$n.s 2>/dev/null || echo "FAIL stock $c"
  "$C272" $DEF_CC1 /work/$n.i -o /out/stock_default/$n.s 2>/dev/null || echo "FAIL stock_default $c"
  [ "$backend" = maspsx ] || continue
  asm() {  # $1 variant, $2 aspsx version, $3 as -G, rest = maspsx flags
    local v=$1 av=$2 g=$3; shift 3
    python3 $MASPSX --aspsx-version="$av" "$@" --gnu-as-path=mipsel-linux-gnu-as --run-assembler \
      -EL "$g" -march=r3000 -mtune=r3000 -no-pad-sections -I . -I include -I asm/USA/main -I asm/USA/overlays \
      -o /work/$v.o < /out/project/$n.s 2>/dev/null \
      && mipsel-linux-gnu-objdump -dr --no-show-raw-insn /work/$v.o > /out/$v/$n.dis || echo "FAIL $v $c"
  }
  asm asm_project "$aver" "$asg" $mflags
  asm asm_default 2.70 -G0 --expand-div
done
echo done
