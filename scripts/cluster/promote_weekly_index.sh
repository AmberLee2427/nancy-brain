#!/usr/bin/env bash
set -Eeuo pipefail

KB_ROOT="/home/nancy/slack-bot/ref/nancy-brain/knowledge_base"
COMPOSE_ROOT="/home/nancy/slack-bot"
ACTIVE="$KB_ROOT/embeddings"
INCOMING="$KB_ROOT/embeddings.incoming"
PREVIOUS="$KB_ROOT/embeddings.previous"
FAILED="$KB_ROOT/embeddings.failed"
ORIGINAL_COMMAND="${SSH_ORIGINAL_COMMAND:-}"

if [[ "$ORIGINAL_COMMAND" == rsync\ --server* ]]; then
    exec /usr/bin/rrsync -wo "$KB_ROOT"
fi

if [[ "$ORIGINAL_COMMAND" != "promote-weekly-index" ]]; then
    printf 'Denied deployment command.\n' >&2
    exit 126
fi

read -r section_count summary_count < <(
    python3 -c '
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
' "$INCOMING"
)

if (( section_count < 1000 || summary_count < 1 )); then
    printf 'Refusing promotion: sections=%s summaries=%s\n' "$section_count" "$summary_count" >&2
    exit 3
fi

cd "$COMPOSE_ROOT"
docker compose stop nancy-brain
rm -rf "$PREVIOUS" "$FAILED"
mv "$ACTIVE" "$PREVIOUS"
mv "$INCOMING" "$ACTIVE"

rollback() {
    printf 'New MCP index failed health checks; restoring previous index.\n' >&2
    docker compose stop nancy-brain || true
    mv "$ACTIVE" "$FAILED"
    mv "$PREVIOUS" "$ACTIVE"
    docker compose up -d --force-recreate nancy-brain
    exit 4
}

docker compose up -d --force-recreate nancy-brain
for _ in $(seq 1 60); do
    health="$(
        docker inspect \
            --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
            nancy-brain-mcp 2>/dev/null || true
    )"
    if [[ "$health" == "healthy" ]]; then
        printf 'Promoted index: sections=%s summaries=%s\n' "$section_count" "$summary_count"
        exit 0
    fi
    if [[ "$health" == "unhealthy" || "$health" == "exited" || "$health" == "dead" ]]; then
        rollback
    fi
    sleep 3
done

rollback
