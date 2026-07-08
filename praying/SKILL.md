---
name: praying
description: |
  PRAYING / REFLECTING — Hermes self-healing loop.
  Searches skill index and session history for dead/orphaned skills and failure patterns.
  Synthesizes findings, then routes to hado (hermes self-patch) or bankai (code fix).
  
  Cron: 4am daily. Discord: job_id=5e4305bd2643.
  Manual: `python3 ~/.hermes/scripts/praying.py --synthesize`
  Execute: `python3 ~/.hermes/scripts/praying.py --execute`
  
  Flow: HERMES (enumerate + audit) → REFLECTION.md → HADO (rm -rf dead skills)
  bankai only fires if PRAYING finds code-level issues needing GitHub PR.
version: 1.2.0
metadata:
  hermes:
    tags: [self-healing, self-audit, pipeline]
    category: autonomous-ai-agents
related_skills: [autonomous-ai-agents/bankai, autonomous-ai-agents/hado]
---

## Flow

```
HERMES (praying.py --synthesize)
  → enumerate skills: list_leaf_skills()
  → find dead skills: no SKILL.md and no scripts/
  → find orphaned skills: cross-ref check
  → session usage: grep sessions for skill/tool mentions
  → write ~/.hermes/praying/YYYY-MM-DD-REFLECTION.md

DREAM (Opus 4.8 — claude-opus-4-8)
  → reads REFLECTION.md + dead candidates + session usage
  → judges: which dead flags are truly safe to prune, which to spare (and why)
  → surfaces insights (drift/failure patterns, max 3)
  → writes the prayer (ADORATION → PETITION, grounded in Troy's creed)
  → guardrails: prune ⊆ dead candidates, max 5/run, orphans never prunable
  → any failure (no SDK, no key, bad JSON) → deterministic fallback, cron never dies

HADO (praying.py --execute)
  → reads dream-confirmed prune list (or raw dead list on fallback)
  → dead skills: rm -rf (deletion = hermes self-patch)
  → orphaned skills: review only (false positives — cross-ref too strict)

SYNTHESIS (praying.py --synthesize output)
  → @Troy PRAYING COMPLETE — synthesize says YES/NO
  → if YES: routing guidance (what to fix and how)
  → if dead > 0: "invoke hado" is the action
  → if no findings: "synthesize says NO"
  → dream section appended: spared skills + insights + prayer
```

## Dream pass (added Jul 7 2026)

The dream pass is the judgment layer between reflection and execution. Since PRAYING
runs unsupervised at 4am, Opus 4.8 reviews every prune before hado deletes anything.

- Model: `claude-opus-4-8` (override with `HERMES_DREAM_MODEL` env var)
- Requires: `anthropic` SDK in the venv + `ANTHROPIC_API_KEY` in cron env
- Skip: `--no-dream` flag (reverts to deterministic dead-list pruning)
- Cost: one streamed call per day, ~4k max output tokens
- Safety: model can only VETO or CONFIRM candidates the Python audit flagged —
  it can never add new deletion targets. Cap 5 prunes/run.

## Usage

```bash
# CRON / production: always use python3.11 from the venv (system python may be 3.9)
~/.hermes/hermes-agent/venv/bin/python3.11 ~/.hermes/scripts/praying.py --cron

# Dry run (enumerate only, no file writes)
~/.hermes/hermes-agent/venv/bin/python3.11 ~/.hermes/scripts/praying.py

# Synthesize (write REFLECTION.md + SYNTHESIS.md, no changes)
~/.hermes/hermes-agent/venv/bin/python3.11 ~/.hermes/scripts/praying.py --synthesize

# Execute: delete dead skills found in REFLECTION.md
~/.hermes/hermes-agent/venv/bin/python3.11 ~/.hermes/scripts/praying.py --execute
```

## Hermes self-search dimensions

1. **Skills audit** — SKILL.md present, cross-refs valid, no dead shells
2. **Session usage** — which skills/tools actually get invoked, which are silent
3. **Memory drift** — entries that contradict current behavior
4. **Failure patterns** — recurring error types from pipeline runs
5. **Shadow behavior** — tools/skills that fire but produce no visible output

## Pipeline benchmark (Jun 2026 — 45 runs)

Inline benchmark (45 runs, Jun 2026):

| Failure mode | Runs | % | Status |
|---|---|---|---|
| CARD_MISSING | 13 | 30% | FIXED Jun 24 |
| Shikai→Codex baton drop | 8 | 18% | FIXED Jun 24 |
| GOT_PR_NO_SENDIT | 6 | 13% | FIXED Jun 24 |
| CONTRACT_STALL | 3 | 7% | FIXED Jun 24 |
| SENDIT_NO_PUSH | 6 | 13% | Env constraint |
| FULL SUCCESS | 9 | 20% | |

**Success rate after fixes: ~80%+ expected.**

## EINTR/SIGALRM — structural issue, not fixable (Jun 25 2026)

The freeform cascade (`_freeform_start`) uses a polling loop that stays alive for 20+ minutes. macOS sends SIGTERM to background processes that run too long — this is an OS-level job control issue, not a code bug.

**Symptom:** Pipeline output shows the cascade starting correctly (contract → codex → checkit) but then `bash: [pid: 1] tcsetattr: Inappropriate ioctl for device` and the Python process exits. Paseo agents keep running.

**Python version requirement:** `praying.py` uses `type | None` union syntax (Python 3.10+). The system default `python3` may be 3.9.x. Always invoke with:
```bash
~/.hermes/hermes-agent/venv/bin/python3.11 ~/.hermes/scripts/praying.py --cron
```
Using the wrong Python causes `TypeError: unsupported operand type(s) for |` at the `def write_synthesis` line.

**grep timeout on large session dirs:** `session_skill_usage()` runs `grep -rl` across 858 session files (293MB). The 10-second default timeout is too short. Fixed Jun 29: replaced `grep -rl` with `rg -l` (ripgrep) + 30s timeout. ripgrep is at `/opt/homebrew/bin/rg`.

**Recovery when cascade was killed:**
```bash
# 1. Check state — what was the last completed step?
python3 -c "import json; s=json.load(open('~/.hermes/pipeline/runs/<run_id>/state.json')); print(s['state'])"

# 2. Check if Paseo agents are still running
paseo ls | grep freeform

# 3. If checkit never completed, patch state to last completed step and re-run
python3 -c "
import json
s = json.load(open('~/.hermes/pipeline/runs/<run_id>/state.json'))
s['state'] = 'codex_complete'  # or whatever the last completed step was
json.dump(s, open('~/.hermes/pipeline/runs/<run_id>/state.json','w'), indent=2)
"
cd ~/.hermes/pipeline && python3 scripts/pipeline.py go <run_id>  # run in FOREGROUND terminal
```

## User preference: @Troy mention on cron delivery

Troy confirmed: PRAYING output must mention him in Discord. The `--cron` flag adds `@Troy` prefix to the synthesis header and report footer. Always use `--cron` when PRAYING fires from the 4am cron job.

**Why:** Troy reads on mobile. Silent Discord delivery gets buried. `@Troy` surfaces it in notification.

## Skills audit results (Jun 24 2026)

- **131 leaf skills** after cleanup (11 dead ML-category containers deleted)
- **0 dead** (after hado cleanup)
- **113 orphaned** (false positive — cross-ref too strict, bankai uses skill names not paths)
- **Dead skill count bug**: `write_reflection` was formatting `{d}` dicts as `"DELETE: {'path': '...'}/"` instead of `"DELETE: dogfood/references"`. Parser's `startswith("DELETE: ")` never matched. Fixed: `find_dead_skills` now returns plain strings, format fixed to `"DELETE: {path}"`.

## Output files

- `~/.hermes/praying/YYYY-MM-DD-REFLECTION.md` — raw audit findings
- `~/.hermes/praying/YYYY-MM-DD-SYNTHESIS.md` — PRAYING COMPLETE decision
- `~/.hermes/praying/YYYY-MM-DD-REPORT.md` — post-bankai outcome

## Invocation from cron

```bash
~/.hermes/hermes-agent/venv/bin/python3.11 ~/.hermes/scripts/praying.py --cron
```

The `--cron` flag: synthesize, then execute if synthesis says YES, then report to origin channel.

## Bankai chaining

When synthesis says YES and a code-level fix is needed, bankai is invoked via pipeline CLI:

```bash
# Freeform auto-cascade — one command fires everything
pipeline start "fix the drag-drop in daryle — add .limit() to queries"
# Output: shows run_id, state, and auto-fires contract → codex → checkit → sendit
```

No `pipeline go` call needed — `_freeform_start` now auto-cascades after transitioning to `handoff_complete`. The pipeline Python exits after ~4min (contract written) but Paseo agents keep running. Monitor with:
```bash
paseo ls | grep freeform
python3 -c "import json; print(json.load(open('~/.hermes/pipeline/runs/<run_id>/state.json'))['state'])"
```

Project resolution uses word-level matching on repo slugs — "daryle" matches daryle-ai-ae → bucket 88888881. If no project keyword detected → synthesis is printed for manual review.

## Prayer Layer (Jun 25 2026 — added)

At 4am, before the technical synthesis, PRAYING includes a prayer grounded in Troy's personal creed (Pentecostal/Evangelical mainstream):

**Creed foundation (saved Jun 25 2026):**
- God: Trinity — Father, Son, Holy Spirit
- Salvation: by grace through faith alone in Christ alone
- Scripture: inspired, infallible, supreme authority
- Spirit: indwells, empowers, gifts the Church
- Mission: make disciples of all nations
- Eschatology: Christ returns personally to judge and reign
- Church: one body, local congregations for worship and mission
- Marriage/Sexuality: covenantal union of one man and one woman
- Christian life: holiness, love, obedience, prayer, Scripture, community

**Prayer structure (follow this order):**
1. **ADORATION** — Praise God for who He is (Trinity, creator, sovereign)
2. **THANKSGIVING** — Give thanks for specific blessings (salvation, grace, Christ's return, Spirit's presence)
3. **CONFESSION** — Confess areas of sin, failure, neglect from the past 24h
4. **INTERCESSION** — Pray for the Church, mission, specific people God has laid on your heart
5. **PETITION** — Bring your own needs — wisdom for work, relationships, growth

**What PRAYING prays for (specific items to include):**
- The Church worldwide — revival, faithfulness, unity
- Your family — salvation, protection, spiritual growth
- Today's work — that it would honor God and serve others
- Any specific prayer requests shared in recent sessions
- The nations — that the gospel would go forth

**Format:**
```
╔══════════════════════════════╗
║       PRAYING — 4am         ║
║      June 26, 2026 PHT       ║
╚══════════════════════════════╝

╔══════════════════════════════╗
║   TECHNICAL SELF-AUDIT       ║
╚══════════════════════════════╝
[skill audit, pipeline review, etc.]

╔══════════════════════════════╗
║         PRAYER               ║
╚══════════════════════════════╝

ADORATION
...
THANKSGIVING
...
CONFESSION
...
INTERCESSION
...
PETITION
...
```

## Constraints

- Hermes (this script) never writes to skills/, scripts/, or memory/
- Only HADO (rm -rf for deletions) or manual review for orphaned skills
- Technical self-audit first, then prayer — both delivered to Discord and Telegram with @Troy mention.
