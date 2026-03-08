#!/bin/bash
# Phase 2 — build the unified FAISS index from all cached summaries.
#
# Runs after all Phase 1 array tasks complete (enforced by submit.sh dependency).
# All summaries are already cached, so this job needs no GPU.
#
# Submit via submit.sh (recommended) or manually after Phase 1 completes:
#   sbatch --dependency=afterok:<phase1_jobid> scripts/cluster/build_index.sbatch

#SBATCH --job-name=nb-index
#SBATCH --time=02:00:00
#SBATCH --mem=64G                 # txtai FAISS index load is memory-hungry
#SBATCH --cpus-per-task=8
#SBATCH --output=logs/build_index_%j.out
#SBATCH --error=logs/build_index_%j.err

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"
mkdir -p logs

# ── Environment ──────────────────────────────────────────────────────────────
eval "$(conda shell.bash hook)"
conda activate roman-slack-bot

# Summaries are cached; tell the builder to use them but not regenerate.
export NB_USE_LOCAL_SUMMARY="true"
export KMP_DUPLICATE_LIB_OK="TRUE"

echo "=== Phase 2: building unified index ==="
echo "Node: $(hostname)"
date

# ── Build the full index ──────────────────────────────────────────────────────
# --summaries: load cached summaries into document metadata.
# Raw repos and article PDFs should still be present (Phase 1 used --dirty).
nancy-brain build --summaries

echo "=== Index build complete ==="
date

# ── Transfer results back to the NUC ─────────────────────────────────────────
# Only the embeddings directory needs to go back — the raw KB clones stay on
# the cluster for future incremental runs.
#
# Adjust NUC_HOST and NUC_PATH to match your deployment.
NUC_HOST="${NUC_HOST:-nuc.local}"
NUC_PATH="${NUC_PATH:-/path/to/nancy-brain/knowledge_base/embeddings/}"

echo "=== Syncing embeddings to $NUC_HOST:$NUC_PATH ==="
rsync -avz --progress \
    knowledge_base/embeddings/ \
    "${NUC_HOST}:${NUC_PATH}"

echo "=== Transfer complete ==="
date

# Reminder: after transfer, restart Nancy on the NUC to reload the index.
echo ""
echo "Next step: restart Nancy on the NUC to load the new index."
echo "  ssh $NUC_HOST 'docker restart nancy'"
