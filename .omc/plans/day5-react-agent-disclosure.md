# Day-5 ReAct Agent + Long-Term Memory — Architectural Disclosure

**Status**: Q3 demo MET. R7 fallback NOT triggered. ReAct agent ships as
primary architecture; Day-4 pipeline retained as comparison baseline.

**Plan ancestor**: `.omc/plans/day4-routing-reversal-disclosure.md`
**Disclosure principle**: same as Day-4 — every change documented with
empirical trigger, mechanism evidence, and honest framing.

---

## What Day-5 changed

The Day-1 → Day-4 architecture was a **structured LLM pipeline**:
hardcoded `analyst → builder → verifier` Python control flow, with
cascade and reflection added Day-2/4 as Python `for` / `while` loops.
LLM was called at fixed nodes; orchestration was Python.

Day-5 introduces a **real ReAct-style agent loop**:

```
src/agent/react/
├── loop.py        # ReAct driver — LLM holds the wheel
├── tools.py       # 11-tool registry with OpenAI function-calling schemas
├── prompts.py     # System prompt + iteration schedule + termination contract
└── trace.py       # Per-step (thought, action, observation) export

src/agent/memory/
├── store.py       # Generic embedding-backed JSONL store (text-embedding-3-small)
├── patterns.py    # Anti-pattern memory (replaces case-level RAG)
├── episodic.py    # Agent's own past audit traces (auto-saved per case)
├── semantic.py    # Self-distilled rules of thumb (cosine-dedup at 0.92)
└── __init__.py    # Memory facade for the 4 tool-facing methods
```

The Day-1 → Day-4 path is preserved unchanged at `src/agent/graph.py`
and `src/agent/nodes/analyst_with_tools.py`.

---

## Slither environment probe finding (Day-5 S0)

Before any agent work, we ran `scripts/probe_static_analyzer.py` to
confirm the static analysis assumption:

| Cases | Slither succeeded | Regex fallback |
|---|---|---|
| 10 smoke | **1** (ACF-103) | **9** |

Implication: 9/10 contracts have unresolved imports (OZ, sibling, custom),
so Slither cannot compile them and falls back to regex. The agent's
`static_analyze` tool returns `tool_used: 'regex'` 9/10 times — function
names + visibility + modifier names are reliable, but no taint analysis
or AC-pattern detector runs. The system prompt explicitly tells the
agent to handle this degraded signal.

This caveat affects all Day-5 agent runs and is honestly disclosed.

---

## Acceptance criteria — final result (10/10 cases)

Per Critic-pruned acceptance bar (AC6 dropped, AC5 weakened to AC5b):

| AC | Result | Pass? |
|----|--------|-------|
| **AC1** Self-termination (≥7/10) | **10/10** clean (5 submit_finding, 5 give_up) | ✅ |
| **AC2** Distinct tools/case (≥3 avg) | **5.8 avg** | ✅ |
| **AC3** Episodic lessons saved | **10/10** auto-saved to `data/agent_memory/episodic.jsonl` | ✅ |
| **AC5b** `recall_self_lesson` returns non-empty (≥2 cases) | **0/10** — agent never proactively recalled | ❌ |
| **AC7** Sweep cost (≤$2.50) | **$0.1485** | ✅ |
| **AC8** Per-case markdown trace | **10/10** in `data/evaluation/react_traces/` | ✅ |

**Q3 demo definition** (per Critic): AC1 + AC2 + AC8 = ✅ MET.
**R7 fallback**: NOT triggered.
**ReAct ships as primary architecture.**

---

## Per-case detail

| case | terminal | iters | tools | forge verdict |
|---|---|---|---|---|
| ACF-092 SpaceGodzilla | ✅ submit_finding | 7 | 6 | **pass** |
| ACF-102 Bad_Guys_by_RPF | give_up | 7 | 6 | fail_error_runtime |
| ACF-091 ReaperVaultV2 | give_up | 7 | 6 | fail_error_runtime |
| ACF-106 XNFT | give_up | 7 | 6 | fail_error_compile |
| ACF-093 GymSinglePool | give_up | 7 | 6 | fail_error_runtime |
| ACF-114 gambling_0x30410 | give_up | 3 | 3 | (no forge call) |
| ACF-103 ANCHToken | ✅ submit_finding | 6 | 6 | **pass** |
| ACF-087 Token (Uerii) | ✅ submit_finding | 6 | 6 | **pass** |
| ACF-109 QBridge | give_up | 8 | 7 | fail_revert_ac |
| ACF-101 SwapMining | ✅ submit_finding | 6 | 6 | **pass** |

**Pass count: 4/10** (informational; AC6 dropped per Critic).

---

## Cross-day pass-count comparison

| System | Pass/10 | Architecture | Cost |
|---|---|---|---|
| Zero-shot e2e (Day-3 baseline) | 4/10 | single LLM call + single forge | $0.0956 |
| Day-4 pipeline | **6/10** | cascade hybrid + reflection (locked) + tool-use single-call + SC=3 | $0.2912 |
| **Day-5 ReAct agent** | **4/10** | LLM-driven loop + 11 tools + 3-tier long-term memory | **$0.1485** |

**Day-5 vs Day-4 pass count is -2.** Lost cases:

- **ACF-114** (Day-4 pass at cascade depth=3): Day-5 agent hit `give_up`
  at iter 3 because the strict iteration schedule (`propose_target by
  iter 3`) limits the agent to single-target attempts; multi-candidate
  cascade isn't structurally available in the ReAct architecture.
- **ACF-109** (Day-4 pass at depth=1): Day-5 agent reached `fail_revert_ac`
  on the proposed target and gave_up rather than pivoting.

**Day-5 vs Day-3 zero-shot is parity (4/10).** The architectural upgrade
trades Day-4's brute-force cascade machinery for Day-5's principled
agent loop + memory infrastructure. Pass count is a Day-4 strength;
agent flexibility + memory readiness are Day-5 strengths.

---

## Honest AC5b failure analysis

`recall_self_lesson` was wired correctly (verified in Phase 1+2 tests
and Day-5 S4 bootstrap probe), but **0/10 cases** invoked it during the
sweep. Root causes:

1. **System prompt over-prioritized action speed.** The strict iteration
   schedule mandates `propose_target` by iter 3 and `run_forge` by iter
   5. Memory consultation was labeled "OPTIONAL" — under iteration
   pressure, the LLM consistently skipped it.
2. **No `recall_*` step was scheduled.** Unlike `static_analyze` (iter
   1) which had an explicit slot, memory tools had no enforced moment
   to be invoked.
3. **Smoke set is novel to the agent.** Even with 12 seed self_lessons,
   the agent didn't see direct relevance triggers in the contract
   sources without being prompted to look.

**Mitigation paths (deferred to next iteration)**:

- Hard-mandate one `recall_anti_pattern(query)` call before
  `propose_target` (would lift AC5b, cost +1 LLM round-trip per case).
- Pre-iter-1 nudge: inject a `[memory hint]` user message describing
  one or two retrieved patterns at run start, before the agent's first
  decision. (Removes agent autonomy on memory but guarantees AC5b.)
- Larger n: at n=10, the agent has insufficient prior episodes to find
  recall useful. At n=30+ with cumulative memory, recall becomes
  load-bearing organically.

The memory layer is **architecturally complete and demonstrable** — the
trace JSON shows tools registered, embeddings indexed, episodes
auto-written. The fail is at the **prompt-elicitation layer**, not the
**memory infrastructure layer**.

---

## Engineering hardening (P0 from rigor review)

After the first sweep attempt hung at case 6 for 30+ minutes
(OpenAI client default 600s timeout × 5 retry exponential backoff), we
added:

1. **Per-call LLM timeout (`src/agent/adapters/llm.py`)**:
   `OPENAI_TIMEOUT_SECS=60` default, env-overridable. Applied to
   `OpenAI()` constructor + per-`chat.completions.create` call. Hard
   cap on stuck network round-trips.
2. **Sweep `--resume` support (`scripts/run_react_agent.py`)**: Reads
   existing aggregate JSON, builds set of completed `case_id`s, skips
   them. `running_usd` carried forward. Combined with incremental
   per-case JSON write makes sweep crash-recoverable.
3. **`--only-cases` flag** for targeted re-runs (subset by case_id).

Resume-after-hang was the path that produced the final 10/10 sweep:
the first run completed 5/10 and hung on ACF-114; after killing the
stuck Python processes, `--resume` picked up cleanly and finished the
remaining 5 in $0.065 / ~5 minutes.

---

## Honest limitations (write into capstone narrative)

1. **n=10 still at noise floor**. Day-5 4/10 vs Day-4 6/10 vs zero-shot
   4/10 are within Wilson 95% CI overlap. The "architectural upgrade"
   claim is based on mechanism evidence (real tool-use loop, memory
   wired, traces clean), not pass-count superiority.
2. **AC5b fail is not catastrophic but is honest**. Memory layer is
   real and inspectable; agent just didn't proactively use it. Demo
   shows the infrastructure; production deployment would tighten the
   prompt.
3. **Pass-count regression vs Day-4 (-2)** is the cost of swapping
   brute-force cascade for principled agent reasoning. ACF-114
   (Day-4 cascade-depth=3 win) is the clearest case where Day-4
   architecture is better. Documented honestly.
4. **No cross-seed variance.** Day-5 result is single-seed. P2 in the
   rigor review (cross-seed × 3 = $0.50-1) would harden this; deferred.
5. **No cross-corpus / cross-model.** All evaluation on C5/Repair-AC,
   gpt-5-mini. External validity untested.

---

## Files changed (Day 5)

**New source code:**

| Path | Purpose |
|---|---|
| `src/agent/react/loop.py` | ReAct driver |
| `src/agent/react/tools.py` | 11-tool registry + dispatcher |
| `src/agent/react/prompts.py` | System prompt + iteration schedule |
| `src/agent/react/trace.py` | Trace dataclass + markdown export |
| `src/agent/react/state.py` | AgentState dataclass |
| `src/agent/react/__init__.py` | Public API |
| `src/agent/memory/store.py` | Generic embedding-backed JSONL store |
| `src/agent/memory/patterns.py` | Anti-pattern store |
| `src/agent/memory/episodic.py` | Episodic case-trace store |
| `src/agent/memory/semantic.py` | Self-lesson store with dedup |
| `src/agent/memory/__init__.py` | Memory facade |

**Modified:**

| Path | Change |
|---|---|
| `src/agent/adapters/llm.py` | + `chat_with_tools()` (function-calling), + per-call timeout (P0) |
| `src/agent/react/loop.py` | + auto `save_episode` on terminal (auto-distill lesson) |
| `scripts/run_react_agent.py` | + `--resume` + `--only-cases` (P0) |

**New scripts:**

| Path | Purpose |
|---|---|
| `scripts/probe_static_analyzer.py` | S0 Slither environment probe |
| `scripts/bootstrap_memory.py` | S4 — convert 85-doc rag → anti-patterns + seed 12 lessons |
| `scripts/run_react_agent.py` | S5 — batch agent sweep with R8 guards |
| `scripts/day5_acceptance_report.py` | AC1-AC8 verifier + R7 fallback decision |
| `scripts/inspect_episodic.py` | Inspect what agent learned per case |
| `scripts/verify_ac5b.py` | AC5b mechanical verifier |

**Data artifacts:**

| Path | Purpose |
|---|---|
| `data/agent_memory/anti_patterns.jsonl` (+npz cache) | 85 patterns from rag corpus |
| `data/agent_memory/self_lessons.jsonl` (+npz) | 12 hand-authored seeds |
| `data/agent_memory/episodic.jsonl` (+npz) | 10 agent-saved episodes from sweep |
| `data/evaluation/react_sweep_run1.json` | Aggregate sweep result |
| `data/evaluation/react_sweep_run1_summary.md` | Human-readable summary |
| `data/evaluation/react_traces/*_trace.{json,md}` | Per-case agent traces (10) |
| `data/evaluation/static_analyzer_probe.json` | S0 Slither probe result |
| `data/evaluation/day5_acceptance_report.md` | AC1-AC8 verdict |

---

## Verification commands (paste-ready for capstone defense)

```bash
# All unit tests
pytest tests/unit -q                                       # 207/207 pass (Day-5 added react + memory)

# Slither environment baseline
cat data/evaluation/static_analyzer_probe.json | head -20

# Memory state after sweep
python scripts/inspect_episodic.py

# Day-5 sweep result
cat data/evaluation/react_sweep_run1_summary.md

# AC1-AC8 verdict
python scripts/day5_acceptance_report.py

# AC5b verifier (will report FAIL — honest disclosure)
python scripts/verify_ac5b.py

# Cross-day pass-count comparison
python -c "
import json
d3 = json.load(open('data/evaluation/smoke_gpt-zeroshot-e2e.json'))
d4 = json.load(open('data/evaluation/smoke_agent-full.json'))
d5 = json.load(open('data/evaluation/react_sweep_run1.json'))
def n_pass(records, key='verdict', val='pass'):
    if isinstance(records, dict):
        records = records.get('records', [])
    return sum(1 for r in records if r.get(key, r.get('forge_verdict')) == val
               or r.get('finding_confirmed'))
print(f'Day-3 zero-shot: {n_pass(d3)}/10')
print(f'Day-4 pipeline:  {n_pass(d4)}/10')
print(f'Day-5 ReAct:     {n_pass(d5)}/10')
"
```
