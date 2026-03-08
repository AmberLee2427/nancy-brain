#!/bin/bash
# Phase 2 — build the unified FAISS index from cached summaries.
# No GPU needed; uses RM-shared.

#SBATCH --job-name=nb-index
#SBATCH --account=cis240096p
#SBATCH --partition=RM-shared
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=logs/build_index_%j.out
#SBATCH --error=logs/build_index_%j.err

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"
mkdir -p logs

ENV_PREFIX="/ocean/projects/cis240096p/mvyas2/envs/nancy-brain"
module load anaconda3
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV_PREFIX"

export NB_USE_LOCAL_SUMMARY="true"
export KMP_DUPLICATE_LIB_OK="TRUE"

echo "=== Phase 2: building unified index ==="
echo "Node: $(hostname)"
date

nancy-brain build --summaries

echo "=== Index build complete ==="
date
echo ""
echo "Embeddings are in: knowledge_base/embeddings/"
echo "Copy them back to the NUC however you prefer (scp, rsync, etc.)"
