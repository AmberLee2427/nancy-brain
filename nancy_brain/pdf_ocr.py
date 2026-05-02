"""PDF OCR helpers with cache-aware markdown extraction."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
import tomllib
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_DEEPSEEK_MODEL = os.environ.get("NB_PDF_OCR_DEEPSEEK_MODEL", "deepseek-ai/DeepSeek-OCR")
DEFAULT_DEEPSEEK_PROMPT = os.environ.get(
    "NB_PDF_OCR_DEEPSEEK_PROMPT",
    "<image>\n<|grounding|>Convert the document to markdown.",
)
DEFAULT_RENDER_SCALE = float(os.environ.get("NB_PDF_OCR_RENDER_SCALE", "2.0"))
DEFAULT_BASE_SIZE = int(os.environ.get("NB_PDF_OCR_DEEPSEEK_BASE_SIZE", "1024"))
DEFAULT_IMAGE_SIZE = int(os.environ.get("NB_PDF_OCR_DEEPSEEK_IMAGE_SIZE", "640"))
DEFAULT_CROP_MODE = os.environ.get("NB_PDF_OCR_DEEPSEEK_CROP_MODE", "true").strip().lower() == "true"
DEFAULT_BACKEND = os.environ.get("NB_PDF_OCR_BACKEND", "auto").strip().lower() or "auto"
CACHE_VERSION = 1
DEEPSEEK_RUNTIME_MODULES = {
    "addict": "addict",
    "easydict": "easydict",
    "einops": "einops",
    "matplotlib": "matplotlib",
    "torchvision": "torchvision",
}
PROJECT_OCR_WORKER_CONFIG_FILENAMES = ("ocr_worker.toml", "ocr-worker.toml")


def _normalize_quantization_mode(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip().lower()
    if raw in {"", "none", "off", "false", "fp16", "full", "16bit"}:
        return None
    if raw in {"4", "4bit", "int4", "nf4"}:
        return "4bit"
    if raw in {"8", "8bit", "int8"}:
        return "8bit"
    if raw == "auto":
        return "auto"
    return raw


def _quantization_threshold_gib(env_name: str, default: float) -> float:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _configured_deepseek_quantization_mode() -> Optional[str]:
    explicit = os.environ.get("NB_PDF_OCR_QUANTIZE", "")
    if explicit.strip():
        return _normalize_quantization_mode(explicit)
    shared = os.environ.get("NB_QUANTIZE", "")
    if shared.strip():
        return _normalize_quantization_mode(shared)
    return "auto"


def _resolve_deepseek_quantization_mode(torch_module) -> Optional[str]:
    configured = _configured_deepseek_quantization_mode()
    if configured != "auto":
        return configured

    cuda = getattr(torch_module, "cuda", None)
    if cuda is None or not getattr(cuda, "is_available", lambda: False)():
        return None

    try:
        current_device = getattr(cuda, "current_device", lambda: 0)()
        props = cuda.get_device_properties(current_device)
        total_memory_gib = props.total_memory / float(1024**3)
    except Exception:
        return None

    four_bit_max = _quantization_threshold_gib("NB_PDF_OCR_AUTO_4BIT_MAX_GIB", 16.0)
    eight_bit_max = _quantization_threshold_gib("NB_PDF_OCR_AUTO_8BIT_MAX_GIB", 24.0)
    if total_memory_gib <= four_bit_max:
        return "4bit"
    if total_memory_gib <= eight_bit_max:
        return "8bit"
    return None


def _deepseek_attention_kwargs_candidates(quantization_mode: Optional[str]) -> list[dict]:
    attn_impl = os.environ.get("NB_PDF_OCR_ATTN_IMPLEMENTATION")
    if attn_impl is not None:
        attn_impl = attn_impl.strip()
        if attn_impl:
            return [{"_attn_implementation": attn_impl}, {}]
        return [{}]

    if quantization_mode:
        return [{}]

    return [{"_attn_implementation": "flash_attention_2"}, {}]


@dataclass(frozen=True)
class PDFOCRBackendStatus:
    """Availability status for an OCR backend."""

    name: str
    available: bool
    reason: Optional[str] = None
    model: Optional[str] = None


@dataclass(frozen=True)
class PDFOCRResult:
    """OCR output for a single PDF."""

    markdown: Optional[str]
    backend: str
    cached: bool
    cache_key: str
    status: str = "generated"
    needs_ocr: bool = False
    deferred: bool = False
    model: Optional[str] = None
    page_count: int = 0
    warning: Optional[str] = None

    def to_worker_record(
        self,
        pdf_path: Path | str,
        *,
        cache_dir: Optional[Path | str] = None,
    ) -> dict:
        """Return the machine-facing OCR worker payload.

        The worker contract is limited to the OCR markdown cache entry:
        it reports where the cache lives, but it does not touch embeddings
        or summary artifacts.
        """

        pdf_path = Path(pdf_path).resolve()
        cache_root = (Path(cache_dir) if cache_dir is not None else default_pdf_ocr_cache_dir()).resolve()
        cache_key = self.cache_key or None
        cache_entry_dir = cache_root / cache_key if cache_key else None
        content_path = cache_entry_dir / "content.md" if cache_entry_dir is not None else None
        metadata_path = cache_entry_dir / "metadata.json" if cache_entry_dir is not None else None
        return {
            "pdf_path": str(pdf_path),
            "cache_dir": str(cache_root),
            "cache_key": cache_key,
            "cache_entry_dir": str(cache_entry_dir) if cache_entry_dir is not None else None,
            "content_path": str(content_path) if content_path is not None else None,
            "metadata_path": str(metadata_path) if metadata_path is not None else None,
            "backend": self.backend,
            "status": self.status,
            "cached": self.cached,
            "needs_ocr": self.needs_ocr,
            "deferred": self.deferred,
            "model": self.model,
            "page_count": self.page_count,
            "warning": self.warning,
        }


def build_pdf_ocr_worker_record(
    pdf_path: Path | str,
    *,
    cache_dir: Optional[Path | str] = None,
    backend: Optional[str] = None,
    status: str = "error",
    warning: Optional[str] = None,
    result: Optional[PDFOCRResult] = None,
) -> dict:
    """Build a stable machine-facing OCR worker payload.

    The returned schema matches successful and deferred worker results so
    subprocess callers can rely on the same keys even during hard failures.
    """

    pdf_path = Path(pdf_path).resolve()
    cache_root = (Path(cache_dir) if cache_dir is not None else default_pdf_ocr_cache_dir()).resolve()
    if result is not None:
        payload = result.to_worker_record(pdf_path, cache_dir=cache_dir)
        if payload.get("cache_key") is None:
            payload["cache_entry_dir"] = None
            payload["content_path"] = None
            payload["metadata_path"] = None
        return payload

    cache_key = None
    cache_entry_dir = None
    content_path = None
    metadata_path = None
    return {
        "pdf_path": str(pdf_path),
        "cache_dir": str(cache_root),
        "cache_key": cache_key,
        "cache_entry_dir": cache_entry_dir,
        "content_path": content_path,
        "metadata_path": metadata_path,
        "backend": backend or "worker",
        "status": status,
        "cached": False,
        "needs_ocr": False,
        "deferred": False,
        "model": None,
        "page_count": 0,
        "warning": warning,
    }


class DeepSeekOCRBackend:
    """DeepSeek OCR backend backed by the upstream transformers integration."""

    name = "deepseek"

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_DEEPSEEK_MODEL,
        prompt: str = DEFAULT_DEEPSEEK_PROMPT,
        render_scale: float = DEFAULT_RENDER_SCALE,
        base_size: int = DEFAULT_BASE_SIZE,
        image_size: int = DEFAULT_IMAGE_SIZE,
        crop_mode: bool = DEFAULT_CROP_MODE,
    ) -> None:
        self.model_name = model_name
        self.prompt = prompt.rstrip()
        self.render_scale = render_scale
        self.base_size = base_size
        self.image_size = image_size
        self.crop_mode = crop_mode
        self._tokenizer = None
        self._model = None

    def status(self) -> PDFOCRBackendStatus:
        try:
            import torch
        except Exception as exc:
            return PDFOCRBackendStatus(
                name=self.name,
                available=False,
                reason=f"torch unavailable: {exc}",
                model=self.model_name,
            )

        if not torch.cuda.is_available():
            return PDFOCRBackendStatus(
                name=self.name,
                available=False,
                reason="CUDA unavailable",
                model=self.model_name,
            )

        try:
            import transformers
            from transformers import AutoModel, AutoTokenizer  # noqa: F401
        except Exception as exc:
            return PDFOCRBackendStatus(
                name=self.name,
                available=False,
                reason=f"transformers unavailable: {exc}",
                model=self.model_name,
            )

        try:
            from transformers.models.llama.modeling_llama import LlamaFlashAttention2  # noqa: F401
        except Exception as exc:
            tokenizers_version = "unknown"
            try:
                import tokenizers

                tokenizers_version = getattr(tokenizers, "__version__", "unknown")
            except Exception:
                pass
            return PDFOCRBackendStatus(
                name=self.name,
                available=False,
                reason=(
                    "incompatible transformers stack for DeepSeek OCR "
                    f"(transformers {getattr(transformers, '__version__', 'unknown')}, "
                    f"tokenizers {tokenizers_version}): {exc}. "
                    "DeepSeek OCR upstream is tested on transformers==4.46.3 and tokenizers==0.20.3."
                ),
                model=self.model_name,
            )

        missing_modules = [
            package for module_name, package in DEEPSEEK_RUNTIME_MODULES.items() if find_spec(module_name) is None
        ]
        if missing_modules:
            return PDFOCRBackendStatus(
                name=self.name,
                available=False,
                reason="missing DeepSeek OCR runtime deps: " + ", ".join(missing_modules),
                model=self.model_name,
            )

        quantization_mode = _resolve_deepseek_quantization_mode(torch)
        if quantization_mode and find_spec("bitsandbytes") is None:
            return PDFOCRBackendStatus(
                name=self.name,
                available=False,
                reason=f"missing DeepSeek OCR quantization runtime dep: bitsandbytes ({quantization_mode})",
                model=self.model_name,
            )

        return PDFOCRBackendStatus(name=self.name, available=True, model=self.model_name)

    def signature(self) -> dict:
        quantization_mode = None
        try:
            import torch

            quantization_mode = _resolve_deepseek_quantization_mode(torch)
        except Exception:
            quantization_mode = _configured_deepseek_quantization_mode()
        return {
            "backend": self.name,
            "model": self.model_name,
            "prompt": self.prompt,
            "render_scale": self.render_scale,
            "base_size": self.base_size,
            "image_size": self.image_size,
            "crop_mode": self.crop_mode,
            "quantize": quantization_mode or "none",
            "cache_version": CACHE_VERSION,
        }

    def ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return

        status = self.status()
        if not status.available:
            raise RuntimeError(status.reason or "DeepSeek OCR unavailable")

        import torch
        from transformers import AutoModel, AutoTokenizer

        logger.info("Loading DeepSeek OCR tokenizer: model=%s", self.model_name)
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)

        quantization_mode = _resolve_deepseek_quantization_mode(torch)
        model_kwargs_candidates = _deepseek_attention_kwargs_candidates(quantization_mode)
        logger.info(
            "Loading DeepSeek OCR model: model=%s quantize=%s candidates=%s",
            self.model_name,
            quantization_mode or "none",
            len(model_kwargs_candidates),
        )

        load_errors: list[str] = []
        for extra_kwargs in model_kwargs_candidates:
            try:
                dtype = torch.bfloat16 if getattr(torch.cuda, "is_bf16_supported", lambda: False)() else torch.float16
                common_kwargs = {
                    "trust_remote_code": True,
                    "use_safetensors": True,
                    **extra_kwargs,
                }
                attn_label = extra_kwargs.get("_attn_implementation", "default")
                logger.info(
                    "Attempting DeepSeek OCR load: model=%s quantize=%s attention=%s",
                    self.model_name,
                    quantization_mode or "none",
                    attn_label,
                )
                if quantization_mode in {"4bit", "8bit"}:
                    from transformers import BitsAndBytesConfig

                    if quantization_mode == "4bit":
                        quantization_config = BitsAndBytesConfig(
                            load_in_4bit=True,
                            bnb_4bit_compute_dtype=dtype,
                            bnb_4bit_quant_type="nf4",
                        )
                    else:
                        quantization_config = BitsAndBytesConfig(load_in_8bit=True)
                    model = AutoModel.from_pretrained(
                        self.model_name,
                        quantization_config=quantization_config,
                        device_map="auto",
                        low_cpu_mem_usage=True,
                        **common_kwargs,
                    )
                    self._model = model.eval()
                else:
                    model = AutoModel.from_pretrained(
                        self.model_name,
                        **common_kwargs,
                    )
                    self._model = model.eval().cuda().to(dtype)
                logger.info(
                    "Loaded DeepSeek OCR model: model=%s quantize=%s attention=%s",
                    self.model_name,
                    quantization_mode or "none",
                    attn_label,
                )
                return
            except Exception as exc:
                label = extra_kwargs.get("_attn_implementation", "default")
                if quantization_mode:
                    label = f"{quantization_mode}/{label}"
                logger.warning(
                    "DeepSeek OCR load attempt failed: model=%s variant=%s error=%s", self.model_name, label, exc
                )
                load_errors.append(f"{label}: {exc}")

        raise RuntimeError("failed to load DeepSeek OCR model: " + " | ".join(load_errors))

    def ocr_images(self, image_paths: list[Path]) -> str:
        self.ensure_loaded()

        import torch

        page_outputs: list[str] = []
        total_pages = len(image_paths)
        for page_num, image_path in enumerate(image_paths, start=1):
            page_start = time.monotonic()
            logger.info(
                "DeepSeek OCR page start: model=%s page=%s/%s image=%s",
                self.model_name,
                page_num,
                total_pages,
                image_path,
            )
            with tempfile.TemporaryDirectory(prefix="nancy-deepseek-page-") as temp_dir:
                output_dir = Path(temp_dir)
                with torch.inference_mode():
                    infer_kwargs = {
                        "prompt": self.prompt,
                        "image_file": str(image_path),
                        "output_path": str(output_dir),
                        "base_size": self.base_size,
                        "image_size": self.image_size,
                        "crop_mode": self.crop_mode,
                        "save_results": True,
                        "test_compress": False,
                        "eval_mode": True,
                    }
                    try:
                        result = self._model.infer(self._tokenizer, **infer_kwargs)
                    except TypeError as exc:
                        if "eval_mode" not in str(exc):
                            raise
                        logger.warning(
                            "DeepSeek OCR infer() does not accept eval_mode; retrying without it: model=%s",
                            self.model_name,
                        )
                        infer_kwargs.pop("eval_mode", None)
                        result = self._model.infer(self._tokenizer, **infer_kwargs)
                page_markdown = _coerce_deepseek_output(result, output_dir)
                if page_markdown:
                    page_outputs.append(f"## Page {page_num}\n\n{page_markdown.strip()}")
                    logger.info(
                        "DeepSeek OCR page complete: model=%s page=%s/%s seconds=%.2f chars=%s",
                        self.model_name,
                        page_num,
                        total_pages,
                        time.monotonic() - page_start,
                        len(page_markdown.strip()),
                    )
                else:
                    logger.warning("DeepSeek OCR returned no markdown for page %s (%s)", page_num, image_path)

        return "\n\n".join(chunk for chunk in page_outputs if chunk)


_DEEPSEEK_BACKEND = DeepSeekOCRBackend()


def default_pdf_ocr_cache_dir(project_root: Optional[Path] = None) -> Path:
    env_override = os.environ.get("NB_PDF_OCR_CACHE_DIR", "").strip()
    if env_override:
        return Path(env_override)
    if project_root is None:
        project_root = _discover_pdf_ocr_project_root()
    return project_root / "knowledge_base" / "cache" / "pdf_ocr"


def _discover_pdf_ocr_project_root() -> Path:
    cwd = Path.cwd().resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "knowledge_base").is_dir():
            return candidate
        if candidate.name == "knowledge_base":
            return candidate.parent
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
    return cwd


def compute_pdf_content_hash(pdf_path: Path | str) -> str:
    pdf_path = Path(pdf_path)
    hasher = hashlib.sha256()
    with pdf_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_pdf_ocr_backend_status(preferred_backend: Optional[str] = None) -> PDFOCRBackendStatus:
    backend_name = (preferred_backend or DEFAULT_BACKEND).strip().lower()
    if backend_name in {"", "auto"}:
        status = _DEEPSEEK_BACKEND.status()
        if status.available:
            return status
        return PDFOCRBackendStatus(name="none", available=False, reason=status.reason, model=status.model)

    if backend_name in {"none", "skip"}:
        return PDFOCRBackendStatus(name="none", available=False, reason="OCR disabled by configuration")

    if backend_name == "deepseek":
        return _DEEPSEEK_BACKEND.status()

    return PDFOCRBackendStatus(
        name=backend_name,
        available=False,
        reason=f"unsupported OCR backend: {backend_name}",
    )


def extract_pdf_markdown(
    pdf_path: Path | str,
    *,
    cache_dir: Optional[Path | str] = None,
    preferred_backend: Optional[str] = None,
    worker_cmd: Optional[str | list[str]] = None,
    allow_worker_spawn: bool = True,
) -> PDFOCRResult:
    pdf_path = Path(pdf_path)
    resolved_pdf_path = pdf_path.resolve(strict=False)
    cache_root = Path(cache_dir) if cache_dir is not None else default_pdf_ocr_cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)

    cache_key = compute_pdf_content_hash(pdf_path)
    cache_entry_dir = cache_root / cache_key
    backend = _select_backend(preferred_backend)
    if backend is None:
        cached_result = _load_cached_result(cache_entry_dir, cache_key, preferred_backend=preferred_backend)
        if cached_result is not None:
            logger.info("OCR cache hit: pdf=%s cache_key=%s", resolved_pdf_path, cache_key)
            return cached_result
        if allow_worker_spawn and not _backend_is_cache_only(preferred_backend):
            logger.info("OCR cache miss, delegating to worker: pdf=%s cache_key=%s", resolved_pdf_path, cache_key)
            worker_result = _run_worker_subprocess(
                pdf_path,
                cache_root=cache_root,
                cache_key=cache_key,
                preferred_backend=preferred_backend,
                worker_cmd=worker_cmd,
            )
            if worker_result is not None:
                return worker_result
        status = get_pdf_ocr_backend_status(preferred_backend)
        logger.warning(
            "OCR unavailable for PDF: pdf=%s backend=%s reason=%s",
            resolved_pdf_path,
            status.name,
            status.reason or "unknown",
        )
        return PDFOCRResult(
            markdown=None,
            backend=status.name,
            cached=False,
            cache_key=cache_key,
            status="needs_ocr",
            needs_ocr=True,
            deferred=True,
            model=status.model,
            warning=status.reason or "No OCR backend available",
        )

    cached_result = _load_cached_result(
        cache_entry_dir,
        cache_key,
        preferred_backend=preferred_backend,
        signature=backend.signature(),
    )
    if cached_result is not None:
        logger.info("OCR cache hit: pdf=%s cache_key=%s", resolved_pdf_path, cache_key)
        return cached_result

    logger.info("OCR start: pdf=%s backend=%s cache_key=%s", resolved_pdf_path, backend.name, cache_key)
    extraction_start = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="nancy-pdf-pages-") as temp_dir:
            logger.info("Rendering PDF for OCR: pdf=%s scale=%.2f", resolved_pdf_path, backend.render_scale)
            image_paths = render_pdf_to_images(
                pdf_path,
                output_dir=Path(temp_dir),
                scale=backend.render_scale,
            )
            logger.info("Rendered PDF pages: pdf=%s pages=%s", resolved_pdf_path, len(image_paths))
            markdown = backend.ocr_images(image_paths)
    except Exception as exc:
        logger.exception("OCR failed for PDF: pdf=%s", resolved_pdf_path)
        return PDFOCRResult(
            markdown=None,
            backend=backend.name,
            cached=False,
            cache_key=cache_key,
            status="error",
            model=backend.model_name,
            warning=str(exc),
        )

    markdown = markdown.strip()
    if not markdown:
        return PDFOCRResult(
            markdown=None,
            backend=backend.name,
            cached=False,
            cache_key=cache_key,
            status="error",
            model=backend.model_name,
            warning="OCR produced empty markdown",
        )

    result = PDFOCRResult(
        markdown=markdown,
        backend=backend.name,
        cached=False,
        cache_key=cache_key,
        status="generated",
        model=backend.model_name,
        page_count=len(image_paths),
    )
    _write_cache_entry(cache_entry_dir, cache_key, backend.signature(), result)
    logger.info(
        "OCR complete: pdf=%s pages=%s cache_key=%s seconds=%.2f",
        resolved_pdf_path,
        len(image_paths),
        cache_key,
        time.monotonic() - extraction_start,
    )
    return result


def render_pdf_to_images(pdf_path: Path | str, *, output_dir: Path, scale: float = DEFAULT_RENDER_SCALE) -> list[Path]:
    pdf_path = Path(pdf_path)
    try:
        import fitz
    except Exception as exc:
        raise RuntimeError(
            "PyMuPDF is required for PDF OCR rendering. Install with `pip install nancy-brain[ocr]` "
            "or `pip install nancy-brain[ocr-gpu]`."
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    image_paths: list[Path] = []
    logger.info("Rendering PDF pages to images: pdf=%s output_dir=%s scale=%.2f", pdf_path, output_dir, scale)
    with fitz.open(str(pdf_path)) as document:
        for page_index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image_path = output_dir / f"page-{page_index:04d}.png"
            pixmap.save(str(image_path))
            image_paths.append(image_path)
    logger.info("Rendered PDF page images: pdf=%s pages=%s", pdf_path, len(image_paths))
    return image_paths


def _select_backend(preferred_backend: Optional[str] = None) -> Optional[DeepSeekOCRBackend]:
    status = get_pdf_ocr_backend_status(preferred_backend)
    if not status.available:
        return None
    if status.name == "deepseek":
        return _DEEPSEEK_BACKEND
    return None


def _load_cached_result(
    cache_entry_dir: Path,
    cache_key: str,
    preferred_backend: Optional[str] = None,
    signature: Optional[dict] = None,
) -> Optional[PDFOCRResult]:
    metadata_path = cache_entry_dir / "metadata.json"
    markdown_path = cache_entry_dir / "content.md"
    if not metadata_path.exists() or not markdown_path.exists():
        return None

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    cached_signature = metadata.get("signature") or {}
    if metadata.get("pdf_sha256") != cache_key:
        return None
    if cached_signature.get("cache_version") != CACHE_VERSION:
        return None

    requested_backend = (preferred_backend or DEFAULT_BACKEND).strip().lower()
    cached_backend = metadata.get("backend", "unknown")
    if requested_backend not in {"", "auto", "skip", "none"} and requested_backend != cached_backend:
        return None
    if signature is not None and cached_signature != signature:
        return None

    try:
        markdown = markdown_path.read_text(encoding="utf-8")
    except Exception:
        return None

    return PDFOCRResult(
        markdown=markdown,
        backend=metadata.get("backend", "unknown"),
        cached=True,
        cache_key=cache_key,
        status="cached",
        model=metadata.get("model"),
        page_count=int(metadata.get("page_count", 0)),
    )


def _write_cache_entry(cache_entry_dir: Path, cache_key: str, signature: dict, result: PDFOCRResult) -> None:
    cache_entry_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = cache_entry_dir / "content.md"
    metadata_path = cache_entry_dir / "metadata.json"

    temp_markdown_path = cache_entry_dir / "content.md.tmp"
    temp_metadata_path = cache_entry_dir / "metadata.json.tmp"

    temp_markdown_path.write_text(result.markdown or "", encoding="utf-8")
    temp_metadata_path.write_text(
        json.dumps(
            {
                "pdf_sha256": cache_key,
                "backend": result.backend,
                "status": result.status,
                "model": result.model,
                "page_count": result.page_count,
                "signature": signature,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    temp_markdown_path.replace(markdown_path)
    temp_metadata_path.replace(metadata_path)
    logger.info(
        "Wrote OCR cache entry: entry=%s cache_key=%s status=%s pages=%s",
        cache_entry_dir,
        cache_key,
        result.status,
        result.page_count,
    )


def _coerce_deepseek_output(result, output_dir: Path) -> Optional[str]:
    if isinstance(result, str):
        return result

    if isinstance(result, dict):
        for key in ("markdown", "text", "result", "output", "content"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value
        for key in ("data", "payload", "prediction", "pred_dict", "results"):
            nested = _coerce_deepseek_output(result.get(key), output_dir)
            if nested:
                return nested

    if isinstance(result, (list, tuple)):
        parts = []
        for value in result:
            coerced = _coerce_deepseek_output(value, output_dir)
            if coerced:
                parts.append(coerced.strip())
        if parts:
            return "\n\n".join(parts)

    for pattern in ("*.md", "*.markdown", "*.txt"):
        candidates = sorted(output_dir.rglob(pattern))
        if not candidates:
            continue
        contents = []
        for candidate in candidates:
            try:
                text = candidate.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            if text:
                contents.append(text)
        if contents:
            return "\n\n".join(contents)

    return None


def warm_pdf_ocr_cache(
    paths: list[Path | str],
    *,
    cache_dir: Optional[Path | str] = None,
    preferred_backend: Optional[str] = None,
    worker_cmd: Optional[str | list[str]] = None,
    allow_worker_spawn: bool = True,
    recursive: bool = True,
) -> list[PDFOCRResult]:
    """Warm OCR cache entries for the provided files or directories."""

    pdf_paths: list[Path] = []
    for item in paths:
        path = Path(item)
        if path.is_dir():
            pattern = "**/*.pdf" if recursive else "*.pdf"
            pdf_paths.extend(sorted(path.glob(pattern)))
        elif path.is_file() and path.suffix.lower() == ".pdf":
            pdf_paths.append(path)

    logger.info("OCR warm scan complete: input_items=%s pdfs=%s recursive=%s", len(paths), len(pdf_paths), recursive)

    backend = _select_backend(preferred_backend)
    if backend is None and allow_worker_spawn and not _backend_is_cache_only(preferred_backend):
        return _warm_pdf_ocr_cache_via_worker_batch(
            pdf_paths,
            cache_dir=cache_dir,
            preferred_backend=preferred_backend,
            worker_cmd=worker_cmd,
        )

    results: list[PDFOCRResult] = []
    for pdf_path in pdf_paths:
        results.append(
            extract_pdf_markdown(
                pdf_path,
                cache_dir=cache_dir,
                preferred_backend=preferred_backend,
                worker_cmd=worker_cmd,
                allow_worker_spawn=allow_worker_spawn,
            )
        )
    return results


def _warm_pdf_ocr_cache_via_worker_batch(
    pdf_paths: list[Path],
    *,
    cache_dir: Optional[Path | str] = None,
    preferred_backend: Optional[str] = None,
    worker_cmd: Optional[str | list[str]] = None,
) -> list[PDFOCRResult]:
    cache_root = Path(cache_dir) if cache_dir is not None else default_pdf_ocr_cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)

    results_by_path: dict[Path, PDFOCRResult] = {}
    cache_keys_by_path: dict[Path, str] = {}
    worker_batch: list[Path] = []

    for pdf_path in pdf_paths:
        resolved_path = pdf_path.resolve(strict=False)
        cache_key = compute_pdf_content_hash(resolved_path)
        cache_keys_by_path[resolved_path] = cache_key
        cache_entry_dir = cache_root / cache_key
        cached_result = _load_cached_result(cache_entry_dir, cache_key, preferred_backend=preferred_backend)
        if cached_result is not None:
            results_by_path[resolved_path] = cached_result
        else:
            worker_batch.append(resolved_path)

    logger.info(
        "OCR warm batch prepared: total=%s cached=%s worker_batch=%s cache_dir=%s",
        len(pdf_paths),
        len(results_by_path),
        len(worker_batch),
        cache_root,
    )

    if worker_batch:
        worker_results = _run_worker_batch_subprocess(
            worker_batch,
            cache_root=cache_root,
            cache_keys_by_path=cache_keys_by_path,
            preferred_backend=preferred_backend,
            worker_cmd=worker_cmd,
        )
        results_by_path.update(worker_results)

    ordered_results: list[PDFOCRResult] = []
    for pdf_path in pdf_paths:
        resolved_path = pdf_path.resolve(strict=False)
        result = results_by_path.get(resolved_path)
        if result is None:
            ordered_results.append(
                PDFOCRResult(
                    markdown=None,
                    backend="worker",
                    cached=False,
                    cache_key=cache_keys_by_path.get(resolved_path, ""),
                    status="error",
                    warning="OCR warm did not return a result for this PDF",
                )
            )
        else:
            ordered_results.append(result)

    return ordered_results


def _backend_is_cache_only(preferred_backend: Optional[str]) -> bool:
    backend_name = (preferred_backend or DEFAULT_BACKEND).strip().lower()
    return backend_name in {"skip", "none"}


def _resolve_worker_command(
    worker_cmd: Optional[str | list[str]] = None,
    *,
    project_path: Optional[Path | str] = None,
) -> Optional[list[str]]:
    command, _warning = _resolve_worker_command_with_warning(worker_cmd, project_path=project_path)
    return command


def _resolve_worker_command_with_warning(
    worker_cmd: Optional[str | list[str]] = None,
    *,
    project_path: Optional[Path | str] = None,
) -> tuple[Optional[list[str]], Optional[str]]:
    if os.environ.get("NB_IN_OCR_WORKER", "").strip():
        return None, None

    if worker_cmd is not None:
        try:
            parts = _normalize_worker_command_prefix(_coerce_worker_command(worker_cmd))
        except Exception as exc:
            return None, f"failed to parse explicit OCR worker command: {exc}"
        if not parts:
            return None, "explicit OCR worker command is empty after normalization"
        return parts, None

    env_cmd = os.environ.get("NB_OCR_WORKER_CMD", "").strip()
    if env_cmd:
        try:
            parts = _normalize_worker_command_prefix(_coerce_worker_command(env_cmd))
        except Exception as exc:
            return None, f"failed to parse NB_OCR_WORKER_CMD: {exc}"
        if not parts:
            return None, "NB_OCR_WORKER_CMD is empty after normalization"
        return parts, None

    config_command, config_warning = _load_worker_command_from_project_config(project_path)
    if config_command is not None:
        return config_command, config_warning
    if config_warning:
        return None, config_warning

    shared_command = _default_shared_worker_command()
    if shared_command is not None:
        return shared_command, None

    return None, None


def _coerce_worker_command(worker_cmd: str | list[str]) -> list[str]:
    if isinstance(worker_cmd, str):
        return shlex.split(worker_cmd)
    return [str(part).strip() for part in worker_cmd if str(part).strip()]


def _project_worker_config_paths(project_path: Optional[Path | str] = None) -> list[Path]:
    search_roots = _project_config_search_roots(project_path)
    config_paths: list[Path] = []
    for root in search_roots:
        for filename in PROJECT_OCR_WORKER_CONFIG_FILENAMES:
            config_paths.append(root / "config" / filename)
    return config_paths


def _load_worker_command_from_project_config(
    project_path: Optional[Path | str] = None,
) -> tuple[Optional[list[str]], Optional[str]]:
    for config_path in _project_worker_config_paths(project_path):
        if not config_path.exists():
            continue
        try:
            raw_config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return None, f"failed to read OCR worker config {config_path}: {exc}"

        raw_command = raw_config.get("worker_cmd") or raw_config.get("command")
        if raw_command is None and isinstance(raw_config.get("worker"), dict):
            worker_section = raw_config["worker"]
            raw_command = worker_section.get("worker_cmd") or worker_section.get("command") or worker_section.get("cmd")

        if raw_command is None:
            return None, f"OCR worker config {config_path} does not define worker_cmd"

        try:
            return _normalize_worker_command_prefix(_coerce_worker_command(raw_command)), None
        except Exception as exc:
            return None, f"failed to parse OCR worker command in {config_path}: {exc}"
    return None, None


def _project_config_search_roots(project_path: Optional[Path | str] = None) -> list[Path]:
    start = Path(project_path).resolve() if project_path is not None else Path.cwd().resolve()
    if start.is_file():
        start = start.parent

    roots: list[Path] = []
    current = start
    while True:
        roots.append(current)
        if (current / "pyproject.toml").exists() or (current / ".git").exists():
            break
        if current.parent == current:
            break
        current = current.parent
    return roots


def _default_shared_worker_command() -> Optional[list[str]]:
    candidates: list[Path]
    if os.name == "nt":
        base = _windows_shared_worker_base()
        candidates = [
            base / "Scripts" / "nancy-brain.exe",
            base / "Scripts" / "nancy-brain.cmd",
            base / "Scripts" / "nancy-brain",
        ]
    else:
        base = Path.home() / ".local" / "share" / "nancy-brain" / "ocr-worker"
        candidates = [base / "bin" / "nancy-brain", base / "bin" / "nancy-brain.exe"]

    for candidate in candidates:
        if candidate.exists() and (os.name == "nt" or os.access(candidate, os.X_OK)):
            return [str(candidate)]
    return None


def _windows_shared_worker_base() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    if local_appdata:
        return Path(local_appdata) / "nancy-brain" / "ocr-worker"
    return Path.home() / "AppData" / "Local" / "nancy-brain" / "ocr-worker"


def _normalize_worker_command_prefix(parts: list[str]) -> list[str]:
    normalized = [part for part in parts if str(part).strip()]
    while normalized and normalized[-1] in {"worker", "ocr"}:
        normalized.pop()
    return normalized


def _parse_worker_payload(stdout: str) -> Optional[dict]:
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _parse_worker_payload_stream(stdout: str) -> list[dict]:
    payloads: list[dict] = []
    for line in stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            return []
        if isinstance(payload, dict):
            payloads.append(payload)
        else:
            return []
    return payloads


def _result_from_worker_payload(
    payload: Optional[dict],
    *,
    pdf_path: Path,
    cache_root: Path,
    cache_key: str,
    preferred_backend: Optional[str],
    fallback_warning: Optional[str] = None,
) -> PDFOCRResult:
    if not payload:
        return PDFOCRResult(
            markdown=None,
            backend="worker",
            cached=False,
            cache_key=cache_key,
            status="error",
            warning=fallback_warning or "OCR worker did not return a JSON payload",
        )

    status = str(payload.get("status", "error"))
    warning = payload.get("warning")
    backend_name = str(payload.get("backend") or "worker")
    model = payload.get("model")
    page_count = int(payload.get("page_count") or 0)
    cache_entry_dir = cache_root / cache_key

    if status == "needs_ocr":
        return PDFOCRResult(
            markdown=None,
            backend=backend_name,
            cached=False,
            cache_key=cache_key,
            status="needs_ocr",
            needs_ocr=True,
            deferred=True,
            model=model,
            page_count=page_count,
            warning=warning or fallback_warning,
        )

    if status == "error":
        return PDFOCRResult(
            markdown=None,
            backend=backend_name,
            cached=False,
            cache_key=cache_key,
            status="error",
            model=model,
            page_count=page_count,
            warning=warning or fallback_warning or "OCR worker reported an error",
        )

    cached_result = _load_cached_result(cache_entry_dir, cache_key, preferred_backend=preferred_backend)
    if cached_result is None:
        return PDFOCRResult(
            markdown=None,
            backend=backend_name,
            cached=False,
            cache_key=cache_key,
            status="error",
            model=model,
            page_count=page_count,
            warning=fallback_warning or "OCR worker completed successfully but cache entry was not written",
        )

    if status == "cached":
        return cached_result

    return PDFOCRResult(
        markdown=cached_result.markdown,
        backend=backend_name,
        cached=False,
        cache_key=cache_key,
        status="generated",
        model=model or cached_result.model,
        page_count=page_count or cached_result.page_count,
        warning=warning,
    )


def _run_worker_subprocess(
    pdf_path: Path,
    *,
    cache_root: Path,
    cache_key: str,
    preferred_backend: Optional[str],
    worker_cmd: Optional[str | list[str]] = None,
) -> Optional[PDFOCRResult]:
    try:
        command, resolution_warning = _resolve_worker_command_with_warning(worker_cmd, project_path=pdf_path)
    except ValueError as exc:
        return PDFOCRResult(
            markdown=None,
            backend="worker",
            cached=False,
            cache_key=cache_key,
            status="error",
            warning=str(exc),
        )

    if not command:
        if resolution_warning:
            return PDFOCRResult(
                markdown=None,
                backend="worker",
                cached=False,
                cache_key=cache_key,
                status="error",
                warning=resolution_warning,
            )
        return None

    pdf_path_abs = pdf_path.resolve(strict=False)
    cache_root_abs = cache_root.resolve(strict=False)

    invocation = [*command, "ocr", "worker", str(pdf_path_abs), "--cache-dir", str(cache_root_abs)]
    backend_name = (preferred_backend or DEFAULT_BACKEND).strip().lower()
    if backend_name not in {"", "auto", "skip", "none"}:
        invocation.extend(["--backend", backend_name])

    env = os.environ.copy()
    env["NB_IN_OCR_WORKER"] = "1"
    env["NB_OCR_WORKER_CMD"] = ""

    logger.info("Launching OCR worker: pdf=%s command=%s", pdf_path_abs, shlex.join(invocation))
    worker_start = time.monotonic()
    try:
        completed = subprocess.run(
            invocation,
            check=False,
            stdout=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(cache_root_abs),
        )
    except Exception as exc:
        return PDFOCRResult(
            markdown=None,
            backend="worker",
            cached=False,
            cache_key=cache_key,
            status="error",
            warning=f"failed to launch OCR worker: {exc}",
        )

    logger.info(
        "OCR worker finished: pdf=%s returncode=%s seconds=%.2f",
        pdf_path_abs,
        completed.returncode,
        time.monotonic() - worker_start,
    )
    payload = _parse_worker_payload(completed.stdout)
    warning = None
    if completed.returncode != 0 and payload is not None:
        warning = payload.get("warning")
    if completed.returncode != 0 and not warning:
        warning = (
            (completed.stderr or "").strip()
            or (completed.stdout or "").strip()
            or f"OCR worker exited with code {completed.returncode}"
        )
    return _result_from_worker_payload(
        payload,
        pdf_path=pdf_path_abs,
        cache_root=cache_root,
        cache_key=cache_key,
        preferred_backend=preferred_backend,
        fallback_warning=warning,
    )


def _run_worker_batch_subprocess(
    pdf_paths: list[Path],
    *,
    cache_root: Path,
    cache_keys_by_path: dict[Path, str],
    preferred_backend: Optional[str],
    worker_cmd: Optional[str | list[str]] = None,
) -> dict[Path, PDFOCRResult]:
    if not pdf_paths:
        return {}

    try:
        command, resolution_warning = _resolve_worker_command_with_warning(worker_cmd, project_path=pdf_paths[0])
    except ValueError as exc:
        return {
            pdf_path: PDFOCRResult(
                markdown=None,
                backend="worker",
                cached=False,
                cache_key=cache_keys_by_path[pdf_path],
                status="error",
                warning=str(exc),
            )
            for pdf_path in pdf_paths
        }

    if not command:
        if resolution_warning:
            return {
                pdf_path: PDFOCRResult(
                    markdown=None,
                    backend="worker",
                    cached=False,
                    cache_key=cache_keys_by_path[pdf_path],
                    status="error",
                    warning=resolution_warning,
                )
                for pdf_path in pdf_paths
            }
        return {}

    cache_root_abs = cache_root.resolve(strict=False)
    pdf_path_args = [str(pdf_path.resolve(strict=False)) for pdf_path in pdf_paths]
    invocation = [*command, "ocr", "worker", *pdf_path_args, "--cache-dir", str(cache_root_abs)]
    backend_name = (preferred_backend or DEFAULT_BACKEND).strip().lower()
    if backend_name not in {"", "auto", "skip", "none"}:
        invocation.extend(["--backend", backend_name])

    env = os.environ.copy()
    env["NB_IN_OCR_WORKER"] = "1"
    env["NB_OCR_WORKER_CMD"] = ""

    logger.info("Launching OCR worker batch: pdfs=%s command=%s", len(pdf_paths), shlex.join(invocation))
    worker_start = time.monotonic()
    try:
        completed = subprocess.run(
            invocation,
            check=False,
            stdout=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(cache_root_abs),
        )
    except Exception as exc:
        return {
            pdf_path: PDFOCRResult(
                markdown=None,
                backend="worker",
                cached=False,
                cache_key=cache_keys_by_path[pdf_path],
                status="error",
                warning=f"failed to launch OCR worker: {exc}",
            )
            for pdf_path in pdf_paths
        }

    logger.info(
        "OCR worker batch finished: pdfs=%s returncode=%s seconds=%.2f",
        len(pdf_paths),
        completed.returncode,
        time.monotonic() - worker_start,
    )
    payloads = _parse_worker_payload_stream(completed.stdout)
    payloads_by_path: dict[Path, dict] = {}
    for payload in payloads:
        payload_path = payload.get("pdf_path")
        if not payload_path:
            continue
        payloads_by_path[Path(payload_path).resolve(strict=False)] = payload

    fallback_warning = None
    if completed.returncode != 0:
        fallback_warning = (
            (completed.stderr or "").strip()
            or (completed.stdout or "").strip()
            or f"OCR worker exited with code {completed.returncode}"
        )

    results: dict[Path, PDFOCRResult] = {}
    for pdf_path in pdf_paths:
        resolved_path = pdf_path.resolve(strict=False)
        results[resolved_path] = _result_from_worker_payload(
            payloads_by_path.get(resolved_path),
            pdf_path=resolved_path,
            cache_root=cache_root,
            cache_key=cache_keys_by_path[resolved_path],
            preferred_backend=preferred_backend,
            fallback_warning=fallback_warning,
        )
    return results


__all__ = [
    "PDFOCRBackendStatus",
    "PDFOCRResult",
    "build_pdf_ocr_worker_record",
    "compute_pdf_content_hash",
    "default_pdf_ocr_cache_dir",
    "extract_pdf_markdown",
    "get_pdf_ocr_backend_status",
    "render_pdf_to_images",
    "warm_pdf_ocr_cache",
]
