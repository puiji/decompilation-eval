"""Run inside a copy of a dtk-template repo: print one JSON line per source unit.

    VERSION=GCCJGC python units.py

Like bfbb/units.py (configure.py only lists compile steps after dtk splits the retail DOL,
so import its config with generate_build swapped for a dump), plus the library-level
compiler and flags each unit would get without its own overrides, for the settings test.
"""
import json
import os
import runpy
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.argv = ["configure.py"] + (["--version", os.environ["VERSION"]] if os.environ.get("VERSION") else [])
import tools.project as project

try:  # FFCC also configures GBA multiboot programs (separate agbcc toolchain, out of scope)
    import tools.gba_project as gba
    gba.configure_gba = lambda *a, **k: None
except ImportError:
    pass


def lang(flags, src):
    flags = list(flags or [])
    if not any(f.startswith("-lang") for f in flags):
        flags.insert(0, "-lang=c++" if src.suffix in (".cpp", ".cp") else "-lang=c")
    return flags


def toolchain(config):
    """TOOLCHAIN=1: the project's own compiler recipe (bundle tag, wibo tag, pre-compile patch steps)."""
    rules = {r["name"]: r["command"] for r in config.custom_build_rules or []}
    steps = []
    for s in (config.custom_build_steps or {}).get("pre-compile", []):
        outs = s["outputs"] if isinstance(s["outputs"], list) else [s["outputs"]]
        ins = s.get("inputs") or []
        ins = ins if isinstance(ins, list) else [ins]
        cmd = (rules.get(s["rule"], "").replace("$python", "python3").replace("$out", " ".join(map(str, outs)))
               .replace("$in", " ".join(map(str, ins))))
        steps.append({"rule": s["rule"], "command": cmd})
    print(json.dumps({"compilers_tag": config.compilers_tag, "wibo_tag": getattr(config, "wibo_tag", None), "steps": steps}))


def dump(config):
    if os.environ.get("TOOLCHAIN"):
        return toolchain(config)
    for lib in config.libs:
        for o in lib["objects"]:
            if hasattr(o, "resolve"):
                obj = o.resolve(config, lib)
                opt = obj.options
            else:  # older dtk-template: generate_build merged library options itself
                obj, opt = o, {**lib, **{k: v for k, v in o.options.items() if v is not None or k not in lib}}
                opt.setdefault("src_dir", config.src_dir)
                opt["mw_version"] = opt.get("mw_version") or config.linker_version
            src = Path(opt["src_dir"]) / opt["source"]
            # "host": True only adds a clang build alongside MWCC in dtk-template; not a reason to skip.
            # NO_SRC: configure.py alone (jev_commits.py evaluates old revisions without their source trees).
            if src.suffix not in (".c", ".cpp", ".cp") or not (src.exists() or os.environ.get("NO_SRC")):
                continue
            print(json.dumps({
                "lib": lib["lib"], "src": str(src), "matching": bool(obj.completed),
                "category": opt.get("progress_category"), "mw_version": opt["mw_version"],
                "flags": lang(list(opt["cflags"] or []) + list(opt.get("extra_cflags") or []), src),
                "lib_mw_version": lib.get("mw_version") or config.linker_version,
                "lib_flags": lang(lib.get("cflags"), src),
            }))


project.generate_build = dump
runpy.run_path("configure.py", run_name="__main__")
