import base64

from across_agents_assistant.attachments import (
    _safe_local_path,
    append_image_attachment_context,
    build_image_attachment_context,
    build_openai_user_content,
    convert_openai_content_to_anthropic,
    has_image_attachments,
    model_supports_vision,
)


def test_build_openai_user_content_encodes_image_attachment(tmp_path):
    image_path = tmp_path / "screen.png"
    image_path.write_bytes(b"fake-png-bytes")

    content = build_openai_user_content(
        "Look at this.",
        [{
            "name": "screen.png",
            "path": str(image_path),
            "is_folder": False,
            "kind": "screenshot",
            "mime_type": "image/png",
        }],
    )

    assert content[0] == {"type": "text", "text": "Look at this."}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == (
        "data:image/png;base64," + base64.b64encode(b"fake-png-bytes").decode("ascii")
    )


def test_safe_local_path_rejects_control_characters():
    assert _safe_local_path("/tmp/screen.png\nsecret") is None
    assert _safe_local_path("/tmp/screen.png\x00secret") is None


def test_has_image_attachments_ignores_non_image_files(tmp_path):
    text_path = tmp_path / "notes.txt"
    text_path.write_text("hello")

    assert not has_image_attachments([{
        "name": "notes.txt",
        "path": str(text_path),
        "is_folder": False,
        "mime_type": "text/plain",
    }])


def test_build_image_attachment_context_adds_ocr_fallback(tmp_path):
    image_path = tmp_path / "screen.png"
    image_path.write_bytes(b"fake-png-bytes")

    context = build_image_attachment_context(
        [{
            "name": "screen.png",
            "path": str(image_path),
            "is_folder": False,
            "kind": "screenshot",
            "mime_type": "image/png",
        }],
        ocr_fn=lambda path: "class TritonPythonModel:\n    def initialize(self, args): ...",
    )

    assert "Attached image context follows" in context
    assert "screen.png" in context
    assert "class TritonPythonModel" in context
    assert "Do not ask the user to re-specify the image" in context


def test_build_image_attachment_context_omits_paths_by_default(tmp_path):
    image_path = tmp_path / "screen.png"
    image_path.write_bytes(b"fake-png-bytes")

    context = build_image_attachment_context(
        [{
            "name": "screen.png",
            "path": str(image_path),
            "is_folder": False,
            "kind": "screenshot",
            "mime_type": "image/png",
        }],
        ocr_fn=lambda path: "visible text",
    )
    path_context = build_image_attachment_context(
        [{
            "name": "screen.png",
            "path": str(image_path),
            "is_folder": False,
            "kind": "screenshot",
            "mime_type": "image/png",
        }],
        include_paths=True,
        ocr_fn=lambda path: "visible text",
    )

    assert str(image_path) not in context
    assert f"Local path: {image_path}" in path_context


def test_append_image_attachment_context_keeps_user_text_first():
    enriched = append_image_attachment_context("What does this mean?", "Image 1 OCR: foo")

    assert enriched.startswith("What does this mean?")
    assert "[Attached Image Context]" in enriched
    assert "Image 1 OCR: foo" in enriched


def test_model_supports_vision_uses_explicit_flag_or_model_name():
    assert model_supports_vision({"model": "deepseek-chat"}) is False
    assert model_supports_vision({"model": "MiniMax-M2.7"}) is False
    assert model_supports_vision({"model": "gpt-4o"}) is True
    assert model_supports_vision({"model": "qwen2.5-vl-72b"}) is True
    assert model_supports_vision({"model": "custom-text", "supports_vision": True}) is True


def test_convert_openai_content_to_anthropic_image_blocks():
    content = [
        {"type": "text", "text": "hello"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,Zm9v"}},
    ]

    converted = convert_openai_content_to_anthropic(content)

    assert converted == [
        {"type": "text", "text": "hello"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "Zm9v",
            },
        },
    ]
