#!/bin/bash
# Smoke-test a wheel install plus managed OCR worker setup on the Unity GPU queue.
#
# This script is intentionally hard-coded for the current user/cluster setup.
# Submit it from the project root with:
#   sbatch smoke_wheel_ocr.sbatch

#SBATCH --job-name=nb-ocr-smoke
#SBATCH --partition=batch-gpu
#SBATCH --time=06:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --gres=gpu:1
#SBATCH --output=logs/smoke_wheel_ocr_%j.out
#SBATCH --error=logs/smoke_wheel_ocr_%j.err

set -euo pipefail

PROJECT_ROOT="$HOME/project_amber/Nancy"
ARTICLES_CONFIG="$PROJECT_ROOT/config/articles.yml"
WHEEL_PATH="$HOME/project_amber/nancy_brain-0.2.1-py3-none-any.whl"
ENV_PREFIX="$HOME/envs/nancy-brain-smoke"
TORCH_INDEX_URL="https://download.pytorch.org/whl/cu128"
OCR_WARM_ARTICLES="1"
RECREATE_ENV="0"

cd "$PROJECT_ROOT"
mkdir -p logs

if [[ ! -f "$WHEEL_PATH" ]]; then
    echo "Wheel not found: $WHEEL_PATH"
    exit 2
fi

module load mamba
eval "$(mamba shell hook --shell bash)"

if [[ "$RECREATE_ENV" == "1" && -d "$ENV_PREFIX" ]]; then
    echo "Removing existing smoke env at $ENV_PREFIX"
    rm -rf "$ENV_PREFIX"
fi

if [[ -d "$ENV_PREFIX" ]]; then
    echo "Using existing smoke env at $ENV_PREFIX"
else
    echo "Creating smoke env at $ENV_PREFIX"
    mamba create --prefix "$ENV_PREFIX" python=3.12 pip -y
fi

mamba activate "$ENV_PREFIX"

export HF_HOME="${SLURM_TMPDIR:-/tmp}/hf"
export TMPDIR="${SLURM_TMPDIR:-/tmp}"
export PIP_CACHE_DIR="${SLURM_TMPDIR:-/tmp}/pip-cache"
export KMP_DUPLICATE_LIB_OK="TRUE"
mkdir -p "$HF_HOME" "$TMPDIR" "$PIP_CACHE_DIR"

echo "=== Smoke env ==="
echo "Node: $(hostname)"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-none}"
date

echo ""
echo "=== Install wheel ==="
python -m pip install --upgrade --force-reinstall "$WHEEL_PATH"
nancy-brain --version

echo ""
echo "=== Managed OCR worker setup ==="
nancy-brain ocr setup --recreate --torch-index-url "$TORCH_INDEX_URL"

echo ""
echo "=== Managed OCR worker status ==="
nancy-brain ocr status --verify

if [[ "$OCR_WARM_ARTICLES" == "1" ]]; then
    if [[ ! -f "$ARTICLES_CONFIG" ]]; then
        echo "Articles config not found: $ARTICLES_CONFIG"
    else
        echo ""
        echo "=== OCR warm ==="
        nancy-brain ocr warm --articles-config "$ARTICLES_CONFIG"
    fi
fi

echo ""
echo "Smoke test complete."
date
