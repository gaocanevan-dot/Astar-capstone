#!/usr/bin/env python3
"""Day-5 S4 — bootstrap the long-term memory stores.

Converts the curated 85-doc rag corpus
(`data/dataset/rag_training_dataset.json`) into pattern-level
`anti_patterns.jsonl`, seeds 12 hand-authored `self_lessons.jsonl` based on
Day-3/4 empirical observations, and triggers the embedding index build for
both stores.

One-time cost (text-embedding-3-small over ≈100 docs): ~$0.001.

Re-running is idempotent: existing JSONL is overwritten, embedding cache is
re-built from scratch (sidesteps stale-cache concerns).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from agent.memory import Memory  # noqa: E402


# ---------------------------------------------------------------------------
# Hand-authored seed lessons (Day-3/4 empirically grounded)
# ---------------------------------------------------------------------------

SEED_LESSONS = [
    {
        "trigger": "Custom ERC20 with hand-rolled _transfer or transferFrom variants (e.g. transferFromm)",
        "takeaway": "Often the variant is public + missing modifier. Attacker calls _transfer directly to bypass allowance/balance checks.",
    },
    {
        "trigger": "Public setOwner / setAdmin / setManager without onlyOwner modifier",
        "takeaway": "vm.prank(attacker); target.setOwner(attacker); — direct ownership takeover. Usually the easiest demonstrable bug.",
    },
    {
        "trigger": "initialize() function without initializer guard or onlyOwner",
        "takeaway": "Front-runnable: call initialize() before legit deploy script. Sets attacker as owner.",
    },
    {
        "trigger": "External/public function that writes state and has no modifier list",
        "takeaway": "Direct invocation by attacker via vm.prank. Always test first with no preconditions.",
    },
    {
        "trigger": "Hand-rolled gambling / yield farm / dapp contracts (vs OpenZeppelin-based)",
        "takeaway": "Frequently have multiple AC-deficient functions. If top-1 candidate fails, advance to top-2/3 — same contract often has another bug.",
    },
    {
        "trigger": "Contract has @openzeppelin/ or solady/ imports in source",
        "takeaway": "Forge compile against original likely fails with unresolved-import. Either set verifier_mode=replica_only or vendor the OZ snapshot.",
    },
    {
        "trigger": "static_analyze returned tool_used='regex'",
        "takeaway": "No Slither taint analysis available. Rely on suspicious_summary's external+state-changing+no-modifier filter; trust function names and visibility.",
    },
    {
        "trigger": "run_forge returned fail_error_compile with 'unresolved import' or 'undeclared identifier'",
        "takeaway": "Builder wrote a PoC importing the original which has dependencies. Retry write_poc requesting a self-contained replica that inlines only the vulnerable function.",
    },
    {
        "trigger": "run_forge returned fail_revert_ac for the top-1 candidate",
        "takeaway": "That function HAS access control. Don't retry it — call propose_target for a different candidate from the suspicious_summary list.",
    },
    {
        "trigger": "run_forge returned fail_error_runtime twice on same target",
        "takeaway": "PoC's exploit logic is wrong, not the target. Try a different candidate function rather than rewriting the PoC.",
    },
    {
        "trigger": "Function named rescueToken / sweepTokens / withdrawAll / emergencyWithdraw",
        "takeaway": "Check msg.sender vs hardcoded address — many such functions trust msg.sender == _tokenOwner without onlyOwner modifier.",
    },
    {
        "trigger": "Long contract (≥800 LOC) with many small public state-mutating functions",
        "takeaway": "Read static_analyze first; pick smallest candidate functions that mutate critical state (owner, balances, allowances) — they're the cheapest PoCs.",
    },
]


def _convert_rag_doc_to_pattern(doc: dict, idx: int) -> dict:
    """Map a rag_training_dataset.json document into a pattern record."""
    meta = doc.get("metadata", {}) or {}
    fn = meta.get("function", "") or meta.get("functions", "")
    desc = meta.get("description", "") or doc.get("content", "")
    missing = meta.get("missing_check", "")
    code = meta.get("code_snippet", "")

    name_parts = []
    if missing:
        name_parts.append(f"Missing {missing}")
    if fn:
        name_parts.append(f"on {fn}")
    name = " ".join(name_parts) or (desc[:80] if desc else f"Pattern {idx}")

    indicators: list[str] = []
    if missing:
        indicators.append(f"missing {missing}")
    if fn:
        indicators.append(f"function name pattern: {fn}")
    if "external" in code.lower() or "public" in code.lower():
        indicators.append("externally callable")

    embedding_text_parts = [name, desc]
    if missing:
        embedding_text_parts.append(f"missing check: {missing}")
    if fn:
        embedding_text_parts.append(f"function: {fn}")
    if code:
        embedding_text_parts.append(code[:300])
    embedding_text = "\n".join(p for p in embedding_text_parts if p)

    return {
        "id": doc.get("id") or f"P{idx:04d}",
        "name": name[:200],
        "description": desc[:500],
        "indicators": indicators,
        "exploit_template": code[:500],
        "source_dataset": "rag_training_dataset",
        "embedding_text": embedding_text,
    }


def _wipe(jsonl_path: Path) -> None:
    """Truncate the JSONL + remove any embedding cache."""
    if jsonl_path.exists():
        jsonl_path.unlink()
    cache = jsonl_path.with_suffix(".embcache.npz")
    if cache.exists():
        cache.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--rag-source",
        default=str(REPO_ROOT / "data" / "dataset" / "rag_training_dataset.json"),
    )
    ap.add_argument(
        "--memory-root",
        default=str(REPO_ROOT / "data" / "agent_memory"),
    )
    ap.add_argument(
        "--verify",
        action="store_true",
        help="After bootstrap, run a sample query to confirm index works.",
    )
    ap.add_argument(
        "--no-embedding-build",
        action="store_true",
        help="Skip building the embedding cache (defers cost; first query will build).",
    )
    args = ap.parse_args()

    rag_path = Path(args.rag_source)
    if not rag_path.exists():
        print(f"ERROR: rag source not found: {rag_path}", file=sys.stderr)
        return 1

    mem_root = Path(args.memory_root)
    mem_root.mkdir(parents=True, exist_ok=True)

    # Idempotent: wipe + recreate
    print(f"[bootstrap] Wiping previous memory under {mem_root}...")
    _wipe(mem_root / "anti_patterns.jsonl")
    _wipe(mem_root / "self_lessons.jsonl")
    # Note: episodic.jsonl is NOT wiped — leave any prior agent runs intact

    mem = Memory(mem_root)

    # ---- Anti-patterns ----
    rag_data = json.loads(rag_path.read_text(encoding="utf-8"))
    docs = rag_data.get("documents", [])
    print(f"[bootstrap] Converting {len(docs)} rag docs → anti-patterns...")
    for i, d in enumerate(docs):
        pattern = _convert_rag_doc_to_pattern(d, i)
        mem.patterns.add_pattern(pattern)
    print(f"[bootstrap]   wrote {len(mem.patterns)} anti-patterns")

    # ---- Seed lessons ----
    print(f"[bootstrap] Seeding {len(SEED_LESSONS)} self-lessons...")
    for i, lesson in enumerate(SEED_LESSONS):
        result = mem.save_lesson(
            trigger=lesson["trigger"],
            takeaway=lesson["takeaway"],
            source_case_id=f"day5_seed_{i+1:02d}",
        )
        if not result.get("saved"):
            print(f"[bootstrap]   WARN seed {i} not saved: {result}")
    print(f"[bootstrap]   wrote {len(mem.lessons)} lessons")

    # ---- Build embedding index ----
    if not args.no_embedding_build:
        print("[bootstrap] Building embedding index (text-embedding-3-small)...")
        mem.patterns.index.index()
        mem.lessons.index.index()
        print(f"[bootstrap]   patterns cache → {(mem_root / 'anti_patterns.embcache.npz').name}")
        print(f"[bootstrap]   lessons cache  → {(mem_root / 'self_lessons.embcache.npz').name}")

    # ---- Verify ----
    if args.verify:
        print("\n[verify] Sanity queries:")
        sample_pat = mem.recall_anti_pattern("missing modifier on setter", top_k=3)
        print(f"  recall_anti_pattern('missing modifier on setter') → {len(sample_pat)} hits")
        for p in sample_pat:
            print(f"    [{p['score']:.3f}] {p['name'][:80]}")
        sample_les = mem.recall_self_lesson("forge compile fail unresolved import", top_k=3)
        print(f"  recall_self_lesson('forge compile fail unresolved import') → {len(sample_les)} hits")
        for l in sample_les:
            print(f"    [{l['score']:.3f}] trigger: {l['trigger'][:80]}")

    print(f"\n[bootstrap] DONE. Stats: {mem.stats()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
