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
if [[ -d "$ENV_PREFIX" ]]; then
    echo "Environment already exists at $ENV_PREFIX, skipping create."
else
    echo "Creating conda environment at $ENV_PREFIX with Python $PYTHON_VERSION..."
    mamba create --prefix "$ENV_PREFIX" python="$PYTHON_VERSION" -y
fi

# ── Step 2: install packages inside an interactive compute node
echo ""
echo "Requesting compute node for package install (CUDA_TAG=$CUDA_TAG)..."
srun --partition=batch-gpu --ntasks=1 --cpus-per-task=4 --mem=16G --time=00:30:00 --gres=gpu:1 bash -c "
    set -euo pipefail
    module load mamba
    mamba activate ${ENV_PREFIX}
    cd ${NANCY_DIR}
    pip install -e .
    echo 'Replacing CPU torch with CUDA build (${CUDA_TAG})...'
    pip install torch --index-url https://download.pytorch.org/whl/${CUDA_TAG}
    echo ''
    echo 'Verify CUDA torch:'
    python -c 'import torch; print(\"torch:\", torch.__version__, \"| CUDA available:\", torch.cuda.is_available())'
"

echo ""
echo "Done. Activate with:  mamba activate ${ENV_PREFIX}"
