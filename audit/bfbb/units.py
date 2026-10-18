"""Run inside a copy of the bfbb repo: print one JSON line per source unit.

configure.py only lists compile steps after dtk splits the retail DOL, which we
don't have, so this imports its config with generate_build swapped for a dump.
Flags are assembled the way tools/project.py's c_build does.
"""
import json
import runpy
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.argv = ["configure.py"]
import tools.project as project


def dump(config):
    for lib in config.libs:
        for o in lib["objects"]:
            obj = o.resolve(config, lib)
            opt = obj.options
            src = Path(opt["src_dir"]) / opt["source"]
            if not src.suffix in (".c", ".cpp") or not src.exists():  # "host" only adds a clang build; keep it
                continue
            flags = list(opt["cflags"] or []) + list(opt["extra_cflags"])
            if not any(f.startswith("-lang") for f in flags):
                flags.insert(0, "-lang=c++" if src.suffix == ".cpp" else "-lang=c")
            print(json.dumps({"lib": lib["lib"], "src": str(src), "matching": bool(obj.completed),
                              "mw_version": opt["mw_version"], "name": obj.name, "sjis": bool(opt.get("shift_jis")),
                              "flags": flags}))


project.generate_build = dump
runpy.run_path("configure.py", run_name="__main__")
