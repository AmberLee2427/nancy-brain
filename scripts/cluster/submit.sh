#!/bin/bash
# Submit the two-phase KB rebuild to SLURM.
#
# Phase 1: parallel array job — one node per repo, generates summary cache.
# Phase 2: single job (depends on all Phase 1 success) — builds unified FAISS index.
#
# Usage (run from the nancy-brain root):
#   cd /path/to/nancy-brain
#   bash scripts/cluster/submit.sh
#
# Optional overrides:
#   NB_SUMMARY_MODEL=Qwen/Qwen2.5-Coder-7B-Instruct bash scripts/cluster/submit.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"

# Count repos dynamically so the array spec is always correct.
REPO_COUNT=$(python3 scripts/cluster/list_repos.py config/repositories.yml | wc -l | tr -d ' ')
ARRAY_MAX=$((REPO_COUNT - 1))

echo "Nancy Brain KB rebuild — $REPO_COUNT repos (array 0–$ARRAY_MAX)"
mkdir -p logs

# Patch the array spec in the sbatch file so it matches the current repo list.
SBATCH="scripts/cluster/summarize_array.sbatch"
sed -i "s/^#SBATCH --array=.*/#SBATCH --array=0-${ARRAY_MAX}/" "$SBATCH"

echo ""
echo "▶ Submitting Phase 1 (summarize, array 0-$ARRAY_MAX)..."
P1_JOB=$(sbatch --parsable "$SBATCH")
echo "  Phase 1 job ID: $P1_JOB"

echo ""
echo "▶ Submitting Phase 2 (build index, depends on Phase 1)..."
P2_JOB=$(sbatch --parsable \
    --dependency="afterok:$P1_JOB" \
    scripts/cluster/build_index.sbatch)
echo "  Phase 2 job ID: $P2_JOB"

echo ""
echo "Monitor with:"
echo "  squeue -j $P1_JOB,$P2_JOB"
echo "  watch -n 30 squeue -u \$USER"
echo ""
echo "Phase 1 logs: logs/summarize_<task>_<jobid>.out"
echo "Phase 2 log:  logs/build_index_$P2_JOB.out"
echo ""
echo "Output: knowledge_base/embeddings/"
