"""Held-out label set for Jev v2: Bushido Blade 2 functions that were once C bodies of inline asm.

    python heldout_labels.py <bushido_full_clone> <out.jsonl>

Walks weekly snapshots of the project's history, keeps the last version of every C function
whose body contains inline asm, then labels it by its fate at HEAD:
  hand_written  listed in inline_asm_canonical.txt (the project's judgment: original was asm)
  compiled      now plain C with no asm in src/, and not canonical (it matched on the stock
                compiler, so the original was compiled C; this label is objective)
Anything else (still unresolved, renamed beyond recognition) is dropped.
Function text is the other project's code: keep the output in out/ (gitignored).
"""
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from labels import functions  # noqa: E402  (regex + brace matching, shared with the ssx3 labels)

ASM = re.compile(r"\b(?:__asm__|asm)\s*(?:volatile\s*)?\(")
ADDR = re.compile(r"(?:func|fn)_(8[0-9A-Fa-f]{7})$")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout


def address(name, syms):
    m = ADDR.search(name)
    return int(m.group(1), 16) if m else syms.get(name)


def main(repo, out_path):
    head_syms = {m.group(1): int(m.group(2), 16)
                 for m in re.finditer(r"^(\w+)\s*=\s*(0x[0-9A-Fa-f]+);", git(repo, "show", "HEAD:named_syms.txt"), re.M)}
    # Each canonical row may carry a recorded reason tag, e.g. gcc-cannot-emit:gte_psyq_macro_call
    # ("Mixed C/GTE": compiled C calling Sony's GTE macros, not hand-written asm).
    tags = {}
    for l in git(repo, "show", "HEAD:inline_asm_canonical.txt").splitlines():
        name, _, note = l.partition("#")
        if name.strip():
            m = re.search(r"([a-z-]+:[\w-]+)", note)
            tags[name.strip()] = m.group(1) if m else "untagged"
    canonical = set(tags)
    canonical_addr = {address(n, head_syms): n for n in canonical} if canonical else {}
    canonical_addr.pop(None, None)

    # Last asm-bodied version of each function, keyed by address when known.
    seen = {}
    commits = git(repo, "rev-list", "--reverse", "--since=2026-03-20", "HEAD").split()
    snapshots = commits[::max(1, len(commits) // 40)] + [commits[-1]]
    for c in snapshots:
        for path in git(repo, "grep", "-l", "-E", r"__asm__|asm volatile|asm\(", c, "--", "src/").splitlines():
            path = path.split(":", 1)[1]
            if not path.endswith(".c"):
                continue
            for name, src in functions(git(repo, "show", f"{c}:{path}")).items():
                body = src.split("{", 1)[-1]
                if ASM.search(body):
                    seen[address(name, head_syms) or name] = (name, path, c[:9], src)

    # Fate at HEAD: plain C functions (no asm) by address.
    head_c = {}
    for path in git(repo, "ls-tree", "-r", "--name-only", "HEAD", "src/").split():
        if path.endswith(".c"):
            for name, src in functions(git(repo, "show", f"HEAD:{path}")).items():
                if not ASM.search(src.split("{", 1)[-1]):
                    head_c[address(name, head_syms) or name] = name
    rows = []
    for key, (name, path, commit, src) in seen.items():
        if key in canonical_addr or name in canonical:
            label = "hand_written"
        elif key in head_c:
            label = "compiled"
        else:
            continue
        canon_name = name if name in canonical else canonical_addr.get(key)
        rows.append({"project": "bushido", "symbol": name, "label": label, "file": path, "commit": commit,
                     "canon_tag": tags.get(canon_name) if label == "hand_written" else None, "source": src})
    with open(out_path, "w") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in rows)
    print(f"{len(snapshots)} snapshots, {len(seen)} asm-bodied functions seen;", dict(Counter(r["label"] for r in rows)))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
