#!/bin/bash
# Phase 1 — one task per repo: clone + generate summaries.
# Targets l40s GPUs (48GB VRAM, 1 SU/hr) — good fit for 7B summary model.
#
# Submit via submit.sh or manually:
#   sbatch --array=0-37 scripts/cluster/psc/summarize_array.sbatch

#SBATCH --job-name=nb-summarize
#SBATCH --account=cis240096p
#SBATCH --partition=GPU-shared
#SBATCH --array=0-37              # submit.sh updates this automatically
#SBATCH --time=04:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gpus=l40s:1             # l40s: 48GB VRAM, 1 SU/hr
#SBATCH --mem=32G
#SBATCH --output=logs/summarize_%a_%j.out
#SBATCH --error=logs/summarize_%a_%j.err

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"
mkdir -p logs

# ── Environment ──────────────────────────────────────────────────────────────
ENV_PREFIX="/ocean/projects/cis240096p/mvyas2/envs/nancy-brain"
module load anaconda3
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV_PREFIX"

export NB_SUMMARY_MODEL="${NB_SUMMARY_MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
export NB_USE_LOCAL_SUMMARY="true"
export NB_MIN_SUMMARY_CHARS="${NB_MIN_SUMMARY_CHARS:-100}"
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
nancy-brain build \
    --repo "$REPO" \
    --summaries-only \
    --summaries \
    --dirty

echo "=== Done: $REPO ==="
date
