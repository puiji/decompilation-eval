"""Set each library's default settings to what most of its Matching units use (stdin units.jsonl -> stdout).

    python default.py < units.jsonl > units_default.jsonl
    python default.py selftest

dtk configs declare library defaults (lib_mw_version, lib_flags) that can be nominal: Colosseum puts all
1,867 units in one library declared GC/1.2.5n, while 1,105 of its 1,460 Matching game units use GC/1.3 and
the 171 on 1.2.5n hold only data. Resetting to the declared default would measure "rebuild the game on a
compiler it never used". So the settings test resets each unit to its library's most common (compiler
version, codegen flags) among Matching units of the same progress category, ties going to the declared default. The declared values are
kept as decl_lib_mw_version / decl_lib_flags. Units are counted, not functions (Limitation: a library whose
few big units disagree with many small ones is defaulted by the small ones; weight by function count if
that ever matters). A one-unit library defaults to its own settings, so its settings dependence is 0.
"""
import json
import re
import sys
from collections import Counter

CODEGEN = re.compile(r"-(O|opt |schedule |inline |use_lmw_stmw )")  # as ffcc/sweep.py


def settings(version, flags):
    return version, tuple(f for f in flags if CODEGEN.match(f))


def group(u):
    """Library and progress category: Colosseum puts game and SDK units in one library."""
    return u["lib"], u.get("category")


def modal_defaults(units):
    by_lib = {}
    for u in units:
        if u["matching"] and u["mw_version"].startswith("GC/"):
            by_lib.setdefault(group(u), Counter())[settings(u["mw_version"], u["flags"])] += 1
    out = {}
    for u in units:
        c = by_lib.get(group(u))
        if c is None or group(u) in out:
            continue
        declared = settings(u["lib_mw_version"], u["lib_flags"])
        top = max(c.values())
        out[group(u)] = declared if c.get(declared) == top else c.most_common(1)[0][0]
    return out


def apply(units):
    defaults = modal_defaults(units)
    for u in units:
        if group(u) in defaults and defaults[group(u)] != settings(u["lib_mw_version"], u["lib_flags"]):
            version, codegen = defaults[group(u)]
            other = [f for f in u["lib_flags"] if not CODEGEN.match(f)]
            u = {**u, "decl_lib_mw_version": u["lib_mw_version"], "decl_lib_flags": u["lib_flags"],
                 "lib_mw_version": version, "lib_flags": other + list(codegen)}
        yield u


def selftest():
    mk = lambda src, v, fl, m=True: {"src": src, "lib": "game", "matching": m, "mw_version": v, "flags": ["-lang=c", *fl],
                                     "lib_mw_version": "GC/1.2.5n", "lib_flags": ["-lang=c", "-O4,p"]}
    units = [mk("a.c", "GC/1.3", ["-O4,p"]), mk("b.c", "GC/1.3", ["-O4,p"]), mk("c.c", "GC/1.3", ["-O4,s"]),
             mk("d.c", "GC/1.2.5n", ["-O4,p"]), mk("e.c", "GC/1.2.5n", ["-O4,p"], m=False)]
    out = list(apply(units))
    assert out[0]["lib_mw_version"] == "GC/1.3" and out[0]["lib_flags"] == ["-lang=c", "-O4,p"], out[0]
    assert out[0]["decl_lib_mw_version"] == "GC/1.2.5n"
    tie = [mk("a.c", "GC/1.3", ["-O4,p"]), mk("d.c", "GC/1.2.5n", ["-O4,p"])]
    assert list(apply(tie))[0]["lib_mw_version"] == "GC/1.2.5n"  # tie -> declared
    sdk = [mk("a.c", "GC/1.3", ["-O4,p"]), mk("b.c", "GC/1.3", ["-O4,p"]), {**mk("s.c", "GC/1.2.5n", ["-O4,p"]), "category": "sdk"}]
    assert list(apply(sdk))[2]["lib_mw_version"] == "GC/1.2.5n"  # SDK units keep their own category's default
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:2] == ["selftest"]:
        selftest()
    else:
        units = [json.loads(line) for line in sys.stdin if line.strip()]
        sys.stdout.writelines(json.dumps(u) + "\n" for u in apply(units))
