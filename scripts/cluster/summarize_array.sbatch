#!/bin/bash
# Phase 1 — one task per repo: clone + generate summaries.
#
# Summaries are written to knowledge_base/cache/summaries/ (shared filesystem).
# No embeddings index is produced by this phase; that happens in build_index.sbatch.
#
# Submit via submit.sh (which auto-computes the array range), or manually:
#   sbatch --array=0-38 scripts/cluster/summarize_array.sbatch

#SBATCH --job-name=nb-summarize
#SBATCH --array=0-38              # submit.sh updates this automatically
#SBATCH --time=04:00:00           # generous; most repos finish in <30 min
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1              # one GPU per node for the summary model
#SBATCH --output=logs/summarize_%a_%j.out
#SBATCH --error=logs/summarize_%a_%j.err

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"
mkdir -p logs

# ── Environment ──────────────────────────────────────────────────────────────
module load mamba
mamba activate nancy-brain

# Larger summary model; the 0.5B default is too small for good code summaries.
export NB_SUMMARY_MODEL="${NB_SUMMARY_MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
export NB_USE_LOCAL_SUMMARY="true"
export NB_MIN_SUMMARY_CHARS="${NB_MIN_SUMMARY_CHARS:-100}"
# Suppress OpenMP duplicate-library warnings common on cluster nodes.
export KMP_DUPLICATE_LIB_OK="TRUE"

# ── Repo selection ────────────────────────────────────────────────────────────
REPO=$(python3 scripts/cluster/list_repos.py config/repositories.yml \
       | sed -n "$((SLURM_ARRAY_TASK_ID + 1))p")

if [[ -z "$REPO" ]]; then
    echo "ERROR: no repo found for array task $SLURM_ARRAY_TASK_ID" >&2
    exit 1
fi

echo "=== Task $SLURM_ARRAY_TASK_ID: $REPO ==="
echo "Node: $(hostname), GPUs: ${CUDA_VISIBLE_DEVICES:-none}"
date

# ── Build ─────────────────────────────────────────────────────────────────────
# --summaries-only: clone/update this repo, generate summaries into the shared
# cache, then exit without writing a (useless) partial FAISS index.
# --dirty: keep the raw clone for the phase-2 index build (or remove for disk savings).
nancy-brain build \
    --repo "$REPO" \
    --summaries-only \
    --summaries \
    --dirty

echo "=== Done: $REPO ==="
date
