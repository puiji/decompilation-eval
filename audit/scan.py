"""Static audit of a cloned decomp repo. Needs no ROM.

Flags source constructs that can produce a byte match without matching source, plus history and
toolchain edits that can weaken the checker.

    python scan.py <repo_path> [out.csv]
"""
import csv
import re
import subprocess
import sys
from pathlib import Path

SRC_EXT = {".c", ".cpp", ".cc", ".h", ".hpp", ".inc"}
SKIP_DIRS = {"tools", ".git", "asm", "build", "extern", "third_party"}

# Counted, then removed from the text, so later patterns don't double-count them.
# asm_label is symbol aliasing (`void f() __asm__("func_X")`), not a codegen trick.
CONSUMED = {
    "asm_label": re.compile(r"\)\s*(?:__asm__|asm)\s*\(\s*\"[\w.$]+\"\s*\)"),
    "register_pin": re.compile(r"\bregister\b[^;=]*?\b(?:__)?asm(?:__)?\s*\(\s*\"[^\"]*\"\s*\)"),
    "empty_asm_barrier": re.compile(r"\b(?:__)?asm(?:__)?\s*(?:volatile\s*|__volatile__\s*)?\(\s*\"\s*\"[^;]*;"),
}
PATTERNS = {
    "inline_asm": re.compile(r"\b(?:__)?asm(?:__)?\s*(?:volatile\s*|__volatile__\s*)?[({]|\b__asm\b"),
    "naked": re.compile(r"__declspec\s*\(\s*naked\s*\)|__attribute__\s*\(\(\s*naked"),
    "emit": re.compile(r"\b_?_emit\b"),
    # From sm64ds tools/tiers.py, written after its fakematch audit (#821):
    # `& 0xFFFFFFFFFFFFFFFF` forces a u64 round-trip; a volatile OBJECT (no `*`) pins a spill.
    "mask_u64": re.compile(r"&\s*0x[fF]{16}[uUlL]*\b"),
    "volatile_object": re.compile(r"\bvolatile\b(?![\s\w:]*\*)"),
    "include_asm": re.compile(r"\b(?:INCLUDE_ASM|GLOBAL_ASM|INCLUDE_RODATA)\b"),
    "incbin": re.compile(r"\.incbin\b|\bINCBIN\w*\s*\("),
    # Limitation: 16+ hex bytes in a row is a heuristic for code pasted as data; tune per platform.
    "byte_array": re.compile(r"(?:0x[0-9A-Fa-f]{1,8}\s*,\s*){16,}"),
}
FIELDS = [*CONSUMED, *PATTERNS]
# Constructs that can produce a match from source alone (asm_label, include_asm, incbin are info).
IDIOMS = ["register_pin", "empty_asm_barrier", "inline_asm", "naked", "emit", "mask_u64",
          "volatile_object", "byte_array"]
# Files whose edits can weaken the checker itself.
VERIFIER = re.compile(r"(sha1|\.sha|checksum|verify|baseline|objdiff\.json|progress|configure\.py|Makefile|\.github/workflows)", re.I)


def scan_text(text):
    counts = {}
    for name, rx in CONSUMED.items():
        counts[name] = len(rx.findall(text))
        text = rx.sub("", text)
    asm_kw_gone = re.sub(r"\b(?:__)?asm(?:__)?\s*(?:volatile|__volatile__)", "asm", text)
    for name, rx in PATTERNS.items():
        counts[name] = len(rx.findall(asm_kw_gone if name == "volatile_object" else text))
    return counts


def scan_repo(root):
    root = Path(root)
    rows = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.suffix not in SRC_EXT or not p.is_file() or set(rel.parts[:-1]) & SKIP_DIRS:
            continue
        counts = scan_text(p.read_text(errors="replace"))
        if any(counts.values()):
            rows.append({"file": str(rel), **counts})
    return rows


def git_lines(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else []


def verifier_edits(root):
    """Commits touching checksum / checker / CI files: (hash, date, subject, file)."""
    out, commit = [], None
    for line in git_lines(root, "log", "--no-renames", "--name-only", "--format=@@%h|%as|%s"):
        if line.startswith("@@"):
            commit = line[2:].split("|", 2)
        elif line and commit and VERIFIER.search(line):
            out.append((*commit, line))
    return out


def toolchain_flags(root):
    """Submodules and compiler-patching files worth diffing against stock."""
    root = Path(root)
    hits = git_lines(root, "config", "-f", ".gitmodules", "--get-regexp", r"submodule\..*\.url")
    for p in (root / "tools").rglob("*") if (root / "tools").is_dir() else []:
        if re.search(r"patch|cc1|agbcc|mwcc|ccps|\bsn[_.-]|gcc", p.name, re.I) and p.is_file():
            hits.append(str(p.relative_to(root)))
    return hits


def main(repo, out=None):
    rows = scan_repo(repo)
    totals = {k: sum(r[k] for r in rows) for k in FIELDS}
    print(f"{repo}: {len(rows)} flagged files")
    for k, v in totals.items():
        print(f"  {k:18} {v}")
    edits = verifier_edits(repo)
    print(f"  verifier/CI commits {len(edits)}")
    for h, d, s, f in edits[:15]:
        print(f"    {h} {d} {f}  ({s[:60]})")
    tc = toolchain_flags(repo)
    print(f"  toolchain items     {len(tc)}")
    for t in tc[:15]:
        print(f"    {t}")
    if out:
        with open(out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["file", *FIELDS])
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
