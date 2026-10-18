#!/bin/bash
# Runs INSIDE a throwaway linux/amd64 container. Digimon Digital Card Battle (ReGame-Labs/dcb_decomp),
# USA version. Compares cc1 output per function (maspsx and the align fixups run after cc1 and are the
# same deterministic step for every compiler, so they can't create or hide a difference).
#   game/project         game C, the project's compiler: stock old-gcc 2.95.2, the Makefile's flags
#   psyq/project         PsyQ objects, the project's lanes: patched 2.7.2 (tools/patch_cc1.py) or
#                        patched 2.8.1 (tools/sn_cc1.py), plus each object's extra flags
#   psyq/stock           same lanes and flags, unpatched old-gcc of the same version
#   psyq/stock_default   unpatched 2.7.2 with the base PsyQ flags for every object
#   psyq/any_<ver>       unpatched <ver> with each object's own flags (any-released-compiler check)
# Mounts: /src/dcb_decomp read-only, /out results.
set -euo pipefail
apt-get update -qq && apt-get install -y -qq cpp-mipsel-linux-gnu python3 python3-pip wget ca-certificates make >/dev/null
pip install -q --break-system-packages pyelftools >/dev/null 2>&1

cp -R /src/dcb_decomp /work && cd /work
mkdir -p bin && cd bin
for v in 2.7.2 2.8.1 2.95.2; do
  wget -q "https://github.com/decompals/old-gcc/releases/download/0.17/gcc-$v-psx.tar.gz"
  grep " gcc-$v-psx.tar.gz\$" ../tools/deps.sha256 | sha256sum -c - >/dev/null
  mkdir "gcc-$v-psx" && tar -xzf "gcc-$v-psx.tar.gz" -C "gcc-$v-psx"
done
cd /work
mkdir -p build/tools/gcc-2.7.2-psx
python3 tools/patch_cc1.py bin/gcc-2.7.2-psx/cc1 build/tools/gcc-2.7.2-psx/cc1 > /out/patch_cc1.log 2>&1
python3 tools/sn_cc1.py bin/gcc-2.8.1-psx/cc1 build/tools/cc1-2.8.1-sn > /out/sn_cc1.log 2>&1
sha256sum bin/*/cc1 build/tools/gcc-2.7.2-psx/cc1 build/tools/cc1-2.8.1-sn > /out/compilers.sha256

# the Makefile's variables, read from its own files
CPPFLAGS="-Iinclude -Iexternal/psyq_headers/psyq_lib47/include -undef -nostdinc -Wundef \
  -D__GNUC__=2 -Dmips -D__mips__ -D__mips -Dpsx -D__psx__ -D__psx -D_PSYQ -D__EXTENSIONS__ -D_MIPSEL \
  -D_LANGUAGE_C -DLANGUAGE_C -DVERSION_US -DASM_DIR=\"asm/us\" -Ibuild/us"
GAME="-quiet -O1 -G0 -mips1 -mcpu=3000 -mgas -msoft-float -fgnu-linker -Wall -Wno-unused"
PSYQ="-quiet -O2 -G0 -mips1 -mcpu=3000 -mgas -mhard-float -fgnu-linker -fsigned-char -fno-builtin -fdollars-in-identifiers -Wall -Wno-unused"
printf 'include mk/version/us.mk\n$(foreach v,$(filter %%_C_SRC,$(.VARIABLES)),$(info $($(v))))\nall: ;\n' > /tmp/print.mk
make -s -f /tmp/print.mk | tr ' ' '\n' | grep '\.c$' | sort -u > /out/game_files.txt

pp() {  # $1 .c -> /work/i/<name>.i
  local n; n=$(echo "${1#src/}" | tr / _ | sed 's/\.c$//')
  mipsel-linux-gnu-cpp $CPPFLAGS "$1" -o "/work/i/$n.i" 2>>/out/cpp.log || echo "CPPFAIL $1"
}
mkdir -p /work/i
while read -r c; do pp "$c"; done < /out/game_files.txt

mkdir -p /out/game/project
while read -r c; do
  n=$(echo "${c#src/}" | tr / _ | sed 's/\.c$//')
  [ -f "/work/i/$n.i" ] && { bin/gcc-2.95.2-psx/cc1 $GAME -o "/out/game/project/$n.s" "/work/i/$n.i" 2>/dev/null || echo "FAIL game $c"; }
done < /out/game_files.txt

# PsyQ: lane and extra flags per object, from config/us/psyq_objects.txt and the Makefile
awk '{print $1, ($2==""?"272":$2)}' config/us/psyq_objects.txt > /out/psyq_lanes.txt
extra() {  # $1 object, $2 lane -> the object's extra flags
  local f=""
  [ "$2" = gcc2.8 ] && f="$f -mno-split-addresses"
  [ "$2" = nocse ] && f="$f -fno-rerun-cse-after-loop"
  [ "$1" = libc2_putchar ] && f="$f -finline-functions"
  [ "$1" = libcd_bios_1_2 ] && f="$f -fno-strength-reduce"
  echo "$f"
}
mkdir -p /out/psyq/{project,stock,stock_default,any_2.8.1,any_2.95.2}
while read -r o lane; do
  [ -f "src/main/psyq/$o.c" ] || continue
  mipsel-linux-gnu-cpp $CPPFLAGS "src/main/psyq/$o.c" -o "/work/i/psyq_$o.i" 2>>/out/cpp.log || { echo "CPPFAIL $o"; continue; }
  x=$(extra "$o" "$lane")
  if [ "$lane" = gcc2.8 ]; then pc=build/tools/cc1-2.8.1-sn; sc=bin/gcc-2.8.1-psx/cc1
  else pc=build/tools/gcc-2.7.2-psx/cc1; sc=bin/gcc-2.7.2-psx/cc1; fi
  i="/work/i/psyq_$o.i"
  $pc $PSYQ $x -o "/out/psyq/project/$o.s" "$i" 2>/dev/null || echo "FAIL project $o"
  $sc $PSYQ $x -o "/out/psyq/stock/$o.s" "$i" 2>/dev/null || echo "FAIL stock $o"
  bin/gcc-2.7.2-psx/cc1 $PSYQ -o "/out/psyq/stock_default/$o.s" "$i" 2>/dev/null || echo "FAIL stock_default $o"
  bin/gcc-2.8.1-psx/cc1 $PSYQ $x -o "/out/psyq/any_2.8.1/$o.s" "$i" 2>/dev/null || echo "FAIL any_2.8.1 $o"
  bin/gcc-2.95.2-psx/cc1 $PSYQ $x -o "/out/psyq/any_2.95.2/$o.s" "$i" 2>/dev/null || echo "FAIL any_2.95.2 $o"
done < /out/psyq_lanes.txt
echo done
