from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .config import POISONED_OUTPUT_MAX_LEN


class OutputClassification(str, Enum):
    NORMAL = "normal"
    POISONED_TEXT_TOOL_MENTION = "poisoned_text_tool_mention"
    ITERATION_LIMIT = "iteration_limit"
    EMPTY_OUTPUT = "empty_output"


@dataclass
class ProcessedResponse:
    original_text: Optional[str]
    original_tool_calls: list
    classification: OutputClassification
    should_retry: bool
    retry_count: int = 0
    recovery_prompt: Optional[str] = None


# Markers that indicate the LLM mentioned a tool in plain text but did not
# emit structured tool_calls.  Only checked when tool_calls is empty and
# the text is short enough to avoid false positives on long explanations.
_POISONED_MARKERS = [
    "请求调用工具",
    "我需要调用",
    "我将调用",
    "让我调用",
    "正在调用工具",
    "call the tool",
    "invoke the tool",
    "use the tool",
]

_ITERATION_LIMIT_MARKERS = [
    "i reached the iteration limit",
    "iteration limit reached",
    "达到迭代限制",
    "迭代次数已达上限",
]


def post_process_llm_response(reply) -> ProcessedResponse:
    """Inspect an OrchestratorResponse for degenerate / poisoned output patterns.

    Args:
        reply: An object with ``text`` (Optional[str]) and ``tool_calls`` (list).

    Returns:
        ProcessedResponse describing the classification and whether a retry
        should be attempted.
    """
    text = (reply.text or "").strip()
    tool_calls = reply.tool_calls or []

    # If there are structured tool calls, trust them and skip heuristics.
    if tool_calls:
        return ProcessedResponse(
            original_text=reply.text,
            original_tool_calls=tool_calls,
            classification=OutputClassification.NORMAL,
            should_retry=False,
        )

    # Empty output
    if not text:
        return ProcessedResponse(
            original_text=reply.text,
            original_tool_calls=[],
            classification=OutputClassification.EMPTY_OUTPUT,
            should_retry=True,
            retry_count=2,
            recovery_prompt="请提供有用的回复或调用合适的工具来完成任务。",
        )

    # Iteration limit marker
    lower = text.lower()
    for marker in _ITERATION_LIMIT_MARKERS:
        if marker in lower:
            return ProcessedResponse(
                original_text=reply.text,
                original_tool_calls=[],
                classification=OutputClassification.ITERATION_LIMIT,
                should_retry=False,
                recovery_prompt=None,
            )

    # Poisoned output: text mentions tool intent but no structured tool_calls.
    # Only flag when the text is short to avoid false positives.
    if len(text) <= POISONED_OUTPUT_MAX_LEN:
        for marker in _POISONED_MARKERS:
            if marker in text:
                return ProcessedResponse(
                    original_text=reply.text,
                    original_tool_calls=[],
                    classification=OutputClassification.POISONED_TEXT_TOOL_MENTION,
                    should_retry=True,
                    retry_count=2,
                    recovery_prompt=(
                        "你刚才的回复中提到了工具调用，但没有使用正确的工具调用格式。"
                        "请使用标准的 function_call / tool_calls 格式来调用工具，"
                        "而不是在普通文本中描述工具调用意图。"
                    ),
                )

    return ProcessedResponse(
        original_text=reply.text,
        original_tool_calls=[],
        classification=OutputClassification.NORMAL,
        should_retry=False,
    )
