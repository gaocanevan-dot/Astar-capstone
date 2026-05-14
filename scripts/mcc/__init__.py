"""MCC (Minimal Compilable Closure) pipeline.

Given a vulnerable Solidity case + its locally-sourced files (under
data/contracts/raw/<incident_id>/), produce a forge-compileable project at
data/mcc_projects/<incident_id>/ by:

  1. case_loader       — read CaseInfo from eval_set.json
  2. extract_closure   — BFS over import graph, MAX_FILES = 10
  3. dep_router        — pragma -> solc + OZ version (Day 3)
  4. materialize       — write foundry.toml + remappings + lib/ symlink (Day 3)
  5. build_probe       — run forge build, classify outcome (Day 4)

Day 2 here implements (1) and (2).
"""
