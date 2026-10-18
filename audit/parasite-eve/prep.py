"""Copy run.sh's cc1-layer .s dirs to <out>/norm/, dropping two GCC 2.x pseudo-labels that
klonoa/compare.py would parse as functions:
  __gnu_compiled_c:   file-start marker (one per file)
  LM<n>:              -g3 line-number labels (they split every real function into pieces)

    python prep.py <out_dir>
"""
import re
import sys
from pathlib import Path

PSEUDO = re.compile(r"^(__gnu_compiled_c|LM\d+):\s*$")


def main(out_dir):
    out = Path(out_dir)
    for v in ("project", "stock", "stock_default"):
        dst = out / "norm" / v
        dst.mkdir(parents=True, exist_ok=True)
        for s in (out / v).glob("*.s"):
            lines = s.read_text(errors="replace").splitlines(keepends=True)
            (dst / s.name).write_text("".join(l for l in lines if not PSEUDO.match(l)))


if __name__ == "__main__":
    assert PSEUDO.match("LM12:\n") and PSEUDO.match("__gnu_compiled_c:\n") and not PSEUDO.match("LMain:\n")
    main(sys.argv[1])
