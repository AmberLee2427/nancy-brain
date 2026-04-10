#!/bin/bash
# Smoke-test a wheel install plus managed OCR worker setup on Bridges-2.
#
# Usage:
#   cd /ocean/projects/cis240096p/mvyas2/Nancy
#   export WHEEL_PATH=/path/to/dist/nancy_brain-0.2.1-py3-none-any.whl
#   sbatch scripts/cluster/psc/smoke_wheel_ocr.sbatch
#
# Optional env overrides:
#   ENV_PREFIX=/ocean/projects/cis240096p/mvyas2/envs/nancy-brain-smoke
#   TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128
#   OCR_WARM_ARTICLES=1
#   RECREATE_ENV=1

#SBATCH --job-name=nb-ocr-smoke
#SBATCH --account=cis240096p
#SBATCH --partition=GPU-shared
#SBATCH --time=02:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gpus=l40s:1
#SBATCH --mem=32G
#SBATCH --output=logs/smoke_wheel_ocr_%j.out
#SBATCH --error=logs/smoke_wheel_ocr_%j.err

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"
mkdir -p logs

WHEEL_PATH="${WHEEL_PATH:-}"
if [[ -z "$WHEEL_PATH" ]]; then
    mapfile -t WHEELS < <(find dist -maxdepth 1 -name 'nancy_brain-*.whl' | sort)
    if [[ ${#WHEELS[@]} -eq 0 ]]; then
        echo "No wheel found under dist/. Set WHEEL_PATH=/path/to/wheel.whl"
        exit 2
    fi
    LAST_INDEX=$((${#WHEELS[@]} - 1))
    WHEEL_PATH="${WHEELS[$LAST_INDEX]}"
fi

if [[ ! -f "$WHEEL_PATH" ]]; then
    echo "Wheel not found: $WHEEL_PATH"
    exit 2
fi

ENV_PREFIX="${ENV_PREFIX:-/ocean/projects/cis240096p/mvyas2/envs/nancy-brain-smoke}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu128}"
OCR_WARM_ARTICLES="${OCR_WARM_ARTICLES:-1}"
RECREATE_ENV="${RECREATE_ENV:-0}"

module load anaconda3
source "$(conda info --base)/etc/profile.d/conda.sh"

if [[ "$RECREATE_ENV" == "1" && -d "$ENV_PREFIX" ]]; then
    echo "Removing existing smoke env at $ENV_PREFIX"
    rm -rf "$ENV_PREFIX"
fi

if [[ -d "$ENV_PREFIX" ]]; then
    echo "Using existing smoke env at $ENV_PREFIX"
else
    echo "Creating smoke env at $ENV_PREFIX"
    conda create --prefix "$ENV_PREFIX" python=3.12 pip -y
fi

conda activate "$ENV_PREFIX"

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
    if [[ ! -f config/articles.yml ]]; then
        echo "config/articles.yml not found; skipping OCR warm."
    else
        echo ""
        echo "=== OCR warm ==="
        nancy-brain ocr warm --articles-config config/articles.yml
    fi
fi

echo ""
echo "Smoke test complete."
date
