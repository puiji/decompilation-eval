# Evaluating AI-assisted decompilations: a stock-compiler rebuild of 16 games

*Enmanuel, October 2026. A personal side project, built with Claude Code.*

## Summary

A matching decomp has one check: the build reproduces the retail binary byte for byte. That confirms
the bytes, not what produced them: recovered C on the original compiler, or C plus a patched compiler,
per-file compiler settings, particular file splits or inline asm. I was curious how matches break down,
so I rebuilt every matched function of 16 public projects two more ways:

- on the **released vendor compiler**, keeping each file's own settings;
- with each file's compiler version and codegen flags **reset to the project default**.

A function that comes out the same both ways is a **stock match**. Each project's CI already ties its
build to the retail hash, so no ROM is needed.

Across 14 agent-assisted projects (a 15th couldn't be tested) and two human-built projects as a reference:

- **Ten of the 14 match at 99–100% on stock tools** in game code.
- **Four fall below 99%, using project-specific tooling for part of their game code:** Pokémon Colosseum 71.4% (per-file
  settings), FFCC 89–93%, BFBB 94.1% (330 functions on its own compiler patch), Parasite Eve 98.0%.
- **The human-built projects use no per-file codegen overrides.** Melee uses a small community compiler
  patch for 27% of its game code, so community-shared patches get their own tier and count as stock.
- **Reading the source can't pick these functions out**; neither a static scanner nor an LLM classifier
  could. The rebuild is what finds them.

None of this judges any project. These are large, careful efforts, and their being public is what made
this possible. Original games were sometimes built with per-file settings too, so a non-stock match may
well be exactly the original C.

## Method

- **Differential rebuild, per function.** Disassembly is compared with addresses and local labels
  normalized. Each comparator is checked by flipping one bit of one instruction (exactly one function
  must differ), and functions in files without overrides must not change under the default rebuild
  (0 changed in every project).
- **Project default.** For dtk projects (the standard GameCube decomp toolkit), the most common settings among units the project marks Matching, in the same library and progress category; otherwise the build's base flags.
- **Three compiler tiers:** released; community-shared patch (e.g. GC/1.2.5n, GC/2.0p1, counted as
  stock and shown separately); project-specific patch ("compiler-dependent").
- **Same conventions everywhere.** Data-layout flags (`-sdata`, `-G`) are kept and changes they cause
  are reported as layout-only. `#pragma` and `-fp_contract` are kept, so settings dependence is a lower
  bound. Hand-written asm and files needing ROM-generated headers are excluded. Game and SDK code are
  reported separately.
- **Sample chosen by rule:** public matching decomps with C compiled from source, a retail-hash-checked
  build and a compiler obtainable without the ROM. Agent-assisted means signs of agent use (appendix);
  the human-built projects are measured at a commit before 2025.

## Results (game code)

"Stock match rate" counts layout-only and community-patch functions as stock.

| Project | Platform | Built | Functions | Project-patch | Settings | Community patch | Stock match |
|---|---|---|---|---|---|---|---|
| Pokémon Colosseum | GameCube | agent | 6,252 | 0 | 1,785 | 0 | 71.4% |
| Final Fantasy Crystal Chronicles (JP) | GameCube | agent | 1,039 | 76 | 34 | 108 | 89.4% |
| Final Fantasy Crystal Chronicles (PAL) | GameCube | agent | 1,298 | 0 | 94 | 0 | 92.8% |
| SpongeBob: Battle for Bikini Bottom ("duplotron") | GameCube | agent | 5,596 | 330 | 0 | 483 | 94.1% |
| Parasite Eve | PS1 | agent⁵ | 2,740 | 0 | 55 | 0 | 98.0%¹ |
| SSX 3 | PS2 | agent | 13,484 | 72 | 0 (+38 asm)² | 0 | 99.2% |
| Tiger Woods PGA Tour 2004 | GameCube | agent | 6,510 | 0 | 11 | 0 | 99.8% |
| Snowboard Kids 2 | N64 | agent | 2,503 | 0 | 2 | 0 | 99.9% |
| Conker's Bad Fur Day | N64 | agent | 3,267 | 0 | 1 | 0 | 100% |
| Kirby: Nightmare in Dream Land | GBA | agent | 5,214 | 0 | 0 | 0 | 100% |
| Boktai 2 | GBA | agent | 3,342 | 0 | 0 | 0 | 100% |
| Klonoa: Empire of Dreams | GBA | agent | 261 | 0 | 0 | 0 | 100%³ |
| The Lord of the Rings: Return of the King | GBA | agent | 321 | 0 | 0 | 0 | 100% |
| Bushido Blade 2 | PS1 | agent | 956 | 0 | 0 | 0 | 100% |
| Digimon Digital Card Battle | PS1 | agent⁵ | 1,372 | 0 | 0 | 0 | 100%⁴ |
| Need for Speed: High Stakes | PS1 | agent | not testable: compilers aren't public | | | | |
| Super Smash Bros. Melee | GameCube | human | 5,471 | 0 | 0 | 1,470 | 100% |
| The Legend of Zelda: The Wind Waker | GameCube | human | 6,487 | 0 | 0 | 0 | 100% |

1. 67.2% if the data-layout flag `-G8` (52 files, 843 functions) counted.
2. From a stock-tools cleanup in the [candidtheartist/ssx3](https://github.com/candidtheartist/ssx3/pull/13)
   fork (PR #13): 72 patch-dependent and 27 inline-asm functions moved back to assembly, 11 never-compiled
   wrapped functions removed. Used as labels, not re-run.
3. An April snapshot had 2 SDK functions needing the project's agbcc fork; the project has since dropped
   the need, and its author [wrote](https://gambiconf.substack.com/p/starting-a-decompilation-project) the
   fork "was not necessary at all."
4. Patched compilers are used only for PsyQ SDK objects, which the project's progress excludes (there:
   96 of 502 compiler-dependent, 88 settings-dependent).
5. Indirect evidence of agent use (see appendix).

**What stands out.**
- **Most projects need nothing beyond the standard toolchain.** Several forked or patched compilers
  (rotk, Klonoa, Bushido Blade, knidl) turn out to be output-neutral.
- **Project-specific compiler patches come from two sources:** BFBB's chain (later extended by FFCC) and
  SSX 3's SN patch (since removed in the fork). No released compiler that accepts BFBB's source
  reproduces 319 of its 330 patch-dependent functions, and none of the 19 bundled versions reproduces
  FFCC's 76.
- **Colosseum's and FFCC's non-stock share is mostly per-file settings.** Colosseum has overrides on 662
  of 1,460 Matching game units, and documents this openly in `docs/RULE_EXCEPTIONS.md` ("byte matching is
  the goal for now", with a clean-up pass planned).
- **Community patches are a shared baseline:** Melee uses GC/1.2.5n more than any agent-assisted project
  uses a community patch.

## Can you spot these functions by reading the source?

Four tests, three of them pre-registered (TypeSafe Jev is a commercial LLM yes/no classifier):

| Test | Result |
|---|---|
| Static scanner on SSX 3 | Finds 26/27 inline-asm functions, 0/72 patch-dependent ones |
| TypeSafe Jev: "does this function need a non-standard build?" (679 vs 2,289) | AUROC 0.63, below function length (0.69); 0.56 length-matched |
| Jev: "does this commit change how code is compiled?" (1,199 commits) | Pre-registered: 0.75 vs 0.91 for a tuned diff regex; after a label fix, about equal per project (0.84–0.92); nothing the regex misses |
| Jev: "was this asm-in-C originally hand-written asm?" | 0.92 on SSX 3 (baseline 0.75); held-out test failed on mislabeled positives, 0.99 post hoc (baseline 0.97) |

Whether a function depends on its compiler or settings isn't written in its source, so no source-only
reader can see it; that's the task, not the classifiers. The one place a model helped is inline asm,
which a rebuild can't see. A by-product: evaluating a dtk project's `configure.py` before and after
each commit lists exactly the commits that changed a file's compiler or flags, beating both regex and
model.

## Limitations

- A stock match rules out compiler and settings dependence only; source written for codegen or wrong
  types that compile to the same bytes aren't measured. A non-stock match isn't evidence of wrong source.
- Hand-written asm and files needing ROM-generated headers are excluded.
- Human references exist only for GameCube.
- "Stock" for PS1 PsyQ code means the community GCC builds; Sony's compilers aren't public.

## Ideas, if this is useful to anyone

A stock rebuild adds one optional number next to the usual match rate: the share that also matches on
released compilers with default settings. It needs no ROM and could run in CI; compiler tiers
(released, community-patched, project-patched) could be declared in the build config.

## Reproduce

Docker, no ROM. Compilers are downloaded at run time from their public sources; this repo hosts none.
Details in [RUNNING.md](RUNNING.md).

```bash
audit/images.sh                               # build the containers once
audit/dtk/eval.sh   audit/targets/melee.env   # any GameCube (dtk) project
audit/agbcc/eval.sh audit/targets/knidl.env   # any GBA (agbcc) project
python3 audit/scorecard.py                    # the table above
```

Every number comes from the per-function label files in `audit/labels/`.

## Related work

- **Diverse double-compiling** ([Wheeler](https://dwheeler.com/trusting-trust/), 2005/2009): checking a
  binary against an independent trusted compiler, the same idea applied here to decomp matches.
- **Matching decompilation as a verifier-guided task**
  ([Oblokulov et al.](https://openreview.net/forum?id=VocaE6pE2J), ICML 2026 workshop) and **Echo**
  ([Bi et al., 2026](https://arxiv.org/abs/2609.18706)), agent systems that search source and compiler
  configuration; this project measures how much of a match uses such configuration.
- **Agents and automated checks** ([METR 2025](https://metr.org/blog/2025-06-05-recent-reward-hacking),
  [ImpossibleBench](https://arxiv.org/abs/2510.20270), [TRACE](https://arxiv.org/abs/2601.20103),
  [SpecBench](https://arxiv.org/abs/2605.21384)): what checks do and don't pin down in general.
- **Community tooling:** [Chris Lewis's hooks](https://blog.chrislewis.au/the-long-tail-of-llm-assisted-decompilation/),
  [momo5502's hashed verify script](https://momo5502.com/posts/2026-10-09-game-decompilation/),
  [dqix's asm allowlist](https://github.com/ZevyaDev/dqix-decomp-kit/blob/main/asm_allow.txt), and a
  matching-standards discussion in [sm64ds-decomp #821](https://github.com/tangosdev/sm64ds-decomp/issues/821).
  I found no earlier cross-project rebuild.

## Appendix: signs of agent use at the measured commit

| Project | Commit | Evidence |
|---|---|---|
| Pokémon Colosseum | `0c2a54e3` | `.claude/`, `AGENTS.md`; ~4.2k Claude co-author lines |
| Final Fantasy Crystal Chronicles | `36140ebb` | `AGENTS.md`; 9,792 Claude trailers |
| BFBB ("duplotron") | `eaf25489` | `.claude/`; 146 commits authored by Claude |
| Parasite Eve | `2f2359b1` | Indirect: `.gitignore` lists `.claude/`; commit messages mention agent drafts |
| SSX 3 (fork) | `dff0e775` | `.claude/`; 571 Claude trailers |
| Tiger Woods PGA Tour 2004 | `e24cabec` | `CLAUDE.md`; 1,619 commits authored by Claude |
| Snowboard Kids 2 | `7600c79d` | `CLAUDE.md`, `AGENTS.md`, `.claude/hooks/`; 4,732 trailers |
| Conker's Bad Fur Day | `6251af62` | `AGENTS.md`; 175 trailers |
| Kirby: Nightmare in Dream Land | `628f4d46` | `AGENTS.md`; 145 trailers |
| Boktai 2 | `f107ada7` | `CLAUDE.md`, `.claude/` |
| Klonoa: Empire of Dreams | `45e66dd` | `CLAUDE.md`; 284 trailers |
| The Lord of the Rings: Return of the King | `15ef9c3` | `CLAUDE.md`, `AGENTS.md`, `.claude/` |
| Bushido Blade 2 | `3e7fcbe8` | `CLAUDE.md`, `AGENTS.md`, `.claude/`; 3,345 trailers |
| Digimon Digital Card Battle | `6c9caf12` | Indirect: a Claude Code scratchpad path in a source comment |
| Need for Speed: High Stakes | `04558fbb` | `AGENTS.md`; 1,595 trailers |
