"""Per-function diff of IDO MIPS objects from compile.sh (run inside the container: needs
mips-linux-gnu-objdump).

    python3 compare.py <out_dir> <ref_variant> <variant> [globalasm.tsv]
    python3 compare.py --mutate <in.o> <out.o>

Disassembles with raw instruction bytes and relocations, drops the address column, and
compares each .text function. globalasm.tsv (source<TAB>symbol) lists GLOBAL_ASM bodies,
which are excluded: they were stripped before compiling, so any object symbol in that list
would be a stub, not compiled C.
"""
import subprocess
import sys
from pathlib import Path

OBJDUMP = "mips-linux-gnu-objdump"


def functions(obj):
    r = subprocess.run([OBJDUMP, "-dr", "-z", "-j", ".text", str(obj)], capture_output=True, text=True)
    if r.returncode:
        if "'.text' mentioned in a -j option, but not found" in r.stderr:
            return {}  # all-GLOBAL_ASM unit: nothing compiled
        raise RuntimeError(r.stderr)
    text = r.stdout
    out, name = {}, None
    for line in text.splitlines():
        if line.endswith(">:") and " <" in line:
            name = line.split(" <", 1)[1][:-2]
            out[name] = []
        elif name and line.strip() and ":" in line:
            # "  1c:\t27bdffe8 \taddiu\tsp,sp,-24" or "\t\t\t1c: R_MIPS_HI16\tsym"
            body = line.split(":", 1)[1].strip()
            out[name].append(" ".join(body.split()))
    return {k: tuple(v) for k, v in out.items()}


def main(out_dir, ref, var, globalasm=None):
    out = Path(out_dir)
    skip = set()
    if globalasm:
        skip = {tuple(l.rstrip("\n").split("\t")) for l in open(globalasm) if "\t" in l}
    n = differ = 0
    rows = []
    for a in sorted((out / ref).rglob("*.o")):
        rel = a.relative_to(out / ref)
        b = out / var / rel
        if not b.exists():
            print(f"missing in {var}: {rel}")
            continue
        src = str(rel.with_suffix(".c"))
        fa, fb = functions(a), functions(b)
        for k in fa:
            if (src, k) in skip:
                continue
            n += 1
            same = fa[k] == fb.get(k)
            differ += not same
            rows.append((src, k, "same" if same else "differ"))
    print(f"{ref} vs {var}: {n} compiled C functions, {differ} differ")
    with open(out / f"diff_{ref}_vs_{var}.tsv", "w") as fh:
        fh.write("source\tfunction\tresult\n")
        fh.writelines("\t".join(r) + "\n" for r in rows)


def mutate(src, dst):
    """Sanity check input: copy src with its first .text instruction word changed.
    Diffing src's dir against dst's must then report exactly 1 differing function."""
    hdr = subprocess.run([OBJDUMP, "-h", src], capture_output=True, text=True, check=True).stdout
    off = next(int(l.split()[5], 16) for l in hdr.splitlines() if l.split()[1:2] == [".text"])
    data = bytearray(Path(src).read_bytes())
    data[off + 3] ^= 0x08  # low byte of the first instruction
    Path(dst).write_bytes(data)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--mutate"]:
        mutate(*sys.argv[2:4])
    else:
        main(*sys.argv[1:5])
