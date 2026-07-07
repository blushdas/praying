# Pipeline benchmark — Jun 2026

**45 runs audited. Updated: 2026-06-24.**

## Stall breakdown

| Failure mode | Runs | % | Status |
|---|---|---|---|
| CARD_MISSING | 13 | 30% | FIXED Jun 24 — freeform merged into bankai, word-level project matching |
| Shikai→Codex baton drop | 8 | 18% | FIXED Jun 24 — handoff_path now set before transition; synthetic artifact pre-written |
| GOT_PR_NO_SENDIT | 6 | 13% | FIXED Jun 24 — freeform_start auto-cascades; shikai path also fixed |
| CONTRACT_STALL | 3 | 7% | FIXED Jun 24 — cmd_go auto-detects completed contracts |
| SENDIT_NO_PUSH | 6 | 13% | Env constraint — git/contract stall in sandbox |
| FULL SUCCESS | 9 | 20% | |

**Success rate after all Jun 24 fixes: ~80%+ expected.**

## Jun 24 structural fixes (not in run count)

These weren't in the 45-run audit but were identified and patched:

| Issue | Fix applied |
|-------|------------|
| Paseo mode drift (bypass → bypassPermissions, default → full-access) | Updated paseo.py lines 23, 25 |
| checkit validation_provider=gemma → claude (no Gemma in Paseo) | Updated projects.json guardrails |
| checkit_model not reset when routing Gemini→Claude | Reset checkit_model in _step_checkit_loop |
| SIGALRM EINTR kills blocking subprocess calls | Flag variable instead of exception raise |
| Freeform preflight fails (no card = no Basecamp auth) | Skip preflight for freeform mode |
| Freeform synthetic shikai artifact missing | rs.write_artifact("03-codex-message.txt") before cascade |
| Freeform git branch never created | git checkout -b freeform/... before cascade |

## Still open after Jun 24

| Issue | Root cause | Status |
|-------|-----------|--------|
| SENDIT_NO_PUSH (13%) | Git push fails in sandbox — Codex commits to branch but can't push | Env constraint — needs git creds in sandbox or terminal fallback |
| EINTR cascade kill | SIGALRM fires during blocking I/O | Fixed in pipeline.py; recovery documented in praying skill |

## By project

| Project | Runs | PRs | Full success | Top failure |
|---|---|---|---|---|
| DARYLE | 14 | 5 (36%) | 1 (7%) | Shikai→Codex baton drop |
| NIIC | 7 | 2 (28%) | 1 (14%) | Shikai fires, codex never runs |
| EJA | 11 | 5 (45%) | 1 (9%) | CARD_MISSING (no card attached) |
| MOGRAPH | 2 | 0 | 1 (50%) | Abandoned mid-pipeline |

## Contract coverage

Audited runs with merged PRs: ~62% of promised items actually shipped.
- NIIC UX run: 5/8 items — 3 MED items skipped
- EJA QA6: 2/6 items — pagination done, 4 skipped
- Daryle drag-drop: full contract, all items

## Common denominator

**1. No card = instant death (30%)**
bankai triggered without card ID. shikai fires, handoff written, pipeline waits for "BANKAI" confirmation. Troy didn't know to say it.

**2. Shikai silently drops baton (18%)**
handoff_complete state reached, but Paseo agent never spawned. No error. No retry. Troy doesn't know it stalled.

**3. PR opened, sendit never fires (13%)**
Codex ran perfectly, PR opened with commits, but `sendit` never notified the channel. Pipeline moved on. Troy never got the PR link.

**4. 62% contract coverage**
Codex ships what it can against the contract, then the pipeline stops. ~1 in 3 contracted items gets silently skipped.

## Shadow behavior — both sides

### Hermes/system side
- Shikai→Codex baton drop: `handoff_complete` state written, `_dispatch_step` not spawning Paseo agent
- sendit not firing after PR: pipeline reaches `pr_opened` and waits passively
- Opus/Sonnet timeout on large repos: contract agent explores too many files before acting, hits subprocess timeout
- Preflight mode drift: invalid Paseo mode names caused preflight to hard-fail, forcing bypass
- Validation contract too ambitious: 24-item NIIC contract → codex shipped HIGH items, skipped MED items silently

### User/Troy side
- "bankai canvas bugs" — `canvas` not a project keyword → bucket not resolved → dies at CARD
- "bankai" after seeing synthesis: Troy expected "do it all and tell me when done" but pipeline was waiting for explicit BANKAI keyword
- Said "BANKAI" without card attached: shikai fires but pipeline waits for confirmation → Troy goes dark
- No card = no scope: freeform without card means shikai invents scope from a sentence
- Scope creep in NIIC card: "UX fixes from Brandon feedback" → 24-item contract → codex overwhelmed

## What was fixed Jun 24 2026

1. **Freeform merged into bankai**: `bankai <text>` now routes correctly via `_freeform_start`
2. **Word-level project matching**: slug `daryle-ai-ae` splits → `["daryle","ai","ae"]` → `daryle` matches
3. **PRAYING loop built**: 4am cron, skill audit, hado for dead skills, Discord report
4. **Hermes synthesis → bankai chain**: Hermes can now `pipeline start` + `pipeline go` without Troy re-confirming
5. **Paseo mode drift**: bypass → bypassPermissions, default → full-access (was causing bypass cascades)
6. **checkit provider/model defaults**: claude-sonnet-4-6, no Gemini in Paseo
7. **hando_path set before shikai transition**: _step_contract no longer reads empty string
8. **contract_running auto-recovery**: cmd_go detects completed contracts
9. **SIGALRM flag variable**: cascade no longer killed mid-blocking-call

## What still needs work

| Issue | Root cause | Priority |
|-------|-----------|----------|
| SENDIT_NO_PUSH (13%) | Git push fails in sandbox — Codex commits to branch but can't push to remote | Medium |
| Cross-ref false positives | 113 orphaned skills — bankai doesn't `related_skills:` all skills it uses | Low |
| checkit A4/A7 failures | Codex implementation gaps — multi-file guard missing, QA creds absent | Medium — not a pipeline bug |
