---
name: hermes-dreams
description: |
  Hermes weekly Fable 5 memory curation — the "dream pass."
  Runs every Friday. Uses Opus 4.8 to analyze the past week's sessions via
  Fable 10-pass thinking, surface contradictions/stale facts, and reorganize
  skill memory. Writes curated output to ~/.hermes/memory/WEEKLY-DREAMS.md
  which Hermes reads on startup.

  Flow:
    HERMES (enumerate recent sessions) → Opus 4.8 (Fable 10-pass analysis)
    → CURATION + SKILL GRAPH + LEDGER → prune skills + write memory

  Output: ~80K chars of session data → Opus → skill graph (prune/keep/merge)
  Cost: ~1 Opus call/week ≈ cents.

  Runs on: Hermes host ( Railway). Sessions live at ~/.hermes/sessions/.
  NOT this Mac — this Mac has stale sessions only.

  Cron: Friday 9am PHT. job_id: TBD (create with cronjob tool).
  Manual:
    python3.11 ~/.hermes/scripts/dreams.py --synthesize  # run dreams
    python3.11 ~/.hermes/scripts/dreams.py --apply       # execute pruning
version: 1.0.0
metadata:
  hermes:
    tags: [memory, curation, self-healing, fable]
    category: autonomous-ai-agents
related_skills: [autonomous-ai-agents/praying, autonomous-ai-agents/hado, fable-thinking, hard-task-method]
---

## What it does

Fable 5 applies 10 verification passes to the week's session history:

1. Distrust summaries — re-derive state from primary sources
2. Define done as observable — results, not implementation steps
3. Static ≠ behavioral — runtime vs code structure gaps
4. Bisect lifecycle — find the first divergence checkpoint
5. Instrument — flag where probes would have cracked issues faster
6. Attack your own fix — guards that swallow legitimate input
7. Sibling hunt — patterns fixed in one place but not everywhere
8. Verify twice — flag single-pass-only verifications
9. Trace supply chain — written→merged→deployed→configured→invoked gaps
10. Ledger — DONE / VERIFIED / LEFT + known limitations

## Output format

```
## CURATION
- [MERGE] fact A + fact B → merged fact (≤300 chars)
- [REPLACE] stale → corrected (≤300 chars)
- [NEW] insight surfaced (≤300 chars)
- [DROP] duplicate / stale — brief reason

## SKILL GRAPH
- [PRUNE] skill/name — reason (≤300 chars)
- [KEEP] skill/name — why still relevant (≤300 chars)
- [MERGE INTO] skill A ← skill B — reason (≤300 chars)

## FABLE INSIGHTS
P1 (Distrust): ...
P2 (Done): ...
...

## WEEKLY LEDGER
### Done
...
### Verified (with observation)
...
### Left
...
### Known limitations
...
```

## Usage

```bash
# CRON / production: Friday 9am PHT
~/.hermes/hermes-agent/venv/bin/python3.11 ~/.hermes/scripts/dreams.py --synthesize

# After reviewing output, apply pruning
~/.hermes/hermes-agent/venv/bin/python3.11 ~/.hermes/scripts/dreams.py --apply

# Dry run (load sessions, no Opus call)
~/.hermes/hermes-agent/venv/bin/python3.11 ~/.hermes/scripts/dreams.py
```

## Skills ≤300 char rule

Every skill name + reason combination in SKILL GRAPH must be ≤300 chars total.
Fable 10-pass entries must be ≤300 chars each.
CURATION entries must be ≤300 chars each.

If a generated entry exceeds 300 chars, it is automatically truncated
with `…` before writing.

## Session path

Sessions live on the Hermes host at `~/.hermes/sessions/*.jsonl`.
The script reads all `.jsonl` files modified in the last 7 days.
Sessions older than 7 days are excluded (Friday pass = one week's data).

## Output files

- `~/.hermes/cache/dreams/dreams-output.json` — raw Opus output + parsed sections (cache)
- `~/.hermes/memory/WEEKLY-DREAMS.md` — curated memory Hermes reads on startup
- `~/.hermes/cache/dreams/skills-index.json` — snapshot of skills at dream time

## Pruning

Skills are NEVER deleted without explicit [PRUNE] entry in the dream output.
The `--apply` step reads [PRUNE] entries and calls `shutil.rmtree()` on skill dirs.
This is a two-step process: `--synthesize` generates, `--apply` executes.
To preview without applying: run `--apply --dry-run` (default).

## Memory output

`~/.hermes/memory/WEEKLY-DREAMS.md` is written on every `--synthesize`.
It is Hermes's canonical weekly memory — Fable insights, skill graph changes,
curation decisions, and the ledger. On startup, Hermes reads this file.
Old weekly dream files are NOT overwritten — they accumulate in memory/
with dated filenames (WEEKLY-DREAMS-YYYY-MM-DD.md).
