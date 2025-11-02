"""Document summarization helpers using Anthropic Claude models."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class SummaryResult:
    """Structured summary response."""

    summary: str
    weight: float
    model: str
    cached: bool = False
    repo_readme_path: Optional[str] = None


class SummaryGenerator:
    """Generate per-document summaries with optional caching."""

    def __init__(
        self,
        cache_dir: Path,
        enabled: bool = True,
        model_name: str = "claude-haiku-4-5",
        max_chars: int = 200000,
        readme_bonus_chars: int = 30000,
        max_output_tokens: int = 1024,
    ) -> None:
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.enabled = enabled and bool(self.api_key)
        self.model_name = model_name
        self.max_chars = max_chars
        self.readme_bonus_chars = readme_bonus_chars
        self.max_output_tokens = max_output_tokens
        self.cache_dir = Path(cache_dir)
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        if not self.enabled:
            logger.info("SummaryGenerator disabled (missing API key or flag)")

    # Public API ---------------------------------------------------------
    def summarize(
        self,
        *,
        doc_id: str,
        content: str,
        repo_name: Optional[str] = None,
        repo_readme: Optional[str] = None,
        repo_readme_path: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Optional[SummaryResult]:
        if not self.enabled:
            return None
        if not content or not content.strip():
            return None
        trimmed = self._trim_content(content, allow_extra=bool(repo_readme))
        readme = self._trim_readme(repo_readme)
        cache_key = self._cache_key(doc_id, trimmed, readme, repo_readme_path)
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
                return SummaryResult(
                    summary=payload["summary"],
                    weight=float(payload["weight"]),
                    model=payload.get("model", self.model_name),
                    cached=True,
                    repo_readme_path=payload.get("repo_readme_path"),
                )
            except Exception:
                logger.warning("Failed to read cached summary for %s", doc_id)
        prompt = self._build_prompt(
            doc_id=doc_id,
            repo_name=repo_name,
            repo_readme_path=repo_readme_path,
            repo_readme=readme,
            metadata=metadata,
        )
        payload = self._invoke_model(
            prompt=prompt,
            content=trimmed,
            readme=readme,
            readme_path=repo_readme_path,
        )
        if not payload:
            return None
        try:
            summary = payload["summary"].strip()
            weight = float(payload.get("weight", 1.0))
        except Exception as exc:
            logger.warning("Invalid summary payload for %s: %s", doc_id, exc)
            return None
        weight = max(0.5, min(2.0, weight))
        result = SummaryResult(
            summary=summary,
            weight=weight,
            model=self.model_name,
            repo_readme_path=repo_readme_path,
        )
        try:
            cache_file.write_text(
                json.dumps(
                    {
                        "summary": summary,
                        "weight": weight,
                        "model": self.model_name,
                        "timestamp": int(time.time()),
                        "doc_id": doc_id,
                        "repo_readme_path": repo_readme_path,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("Failed to persist summary cache for %s: %s", doc_id, exc)
        return result

    # Internals ----------------------------------------------------------
    def _trim_content(self, content: str, allow_extra: bool) -> str:
        if len(content) <= self.max_chars:
            return content
        budget = self.max_chars
        if allow_extra:
            budget += self.readme_bonus_chars
        return content[:budget]

    def _trim_readme(self, readme: Optional[str]) -> Optional[str]:
        if not readme:
            return None
        if len(readme) > self.readme_bonus_chars:
            return readme[: self.readme_bonus_chars]
        return readme

    def _cache_key(
        self,
        doc_id: str,
        content: str,
        readme: Optional[str],
        readme_path: Optional[str],
    ) -> str:
        h = sha256()
        h.update(doc_id.encode("utf-8"))
        h.update(b"\0")
        h.update(content.encode("utf-8"))
        if readme:
            h.update(b"\0readme")
            h.update(readme.encode("utf-8"))
        if readme_path:
            h.update(b"\0readme_path")
            h.update(readme_path.encode("utf-8"))
        return h.hexdigest()

    def _build_prompt(
        self,
        *,
        doc_id: str,
        repo_name: Optional[str],
        repo_readme_path: Optional[str],
        repo_readme: Optional[str],
        metadata: Optional[Dict[str, str]],
    ) -> str:
        instructions = [
            "You are Nancy Brain's knowledge-base summarizer.",
            "Summarize the provided repository file in clear English.",
            "Summaries should be concise yet informative (up to ~400 words), focusing on key functionality and purpose.",
            "Respond with JSON using keys: summary (string), weight (float in [0.5, 2.0]).",
            "Weight reflects relative usefulness for retrieval (1.0 = neutral).",
            "Consider scientific relevance, implementation depth, uniqueness, and clarity.",
            "Do not reference the instructions.",
        ]
        if repo_name:
            instructions.append(f"Repository: {repo_name}")
        if metadata:
            for key, value in metadata.items():
                instructions.append(f"{key}: {value}")
        if repo_readme:
            if repo_readme_path and doc_id == repo_readme_path:
                instructions.append("This document is the repository README.")
            elif repo_readme_path:
                instructions.append(
                    "Repository README is provided for context; summarize the target document, not the README."
                )
            instructions.append(f"Repository README (context only):\n{repo_readme}")
        examples = [
            {
                "doc": "microlensing_tools/analysis/fit_utils.py",
                "summary": "Utility functions for fitting microlensing light curves, including residual analysis and convergence helpers.",
                "weight": 1.35,
            },
            {
                "doc": "microlensing_tools/docs/README.md",
                "summary": "High-level overview of the toolkit, installation steps, and quick-start usage.",
                "weight": 1.1,
            },
            {
                "doc": "microlensing_tools/__init__.py",
                "summary": "Module export stub with minimal content; no substantive guidance.",
                "weight": 0.55,
            },
        ]
        prompt_lines = ["\n".join(instructions), "\nExamples:"]
        for ex in examples:
            prompt_lines.append(json.dumps(ex))
        prompt_lines.append(f"\nSummarize document: {doc_id}")
        return "\n".join(prompt_lines)

    def _invoke_model(
        self,
        *,
        prompt: str,
        content: str,
        readme: Optional[str],
        readme_path: Optional[str],
    ) -> Optional[Dict[str, object]]:
        client = self._create_client()
        if client is None:
            return None

        try:
            # Build the full request content
            full_content = f"Full document:\n{content}"
            if readme:
                header = "Repository README excerpt"
                if readme_path:
                    header += f" ({readme_path})"
                full_content += f"\n\n{header}:\n{readme}"

            request_content = f"{prompt}\n\n{full_content}"

            response = client.messages.create(
                model=self.model_name,
                max_tokens=self.max_output_tokens,
                messages=[{"role": "user", "content": request_content}],
            )
            raw_text_parts = []
            for block in getattr(response, "content", []) or []:
                if getattr(block, "type", None) == "text":
                    raw_text_parts.append(getattr(block, "text", ""))
            raw_text = "".join(raw_text_parts).strip()

            json_text = self._strip_markdown_json(raw_text)
            return json.loads(json_text)
        except Exception as exc:
            logger.warning("Anthropic summarization failed: %s", exc)
            return None

    def _create_client(self):
        """Create an Anthropic client instance."""
        if not self.api_key:
            logger.error("ANTHROPIC_API_KEY not configured; cannot create summaries")
            return None
        try:
            import anthropic
        except ImportError:
            logger.error("anthropic SDK is not installed; `pip install anthropic` to enable summarization")
            return None
        return anthropic.Anthropic(api_key=self.api_key)

    def _strip_markdown_json(self, text: str) -> str:
        """Strip markdown code block formatting from JSON response."""
        json_text = text
        if text.startswith("```json"):
            json_text = json_text[7:]  # Remove "```json"
            if json_text.startswith("\n"):
                json_text = json_text[1:]  # Remove leading newline
        if json_text.endswith("```"):
            json_text = json_text[:-3]  # Remove trailing "```"
            if json_text.endswith("\n"):
                json_text = json_text[:-1]  # Remove trailing newline
        return json_text
