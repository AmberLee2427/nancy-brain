#!/bin/bash
# Warm PDF article OCR + summary cache on a single GPU node.
#
# This job avoids duplicating article downloads/OCR across the per-repo array jobs.

#SBATCH --job-name=nb-articles
#SBATCH --partition=batch-gpu
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --output=logs/warm_articles_%j.out
#SBATCH --error=logs/warm_articles_%j.err

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"
mkdir -p logs

if [[ ! -f config/articles.yml ]]; then
    echo "No config/articles.yml found; nothing to warm."
    exit 0
fi

module load mamba
eval "$(mamba shell hook --shell bash)"
ENV_PREFIX="${ENV_PREFIX:-$HOME/envs/nancy-brain}"
mamba activate "$ENV_PREFIX"

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
