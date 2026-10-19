# Running it yourself

Each project is rebuilt per function with its compiler swapped for the stock release and its per-file
settings reset to the project default. No ROM is needed: the project's own build is already checked
against the retail hash. Everything runs in throwaway Docker containers; the target repo's build
scripts never run on your machine.

**Requirements:** Docker (Apple Silicon works), git, python3, a few hundred MB per project. Build the
containers once with `audit/images.sh`. Compilers are downloaded at run time from their public third-party sources (files.decomp.dev, GitHub releases); none are stored in this repo.

## Reproduce a result

| Family | Projects | Command |
|---|---|---|
| GameCube MWCC (dtk) | BFBB, FFCC, Colosseum, tw2004, Wind Waker, Melee | `audit/dtk/eval.sh audit/targets/<name>.env` |
| GBA agbcc | boktai2, knidl | `audit/agbcc/eval.sh audit/targets/<name>.env` |
| GBA agbcc | Klonoa, rotk | `audit/klonoa/build_and_compile.sh`, `studies/rotk/compile.sh` |
| PS1 / N64 GCC 2.x | Bushido Blade 2, dcb_decomp, Parasite Eve, Snowboard Kids 2 | `audit/<name>/*.sh` |
| N64 IDO | Conker | `audit/conker/compile.sh` |

The two `eval.sh` runners are one command each and launch their own containers. The rest are per-project scripts that run inside a container; each script's header gives the container platform and the mounts it expects (sources read-only at `/src`, results at `/out`). `LABELS_ONLY=1`
re-scores an existing run. The dtk runner skips SN ProDG units (tw2004's 124 come from
`audit/tw2004/sweep.sh`).

Each run writes `audit/labels/<name>.csv` (one row per function: `label`, `category`, `file`, `symbol`,
`commit`, `scope`). SSX 3's file comes from the fork's PR #13 via `audit/labels.py` (not re-run) and adds
`lines` and `extracted`. `python3 audit/scorecard.py` rebuilds the results table from them.

## Add a project

- **GameCube/Wii (dtk):** copy `audit/targets/melee.env`, set the repo, commit and `VERSIONS`. The
  compilers, patch steps and unit list are read from the project's `configure.py`. Check
  `out/eval/<name>/log.txt` afterwards.
- **GBA (agbcc):** copy `audit/targets/knidl.env`, set the repo, commit, compiler fork, `CFLAGS`,
  per-file overrides and an SDK regex. Check `out/<name>/log.txt` for `FAIL` lines (files needing
  ROM-generated data).

## Checks

```bash
python3 audit/klonoa/test_compare.py   # comparator rules
python3 audit/test_scan.py             # static scanner
python3 audit/dtk/default.py selftest  # settings-default rule
```
