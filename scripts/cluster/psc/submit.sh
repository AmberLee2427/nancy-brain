#!/bin/bash
# Submit the two-phase KB rebuild to Bridges-2.
#
# Usage (from /ocean/projects/cis240096p/mvyas2/Nancy):
#   bash scripts/cluster/psc/submit.sh
#
# Run setup_env.sbatch first if the environment doesn't exist yet:
#   sbatch scripts/cluster/psc/setup_env.sbatch

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_ROOT"

REPO_COUNT=$(python3 scripts/cluster/list_repos.py config/repositories.yml | wc -l | tr -d ' ')
ARRAY_MAX=$((REPO_COUNT - 1))

echo "Nancy Brain KB rebuild on Bridges-2 — $REPO_COUNT repos (array 0–$ARRAY_MAX)"
mkdir -p logs

# Patch the array spec in the sbatch file.
SBATCH="scripts/cluster/psc/summarize_array.sbatch"
sed -i "s/^#SBATCH --array=.*/#SBATCH --array=0-${ARRAY_MAX}/" "$SBATCH"

echo ""
echo "▶ Submitting Phase 1 (summarize, array 0-$ARRAY_MAX)..."
P1_JOB=$(sbatch --parsable "$SBATCH")
echo "  Phase 1 job ID: $P1_JOB"

ARTICLE_JOB=""
if [[ -f config/articles.yml ]]; then
    echo ""
    echo "▶ Submitting article OCR warm job..."
    ARTICLE_JOB=$(sbatch --parsable scripts/cluster/psc/warm_articles.sbatch)
    echo "  Article warm job ID: $ARTICLE_JOB"
fi

echo ""
echo "▶ Submitting Phase 2 (build index, depends on Phase 1)..."
DEPENDENCY="afterok:$P1_JOB"
if [[ -n "$ARTICLE_JOB" ]]; then
    DEPENDENCY="${DEPENDENCY}:$ARTICLE_JOB"
fi
P2_JOB=$(sbatch --parsable \
    --dependency="$DEPENDENCY" \
    scripts/cluster/psc/build_index.sbatch)
echo "  Phase 2 job ID: $P2_JOB"

echo ""
echo "Monitor with:  squeue --me"
echo "Phase 1 logs:  logs/summarize_<task>_<jobid>.out"
if [[ -n "$ARTICLE_JOB" ]]; then
    echo "Article log:   logs/warm_articles_$ARTICLE_JOB.out"
fi
echo "Phase 2 log:   logs/build_index_$P2_JOB.out"
echo ""
echo "Output: knowledge_base/embeddings/"
