#!/bin/bash
# One-time environment setup — submitted as a batch job (RM-shared, no GPU needed for install).
#
# Usage (from login node, after uploading and extracting the tarball):
#   cd /ocean/projects/cis240096p/mvyas2/Nancy
#   chmod +x scripts/cluster/psc/*.sh scripts/cluster/psc/*.sbatch
#   sbatch scripts/cluster/psc/setup_env.sbatch
#   squeue --me   # watch it complete before running submit.sh

#SBATCH --job-name=nb-setup
#SBATCH --account=cis240096p
#SBATCH --partition=RM-shared
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=00:45:00
#SBATCH --output=logs/setup_env_%j.out
#SBATCH --error=logs/setup_env_%j.err

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"
mkdir -p logs

ENV_PREFIX="/ocean/projects/cis240096p/mvyas2/envs/nancy-brain"
CUDA_TAG="${CUDA_TAG:-cu129}"

module load anaconda3
source "$(conda info --base)/etc/profile.d/conda.sh"

if [[ -d "$ENV_PREFIX" ]]; then
    echo "Environment already exists at $ENV_PREFIX, skipping create."
else
    echo "Creating conda environment at $ENV_PREFIX with Python 3.12..."
    conda create --prefix "$ENV_PREFIX" python=3.12 -y
fi

conda activate "$ENV_PREFIX"

echo "Installing nancy-brain..."
pip install -e .

echo "Replacing CPU torch with CUDA build ($CUDA_TAG)..."
pip install torch --index-url "https://download.pytorch.org/whl/${CUDA_TAG}"

echo ""
echo "Verify:"
python -c "import nancy_brain; import torch; print('nancy_brain OK'); print('torch:', torch.__version__)"

echo "Done."
