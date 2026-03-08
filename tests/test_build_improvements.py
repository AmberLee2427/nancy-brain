import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

import nancy_brain.summarization as summarization_module
from nancy_brain.cli import cli
from nancy_brain.summarization import SummaryGenerator
from scripts.build_knowledge_base import build_txtai_index, clone_repositories
import scripts.build_knowledge_base as kb_module


class DummyEmbeddings:
    instances = []

    def __init__(self, *args, **kwargs):
        self.indexed = []
        DummyEmbeddings.instances.append(self)

    def index(self, docs):
        self.indexed.extend(list(docs))

    def save(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)

    def search(self, query, limit):
        return []


class StubSummaryResult:
    def __init__(self, summary="summary", weight=1.1, model="stub-model", cached=False, repo_readme_path=None):
        self.summary = summary
        self.weight = weight
        self.model = model
        self.cached = cached
        self.repo_readme_path = repo_readme_path


def _write_repos_config(path: Path, repo_names: list[str]) -> None:
    config = {
        "science": [{"name": repo_name, "url": f"https://example.com/{repo_name}.git"} for repo_name in repo_names]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)


def _install_dummy_txtai(monkeypatch):
    DummyEmbeddings.instances.clear()
    txtai_module = types.ModuleType("txtai")
    embeddings_module = types.ModuleType("txtai.embeddings")
    embeddings_module.Embeddings = DummyEmbeddings
    monkeypatch.setitem(sys.modules, "txtai", txtai_module)
    monkeypatch.setitem(sys.modules, "txtai.embeddings", embeddings_module)


def _run_single_file_build(monkeypatch, tmp_path, filename, content, summary_generator):
    _install_dummy_txtai(monkeypatch)
    monkeypatch.setenv("USE_DUAL_EMBEDDING", "false")

    base_path = tmp_path / "raw"
    repo_dir = base_path / "science" / "target-repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / filename).write_text(content, encoding="utf-8")

    config_path = tmp_path / "repositories.yml"
    _write_repos_config(config_path, ["target-repo"])

    failures = build_txtai_index(
        str(config_path),
        base_path=str(base_path),
        embeddings_path=str(tmp_path / "embeddings"),
        category="science",
        summary_generator=summary_generator,
    )
    return failures, DummyEmbeddings.instances[-1].indexed


def test_repo_filter_skips_other_repos(tmp_path):
    config_path = tmp_path / "repositories.yml"
    _write_repos_config(config_path, ["alpha", "target-repo", "omega"])

    with patch("scripts.build_knowledge_base.subprocess.run") as mock_run:
        clone_repositories(
            str(config_path),
            base_path=str(tmp_path / "raw"),
            repo_filter="target-repo",
        )

    clone_calls = [
        call.args[0] for call in mock_run.call_args_list if call.args and call.args[0][:2] == ["git", "clone"]
    ]
    assert len(clone_calls) == 1
    assert any("target-repo" in str(arg) for arg in clone_calls[0])


def test_repo_filter_none_processes_all(tmp_path):
    config_path = tmp_path / "repositories.yml"
    _write_repos_config(config_path, ["alpha", "target-repo", "omega"])

    with patch("scripts.build_knowledge_base.subprocess.run") as mock_run:
        clone_repositories(
            str(config_path),
            base_path=str(tmp_path / "raw"),
            repo_filter=None,
        )

    clone_calls = [
        call.args[0] for call in mock_run.call_args_list if call.args and call.args[0][:2] == ["git", "clone"]
    ]
    assert len(clone_calls) == 3


def test_summary_skip_small_content(monkeypatch, tmp_path):
    monkeypatch.setattr(kb_module, "MIN_SUMMARY_CHARS", 200)
    summary_generator = MagicMock()
    summary_generator.enabled = True
    summary_generator.summarize.return_value = StubSummaryResult()

    _run_single_file_build(monkeypatch, tmp_path, "main.py", "print('hi')", summary_generator)
    summary_generator.summarize.assert_not_called()


def test_summary_skip_data_extension(monkeypatch, tmp_path):
    monkeypatch.setattr(kb_module, "MIN_SUMMARY_CHARS", 10)
    monkeypatch.setattr(kb_module, "TEXT_EXTENSIONS", set(kb_module.TEXT_EXTENSIONS) | {".fits"})
    summary_generator = MagicMock()
    summary_generator.enabled = True
    summary_generator.summarize.return_value = StubSummaryResult()

    _, indexed_docs = _run_single_file_build(monkeypatch, tmp_path, "catalog.fits", "x" * 400, summary_generator)
    summary_generator.summarize.assert_not_called()
    assert indexed_docs
    assert any(".fits" in doc_id for doc_id, _, _ in indexed_docs)


def test_summary_not_skipped_for_normal_file(monkeypatch, tmp_path):
    monkeypatch.setattr(kb_module, "MIN_SUMMARY_CHARS", 20)
    summary_generator = MagicMock()
    summary_generator.enabled = True
    summary_generator.summarize.return_value = StubSummaryResult()

    _run_single_file_build(
        monkeypatch, tmp_path, "worker.py", "def run():\n    pass\n" + ("a" * 200), summary_generator
    )
    summary_generator.summarize.assert_called_once()


def _invoke_local_with_model(monkeypatch, tmp_path, env_model):
    monkeypatch.setenv("NB_USE_LOCAL_SUMMARY", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    if env_model is None:
        monkeypatch.delenv("NB_SUMMARY_MODEL", raising=False)
    else:
        monkeypatch.setenv("NB_SUMMARY_MODEL", env_model)

    monkeypatch.setattr(summarization_module, "_summarizer_pipeline", None)

    mock_tokenizer_cls = MagicMock()
    mock_tokenizer_cls.from_pretrained.return_value = MagicMock()
    mock_model_cls = MagicMock()
    mock_model_cls.from_pretrained.side_effect = RuntimeError("stop-after-model-load")

    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        float16="float16",
        float32="float32",
    )
    fake_transformers = types.SimpleNamespace(
        AutoModelForCausalLM=mock_model_cls,
        AutoTokenizer=mock_tokenizer_cls,
    )

    with patch.dict(sys.modules, {"torch": fake_torch, "transformers": fake_transformers}):
        generator = SummaryGenerator(cache_dir=tmp_path / "cache", enabled=True)
        generator._invoke_local(content="sample content", readme=None)

    return mock_model_cls


def test_nb_summary_model_env_var(monkeypatch, tmp_path):
    mock_model_cls = _invoke_local_with_model(monkeypatch, tmp_path, "my/model")
    assert mock_model_cls.from_pretrained.call_args[0][0] == "my/model"


def test_nb_summary_model_default(monkeypatch, tmp_path):
    mock_model_cls = _invoke_local_with_model(monkeypatch, tmp_path, None)
    assert mock_model_cls.from_pretrained.call_args[0][0] == "Qwen/Qwen2.5-Coder-0.5B-Instruct"


def test_cli_repo_option_passed_to_subprocess():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("config/repositories.yml")
        _write_repos_config(config_path, ["my-repo"])

        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            result = runner.invoke(cli, ["build", "--repo", "my-repo"])

        assert result.exit_code == 0
        cmd = mock_run.call_args[0][0]
        assert "--repo" in cmd
        assert "my-repo" in cmd
