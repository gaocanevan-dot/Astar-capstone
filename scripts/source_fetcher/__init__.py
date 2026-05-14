"""Source fetcher utilities — convert CSV references into local Solidity sources.

Two pipelines:
- local_copier.py: copy from Repair-Access-Control-C-main/ for the 118 c5 cases
- (future) mcp_fetcher.py: fetch from GitHub via MCP for the 37 c4 cases not in existing eval_set

Outputs:
- data/contracts/raw/<incident_id>/<file>.sol         (one folder per case)
- data/contracts/raw_local_index.json                 (manifest of what got copied)
- data/dataset/eval_set.json                          (merged dataset, post-update_eval_set.py)
"""
