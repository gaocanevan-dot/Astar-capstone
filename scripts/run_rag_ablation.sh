#!/usr/bin/env bash
# Launch the RAG-ablation runs in parallel. Requires that the baseline
# full_pipeline_predictions.json + baseline_slither + baseline_gpt_zeroshot
# already exist (otherwise the aggregator's numbers will be partial).
#
# Run paths:
#   scripts/run_single_agent.py --use-rag → single_agent_rag_static_predictions.json
#   scripts/run_full_pipeline.py          → full_pipeline_rag_predictions.json
#
# Launch both, tail their progress into separate logs. The two jobs share the
# OpenAI API pool but don't both use forge, so parallelization is safe.

set -u

cd "$(dirname "$0")/.."

# Single-agent + RAG (42 cases, no forge)
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/run_single_agent.py \
  --use-rag \
  --predictions-out data/evaluation/single_agent_rag_predictions.json \
  --summary-out data/evaluation/single_agent_rag_summary.md \
  > data/evaluation/single_agent_rag_log.txt 2>&1 &

SA_PID=$!
echo "single-agent +RAG: PID=$SA_PID"

# Full pipeline + RAG — needs a script-level flag. The run_full_pipeline.py
# doesn't expose --use-rag yet (analyst in pipeline always runs without RAG).
# We'll patch that at aggregation time by re-running with an env toggle.
#
# For now, launch just single-agent+RAG and rely on env PIPE_USE_RAG=1 for pipeline.
PIPE_USE_RAG=1 PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/run_full_pipeline.py \
  --predictions-out data/evaluation/full_pipeline_rag_predictions.json \
  --summary-out data/evaluation/full_pipeline_rag_summary.md \
  > data/evaluation/full_pipeline_rag_log.txt 2>&1 &

FP_PID=$!
echo "full-pipeline +RAG: PID=$FP_PID"

echo "Both launched. Tail logs:"
echo "  tail -f data/evaluation/single_agent_rag_log.txt"
echo "  tail -f data/evaluation/full_pipeline_rag_log.txt"
