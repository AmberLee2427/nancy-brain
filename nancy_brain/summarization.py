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

# Lazy load transformers to save startup time if not used
_summarizer_pipeline = None


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

        # Check for local mode override
        self.use_local = os.environ.get("NB_USE_LOCAL_SUMMARY", "").lower() in ("true", "1", "yes")

        # Enabled if we have an API key OR if we are using local mode
        self.enabled = enabled and (bool(self.api_key) or self.use_local)

        self.model_name = model_name
        self.max_chars = max_chars
        self.readme_bonus_chars = readme_bonus_chars
        self.max_output_tokens = max_output_tokens
        self.cache_dir = Path(cache_dir)
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

            if self.use_local:
                logger.info("SummaryGenerator enabled in LOCAL mode (using distilbart-cnn-12-6)")
            else:
                logger.info(f"SummaryGenerator enabled using Anthropic model: {model_name}")
        else:
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
        repo_description: Optional[str] = None,
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
        if self.use_local:
            payload = self._invoke_local(
                content=trimmed, readme=readme, repo_name=repo_name, repo_description=repo_description
            )
        else:
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
            model=payload.get("model", self.model_name),
            repo_readme_path=repo_readme_path,
        )
        try:
            cache_file.write_text(
                json.dumps(
                    {
                        "summary": summary,
                        "weight": weight,
                        "model": payload.get("model", self.model_name),
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
        if self.use_local:
            return self._invoke_local(content, readme)

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

    def _invoke_local(
        self,
        content: str,
        readme: Optional[str],
        repo_name: Optional[str] = None,
        repo_description: Optional[str] = None,
    ) -> Optional[Dict[str, object]]:
        """Run summarization using local Qwen2.5-Coder-0.5B-Instruct."""
        global _summarizer_pipeline
        # Ensure torch is available even if pipeline is cached
        try:
            import torch
        except ImportError:
            logger.error("torch not installed")
            return None

        try:
            if _summarizer_pipeline is None:
                from transformers import AutoModelForCausalLM, AutoTokenizer

                model_name = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
                logger.info(f"Loading local summarization model ({model_name})...")

                tokenizer = AutoTokenizer.from_pretrained(model_name)
                if torch.cuda.is_available():
                    device_map = "auto"
                    torch_dtype = torch.float16
                else:
                    device_map = "cpu"
                    torch_dtype = torch.float32

                model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    torch_dtype=torch_dtype,
                    device_map=device_map,
                    low_cpu_mem_usage=False,
                    use_safetensors=True,
                )
                model.eval()
                _summarizer_pipeline = (model, tokenizer)

            model, tokenizer = _summarizer_pipeline

            # Prepare prompt
            system_prompt = (
                "You are an expert developer assistant. You are summarizing file chunks "
                "from a repository for research purposes. Summarize the provided file "
                "concisely and in plain English. "
                "Focus on the purpose, key functionality, and main classes/functions. "
                "Do not output code, just the summary text. Keep it under 200 words."
            )
            system_prompt_weights = (
                "You are an expert research assistant. You are importance weighting file "
                "chunks from a repository, for training purposes. Files that you give a "
                "high weight to are files you deem most likely to be useful for research "
                "and understanding of the repository contents."
                "Do not output code, just the weight as a float between 0.5 and 2.0."
            )

            # Construct context message
            context_msg = ""
            if repo_name:
                context_msg += f"Repository: {repo_name}\n"
            if repo_description:
                context_msg += f"Description: {repo_description}\n"

            # Structure as a multi-turn conversation to separate context from task
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"I am working in the following repository:\n{context_msg}\nI will provide a file for you to summarize.",
                },
                {
                    "role": "assistant",
                    "content": "Understood. Please provide the file content and I will summarize it based on that context.",
                },
                {"role": "user", "content": f"Please summarize this file:\n\n{content[:30000]}"},
            ]
            messages_weights = [
                {"role": "system", "content": system_prompt_weights},
                {
                    "role": "user",
                    "content": f"I am working in the following repository:\n{context_msg}\nI will provide a file for you to weight.",
                },
                {
                    "role": "assistant",
                    "content": "Understood. Please provide the file content and I will weight it based on that context.",
                },
                {"role": "user", "content": f"Please weight this file:\n\n{content[:30000]}"},
            ]

            text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            text_weight = tokenizer.apply_chat_template(messages_weights, tokenize=False, add_generation_prompt=True)

            inputs = tokenizer([text], return_tensors="pt").to(model.device)
            inputs_weight = tokenizer([text_weight], return_tensors="pt").to(model.device)

            gen_kwargs = {
                "max_new_tokens": 512,
                "do_sample": False,
                "pad_token_id": tokenizer.eos_token_id,
            }
            gen_kwargs_weight = {
                "max_new_tokens": 16,
                "do_sample": False,
                "pad_token_id": tokenizer.eos_token_id,
            }

            with torch.inference_mode():
                generated_ids = model.generate(**inputs, **gen_kwargs)
                generated_ids_weight = model.generate(**inputs_weight, **gen_kwargs_weight)

            generated_ids = [
                output_ids[len(input_ids) :] for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
            ]
            generated_ids_weight = [
                output_ids[len(input_ids) :]
                for input_ids, output_ids in zip(inputs_weight.input_ids, generated_ids_weight)
            ]
            summary_text = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
            weight_text = tokenizer.batch_decode(generated_ids_weight, skip_special_tokens=True)[0]

            # Robust weight parsing
            import re

            weight = 1.0

            # Look for the last float in the text (often the final answer)
            matches = re.findall(r"[-+]?\d*\.\d+|\d+", weight_text)
            if matches:
                try:
                    # Take the last number found
                    parsed = float(matches[-1])
                    weight = max(0.5, min(2.0, parsed))
                except ValueError:
                    pass

            return {"summary": summary_text.strip(), "weight": weight, "model": "local-Qwen2.5-Coder-0.5B"}

        except Exception as e:
            logger.error(f"Local summarization failed: {e}")
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
