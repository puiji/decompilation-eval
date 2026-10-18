"""Compare compiler output per function across variants from build_and_compile.sh.

    python compare.py <out_dir> [reference_variant]
    python compare.py <out_dir> --labels <project> <commit> [sdk_regex] > labels/<project>.csv

--labels needs the agbcc/run.sh variants (project, stock, stock_default): a function is
compiler_dependent if stock differs, settings_dependent if only stock_default does.

Normalizes each .s: drops comments, debug directives and debug sections, and renumbers
local .L labels per function, so only real code differences remain.
"""
import csv
import re
import sys
from pathlib import Path

DEBUG_DIRECTIVE = re.compile(r"^\s*\.(stab[sdn]?|loc|file|ident)\b")
SECTION = re.compile(r"^\s*\.(text|data|rdata|bss|section\s+([.\w]+))")  # .rdata: MIPS gcc rodata
FUNC_LABEL = re.compile(r"^([A-Za-z_]\w*):")
LOCAL = re.compile(r"(?:\.L|\$L)\w+")  # ARM gas .L12, MIPS gcc2 $L12
# GCC 2.x labels that aren't functions: the per-file marker, and -g line labels inside bodies.
PSEUDO = re.compile(r"__gnu_compiled_\w+|LM\d+")
HEX = re.compile(r"(?<![\w.$])-?0x[0-9a-fA-F]+")


def functions(path):
    """{name: tuple(normalized lines)} for code in text sections."""
    out, name, body, in_text = {}, None, [], True
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.split("@", 1)[0].rstrip()  # '@' starts a comment in ARM gas
        if not line.strip() or line.lstrip().startswith("#") or DEBUG_DIRECTIVE.match(line):
            continue
        m = SECTION.match(line)
        if m:
            in_text = m.group(1) == "text" or (m.group(2) or "").startswith(".text")
            continue
        if not in_text:
            continue
        f = FUNC_LABEL.match(line)
        if f and PSEUDO.fullmatch(f.group(1)):
            continue
        if f:
            if name:
                out[name] = body
            name, body = f.group(1), []
            continue
        if name:
            body.append(line.strip())
    if name:
        out[name] = body
    return {n: canon(b) for n, b in out.items()}


def canon(body):
    names = {}
    def sub(m):
        return names.setdefault(m.group(0), f"L{len(names)}")
    # -g adds labels nothing branches to, plus .size bookkeeping; keep only labels code uses.
    body = [l for l in body if not l.startswith(".size")]
    used = {t for l in body if not l.endswith(":") for t in LOCAL.findall(l)}
    body = [l for l in body if not (l.endswith(":") and LOCAL.fullmatch(l[:-1]) and l[:-1] not in used)]
    # Same bytes, different spelling: forks differ on hex vs decimal immediates (#0x18 vs #24).
    return tuple(HEX.sub(lambda m: str(int(m.group(0), 16)), LOCAL.sub(sub, l)) for l in body)


def load(variant_dir):
    funcs = {}
    for s in sorted(variant_dir.glob("*.s")):
        for n, b in functions(s).items():
            funcs[f"{s.stem}:{n}"] = b
    return funcs


def main(out_dir, ref="stock_base"):
    out = Path(out_dir)
    variants = {d.name: load(d) for d in sorted(out.iterdir()) if d.is_dir()}
    base = variants[ref]
    print(f"reference: {ref} ({sum(not is_asm(b) for b in base.values())} compiled C functions, "
          f"{sum(map(is_asm, base.values()))} asm includes skipped)")
    for v, funcs in variants.items():
        if v == ref:
            continue
        common = {k for k in base.keys() & funcs.keys() if not is_asm(base[k])}
        diff = sorted(k for k in common if base[k] != funcs[k])
        only = sorted(base.keys() ^ funcs.keys())
        print(f"  {v:11} same {len(common) - len(diff):5}  differ {len(diff):4}  missing {len(only)}")
        for k in diff[:25]:
            print(f"      {k}  ({len(base[k])} vs {len(funcs[k])} lines)")
        if len(diff) > 25:
            print(f"      ... {len(diff) - 25} more")


def is_asm(body):
    """Not-yet-decompiled function: its body *starts* by including the original asm. (A later
    .include is top-level INCLUDE_ASM that the parser attached to the C function before it.)"""
    code = [l for l in body if not l.startswith(".syntax")]
    return bool(code) and code[0].startswith((".include", ".incbin"))


def labels(out_dir, project, commit, sdk_regex=None):
    v = {n: load(Path(out_dir) / n) for n in ("project", "stock", "stock_default")}
    w = csv.writer(sys.stdout)
    w.writerow(["project", "label", "category", "file", "symbol", "commit", "scope"])
    asm = {k for k, b in v["project"].items() if is_asm(b)}
    print(f"{project}: {len(v['project']) - len(asm)} compiled C, {len(asm)} asm includes skipped", file=sys.stderr)
    for k in sorted(v["project"].keys() - asm):
        b = v["project"][k]
        cat = ("compiler_dependent" if v["stock"].get(k) != b else
               "settings_dependent" if v["stock_default"].get(k) != b else "stock_match")
        f, sym = k.split(":", 1)
        scope = "sdk" if sdk_regex and re.search(sdk_regex, f) else "game"
        w.writerow([project, "stock" if cat == "stock_match" else "assisted", cat, f, sym, commit, scope])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[2:3] == ["--labels"]:
        labels(sys.argv[1], *sys.argv[3:6])
    else:
        main(*sys.argv[1:3])
