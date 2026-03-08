#!/bin/bash
# Phase 2 — build the unified FAISS index from all cached summaries.
#
# Runs after all Phase 1 array tasks complete (enforced by submit.sh dependency).
# All summaries are already cached, so this job needs no GPU.
#
# Submit via submit.sh (recommended) or manually after Phase 1 completes:
#   sbatch --dependency=afterok:<phase1_jobid> scripts/cluster/build_index.sbatch

#SBATCH --job-name=nb-index
#SBATCH --partition=batch          # index build needs no GPU
#SBATCH --time=02:00:00
#SBATCH --mem=64G                 # txtai FAISS index load is memory-hungry
#SBATCH --cpus-per-task=8
#SBATCH --output=logs/build_index_%j.out
#SBATCH --error=logs/build_index_%j.err

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"
mkdir -p logs

# ── Environment ──────────────────────────────────────────────────────────────
module load mamba
source activate ~/envs/nancy-brain

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
echo ""
echo "Embeddings are in: knowledge_base/embeddings/"
echo "Copy them back to the NUC however you prefer (rsync, scp, shared fs, etc.)"
