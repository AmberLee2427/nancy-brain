#!/bin/bash
# One-time environment setup.
# Package installs must NOT run on the login node — this script requests an
# interactive compute node via srun and does all work there.
#
# Usage (from the login node):
#   cd /path/to/nancy-brain   # wherever you extracted the tarball
#   chmod +x scripts/cluster/*.sh
#   bash scripts/cluster/setup_env.sh
#
# The env is created under ~/envs/nancy-brain (writable by you).
# Override with: ENV_PREFIX=/path/to/env bash scripts/cluster/setup_env.sh
#
# Override CUDA tag if needed (check https://download.pytorch.org/whl/ for available tags):
#   CUDA_TAG=cu128 bash scripts/cluster/setup_env.sh

set -euo pipefail

# Put the env somewhere you own -- NOT inside the system mamba prefix.
ENV_PREFIX="${ENV_PREFIX:-$HOME/envs/nancy-brain}"
PYTHON_VERSION="3.12"
CUDA_TAG="${CUDA_TAG:-cu129}"  # cluster has CUDA 12.9; cu129 wheel exists
NANCY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Step 1: create the env (login node is fine -- just downloads pkgs)
module load mamba
eval "$(mamba shell hook --shell bash)"
if [[ -d "$ENV_PREFIX" ]]; then
    echo "Environment already exists at $ENV_PREFIX, skipping create."
else
    echo "Creating conda environment at $ENV_PREFIX with Python $PYTHON_VERSION..."
    mamba create --prefix "$ENV_PREFIX" python="$PYTHON_VERSION" -y
fi

# ── Step 2: install packages inside an interactive compute node
echo ""
echo "Requesting compute node for package install (CUDA_TAG=$CUDA_TAG)..."
export ENV_PREFIX CUDA_TAG NANCY_DIR
srun --partition=batch-gpu --ntasks=1 --cpus-per-task=4 --mem=16G --time=00:30:00 --gres=gpu:1 bash -lc '
    set -euo pipefail
    module load mamba
    eval "$(mamba shell hook --shell bash)"
    mamba activate "$ENV_PREFIX"
    cd "$NANCY_DIR"
    pip install -e ".[ocr-gpu]"
    echo "Replacing CPU torch + torchvision with CUDA build (${CUDA_TAG})..."
    pip install torch torchvision --index-url "https://download.pytorch.org/whl/${CUDA_TAG}"
    echo ""
    echo "Verify OCR deps + CUDA torch:"
    python -c '"'"'import addict, easydict, einops, fitz, matplotlib, nancy_brain, torch, torchvision, transformers, tokenizers; from transformers.models.llama.modeling_llama import LlamaFlashAttention2; print("nancy_brain OK"); print("fitz:", fitz.__doc__.splitlines()[0]); print("torch:", torch.__version__, "| CUDA available:", torch.cuda.is_available()); print("torchvision:", torchvision.__version__); print("transformers:", transformers.__version__, "| tokenizers:", tokenizers.__version__); print("LlamaFlashAttention2 OK:", LlamaFlashAttention2.__name__)'"'"'
'

echo ""
echo "Done. Activate with:  mamba activate ${ENV_PREFIX}"
