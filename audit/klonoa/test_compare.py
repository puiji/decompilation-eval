"""Self-check for compare.py's normalization rules.  python audit/klonoa/test_compare.py"""
from compare import canon, is_asm

# Hex vs decimal immediates are the same instruction (knidl's fork prints #0x18, stock prints #24).
assert canon(["lsl\tr0, r0, #0x18"]) == canon(["lsl\tr0, r0, #24"])
assert canon(["bl\tsub_0x80"]) == ("bl\tsub_0x80",)  # hex inside a symbol name is left alone
# Not-yet-decompiled: body starts with the asm include (boktai2's INCFUNC).
assert is_asm([".syntax unified", '.include "asm/func/F.inc"', ".align 2, 0"])
# Real C that has a later top-level INCLUDE_ASM attached to it (Klonoa, BushidoBlade) stays C.
assert not is_asm(["push\t{r4, lr}", "bl\tfoo", '.include "asm/funcs/next.s"'])
# GCC 2.x pseudo-labels neither start a function nor split one (Parasite Eve -g3 files).
import tempfile, pathlib
from compare import functions
s = pathlib.Path(tempfile.mkdtemp()) / "t.s"
s.write_text("__gnu_compiled_c:\n\t.text\nf:\n\taddiu\t$sp,$sp,-8\nLM2:\n\tjr\t$31\n")
assert list(functions(s)) == ["f"] and len(functions(s)["f"]) == 2
print("ok")
