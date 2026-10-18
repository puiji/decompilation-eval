#!/bin/bash
# Second pass, INSIDE a throwaway linux/amd64 container, after run.sh. Adds the variants that keep
# data-layout settings (as the Colosseum run kept -sdata) and reset only codegen settings:
#   stock_default_g  cc1 2.7.2, default codegen flags, but the file's own -G<n>
#   asm_default_g    project .s through maspsx with the file's as -G, --use-comm-section and
#                    force-G0 choice kept; ASPSX version, --dont-expand-li, --no-expand-div reset
#   /src  read-only: parasite-eve     /prev read-only: run.sh output (settings.tsv, project/*.s)
set -uo pipefail
apt-get update -qq && apt-get install -y -qq curl ca-certificates git python3 binutils-mipsel-linux-gnu >/dev/null
mkdir -p /work/g272 && curl -fsSL https://github.com/decompals/old-gcc/releases/download/0.17/gcc-2.7.2-psx.tar.gz | tar xz -C /work/g272
C272=$(find /work/g272 -name cc1 -type f); CPP=$(find /work/g272 -name cpp -type f)
git clone -q --no-checkout https://github.com/mkst/maspsx.git /work/maspsx
git -C /work/maspsx checkout -q 42b862c988fe7a13fe4e7ac0ebec90ed6b9fb763
cd /src/parasite-eve
mkdir -p /out/stock_default_g /out/asm_default_g
while IFS=$'\t' read -r c cc1 flags backend asg aver mflags; do
  n=$(echo "${c#src/}" | tr / _ | sed 's/\.c$//')
  g=$(printf '%s\n' $flags | grep -E '^-G[0-9]+$' | tail -1); g=${g:--G0}
  "$CPP" -undef -D__GNUC__=2 -D__OPTIMIZE__ -Dmips -D__mips__ -D__LITTLE_ENDIAN__ -Isdk/psyq-4.0/PSX/INCLUDE -Iinclude -Itools/m2c \
    "$c" -o /work/$n.i 2>/dev/null || { echo "CPP $c"; continue; }
  "$C272" -w -O2 "$g" -funsigned-char -mips1 -mcpu=3000 /work/$n.i -o /out/stock_default_g/$n.s 2>/dev/null || echo "FAIL stock_default_g $c"
  [ "$backend" = maspsx ] || continue
  keep=(); for f in $mflags; do case $f in --use-comm-section|--dont-force-G0) keep+=("$f");; esac; done
  python3 /work/maspsx/maspsx.py --aspsx-version=2.70 --expand-div ${keep[@]+"${keep[@]}"} --gnu-as-path=mipsel-linux-gnu-as --run-assembler \
    -EL "$asg" -march=r3000 -mtune=r3000 -no-pad-sections -I . -I include -I asm/USA/main -I asm/USA/overlays \
    -o /work/o.o < /prev/project/$n.s 2>/dev/null \
    && mipsel-linux-gnu-objdump -dr --no-show-raw-insn /work/o.o > /out/asm_default_g/$n.dis || echo "FAIL asm_default_g $c"
done < /prev/settings.tsv
echo done
