#!/bin/bash
# One-time environment setup — run this interactively on a login node
# before submitting the SLURM jobs.
#
# Usage:
#   cd /path/to/nancy-brain   # wherever you extracted the tarball
#   bash scripts/cluster/setup_env.sh

set -euo pipefail

ENV_NAME="nancy-brain"
PYTHON_VERSION="3.12"

module load mamba

echo "Creating conda environment '$ENV_NAME' with Python $PYTHON_VERSION..."
mamba create -n "$ENV_NAME" python="$PYTHON_VERSION" -y

echo "Activating and installing nancy-brain..."
mamba activate "$ENV_NAME"
pip install -e .

# Replace the CPU torch that pip just installed with the CUDA build.
# Check your cluster's CUDA version with: nvidia-smi | head -4
# Then adjust the cu### below (e.g. cu118, cu121, cu124).
echo ""
echo "Installing CUDA torch (edit the cu### tag to match your cluster's CUDA version):"
echo "  nvidia-smi | head -4   # shows CUDA version"
CUDA_TAG="${CUDA_TAG:-cu121}"
echo "Using: $CUDA_TAG (override with: CUDA_TAG=cu124 bash setup_env.sh)"
pip install torch --index-url "https://download.pytorch.org/whl/${CUDA_TAG}"

echo ""
echo "Done. Verify with:"
echo "  mamba activate $ENV_NAME && python -c 'import torch; print(torch.cuda.is_available())'"
