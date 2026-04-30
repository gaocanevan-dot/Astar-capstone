#!/usr/bin/env bash
# Run the full ablation sequence. Sequential to avoid OpenAI rate limits
# and forge lockfile contention.
set -eu
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
PY=venv/Scripts/python.exe
LOGDIR=data/evaluation
mkdir -p "$LOGDIR"

stamp() { date '+%H:%M:%S'; }

echo "[$(stamp)] === 1/8 baseline: slither ==="
$PY scripts/run_baseline.py --method slither > "$LOGDIR/baseline_slither_log.txt" 2>&1 || echo "  slither failed (non-fatal)"

echo "[$(stamp)] === 2/8 baseline: gpt-zero-shot ==="
$PY scripts/run_baseline.py --method gpt_zeroshot > "$LOGDIR/baseline_gpt_zeroshot_log.txt" 2>&1

echo "[$(stamp)] === 3/8 single-agent: plain ==="
$PY scripts/run_single_agent.py > "$LOGDIR/single_agent_run_full.log" 2>&1

echo "[$(stamp)] === 4/8 single-agent: +RAG-curated ==="
$PY scripts/run_single_agent.py --use-rag \
  --rag-dataset data/dataset/rag_training_dataset.json \
  --predictions-out "$LOGDIR/single_agent_ragcur_predictions.json" \
  --summary-out "$LOGDIR/single_agent_ragcur_summary.md" \
  > "$LOGDIR/single_agent_ragcur_log.txt" 2>&1

echo "[$(stamp)] === 5/8 single-agent: topk+static ==="
$PY scripts/run_single_agent.py --use-static \
  --predictions-out "$LOGDIR/single_agent_topk_static_predictions.json" \
  --summary-out "$LOGDIR/single_agent_topk_static_summary.md" \
  > "$LOGDIR/single_agent_topk_static_log.txt" 2>&1

echo "[$(stamp)] === 6/8 full-pipeline: plain ==="
$PY scripts/run_full_pipeline.py > "$LOGDIR/full_pipeline_42_log.txt" 2>&1

echo "[$(stamp)] === 7/8 full-pipeline: +RAG-self-hits ==="
PIPE_USE_RAG=1 $PY scripts/run_full_pipeline.py \
  --predictions-out "$LOGDIR/full_pipeline_rag_predictions.json" \
  --summary-out "$LOGDIR/full_pipeline_rag_summary.md" \
  > "$LOGDIR/full_pipeline_rag_log.txt" 2>&1

echo "[$(stamp)] === 8/8 full-pipeline: +RAG-curated ==="
$PY scripts/run_full_pipeline.py --use-rag \
  --rag-dataset data/dataset/rag_training_dataset.json \
  --predictions-out "$LOGDIR/full_pipeline_ragcur_predictions.json" \
  --summary-out "$LOGDIR/full_pipeline_ragcur_summary.md" \
  > "$LOGDIR/full_pipeline_ragcur_log.txt" 2>&1

echo "[$(stamp)] === aggregate ==="
$PY scripts/aggregate_runs.py > "$LOGDIR/aggregate_log.txt" 2>&1

echo "[$(stamp)] === DONE ==="
