#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

ROOT="${NANCY_KB_ROOT:-/home/amber/nancy-kb}"
REPO="${NANCY_BRAIN_REPO:-$ROOT/nancy-brain}"
ENV_FILE="${NANCY_REFRESH_ENV:-$ROOT/refresh.env}"
EMBEDDINGS_STAGE="${NANCY_EMBEDDINGS_STAGE:-$ROOT/embeddings.weekly}"
LOG_FILE="${NANCY_REFRESH_LOG:-$ROOT/weekly-refresh.log}"
STATUS_FILE="${NANCY_REFRESH_STATUS:-$ROOT/weekly-refresh.status}"
LOCK_FILE="${NANCY_REFRESH_LOCK:-$ROOT/weekly-refresh.lock}"
DEPLOY_HOST="${NANCY_DEPLOY_HOST:-nancy@192.168.12.81}"
DEPLOY_KEY="${NANCY_DEPLOY_KEY:-$HOME/.ssh/id_ed25519_nancy_deploy}"
FALLBACK_SUMMARY_MODEL="${NANCY_FALLBACK_SUMMARY_MODEL:-agents-a1}"

mkdir -p "$ROOT"
exec >>"$LOG_FILE" 2>&1
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    printf '%s skipped: another refresh holds %s\n' "$(date --iso-8601=seconds)" "$LOCK_FILE"
    exit 0
fi

write_status() {
    local state="$1"
    local detail="$2"
    printf 'state=%s\ntime=%s\ndetail=%s\n' \
        "$state" "$(date --iso-8601=seconds)" "$detail" >"$STATUS_FILE"
}

fail() {
    local line="$1"
    local status="$2"
    write_status "failed" "line $line exited with status $status"
    printf '%s failed at line %s with status %s\n' "$(date --iso-8601=seconds)" "$line" "$status"
    exit "$status"
}
trap 'fail "$LINENO" "$?"' ERR

if [[ ! -r "$ENV_FILE" ]]; then
    printf 'Missing protected refresh environment: %s\n' "$ENV_FILE"
    exit 2
fi
if [[ ! -x "$REPO/.venv/bin/nancy-brain" ]]; then
    printf 'Nancy Brain environment not found: %s\n' "$REPO/.venv/bin/nancy-brain"
    exit 2
fi
if [[ ! -r "$DEPLOY_KEY" ]]; then
    printf 'Deployment key not found: %s\n' "$DEPLOY_KEY"
    exit 2
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

for _ in $(seq 1 72); do
    if ! pgrep -u "$(id -u)" -f '[n]ancy-brain build' >/dev/null; then
        break
    fi
    write_status "waiting" "another Nancy Brain build is active"
    sleep 300
done
if pgrep -u "$(id -u)" -f '[n]ancy-brain build' >/dev/null; then
    printf 'Another Nancy Brain build remained active for six hours; aborting refresh.\n'
    exit 75
fi

cd "$REPO"
write_status "running" "warming Gemma summary cache"
printf '\n%s weekly refresh started\n' "$(date --iso-8601=seconds)"

BUILD_COMMON=(
    --config config/repositories.yml
    --embeddings-path "$EMBEDDINGS_STAGE"
    --dirty
    --use-cached-ocr-only
)

# Cache keys include source content, so unchanged files return without an API call.
"$REPO/.venv/bin/nancy-brain" build "${BUILD_COMMON[@]}" --force-update --summaries-only

if [[ -n "$FALLBACK_SUMMARY_MODEL" ]]; then
    write_status "running" "retrying uncached summaries with $FALLBACK_SUMMARY_MODEL"
    CUSTOM_SUMMARY_MODEL="$FALLBACK_SUMMARY_MODEL" \
        "$REPO/.venv/bin/nancy-brain" build "${BUILD_COMMON[@]}" --summaries-only
fi

write_status "running" "building staged summary-enriched index"
rm -rf "$EMBEDDINGS_STAGE"
"$REPO/.venv/bin/nancy-brain" build \
    "${BUILD_COMMON[@]}" \
    --articles-config config/articles.yml \
    --summaries

read -r section_count summary_count < <(
    "$REPO/.venv/bin/python" -c '
import sqlite3
import sys
from pathlib import Path

db = Path(sys.argv[1]) / "index" / "documents"
if not db.is_file():
    raise SystemExit(f"missing txtai document database: {db}")
with sqlite3.connect(db) as connection:
    sections = connection.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    summaries = connection.execute(
        "SELECT COUNT(*) FROM sections WHERE tags LIKE ?",
        ("%\"doc_type\": \"summary\"%",),
    ).fetchone()[0]
print(sections, summaries)
' "$EMBEDDINGS_STAGE"
)

if (( section_count < 1000 || summary_count < 1 )); then
    printf 'Refusing deployment: sections=%s summaries=%s\n' "$section_count" "$summary_count"
    exit 3
fi

write_status "running" "transferring $section_count sections and $summary_count summaries"
SSH_OPTIONS=(
    -i "$DEPLOY_KEY"
    -o IdentitiesOnly=yes
    -o BatchMode=yes
    -o StrictHostKeyChecking=accept-new
)
rsync -a --delete \
    -e "ssh ${SSH_OPTIONS[*]}" \
    "$EMBEDDINGS_STAGE/" \
    "$DEPLOY_HOST:embeddings.incoming/"

write_status "running" "promoting staged index on Nancy"
ssh "${SSH_OPTIONS[@]}" "$DEPLOY_HOST" promote-weekly-index

write_status "complete" "deployed $section_count sections and $summary_count summaries"
printf '%s weekly refresh completed: sections=%s summaries=%s\n' \
    "$(date --iso-8601=seconds)" "$section_count" "$summary_count"
