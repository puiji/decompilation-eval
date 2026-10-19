# Evaluating AI-assisted game decompilations

Over the past year, coding agents have made game reverse engineering much faster. Matching
decompilations, which rebuild a game's original binary byte for byte from C, used to take teams years.
Now new projects, many of them built largely by agents, report matching most of a game in weeks or
months.

A byte match proves the output is right, but not how it got there: recovered C on the original
compiler, or C plus a patched compiler or per-file compiler settings. I was curious how those matches
break down, so this personal side project rebuilds every matched function of public decomps (14
agent-assisted, 2 human-built for reference) on the released compiler with default settings, and counts
how many come out the same.

- Ten of the 14 agent-assisted projects match at 99–100% on stock tools. Four fall below 99%, using patched compilers or per-file settings for part of their code; Pokémon Colosseum has the most, with 71.4% stock matches.
- Both human-built projects (Melee, The Wind Waker) match at 100%, counting community-shared compiler patches as stock.
- You can't tell these functions apart by reading the source; neither a static scanner nor an LLM
  classifier could. The rebuild is what finds them.

**Write-up:** [WRITEUP.md](WRITEUP.md) · **Run it yourself:** [RUNNING.md](RUNNING.md) (Docker, no ROM needed) ·
**Research log:** [findings.md](findings.md)
