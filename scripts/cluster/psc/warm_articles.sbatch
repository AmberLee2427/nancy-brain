#!/bin/bash
# Warm PDF article OCR + summary cache on a single Bridges-2 GPU node.

#SBATCH --job-name=nb-articles
#SBATCH --account=cis240096p
#SBATCH --partition=GPU-shared
#SBATCH --time=04:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gpus=l40s:1
#SBATCH --mem=32G
#SBATCH --output=logs/warm_articles_%j.out
#SBATCH --error=logs/warm_articles_%j.err

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"
mkdir -p logs

if [[ ! -f config/articles.yml ]]; then
    echo "No config/articles.yml found; nothing to warm."
    exit 0
fi

ENV_PREFIX="/ocean/projects/cis240096p/mvyas2/envs/nancy-brain"
module load anaconda3
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV_PREFIX"

export NB_SUMMARY_MODEL="${NB_SUMMARY_MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
export NB_USE_LOCAL_SUMMARY="true"
export NB_MIN_SUMMARY_CHARS="${NB_MIN_SUMMARY_CHARS:-100}"
export NB_QUANTIZE="${NB_QUANTIZE:-4bit}"
export NB_STRICT_SUMMARY_WARM="true"
export KMP_DUPLICATE_LIB_OK="TRUE"

EMPTY_CONFIG="$(mktemp "${SLURM_TMPDIR:-/tmp}/nancy-empty-repos.XXXXXX.yml")"
printf "{}\n" > "$EMPTY_CONFIG"
trap 'rm -f "$EMPTY_CONFIG"' EXIT

echo "=== Warming article OCR + summary cache ==="
echo "Node: $(hostname), GPUs: ${CUDA_VISIBLE_DEVICES:-none}"
date

python - <<'PY'
from nancy_brain.pdf_ocr import get_pdf_ocr_backend_status

status = get_pdf_ocr_backend_status("deepseek")
print(f"DeepSeek OCR backend: {status.name} | available={status.available} | reason={status.reason or 'ok'}")
if not status.available:
    raise SystemExit(1)
PY

nancy-brain build \
    --config "$EMPTY_CONFIG" \
    --articles-config config/articles.yml \
    --summaries-only \
    --summaries \
    --dirty

echo "=== Article cache warm complete ==="
date
