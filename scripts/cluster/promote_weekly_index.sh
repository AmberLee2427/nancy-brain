#!/usr/bin/env bash
set -Eeuo pipefail

KB_ROOT="/home/nancy/slack-bot/ref/nancy-brain/knowledge_base"
COMPOSE_ROOT="/home/nancy/slack-bot"
ACTIVE="$KB_ROOT/embeddings"
INCOMING="$KB_ROOT/embeddings.incoming"
ROLLBACK="$KB_ROOT/embeddings.rollback"
FAILED="$KB_ROOT/embeddings.failed"
ORIGINAL_COMMAND="${SSH_ORIGINAL_COMMAND:-}"

if [[ "$ORIGINAL_COMMAND" == rsync\ --server* ]]; then
    exec /usr/bin/rrsync -wo "$KB_ROOT"
fi

if [[ "$ORIGINAL_COMMAND" != "promote-weekly-index" ]]; then
    printf 'Denied deployment command.\n' >&2
    exit 126
fi

if [[ ! -d "$ACTIVE" ]]; then
    printf 'Refusing promotion: active index is missing: %s\n' "$ACTIVE" >&2
    exit 3
fi

read -r integrity section_count summary_count < <(
    python3 -c '
import sqlite3
import sys
from pathlib import Path

db = Path(sys.argv[1]) / "index" / "documents"
if not db.is_file():
    raise SystemExit(f"missing txtai document database: {db}")
with sqlite3.connect(db) as connection:
    integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
    sections = connection.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    summaries = connection.execute(
        "SELECT COUNT(*) FROM sections WHERE tags LIKE ?",
        ("%\"doc_type\": \"summary\"%",),
    ).fetchone()[0]
print(integrity, sections, summaries)
' "$INCOMING"
)

if [[ "$integrity" != "ok" ]] || (( section_count < 1000 || summary_count < 1 )); then
    printf 'Refusing promotion: integrity=%s sections=%s summaries=%s\n' \
        "$integrity" "$section_count" "$summary_count" >&2
    exit 3
fi

cd "$COMPOSE_ROOT"

# Cleanup must succeed while the current MCP is still serving. Older releases
# used embeddings.previous, which may be root-owned; leave that legacy snapshot
# alone and use a deployment-owned rollback slot from now on.
rm -rf "$ROLLBACK" "$FAILED"
if [[ -e "$ROLLBACK" || -e "$FAILED" ]]; then
    printf 'Refusing promotion: rollback paths could not be prepared.\n' >&2
    exit 3
fi

service_stopped=0
active_moved=0
incoming_moved=0

rollback() {
    local exit_status="${1:-4}"
    printf 'Index promotion failed; restoring the previous index.\n' >&2
    set +e
    docker compose stop nancy-brain || true
    if (( incoming_moved )) && [[ -e "$ACTIVE" ]]; then
        mv "$ACTIVE" "$FAILED"
    fi
    if (( active_moved )) && [[ -e "$ROLLBACK" ]]; then
        mv "$ROLLBACK" "$ACTIVE"
    fi
    docker compose up -d --force-recreate nancy-brain
    exit "$exit_status"
}

on_error() {
    local exit_status=$?
    if (( service_stopped )); then
        rollback "$exit_status"
    fi
    exit "$exit_status"
}
trap on_error ERR

docker compose stop nancy-brain
service_stopped=1
mv "$ACTIVE" "$ROLLBACK"
active_moved=1
mv "$INCOMING" "$ACTIVE"
incoming_moved=1

docker compose up -d --force-recreate nancy-brain
for _ in $(seq 1 60); do
    health="$(
        docker inspect \
            --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
            nancy-brain-mcp 2>/dev/null || true
    )"
    if [[ "$health" == "healthy" ]]; then
        trap - ERR
        printf 'Promoted index: sections=%s summaries=%s\n' "$section_count" "$summary_count"
        exit 0
    fi
    if [[ "$health" == "unhealthy" || "$health" == "exited" || "$health" == "dead" ]]; then
        rollback 4
    fi
    sleep 3
done

rollback 4
