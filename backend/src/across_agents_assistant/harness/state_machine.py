import logging
from enum import Enum
from typing import List, Tuple

logger = logging.getLogger("across_agents_assistant.harness")


class ChatToolLoopState(str, Enum):
    THINKING = "thinking"
    TOOL_EXECUTING = "tool_executing"
    WAIT_APPROVAL = "wait_approval"
    ERROR_CLASSIFY = "error_classify"
    RECOVER = "recover"
    COMPACTING = "compacting"
    DONE = "done"


# Valid state transitions
_VALID_TRANSITIONS = {
    ChatToolLoopState.THINKING: {
        ChatToolLoopState.THINKING,
        ChatToolLoopState.TOOL_EXECUTING,
        ChatToolLoopState.WAIT_APPROVAL,
        ChatToolLoopState.ERROR_CLASSIFY,
        ChatToolLoopState.DONE,
    },
    ChatToolLoopState.TOOL_EXECUTING: {
        ChatToolLoopState.THINKING,
        ChatToolLoopState.WAIT_APPROVAL,
        ChatToolLoopState.ERROR_CLASSIFY,
        ChatToolLoopState.DONE,
    },
    ChatToolLoopState.WAIT_APPROVAL: {
        ChatToolLoopState.TOOL_EXECUTING,
        ChatToolLoopState.DONE,
    },
    ChatToolLoopState.ERROR_CLASSIFY: {
        ChatToolLoopState.RECOVER,
        ChatToolLoopState.DONE,
    },
    ChatToolLoopState.RECOVER: {
        ChatToolLoopState.THINKING,
        ChatToolLoopState.DONE,
    },
    ChatToolLoopState.COMPACTING: {
        ChatToolLoopState.THINKING,
        ChatToolLoopState.DONE,
    },
    ChatToolLoopState.DONE: set(),  # Terminal state
}


class ChatToolLoopStateMachine:
    """Explicit state machine for the host chat/tool execution flow."""

    def __init__(self, session_id: str = "", agent_id: str = ""):
        self._current = ChatToolLoopState.THINKING
        self._history: List[Tuple[ChatToolLoopState, float]] = [
            (ChatToolLoopState.THINKING, __import__("time").time())
        ]
        self._session_id = session_id
        self._agent_id = agent_id

    @property
    def current_state(self) -> ChatToolLoopState:
        return self._current

    def transition(self, to_state: ChatToolLoopState) -> None:
        """Transition to a new state, validating the transition is legal."""
        if to_state not in _VALID_TRANSITIONS.get(self._current, set()):
            raise ValueError(
                f"Invalid state transition: {self._current.value} -> {to_state.value}"
            )

        from_state = self._current
        self._current = to_state
        timestamp = __import__("time").time()
        self._history.append((to_state, timestamp))

        logger.debug(
            "Agent loop state transition [%s/%s]: %s -> %s",
            self._session_id,
            self._agent_id,
            from_state.value,
            to_state.value,
        )

    def get_state_history(self) -> List[Tuple[ChatToolLoopState, float]]:
        """Return the full state transition history."""
        return list(self._history)
