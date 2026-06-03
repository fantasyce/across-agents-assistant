"""Attachment helpers for chat requests.

The Swift client can attach local files and screenshots. Local CLI agents can
read those paths directly, while vision-capable cloud models need image bytes
encoded as provider-native message blocks.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


SUPPORTED_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}


def _safe_local_path(raw_path: Any) -> Optional[Path]:
    value = str(raw_path or "").strip()
    if not value or "\x00" in value or "\r" in value or "\n" in value:
        return None
    return Path(value).expanduser().resolve(strict=False)


def _field(attachment: Any, name: str, default: Any = None) -> Any:
    if isinstance(attachment, dict):
        return attachment.get(name, default)
    return getattr(attachment, name, default)


def _attachment_mime_type(attachment: Any) -> Optional[str]:
    explicit = _field(attachment, "mime_type") or _field(attachment, "mimeType")
    if explicit:
        return str(explicit)

    path = _field(attachment, "path")
    if not path:
        return None
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed


def has_image_attachments(attachments: Optional[Iterable[Any]]) -> bool:
    if not attachments:
        return False
    return any(
        not bool(_field(attachment, "is_folder", _field(attachment, "isFolder", False)))
        and (_attachment_mime_type(attachment) or "").lower() in SUPPORTED_IMAGE_MIME_TYPES
        for attachment in attachments
    )


def iter_image_attachments(attachments: Optional[Iterable[Any]]) -> Iterable[Any]:
    for attachment in attachments or []:
        if bool(_field(attachment, "is_folder", _field(attachment, "isFolder", False))):
            continue
        if (_attachment_mime_type(attachment) or "").lower() in SUPPORTED_IMAGE_MIME_TYPES:
            yield attachment


def model_supports_vision(agent_config: Optional[Dict[str, Any]]) -> bool:
    if not agent_config:
        return False

    if agent_config.get("supports_vision") is True:
        return True

    model = str(agent_config.get("model") or "").lower()
    vision_tokens = (
        "gpt-4o",
        "gpt-4.1",
        "gpt-5",
        "vision",
        "qwen-vl",
        "qwen2-vl",
        "qwen2.5-vl",
        "omni",
        "gemini",
        "claude-3",
        "pixtral",
        "llava",
    )
    return any(token in model for token in vision_tokens)


def build_image_attachment_context(
    attachments: Optional[Iterable[Any]],
    *,
    include_paths: bool = False,
    ocr_fn: Optional[Callable[[Path], str]] = None,
) -> str:
    """Build text fallback context for image attachments.

    This is used for text-only cloud models and local CLI agents. Vision-capable
    models still receive the actual image bytes, but the OCR fallback improves
    small screenshot/code-snippet reliability.
    """

    image_contexts: List[str] = []
    for index, attachment in enumerate(iter_image_attachments(attachments), start=1):
        raw_path = _field(attachment, "path")
        name = str(_field(attachment, "name", "") or (Path(str(raw_path)).name if raw_path else f"image-{index}"))
        mime_type = (_attachment_mime_type(attachment) or "unknown").lower()

        lines = [f"Image {index}: {name}", f"MIME type: {mime_type}"]

        path: Optional[Path] = None
        if raw_path:
            path = _safe_local_path(raw_path)
        if path:
            if include_paths:
                lines.append(f"Local path: {path}")
            if path.exists():
                lines.extend(_image_metadata(path))
            else:
                lines.append("File status: missing on local disk")

        ocr_text = ""
        if path and path.is_file():
            try:
                ocr_text = (ocr_fn or extract_image_ocr)(path)
            except Exception as exc:
                ocr_text = f"[OCR error: {exc}]"
            if _is_no_text_ocr(ocr_text):
                try:
                    labels = extract_image_labels(path)
                    if labels:
                        lines.append("Visual labels: " + ", ".join(labels))
                except Exception:
                    pass
        if ocr_text:
            lines.append("Extracted text/OCR:")
            lines.append(_truncate_text(ocr_text.strip(), 4000))
        else:
            lines.append("Extracted text/OCR: [No text recognized]")

        image_contexts.append("\n".join(lines))

    if not image_contexts:
        return ""

    return (
        "Attached image context follows. It was extracted from the user's attached "
        "image(s) before this message was sent. Use this OCR/visual context as if "
        "the image was visible when answering questions about the attachment(s). "
        "Do not ask the user to re-specify the image or call file tools just to "
        "inspect the attached image.\n\n"
        + "\n\n".join(image_contexts)
    )


def append_image_attachment_context(text: str, image_context: str) -> str:
    if not image_context.strip():
        return text
    prefix = text.strip()
    block = f"[Attached Image Context]\n{image_context.strip()}"
    return f"{prefix}\n\n{block}" if prefix else block


def extract_image_ocr(path: Path) -> str:
    """Extract text from an image file via macOS Vision when available."""

    try:
        import AppKit  # type: ignore
        import Vision  # type: ignore
    except ImportError:
        return "[OCR unavailable: macOS Vision bridge is not installed]"

    image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(path))
    if not image:
        return "[Unable to parse image]"

    representations = image.representations()
    if not representations:
        return "[Unable to parse image]"

    cg_image = representations[0].CGImage()
    if not cg_image:
        return "[Unable to parse image]"

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    try:
        request.setRecognitionLanguages_(["zh-Hans", "en-US"])
        request.setUsesLanguageCorrection_(True)
    except Exception:
        pass

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, {})
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        return f"[OCR failed: {error}]"

    observations = request.results() or []
    text_parts: List[str] = []
    for observation in observations:
        try:
            candidates = observation.topCandidates_(1)
            if candidates:
                text = candidates[0].string()
                if text:
                    text_parts.append(str(text))
        except Exception:
            try:
                text = observation.text()
                if text:
                    text_parts.append(str(text))
            except Exception:
                continue

    return "\n".join(text_parts) if text_parts else "[No text recognized]"


def extract_image_labels(path: Path, *, min_confidence: float = 0.12, max_labels: int = 8) -> List[str]:
    """Return coarse visual labels from macOS Vision image classification."""

    try:
        import AppKit  # type: ignore
        import Vision  # type: ignore
    except ImportError:
        return []

    image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(path))
    if not image:
        return []

    representations = image.representations()
    if not representations:
        return []

    cg_image = representations[0].CGImage()
    if not cg_image:
        return []

    labels: List[str] = []

    def add_label(identifier: str, confidence: float) -> None:
        if confidence < min_confidence:
            return
        cleaned = identifier.replace("_", " ").strip()
        if cleaned and cleaned not in labels:
            labels.append(f"{cleaned} ({confidence:.2f})")

    for request_class_name in ("VNClassifyImageRequest", "VNRecognizeObjectsRequest"):
        if len(labels) >= max_labels:
            break
        request_class = getattr(Vision, request_class_name, None)
        if request_class is None:
            continue
        try:
            request = request_class.alloc().init()
            handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, {})
            ok, _ = handler.performRequests_error_([request], None)
            if not ok:
                continue
            for result in request.results() or []:
                if len(labels) >= max_labels:
                    break
                if hasattr(result, "identifier") and result.identifier():
                    add_label(str(result.identifier()), float(result.confidence()))
                elif hasattr(result, "labels"):
                    for label in result.labels() or []:
                        if len(labels) >= max_labels:
                            break
                        add_label(str(label.identifier()), float(label.confidence()))
        except Exception:
            continue

    return labels[:max_labels]


def _image_metadata(path: Path) -> List[str]:
    lines: List[str] = []
    try:
        size = path.stat().st_size
        lines.append(f"File size: {size} bytes")
    except OSError:
        pass

    try:
        import AppKit  # type: ignore

        image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(path))
        if image:
            image_size = image.size()
            lines.append(f"Dimensions: {int(image_size.width)} x {int(image_size.height)} px")
    except Exception:
        pass
    return lines


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n[truncated]"


def _is_no_text_ocr(text: str) -> bool:
    stripped = (text or "").strip()
    no_text_prefixes = (
        "[No text recognized]",
        "[OCR unavailable",
        "[OCR error",
        "[OCR failed",
        "[Unable to parse image]",
    )
    return not stripped or any(stripped.startswith(prefix) for prefix in no_text_prefixes)


def build_openai_user_content(
    text: str,
    attachments: Optional[Iterable[Any]],
    *,
    max_image_bytes: int = 10 * 1024 * 1024,
) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    if text:
        blocks.append({"type": "text", "text": text})

    for attachment in attachments or []:
        if bool(_field(attachment, "is_folder", _field(attachment, "isFolder", False))):
            continue

        mime_type = (_attachment_mime_type(attachment) or "").lower()
        if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            continue

        raw_path = _field(attachment, "path")
        if not raw_path:
            continue

        path = _safe_local_path(raw_path)
        if not path:
            continue
        if not path.is_file():
            continue

        try:
            size = path.stat().st_size
            if size > max_image_bytes:
                blocks.append({
                    "type": "text",
                    "text": f"[Image attachment omitted because it is larger than {max_image_bytes} bytes: {path.name}]",
                })
                continue
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError:
            continue

        blocks.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{encoded}",
            },
        })

    if not blocks:
        blocks.append({"type": "text", "text": text or ""})
    return blocks


def convert_openai_content_to_anthropic(content: Any) -> Any:
    if not isinstance(content, list):
        return content

    converted: List[Dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            converted.append({"type": "text", "text": str(block)})
            continue

        if block.get("type") == "text":
            converted.append({"type": "text", "text": str(block.get("text", ""))})
            continue

        if block.get("type") == "image_url":
            image_url = block.get("image_url") or {}
            url = str(image_url.get("url", ""))
            if not url.startswith("data:") or ";base64," not in url:
                continue
            header, data = url.split(";base64,", 1)
            media_type = header.removeprefix("data:") or "image/png"
            converted.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data,
                },
            })
            continue

        converted.append(block)

    return converted
