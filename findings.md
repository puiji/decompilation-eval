# Research log

Condensed, in date order. Full methods are in the scripts under `audit/`.

## Oct 16: SSX 3 labels and a static-scan baseline

- **Labels** from the ssx3 fork's PR #13 (`audit/labels/ssx3.csv`): 72 compiler-patch functions
  (objective, rebuilt with the stock compiler), 27 inline-asm functions (the PR author's judgment), 11
  never-compiled wrapped functions, 13,374 stock.
- **The static scanner** finds 26/27 inline-asm functions but **0/72** compiler-patch functions. Those
  look like ordinary C, so only a rebuild can find them.
- Inline asm alone doesn't mean non-stock: 700 stock functions keep asm for instructions the compiler
  can't emit (VU0, COP0).

## Oct 16: Jev on inline-asm functions

- **v1** (726 functions): worse than a one-line heuristic (AUROC 0.62 vs 0.72). Most of that came from
  the population: 657 of the stock functions were one-instruction inline helpers.
- **v2**, on linked functions only (26 vs 43), asking whether the original was hand-written asm:
  **0.92** (CI 0.84–0.98) vs 0.75 for asm share. Caveat: the criteria were written after reading about
  10 examples, so a held-out test was needed.

## Oct 16: Klonoa's agbcc fork

- Built the fork and stock pret agbcc in a container and compared every function. No ROM needed: CI
  already ties the fork's output to the retail hash.
- **Current tree: all 335 functions identical on stock**, under every flag set. The fork's
  "diagnostic only" flags are output-neutral.
- **April snapshot: 2 of 126** (both in the m4a sound SDK) needed the fork's `-ftst` patch. The project
  later replaced that code with a stock-building version, and its author called the fork "not
  necessary at all."

## Oct 16: toolchain survey, rotk, Bushido Blade 2

- **Survey:** found the patched-compiler projects (BFBB, FFCC,
  dcb_decomp's SDK-only patches) and Colosseum's per-unit compiler selection.
- **rotk's agbcc fork** (pret plus 4 commits adding tracing for LLM agents): all 321 functions identical to stock.
- **Bushido Blade 2's cc1** (GCC 2.7.2 plus one crash fix): all 1,310 functions identical to the
  community release. The fix is a single `extern` declaration. Its assembler-side options are disclosed
  and gated by the project's own rules.

## Oct 16: BFBB `duplotron` (GameCube)

- Rebuilt with the project's patched compilers (reproduced from its own SHA-1-pinned scripts) and stock
  GC/2.0p1.
- **330 functions in Matching files compile differently on stock**, all in SB game code. The first
  patch stage (p1a) alone accounts for 308. The change is mostly load/store ordering, e.g. store before
  float-literal load.
- **No released compiler reproduces 319 of the 330.** All 18 stock versions were tried: 11 match GC 2.5
  (consistent with the patch's stated 2.5 alias rules). Versions 1.0–1.2.5n reject the source, and the
  3.0 alphas mostly abort under emulation.
- Context: 329 of the 330 are in files that became Matching on this branch. The project documents the
  patch and its rationale (`tools/patch_compiler.py`, `docs/DUPLOTRON.md`).

## Oct 16: Pokémon Colosseum (GameCube)

- **Per-unit compiler versions are mostly output-neutral.** Libraries need one compiler each (THPDec on
  1.2.5n as prebuilt Nintendo code, as expected). Game code still needs at least two versions, which
  affects about 40 functions.
- **Per-unit codegen flags matter more.** 662 of 1,460 Matching game units have overrides (833 counting
  171 data-only units). Most common: `-opt nopeephole` (332 units) and `-O4,s` (238). Control: 0 of 2,633
  functions in units without overrides change.
- The project documents this in `docs/RULE_EXCEPTIONS.md`: per-unit flags are accepted while "byte
  matching is the goal for now", with recovering original flags listed as future work.
- The final number (71.4% stock) is from the Oct 18 re-run below.

## Oct 16: Jev held-out test on Bushido Blade 2 (pre-registered)

- v2's criteria were frozen and applied to a new game, platform and team: 65 functions the project
  lists as hand-written asm vs 102 compiled.
- **Pre-registered result: did not replicate** (0.70, below a 0.855 line-share baseline).
- **Cause:** 44 of the 65 positives are tagged by the project itself as compiled C calling Sony's GTE
  macros, i.e. the negative class. I hadn't read the tags before registering.
- **Post hoc**, with the project's own tags: 0.993 vs a 0.969 baseline. Jev transfers, but its edge over
  a trivial heuristic is unproven here.

## Oct 18: GBA, N64 and PS1 projects

- **boktai2 and knidl** (shared GBA runner `audit/agbcc/`): game code 100% stock. A few SDK units use
  `-O1` or the older compiler, as pret projects do. knidl's fork differs only in printing shift amounts
  in hex. The comparator now normalizes that.
- **Conker** (IDO 5.3, the stock release by SHA-256): 3,266 of 3,267 stock. The one is a `-g3` drop the
  source comment justifies from the retail delay slot. Object post-passes leave code bytes unchanged.
- **Digimon DCB:** game code 100% stock on the unmodified GCC 2.95.2 release with uniform flags. The
  patched compilers (modeling Sony's SDK compiler) are used only for PsyQ objects the project excludes
  from progress: 96 of 502 compiler-dependent there.
- **Snowboard Kids 2:** stock KMC GCC 2.7.2. 2 functions depend on the one `-O0` file. 19 files need
  ROM-generated headers and are excluded.
- **Parasite Eve:** stock old-gcc and upstream maspsx. 55 functions depend on per-file codegen flags
  (98.0%). `-G8` on 52 files changes 843 more, counted as data layout.
- **Need for Speed: High Stakes:** not testable. Its Sony PsyQ compilers aren't public.

## Oct 18: FFCC and tw2004 (GameCube)

- **FFCC:** only the JP build uses the patched compiler (BFBB's chain plus three FFCC stages). 76 JP
  game functions need it, and none of the 19 bundled compiler versions reproduces them. The same source
  matches PAL on stock GC/2.5. Settings dependence is per-unit `-inline auto,deferred`. The project's
  docs call its compilers "compatibility baselines".
- **tw2004:** stock compiler bundle, no patches. 11 game functions depend on per-unit settings (99.8%).
  ProDG units are stock by construction.

## Oct 18: human-built references (Wind Waker, Melee)

- Measured at their last commit before 2025-01-01.
- **Wind Waker:** no per-unit codegen or version overrides in game code. 100% stock.
- **Melee:** no per-unit settings anywhere, but 1,470 game functions (26.9%) need GC/1.2.5n, a small
  community patch of 1.2.5 that no released version reproduces. That's why community-shared patches get
  their own tier and count as stock.

## Oct 18: community-patch tier and scorecard

- Every unit on GC/1.2.5n or GC/2.0p1 was rebuilt on its released base. The tier is mostly SDK code. In
  game code it appears in BFBB (483), FFCC JP (108) and Melee (1,470).
- `audit/scorecard.py` builds the results table from the label CSVs alone. Every label has a `scope`
  (game/sdk).

## Oct 18: Jev vs rebuild labels (pre-registered)

- **Question:** can source-only review point a rebuild at compiler- or settings-dependent functions?
- **Setup:** BFBB, FFCC and Colosseum; 679 non-stock vs 2,289 stock functions from the same files.
- **Result: no usable signal.** 0.633 vs 0.693 for line count, and 0.557 on length-matched pairs.
  Colosseum is 0.53, and the scanner 0.50.
- **Reading:** that dependence isn't in the source text, so the rebuild is necessary.

## Oct 18: Jev commit triage (pre-registered)

- **Question:** can Jev rank the commits that changed how code is compiled? Labels come from evaluating
  `configure.py` before and after each commit.
- **Result: neither replaces nor complements a tuned diff regex.**
  - Pre-registered: 0.75 vs 0.91.
  - After a post hoc rename fix: about equal per project (0.84–0.92), and 0.42 where the regex is
    silent.
- **Better tool:** the configure.py evaluation itself. It's deterministic and catches changes no diff
  shows.
- Scanner gap found: its history rule misses compiler-patch-script commits.

## Oct 18: one-command dtk runner; all GameCube results re-run

- `audit/dtk/eval.sh` needs only repo, commit and versions. Everything else comes from the project's
  `configure.py`. Each project takes 3–5 minutes.
- **One settings-default rule for all dtk projects:** the most common settings among Matching units in
  the same library and category. Colosseum's declared GC/1.2.5n default is nominal: 1,105 of its 1,460
  game units use GC/1.3.
- **Re-run vs published labels:**
  - Wind Waker, Melee, BFBB: identical.
  - FFCC, tw2004: game code identical, a few more SDK functions settings-dependent.
  - **Colosseum: 1,785 of 6,252 game functions settings-dependent, 71.4% stock** (was 72.9%), because
    compiler versions are now reset too.
