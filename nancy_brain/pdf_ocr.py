"""PDF OCR helpers with cache-aware markdown extraction."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_DEEPSEEK_MODEL = os.environ.get("NB_PDF_OCR_DEEPSEEK_MODEL", "deepseek-ai/DeepSeek-OCR")
DEFAULT_DEEPSEEK_PROMPT = os.environ.get(
    "NB_PDF_OCR_DEEPSEEK_PROMPT",
    "<image>\n<|grounding|>Convert the document to markdown. ",
)
DEFAULT_RENDER_SCALE = float(os.environ.get("NB_PDF_OCR_RENDER_SCALE", "2.0"))
DEFAULT_BASE_SIZE = int(os.environ.get("NB_PDF_OCR_DEEPSEEK_BASE_SIZE", "1024"))
DEFAULT_IMAGE_SIZE = int(os.environ.get("NB_PDF_OCR_DEEPSEEK_IMAGE_SIZE", "640"))
DEFAULT_CROP_MODE = os.environ.get("NB_PDF_OCR_DEEPSEEK_CROP_MODE", "true").strip().lower() == "true"
DEFAULT_BACKEND = os.environ.get("NB_PDF_OCR_BACKEND", "auto").strip().lower() or "auto"
CACHE_VERSION = 1


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
    model: Optional[str] = None
    page_count: int = 0
    warning: Optional[str] = None


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
        self.prompt = prompt
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
            from transformers import AutoModel, AutoTokenizer  # noqa: F401
        except Exception as exc:
            return PDFOCRBackendStatus(
                name=self.name,
                available=False,
                reason=f"transformers unavailable: {exc}",
                model=self.model_name,
            )

        return PDFOCRBackendStatus(name=self.name, available=True, model=self.model_name)

    def signature(self) -> dict:
        return {
            "backend": self.name,
            "model": self.model_name,
            "prompt": self.prompt,
            "render_scale": self.render_scale,
            "base_size": self.base_size,
            "image_size": self.image_size,
            "crop_mode": self.crop_mode,
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

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)

        model_kwargs_candidates = []
        attn_impl = os.environ.get("NB_PDF_OCR_ATTN_IMPLEMENTATION", "flash_attention_2").strip()
        if attn_impl:
            model_kwargs_candidates.append({"_attn_implementation": attn_impl})
        model_kwargs_candidates.append({})

        load_errors: list[str] = []
        for extra_kwargs in model_kwargs_candidates:
            try:
                model = AutoModel.from_pretrained(
                    self.model_name,
                    trust_remote_code=True,
                    use_safetensors=True,
                    **extra_kwargs,
                )
                dtype = torch.bfloat16 if getattr(torch.cuda, "is_bf16_supported", lambda: False)() else torch.float16
                self._model = model.eval().cuda().to(dtype)
                return
            except Exception as exc:
                label = extra_kwargs.get("_attn_implementation", "default")
                load_errors.append(f"{label}: {exc}")

        raise RuntimeError("failed to load DeepSeek OCR model: " + " | ".join(load_errors))

    def ocr_images(self, image_paths: list[Path]) -> str:
        self.ensure_loaded()

        import torch

        page_outputs: list[str] = []
        for page_num, image_path in enumerate(image_paths, start=1):
            with tempfile.TemporaryDirectory(prefix="nancy-deepseek-page-") as temp_dir:
                output_dir = Path(temp_dir)
                with torch.inference_mode():
                    result = self._model.infer(
                        self._tokenizer,
                        prompt=self.prompt,
                        image_file=str(image_path),
                        output_path=str(output_dir),
                        base_size=self.base_size,
                        image_size=self.image_size,
                        crop_mode=self.crop_mode,
                        save_results=True,
                        test_compress=False,
                    )
                page_markdown = _coerce_deepseek_output(result, output_dir)
                if page_markdown:
                    page_outputs.append(f"## Page {page_num}\n\n{page_markdown.strip()}")
                else:
                    logger.warning("DeepSeek OCR returned no markdown for page %s (%s)", page_num, image_path)

        return "\n\n".join(chunk for chunk in page_outputs if chunk)


_DEEPSEEK_BACKEND = DeepSeekOCRBackend()


def default_pdf_ocr_cache_dir(project_root: Optional[Path] = None) -> Path:
    env_override = os.environ.get("NB_PDF_OCR_CACHE_DIR", "").strip()
    if env_override:
        return Path(env_override)
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent
    return project_root / "knowledge_base" / "cache" / "pdf_ocr"


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
) -> PDFOCRResult:
    pdf_path = Path(pdf_path)
    cache_root = Path(cache_dir) if cache_dir is not None else default_pdf_ocr_cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)

    cache_key = compute_pdf_content_hash(pdf_path)
    cache_entry_dir = cache_root / cache_key
    backend = _select_backend(preferred_backend)
    if backend is None:
        cached_result = _load_cached_result(cache_entry_dir, cache_key, preferred_backend=preferred_backend)
        if cached_result is not None:
            return cached_result
        status = get_pdf_ocr_backend_status(preferred_backend)
        return PDFOCRResult(
            markdown=None,
            backend=status.name,
            cached=False,
            cache_key=cache_key,
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
        return cached_result

    try:
        with tempfile.TemporaryDirectory(prefix="nancy-pdf-pages-") as temp_dir:
            image_paths = render_pdf_to_images(
                pdf_path,
                output_dir=Path(temp_dir),
                scale=backend.render_scale,
            )
            markdown = backend.ocr_images(image_paths)
    except Exception as exc:
        return PDFOCRResult(
            markdown=None,
            backend=backend.name,
            cached=False,
            cache_key=cache_key,
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
            model=backend.model_name,
            warning="OCR produced empty markdown",
        )

    result = PDFOCRResult(
        markdown=markdown,
        backend=backend.name,
        cached=False,
        cache_key=cache_key,
        model=backend.model_name,
        page_count=len(image_paths),
    )
    _write_cache_entry(cache_entry_dir, cache_key, backend.signature(), result)
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
    with fitz.open(str(pdf_path)) as document:
        for page_index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image_path = output_dir / f"page-{page_index:04d}.png"
            pixmap.save(str(image_path))
            image_paths.append(image_path)
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
    if requested_backend not in {"", "auto"} and requested_backend != cached_backend:
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


__all__ = [
    "PDFOCRBackendStatus",
    "PDFOCRResult",
    "compute_pdf_content_hash",
    "default_pdf_ocr_cache_dir",
    "extract_pdf_markdown",
    "get_pdf_ocr_backend_status",
    "render_pdf_to_images",
]
