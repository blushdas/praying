#!/usr/bin/env python3
"""
PRAYING — Hermes self-healing loop.
Searches ~/.hermes for stale/dead/duplicate skills, writes REFLECTION.md,
synthesizes findings, then invokes bankai on the synthesis.

Usage:
    python3 ~/.hermes/scripts/praying.py           # dry run: audit only
    python3 ~/.hermes/scripts/praying.py --synthesize  # audit + synthesis
    python3 ~/.hermes/scripts/praying.py --execute   # audit + synthesis + bankai
    python3 ~/.hermes/scripts/praying.py --cron      # full loop for 4am cron
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERMES_DIR = Path.home() / ".hermes"
SKILLS_DIR = HERMES_DIR / "skills"
PRAYING_DIR = HERMES_DIR / "praying"
SCRIPT_DIR = HERMES_DIR / "scripts"
PIPELINE_SCRIPT = HERMES_DIR / "pipeline" / "scripts" / "pipeline.py"

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
REFLECTION_FNAME = f"{TODAY}-REFLECTION.md"
SYNTHESIS_FNAME = f"{TODAY}-SYNTHESIS.md"
REPORT_FNAME = f"{TODAY}-REPORT.md"


def run(cmd: list[str], timeout: int = 30) -> tuple[str, str, int]:
    """Run a command, return stdout, stderr, returncode."""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout, r.stderr, r.returncode


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Skill auditing ────────────────────────────────────────────────────────────

def list_leaf_skills():
    """Enumerate leaf skills (has SKILL.md or scripts/)."""
    if not SKILLS_DIR.exists():
        return {}
    skills = {}
    for category in sorted(SKILLS_DIR.iterdir()):
        if not category.is_dir():
            continue
        # Skip archived
        if category.name.startswith("."):
            continue
        # Category container: has DESCRIPTION.md but no SKILL.md
        # Count as category only; enumerate children
        skill_dirs = []
        for item in sorted(category.iterdir()):
            if item.is_dir():
                skill_dirs.append(item)
            elif item.name == "SKILL.md" and item.parent == category:
                # top-level skill
                skill_dirs.append(item.parent)

        # Get all skill dirs (not category DESCRIPTION-only)
        for skill_dir in skill_dirs:
            if skill_dir.is_dir():
                has_skill = (skill_dir / "SKILL.md").exists()
                has_scripts = any((skill_dir / "scripts").iterdir()) if (skill_dir / "scripts").exists() else False
                has_refs = (skill_dir / "references").exists()
                skills[str(skill_dir.relative_to(SKILLS_DIR))] = {
                    "has_skill": has_skill,
                    "has_scripts": has_scripts,
                    "has_refs": has_refs,
                }
    return skills


def find_dead_skills(skills: dict) -> list[str]:
    """Dead = no SKILL.md and no scripts/. Returns list of skill paths."""
    dead = []
    for path, meta in skills.items():
        if not meta["has_skill"] and not meta["has_scripts"]:
            dead.append(path)
    return dead


def find_orphaned_skills(skills: dict) -> list[dict]:
    """Orphaned = has SKILL.md but not referenced by any other skill."""
    all_refs = set()
    for skill_path, meta in skills.items():
        if not meta["has_skill"]:
            continue
        skill_file = SKILLS_DIR / skill_path / "SKILL.md"
        try:
            content = skill_file.read_text()
            # Find related_skills entries
            for match in re.findall(r"related_skills:\s*(.+?)(?:\n|$)", content, re.IGNORECASE):
                for ref in re.split(r"[,\n]", match):
                    ref = ref.strip().replace("[`", "").replace("`]", "").strip()
                    if ref:
                        all_refs.add(ref.lower())
        except Exception:
            pass

    orphaned = []
    for skill_path, meta in skills.items():
        if not meta["has_skill"]:
            continue
        name = skill_path.split("/")[-1].lower()
        if name not in all_refs:
            orphaned.append(skill_path)
    return orphaned


def session_skill_usage() -> dict:
    """Grep session JSONL files for skill/tool mentions."""
    session_dir = HERMES_DIR / "sessions"
    if not session_dir.exists():
        return {}
    skills = ["bankai", "hado", "paseo", "shikai", "checkit", "gemini", "praying"]
    usage = {}
    for skill in skills:
        result = subprocess.run(
            ["rg", "-l", skill, str(session_dir)],
            capture_output=True, text=True, timeout=30
        )
        count = len([l for l in result.stdout.strip().split("\n") if l])
        usage[skill] = count
    return usage


def audit_runs_failures() -> dict:
    """Read pipeline runs dir and compute failure stats."""
    runs_dir = HERMES_DIR / "pipeline" / "runs"
    if not runs_dir.exists():
        return {}
    
    BUCKET_PROJECT = {
        "42169092": "DARYLE", "42887365": "OHA",
        "45130625": "NIIC", "43897270": "EJA",
        "88888881": "DARYLE", "99999991": "FIT",
    }
    
    failures = {
        "CARD_MISSING": [], "SHIKAI_SILENT": [], "GOT_PR_NO_SENDIT": [],
        "SENDIT_NO_PUSH": [], "CONTRACT_STALL": [], "COMPLETE": [],
    }
    total = 0
    
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        sf = run_dir / "state.json"
        if not sf.exists():
            continue
        total += 1
        try:
            s = json.loads(sf.read_text())
        except Exception:
            continue
        
        state = s.get("state", "")
        pr = s.get("pr_url") or ""
        card_id = s.get("card_id")
        pipeline = s.get("pipeline_type", "")
        
        # Classify
        if state == "merged":
            failures["COMPLETE"].append(run_dir.name)
        elif not card_id and pr:
            failures["GOT_PR_NO_SENDIT"].append(run_dir.name)
        elif not pr and state in ("handoff_complete", "contract_running"):
            failures["SENDIT_NO_PUSH"].append(run_dir.name)
        elif state == "contract_running":
            failures["CONTRACT_STALL"].append(run_dir.name)
        elif not card_id and pipeline in ("shikai", "bankai") and not pr:
            failures["CARD_MISSING"].append(run_dir.name)
        elif state == "handoff_complete":
            failures["SHIKAI_SILENT"].append(run_dir.name)
        else:
            failures["COMPLETE"].append(run_dir.name)
    
    return {"total": total, "buckets": failures}


def write_reflection(skills, dead, orphaned, session_usage, run_failures) -> Path:
    """Write REFLECTION.md to PRAYING_DIR."""
    PRAYING_DIR.mkdir(parents=True, exist_ok=True)
    fpath = PRAYING_DIR / REFLECTION_FNAME
    
    lines = [
        f"# PRAYING Reflection — {TODAY}",
        "",
        f"Generated: {now_iso()}",
        "",
        "## Skills Audit",
        f"Total leaf skills: {len(skills)}",
        f"Dead (no SKILL.md, no scripts): {len(dead)}",
        f"Orphaned (not cross-referenced): {len(orphaned)}",
        "",
    ]
    if dead:
        lines.append("### Dead skills (delete):")
        for d in dead:
            lines.append(f"DELETE: {d}")
        lines.append("")
    if orphaned:
        lines.append("### Orphaned skills (review — may be legitimate):")
        for o in orphaned:
            lines.append(f"  - REVIEW: {o}/")
        lines.append("")
    
    lines += [
        "## Session Skill Usage (skill mentions in sessions)",
        *(f"  {k}: {v} sessions" for k, v in session_usage.items()),
        "",
        "## Pipeline Failure Analysis",
        f"Total runs: {run_failures.get('total', '?')}",
    ]
    buckets = run_failures.get("buckets", {})
    for bucket_name, runs in buckets.items():
        lines.append(f"  {bucket_name}: {len(runs)} runs")
    lines.append("")
    
    # Add failure rates
    total = run_failures.get("total", 0)
    if total > 0:
        complete = len(buckets.get("COMPLETE", []))
        lines.append(f"Success rate: {complete}/{total} ({100*complete/total:.0f}%)")
        lines.append("")
    
    fpath.write_text("\n".join(lines) + "\n")
    return fpath


# ── Synthesis ─────────────────────────────────────────────────────────────────

def write_synthesis(reflection_path: Path, cron: bool = False) -> tuple[Path, bool, str | None]:
    """Synthesize findings into an actionable synthesis.

    Returns (Path to SYNTHESIS.md, needs_action, action_text).
    """
    PRAYING_DIR.mkdir(parents=True, exist_ok=True)
    fpath = PRAYING_DIR / SYNTHESIS_FNAME
    
    content = reflection_path.read_text()
    
    # Parse reflection
    dead = [l.strip().replace("DELETE: ", "") for l in content.split("\n") 
            if l.strip().startswith("DELETE: ")]
    orphaned = [l.strip().replace("REVIEW: ", "") for l in content.split("\n")
                if l.strip().startswith("REVIEW: ")]
    
    # Determine if any bankai invocation is warranted
    # Conditions for YES: dead skills to delete
    needs_bankai = len(dead) > 0
    bankai_cmd = ""
    
    if dead:
        # Build synthesis text for bankai
        items = ", ".join(f"delete {d}" for d in dead[:3])
        if len(dead) > 3:
            items += f" and {len(dead)-3} more dead skills"
        synthesis = (
            f"Clean up {len(dead)} dead skill directories from hermes skills index. "
            f"Tasks: {items}. "
            f"Do NOT create new skills. Do NOT modify working skills. Just delete the dead ones."
        )
    else:
        synthesis = "No action needed. All skills are healthy. PRAYING COMPLETE — synthesize says NO"
    
    mention = "@Troy " if cron else ""
    lines = [
        "# PRAYING Synthesis — " + datetime.now().strftime("%Y-%m-%d"),
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        f"{mention}PRAYING COMPLETE — synthesize says {'YES' if needs_bankai else 'NO'}",
        "",
        "## Reflection summary",
        f"- Dead skills: {len(dead)}",
        f"- Orphaned skills: {len(orphaned)}",
        "",
    ]
    if needs_bankai:
        lines += [
            "## Bankai invocation",
            "",
            "```",
            f"pipeline start \"{synthesis}\"",
            "```",
            "",
            "Project will be auto-detected from keywords. If project not detected,",
            "fall back to daryle (bucket 88888881) as the Hermes infra repo.",
            "",
            "After `pipeline start`, immediately call `pipeline go <run_id>` to fire",
            "the full pipeline without waiting for human confirmation.",
            "",
            f"## Raw synthesis text",
            synthesis,
        ]
    
    fpath.write_text("\n".join(lines) + "\n")
    return fpath, needs_bankai, synthesis if needs_bankai else None


# ── Bankai invocation ──────────────────────────────────────────────────────────

def invoke_hado(tasks: list[str]) -> dict:
    """Delete dead skill directories — direct rm, no frontier model needed."""
    deleted = []
    failed = []
    for task in tasks:
        if not task.startswith("delete dead skill: "):
            continue
        skill_path = task[len("delete dead skill: "):]
        full_path = SKILLS_DIR / skill_path
        if not full_path.exists():
            deleted.append(f"{skill_path} (already gone)")
            continue
        try:
            import shutil
            shutil.rmtree(full_path)
            deleted.append(skill_path)
        except Exception as e:
            failed.append(f"{skill_path}: {e}")
    
    log_path = PRAYING_DIR / f"{TODAY}-HADO-TASKS.txt"
    log_path.write_text(f"Deleted:\n" + "\n".join(f"  - {d}" for d in deleted) + "\n")
    if failed:
        log_path.write_text("Failed:\n" + "\n".join(f"  - {f}" for f in failed) + "\n")
    
    return {"ok": len(failed) == 0, "deleted": deleted, "failed": failed, "log": str(log_path)}

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PRAYING — Hermes self-healing loop")
    parser.add_argument("--synthesize", action="store_true", help="Write synthesis after reflection")
    parser.add_argument("--execute", action="store_true", help="Invoke hado on synthesis")
    parser.add_argument("--cron", action="store_true", help="Full loop: synthesize + execute + report")
    args = parser.parse_args()

    PRAYING_DIR.mkdir(parents=True, exist_ok=True)

    # Phase 1: Audit
    print("PRAYING: auditing skills...")
    skills = list_leaf_skills()
    dead = find_dead_skills(skills)
    orphaned = find_orphaned_skills(skills)
    session_usage = session_skill_usage()
    run_failures = audit_runs_failures()
    
    reflection_path = write_reflection(skills, dead, orphaned, session_usage, run_failures)
    print(f"  Reflection: {reflection_path}")
    print(f"  Skills: {len(skills)} leaf, {len(dead)} dead, {len(orphaned)} orphaned")
    print(f"  Runs: {run_failures.get('total', 0)} total")
    
    if not args.synthesize and not args.execute and not args.cron:
        print("Dry run complete. Use --synthesize, --execute, or --cron.")
        return

    # Phase 2: Synthesize
    print("PRAYING: synthesizing...")
    synthesis_path, needs_action, action_text = write_synthesis(reflection_path, args.cron)
    print(f"  Synthesis: {synthesis_path}")
    print(f"  Needs action: {needs_action}")
    if not needs_action:
        print("No action needed.")
        return

    if not args.execute and not args.cron:
        return

    # Phase 3: Invoke hado for hermes self-patch
    mention = "@Troy " if args.cron else ""
    print(f"PRAYING: invoking hado on hermes self...")
    # Build task list from dead skills
    tasks = [f"delete dead skill: {d}" for d in dead]
    result = invoke_hado(tasks)
    if result.get("ok"):
        print(f"  Hado: SUCCESS")
    elif result.get("fallback"):
        print(f"  Hado: fallback — tasks logged to {result.get('log')}")
    else:
        print(f"  Hado: FAILED — {result.get('stderr', 'unknown error')[:200]}")
    
    print(f"\n{mention}PRAYING complete. Report: {PRAYING_DIR / REPORT_FNAME}")


if __name__ == "__main__":
    main()
