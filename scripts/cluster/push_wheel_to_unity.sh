#!/bin/bash
# Build/copy Nancy Brain OCR smoke assets to Unity and optionally submit jobs.
#
# Examples:
#   bash scripts/cluster/push_wheel_to_unity.sh --build-wheel --copy h200 --run h200
#   bash scripts/cluster/push_wheel_to_unity.sh --copy standard
#   bash scripts/cluster/push_wheel_to_unity.sh --run standard

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

UNITY_HOST="${UNITY_HOST:-unity-proxy}"
UNITY_DEST_DIR="${UNITY_DEST_DIR:-/home/malpas.1/project_amber}"
DEFAULT_ENV_PYTHON="/opt/anaconda3/envs/nancy-brain/bin/python"
PYTHON_BIN="${PYTHON_BIN:-}"

BUILD_WHEEL=0
COPY_TARGET=""
RUN_TARGET=""
WHEEL_PATH=""

usage() {
    cat <<'EOF'
Usage:
  bash scripts/cluster/push_wheel_to_unity.sh [options]

Options:
  --build-wheel     Build the current wheel locally and copy it to Unity.
  --copy TARGET     Copy the current smoke sbatch script to Unity.
                    TARGET must be one of: standard, h200
  --run TARGET      Submit the remote smoke sbatch script on Unity.
                    TARGET must be one of: standard, h200
  -h, --help        Show this help.

Examples:
  bash scripts/cluster/push_wheel_to_unity.sh --build-wheel --copy h200 --run h200
  bash scripts/cluster/push_wheel_to_unity.sh --copy standard
  bash scripts/cluster/push_wheel_to_unity.sh --run standard
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-wheel)
            BUILD_WHEEL=1
            shift
            ;;
        --copy)
            [[ $# -ge 2 ]] || { echo "--copy requires a target" >&2; exit 2; }
            COPY_TARGET="$2"
            shift 2
            ;;
        --run)
            [[ $# -ge 2 ]] || { echo "--run requires a target" >&2; exit 2; }
            RUN_TARGET="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ $BUILD_WHEEL -eq 0 && -z "$COPY_TARGET" && -z "$RUN_TARGET" ]]; then
    usage >&2
    exit 2
fi

case "$COPY_TARGET" in
    ""|standard|h200) ;;
    *) echo "Invalid --copy target: $COPY_TARGET" >&2; exit 2 ;;
esac

case "$RUN_TARGET" in
    ""|standard|h200) ;;
    *) echo "Invalid --run target: $RUN_TARGET" >&2; exit 2 ;;
esac

if [[ -z "$PYTHON_BIN" ]]; then
    if [[ "${CONDA_DEFAULT_ENV:-}" == "nancy-brain" && -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
        PYTHON_BIN="${CONDA_PREFIX}/bin/python"
    elif [[ -x "$DEFAULT_ENV_PYTHON" ]]; then
        PYTHON_BIN="$DEFAULT_ENV_PYTHON"
    elif [[ -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
        PYTHON_BIN="${CONDA_PREFIX}/bin/python"
    else
        PYTHON_BIN="python3"
    fi
fi

cd "$REPO_ROOT"

ensure_python() {
    if [[ "$PYTHON_BIN" == */* ]]; then
        [[ -x "$PYTHON_BIN" ]] || { echo "Python interpreter not found: $PYTHON_BIN" >&2; exit 2; }
    elif ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        echo "Python interpreter not found: $PYTHON_BIN" >&2
        exit 2
    fi
}

build_wheel() {
    ensure_python
    if ! "$PYTHON_BIN" -m build --version >/dev/null 2>&1; then
        echo "Python package 'build' is required. Install it with:" >&2
        echo "  $PYTHON_BIN -m pip install --upgrade build" >&2
        exit 2
    fi

    echo "Using Python: $PYTHON_BIN"
    echo "Building Nancy Brain wheel from $REPO_ROOT"
    "$PYTHON_BIN" -m build --wheel
    WHEEL_PATH="$("$PYTHON_BIN" - <<'PY'
from pathlib import Path

dist = Path("dist")
wheels = sorted(dist.glob("nancy_brain-*.whl"), key=lambda p: p.stat().st_mtime)
if not wheels:
    raise SystemExit(1)
print(wheels[-1].resolve())
PY
)"

    if [[ -z "$WHEEL_PATH" || ! -f "$WHEEL_PATH" ]]; then
        echo "Failed to locate built wheel under dist/" >&2
        exit 2
    fi
}

latest_local_wheel() {
    ensure_python
    "$PYTHON_BIN" - <<'PY'
from pathlib import Path

dist = Path("dist")
wheels = sorted(dist.glob("nancy_brain-*.whl"), key=lambda p: p.stat().st_mtime)
if not wheels:
    raise SystemExit(1)
print(wheels[-1].resolve())
PY
}

copy_wheel_to_unity() {
    [[ -n "$WHEEL_PATH" && -f "$WHEEL_PATH" ]] || { echo "No built wheel available to copy." >&2; exit 2; }
    local wheel_basename remote_path local_sha
    wheel_basename="$(basename "$WHEEL_PATH")"
    remote_path="${UNITY_DEST_DIR}/${wheel_basename}"
    echo "Copying wheel: $wheel_basename -> ${UNITY_HOST}:${UNITY_DEST_DIR}/"
    ssh "$UNITY_HOST" "mkdir -p '$UNITY_DEST_DIR'"
    scp "$WHEEL_PATH" "${UNITY_HOST}:${remote_path}"
    local_sha="$("$PYTHON_BIN" - <<'PY' "$WHEEL_PATH"
from pathlib import Path
import hashlib
import sys

path = Path(sys.argv[1])
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
)"
    echo "Wheel copied successfully."
    echo "Local:  $WHEEL_PATH"
    echo "Remote: ${UNITY_HOST}:${remote_path}"
    echo "SHA256: $local_sha"
}

smoke_script_name() {
    case "$1" in
        standard) echo "smoke_wheel_ocr.sbatch" ;;
        h200) echo "smoke_wheel_ocr_h200.sbatch" ;;
        *) return 1 ;;
    esac
}

copy_smoke_script() {
    local target="$1"
    local script_name local_path remote_path
    script_name="$(smoke_script_name "$target")"
    local_path="${SCRIPT_DIR}/${script_name}"
    remote_path="${UNITY_DEST_DIR}/${script_name}"
    [[ -f "$local_path" ]] || { echo "Local smoke script not found: $local_path" >&2; exit 2; }
    echo "Copying smoke script: ${script_name} -> ${UNITY_HOST}:${UNITY_DEST_DIR}/"
    ssh "$UNITY_HOST" "mkdir -p '$UNITY_DEST_DIR'"
    scp "$local_path" "${UNITY_HOST}:${remote_path}"
    echo "Smoke script copied successfully: ${UNITY_HOST}:${remote_path}"
}

run_smoke_script() {
    local target="$1"
    local script_name
    script_name="$(smoke_script_name "$target")"
    echo "Submitting remote smoke job: ${UNITY_HOST}:${UNITY_DEST_DIR}/${script_name}"
    ssh "$UNITY_HOST" "cd '$UNITY_DEST_DIR' && sbatch '$script_name'"
}

if [[ $BUILD_WHEEL -eq 1 ]]; then
    build_wheel
    copy_wheel_to_unity
fi

if [[ -n "$COPY_TARGET" ]]; then
    copy_smoke_script "$COPY_TARGET"
fi

if [[ -n "$RUN_TARGET" ]]; then
    run_smoke_script "$RUN_TARGET"
fi

