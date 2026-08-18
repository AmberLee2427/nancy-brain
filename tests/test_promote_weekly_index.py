import os
import sqlite3
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "cluster" / "promote_weekly_index.sh"


def _make_index(path: Path, marker: str) -> None:
    database = path / "index" / "documents"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sections (tags TEXT)")
        connection.executemany(
            "INSERT INTO sections VALUES (?)",
            [(f'{{"doc_type": "{("summary" if index == 0 else "source")}"}}',) for index in range(1001)],
        )
    (path / "marker").write_text(marker)


def _test_script(tmp_path: Path, kb_root: Path, compose_root: Path) -> Path:
    source = SCRIPT.read_text()
    source = source.replace(
        'KB_ROOT="/home/nancy/slack-bot/ref/nancy-brain/knowledge_base"',
        f'KB_ROOT="{kb_root}"',
    ).replace(
        'COMPOSE_ROOT="/home/nancy/slack-bot"',
        f'COMPOSE_ROOT="{compose_root}"',
    )
    script = tmp_path / "promote_weekly_index.sh"
    script.write_text(source)
    script.chmod(0o755)
    return script


def _fake_docker(tmp_path: Path) -> Path:
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    docker = binary_dir / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$DOCKER_LOG"
if [[ "$1" == "inspect" ]]; then
    printf 'healthy\n'
elif [[ "$*" == "compose stop nancy-brain" && "${REMOVE_INCOMING_ON_STOP:-0}" == "1" ]]; then
    rm -rf "$INCOMING_PATH"
fi
"""
    )
    docker.chmod(0o755)
    return binary_dir


def _run(script: Path, tmp_path: Path, kb_root: Path, *, remove_incoming: bool = False):
    docker_log = tmp_path / "docker.log"
    env = os.environ.copy()
    env.update(
        {
            "DOCKER_LOG": str(docker_log),
            "INCOMING_PATH": str(kb_root / "embeddings.incoming"),
            "PATH": f"{_fake_docker(tmp_path)}:{env['PATH']}",
            "REMOVE_INCOMING_ON_STOP": "1" if remove_incoming else "0",
            "SSH_ORIGINAL_COMMAND": "promote-weekly-index",
        }
    )
    result = subprocess.run([script], env=env, capture_output=True, text=True)
    return result, docker_log.read_text()


def test_promotes_valid_index_and_retains_rollback(tmp_path):
    kb_root = tmp_path / "knowledge_base"
    compose_root = tmp_path / "compose"
    compose_root.mkdir()
    _make_index(kb_root / "embeddings", "active")
    _make_index(kb_root / "embeddings.incoming", "incoming")

    result, docker_log = _run(_test_script(tmp_path, kb_root, compose_root), tmp_path, kb_root)

    assert result.returncode == 0, result.stderr
    assert (kb_root / "embeddings" / "marker").read_text() == "incoming"
    assert (kb_root / "embeddings.rollback" / "marker").read_text() == "active"
    assert "compose stop nancy-brain" in docker_log
    assert "compose up -d --force-recreate nancy-brain" in docker_log


def test_restores_active_index_when_swap_fails_after_shutdown(tmp_path):
    kb_root = tmp_path / "knowledge_base"
    compose_root = tmp_path / "compose"
    compose_root.mkdir()
    _make_index(kb_root / "embeddings", "active")
    _make_index(kb_root / "embeddings.incoming", "incoming")

    result, docker_log = _run(
        _test_script(tmp_path, kb_root, compose_root),
        tmp_path,
        kb_root,
        remove_incoming=True,
    )

    assert result.returncode != 0
    assert (kb_root / "embeddings" / "marker").read_text() == "active"
    assert docker_log.count("compose stop nancy-brain") == 2
    assert "compose up -d --force-recreate nancy-brain" in docker_log
