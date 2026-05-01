#!/usr/bin/env python3
"""Day-5 — inspect what the agent learned during a sweep.

Reads `data/agent_memory/episodic.jsonl` and prints a per-episode summary:
case_id, terminal_reason, forge_verdict, target_function, lesson, tool_seq.

Use after `run_react_agent.py` finishes to see what got recorded into the
agent's long-term memory. Useful for capstone defense: "look, the agent
wrote these N lessons across 10 cases, here's what it learned."
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    REPO_ROOT = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--memory-root",
        default=str(REPO_ROOT / "data" / "agent_memory"),
    )
    ap.add_argument(
        "--show-tool-sequence",
        action="store_true",
        help="Also print full tool_sequence per episode.",
    )
    args = ap.parse_args()

    root = Path(args.memory_root)
    ep_path = root / "episodic.jsonl"
    lessons_path = root / "self_lessons.jsonl"

    print(f"=== Episodic memory: {ep_path} ===\n")
    if not ep_path.exists():
        print("(file does not exist — agent has not run yet, or memory not wired)")
    else:
        for i, line in enumerate(ep_path.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                ep = json.loads(line)
            except json.JSONDecodeError:
                continue
            print(f"--- Episode {i} ({ep.get('case_id', '?')}) ---")
            print(f"  contract:        {ep.get('contract_name', '?')}")
            print(f"  terminal_reason: {ep.get('terminal_reason', '?')}")
            print(f"  forge_verdict:   {ep.get('forge_verdict') or '-'}")
            print(f"  target_function: {ep.get('target_function') or '-'}")
            print(f"  lesson:          {ep.get('final_lesson', '')[:200]}")
            if args.show_tool_sequence:
                seq = ep.get("tool_sequence", [])
                print(f"  tool_sequence:   {seq}")
            print()

    print(f"\n=== Self-lessons: {lessons_path} ===\n")
    if not lessons_path.exists():
        print("(file does not exist)")
        return 0

    lessons = []
    for line in lessons_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            lessons.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    seed = [l for l in lessons if any("day5_seed" in s for s in (l.get("source_case_ids") or []))]
    learned = [l for l in lessons if l not in seed]
    print(f"Total lessons: {len(lessons)} (seed: {len(seed)}, agent-distilled: {len(learned)})")
    print()
    if learned:
        print("Agent-distilled lessons:")
        for l in learned:
            print(f"  • freq={l.get('freq', 1)}  trigger: {l.get('trigger', '')[:80]}")
            print(f"                takeaway: {l.get('takeaway', '')[:120]}")
    else:
        print("(no agent-distilled lessons yet — only seeds)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
