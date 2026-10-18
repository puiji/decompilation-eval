"""Per-function diff of objdump -dr text (.dis) between two variant dirs from run.sh.

    python compare_dis.py <out_dir> [ref=asm_project] [var=asm_default]

Addresses are dropped and branch targets kept as <symbol+offset>, so only code and
relocation differences remain. Prints counts, writes diff_<ref>_vs_<var>.tsv.
"""
import re
import sys
from pathlib import Path

ADDR = re.compile(r"^\s*[0-9a-f]+:\s*")
TARGET = re.compile(r"\b[0-9a-f]+ <([^>]+)>")
SYM = re.compile(r"^[0-9a-f]+ <(.+)>:$")


def functions(path):
    out, name = {}, None
    for line in path.read_text(errors="replace").splitlines():
        m = SYM.match(line)
        if m:
            name = m.group(1)
            out[name] = []
        elif name and line.strip() and not line.startswith("Disassembly"):
            out[name].append(TARGET.sub(r"<\1>", ADDR.sub("", line)).strip())
    return {k: tuple(v) for k, v in out.items()}


def main(out_dir, ref="asm_project", var="asm_default"):
    out = Path(out_dir)
    n, differ = 0, []
    for a in sorted((out / ref).glob("*.dis")):
        b = out / var / a.name
        fa, fb = functions(a), functions(b) if b.exists() else {}
        for k, body in fa.items():
            n += 1
            if body != fb.get(k):
                differ.append((a.stem, k))
    print(f"{ref} vs {var}: {n} functions, {len(differ)} differ")
    with open(out / f"diff_{ref}_vs_{var}.tsv", "w") as fh:
        fh.write("file\tfunction\n")
        fh.writelines(f"{f}\t{k}\n" for f, k in differ)
    return differ


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
