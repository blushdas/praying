#!/usr/bin/env python3.11
"""
dreams.py — Hermes weekly memory curation via Fable 5 thinking.
Runs every Friday. Uses Opus 4.8 to:
  1. Read the past week's sessions
  2. Apply Fable 10-pass analysis (distrust summaries, define done as observable,
     static ≠ behavioral, bisect lifecycle, instrument, attack your own fix,
     sibling hunt, verify twice, trace supply chain, ledger)
  3. Surface contradictions, stale facts, duplicates
  4. Emit reorganized skill entries (≤300 chars each)
  5. Write curated memory to ~/.hermes/memory/WEEKLY-DREAMS.md
     and pruned skills to ~/.hermes/skills/ ( Hermes reads these on startup)

Usage:
  python3.11 ~/.hermes/scripts/dreams.py              # dry run (no Opus call)
  python3.11 ~/.hermes/scripts/dreams.py --synthesize # full pass + write outputs
  python3.11 ~/.hermes/scripts/dreams.py --apply      # apply dreams output to skills/memory
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ── paths ────────────────────────────────────────────────────────────────────
HERMES_DIR   = Path.home() / ".hermes"
SESSIONS_DIR = HERMES_DIR / "sessions"
SKILLS_DIR   = HERMES_DIR / "skills"
MEMORY_DIR   = HERMES_DIR / "memory"
PRAYING_DIR  = HERMES_DIR / "praying"
CACHE_DIR    = HERMES_DIR / "cache" / "dreams"

MEMORY_FILE  = MEMORY_DIR  / "WEEKLY-DREAMS.md"
SKILLS_INDEX = CACHE_DIR   / "skills-index.json"
DREAMS_OUT   = CACHE_DIR   / "dreams-output.json"

PYTHON_VENV  = "~/.hermes/hermes-agent/venv/bin/python3.11"
OPUS_MODEL   = os.environ.get("HERMES_DREAM_MODEL", "claude-fable-5")

# ── session reading ────────────────────────────────────────────────────────────

def get_recent_sessions(days: int = 7) -> list[dict]:
    """Load all session JSONL files modified in the last `days` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sessions = []
    for jsonl in sorted(SESSIONS_DIR.glob("*.jsonl")):
        mtime = datetime.fromtimestamp(jsonl.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            continue
        msgs = []
        try:
            with open(jsonl, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msgs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except (OSError, IOError):
            continue
        if msgs:
            sessions.append({"file": jsonl.name, "messages": msgs, "mtime": mtime.isoformat()})
    return sessions


def sessions_to_text(sessions: list[dict], max_chars: int = 80_000) -> str:
    """
    Render sessions as a readable transcript excerpt.
    Truncates to ~max_chars to keep the Opus prompt affordable.
    """
    lines = []
    total = 0
    for sess in sessions:
        lines.append(f"\n{'='*60}")
        lines.append(f"SESSION: {sess['file']}  ({sess['mtime']})")
        lines.append(f"{'='*60}")
        for msg in sess["messages"]:
            role = msg.get("role", "?")
            # skip tool blocks
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "tool_result":
                        parts.append(f"[tool: {part.get('name', '?')}]")
                    elif isinstance(part, dict) and part.get("type") == "text":
                        parts.append(part.get("text", ""))
                    else:
                        parts.append(str(part))
                content = "\n".join(parts)
            if not content or not isinstance(content, str):
                continue
            # truncate each message
            if len(content) > 2000:
                content = content[:2000] + "\n[...truncated...]"
            lines.append(f"[{role.upper()}]\n{content[:3000]}")
            total += len(content)
            if total > max_chars:
                lines.append(f"\n[... {len(sessions)} sessions, {total//1000}K chars — truncated ...]")
                break
        if total > max_chars:
            break
    return "\n".join(lines)


# ── Fable 10-pass prompt ─────────────────────────────────────────────────────

FABULE_PROMPT = """You are running the Fable 5 verification mindset over this week's Hermes sessions.

The 10 passes (apply implicitly throughout):

1. DISTURST SUMMARIES — re-derive state from primary sources; don't trust "done/fixed/merged" claims at face value.
2. DEFINE DONE AS OBSERVABLE — look for claims phrased as results, not implementation steps.
3. STATIC ≠ BEHAVIORAL — note where code structure was verified but runtime behavior was not tested.
4. BISECT LIFECYCLE — identify when failures first appeared; look for the divergence checkpoint.
5. INSTRUMENT — flag where a probe would have cracked the issue faster.
6. ATTACK YOUR OWN FIX — flag any guard/flag that might swallow legitimate input.
7. SIBLING HUNT — flag patterns that exist in multiple places but were only fixed in one.
8. VERIFY TWICE — flag cases where single-pass verification is insufficient.
9. TRACE SUPPLY CHAIN — flag written→merged→deployed→configured→invoked gaps.
10. LEDGER — produce three lists: DONE / VERIFIED / LEFT + known-limitations.

Your output format (STRICT — follow exactly):

## CURATION
- [MERGE] <memory entry A> + <memory entry B> → <merged fact ≤300 chars>
- [REPLACE] <stale entry> → <corrected fact ≤300 chars>
- [NEW] <insight surfaced from sessions, ≤300 chars>
- [DROP] <duplicate/stale entry — brief reason>

## SKILL GRAPH
- [PRUNE] <skill name> — <reason ≤200 chars>
- [KEEP] <skill name> — <why it's still relevant ≤200 chars>
- [MERGE INTO] <skill A> ← <skill B> — <reason ≤200 chars>

## FABLE INSIGHTS
For each of the 10 passes, note the most important finding (or "PASS N: nothing notable this week"):
- P1 (Distrust): ...
- P2 (Done): ...
- P3 (Static): ...
- P4 (Bisect): ...
- P5 (Instrument): ...
- P6 (Attack fix): ...
- P7 (Sibling): ...
- P8 (Verify twice): ...
- P9 (Supply chain): ...
- P10 (Ledger): DONE: ... / VERIFIED: ... / LEFT: ...

## WEEKLY LEDGER
### Done
...
### Verified (with the observation that proves it)
...
### Left (what wasn't fixed / what's still broken)
...
### Known limitations
...

Rules:
- Every SKILL GRAPH entry must be ≤300 chars total
- Every CURATION entry must be ≤300 chars
- If a skill has no updates, do not list it in KEEP
- Be specific: "dogfood skill invoked 3x, still live" beats "skill exists"
- Do not invent findings — only what the sessions actually show
"""


# ── Opus call ─────────────────────────────────────────────────────────────────

def call_opus(reflection_text: str, instructions: str = "") -> str | None:
    """Call Opus 4.8 via Anthropic SDK. Returns response text or None on failure."""
    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: anthropic SDK not installed in venv", file=sys.stderr)
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Try loading from .env
        env_file = HERMES_DIR / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return None

    client = Anthropic(api_key=api_key)

    prompt = f"""{instructions}

{FABULE_PROMPT}

---

## THIS WEEK'S SESSIONS
{reflection_text}

---

Output only the structured format described above. Do not preamble.""" if instructions else f"""{FABULE_PROMPT}

## THIS WEEK'S SESSIONS
{reflection_text}

---

Output only the structured format described above. Do not preamble."""

    try:
        response = client.messages.create(
            model=OPUS_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            timeout=120,
        )
        return response.content[0].text
    except Exception as e:
        print(f"ERROR: Opus call failed: {e}", file=sys.stderr)
        return None


# ── output parsing ─────────────────────────────────────────────────────────────

def parse_dreams_output(raw: str) -> dict:
    """Parse the structured Opus output into section dicts."""
    sections = {
        "curation": [],
        "skill_graph": [],
        "fable_insights": [],
        "weekly_ledger": {},
    }

    current_section = None
    current_lines = []

    for line in raw.splitlines():
        line = line.rstrip()
        if line.startswith("## "):
            if current_section and current_lines:
                sections[current_section] = "\n".join(current_lines).strip()
                current_lines = []
            section_name = line[3:].strip().lower().replace(" ", "_")
            if section_name in sections:
                current_section = section_name
            else:
                current_section = None
            continue
        if current_section is not None:
            current_lines.append(line)

    if current_section and current_lines:
        if isinstance(sections.get(current_section), list):
            sections[current_section].extend([l for l in current_lines if l.strip()])
        else:
            val = "\n".join(current_lines).strip()
            if val:
                sections[current_section] = val

    # Also handle bullet lists inside sections
    for key in ["curation", "skill_graph"]:
        if isinstance(sections[key], str):
            items = []
            for line in sections[key].splitlines():
                line = line.strip()
                if line.startswith("-") or line.startswith("*"):
                    items.append(line)
            sections[key] = items

    return sections


# ── skill enforcement (≤300 chars) ───────────────────────────────────────────

def enforce_char_limit(text: str, max_chars: int = 300) -> str:
    """Truncate to max_chars, breaking on word boundaries."""
    if len(text) <= max_chars:
        return text
    # break on last space before limit
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.7:  # only break if not too far back
        truncated = truncated[:last_space]
    return truncated + "…"


def apply_skill_pruning(prune_list: list[str], dry_run: bool = True) -> dict:
    """
    Prune skills listed in [PRUNE] entries.
    Each entry format: "- [PRUNE] <skill_name> — <reason>"
    Returns dict with 'deleted' and 'failed' lists.
    """
    deleted = []
    failed = []

    for entry in prune_list:
        # extract skill name from "- [PRUNE] skill/name — reason"
        m = re.match(r"- \[PRUNE\]\s+(.+?)\s+—", entry)
        if not m:
            continue
        skill_name = m.group(1).strip()
        skill_path = SKILLS_DIR / skill_name
        if not skill_name or skill_name in (".", ".."):
            continue
        # Resolve relative to SKILLS_DIR
        if "/" in skill_name:
            skill_path = SKILLS_DIR / Path(skill_name)
        else:
            # Try as direct subdir
            skill_path = SKILLS_DIR / skill_name

        if dry_run:
            print(f"  [DRY-RUN] Would delete: {skill_path}")
            deleted.append(str(skill_path))
        else:
            import shutil
            try:
                if skill_path.exists() and skill_path.is_dir():
                    shutil.rmtree(skill_path)
                    print(f"  Deleted: {skill_path}")
                    deleted.append(str(skill_path))
                else:
                    print(f"  Not found (skipping): {skill_path}")
                    failed.append(str(skill_path))
            except Exception as e:
                print(f"  Failed to delete {skill_path}: {e}")
                failed.append(str(skill_path))

    return {"deleted": deleted, "failed": failed}


def write_memory_output(sections: dict, week_ending: str):
    """Write the curated memory file that Hermes can read on startup."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Weekly Dreams — week ending {week_ending}",
        f"Generated: {datetime.now().isoformat()}",
        f"Model: {OPUS_MODEL}",
        "",
        "## Skill Graph",
        "",
    ]

    for entry in sections.get("skill_graph", []):
        lines.append(entry)

    lines += ["", "## Curation", ""]
    for entry in sections.get("curation", []):
        lines.append(entry)

    lines += ["", "## Fable Insights", ""]
    if isinstance(sections.get("fable_insights"), dict):
        for k, v in sections["fable_insights"].items():
            lines.append(f"- **{k}**: {v}")
    elif isinstance(sections.get("fable_insights"), list):
        for entry in sections["fable_insights"]:
            lines.append(entry)

    lines += ["", "## Weekly Ledger", ""]
    ledger = sections.get("weekly_ledger", {})
    if isinstance(ledger, str):
        lines.append(ledger)
    else:
        for k, v in ledger.items():
            lines.append(f"### {k}")
            lines.append(v)
            lines.append("")

    content = "\n".join(lines)
    MEMORY_FILE.write_text(content, encoding="utf-8")
    print(f"\nMemory output written to: {MEMORY_FILE}")
    return content


def write_dreams_cache(sections: dict, raw: str):
    """Cache the full dreams output for later application."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DREAMS_OUT.write_text(json.dumps({
        "generated": datetime.now().isoformat(),
        "sections": {k: (v if isinstance(v, list) else str(v)) for k, v in sections.items()},
        "raw": raw,
    }, indent=2), encoding="utf-8")
    print(f"Dreams cache written to: {DREAMS_OUT}")


# ── apply ─────────────────────────────────────────────────────────────────────

def apply_dreams(dry_run: bool = True):
    """Apply the cached dreams output: prune skills, write memory."""
    if not DREAMS_OUT.exists():
        print("ERROR: No dreams output found. Run --synthesize first.")
        return

    data = json.loads(DREAMS_OUT.read_text(encoding="utf-8"))
    sections = data["sections"]

    print("\n=== Applying Dreams ===")

    # Prune skills
    prune_entries = [e for e in sections.get("skill_graph", []) if "[PRUNE]" in e]
    print(f"\nPruning {len(prune_entries)} skills...")
    result = apply_skill_pruning(prune_entries, dry_run=dry_run)

    # Write memory
    week_ending = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    write_memory_output(sections, week_ending)

    print(f"\nDeleted: {result['deleted']}")
    if result['failed']:
        print(f"Failed: {result['failed']}")

    if dry_run:
        print("\n[DRY-RUN] Pass --apply to actually execute deletions.")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Hermes weekly dreams — Fable 5 memory curation")
    parser.add_argument("--synthesize", action="store_true",
                        help="Run full dreams pass: read sessions → Opus → write output")
    parser.add_argument("--apply", action="store_true",
                        help="Apply the cached dreams output (prune + write memory)")
    parser.add_argument("--days", type=int, default=7,
                        help="Number of past days of sessions to analyze (default: 7)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't actually delete skills")
    args = parser.parse_args()

    if args.apply:
        apply_dreams(dry_run=args.dry_run)
        return

    # Default: dry run of session loading
    print(f"Loading sessions from last {args.days} day(s)...")
    sessions = get_recent_sessions(days=args.days)
    print(f"Found {len(sessions)} session file(s)")

    if not sessions:
        print("No sessions found. Exiting.")
        return

    session_text = sessions_to_text(sessions)
    print(f"Session text: ~{len(session_text)//1000}K chars")

    if args.synthesize:
        print(f"\nCalling {OPUS_MODEL}...")
        raw = call_opus(session_text)
        if not raw:
            print("Opus call failed. Exiting.")
            sys.exit(1)

        print(f"\nOpus response (~{len(raw)} chars):")
        print(raw[:500])
        print("...")

        sections = parse_dreams_output(raw)
        write_dreams_cache(sections, raw)

        week_ending = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        write_memory_output(sections, week_ending)

        # Show prune list
        prune_entries = [e for e in sections.get("skill_graph", []) if "[PRUNE]" in e]
        if prune_entries:
            print(f"\n{len(prune_entries)} skills marked for pruning:")
            for e in prune_entries:
                print(f"  {e[:200]}")
        else:
            print("\nNo skills marked for pruning.")

        print(f"\nDreams output cached. Run with --apply to execute.")
    else:
        print("\nDry run complete. Pass --synthesize to run Opus and generate output.")
        print("Then --apply to execute skill pruning.")


if __name__ == "__main__":
    main()
