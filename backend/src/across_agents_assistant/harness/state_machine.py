import logging
from enum import Enum
from typing import List, Tuple

logger = logging.getLogger("across_agents_assistant.harness")


class AgentLoopState(str, Enum):
    THINKING = "thinking"
    TOOL_EXECUTING = "tool_executing"
    WAIT_APPROVAL = "wait_approval"
    ERROR_CLASSIFY = "error_classify"
    RECOVER = "recover"
    COMPACTING = "compacting"
    DONE = "done"


# Valid state transitions
_VALID_TRANSITIONS = {
    AgentLoopState.THINKING: {
        AgentLoopState.THINKING,
        AgentLoopState.TOOL_EXECUTING,
        AgentLoopState.WAIT_APPROVAL,
        AgentLoopState.ERROR_CLASSIFY,
        AgentLoopState.DONE,
    },
    AgentLoopState.TOOL_EXECUTING: {
        AgentLoopState.THINKING,
        AgentLoopState.WAIT_APPROVAL,
        AgentLoopState.ERROR_CLASSIFY,
        AgentLoopState.DONE,
    },
    AgentLoopState.WAIT_APPROVAL: {
        AgentLoopState.TOOL_EXECUTING,
        AgentLoopState.DONE,
    },
    AgentLoopState.ERROR_CLASSIFY: {
        AgentLoopState.RECOVER,
        AgentLoopState.DONE,
    },
    AgentLoopState.RECOVER: {
        AgentLoopState.THINKING,
        AgentLoopState.DONE,
    },
    AgentLoopState.COMPACTING: {
        AgentLoopState.THINKING,
        AgentLoopState.DONE,
    },
    AgentLoopState.DONE: set(),  # Terminal state
}


class AgentLoopStateMachine:
    """Explicit state machine for the Agent Loop execution flow."""

    def __init__(self, session_id: str = "", agent_id: str = ""):
        self._current = AgentLoopState.THINKING
        self._history: List[Tuple[AgentLoopState, float]] = [
            (AgentLoopState.THINKING, __import__("time").time())
        ]
        self._session_id = session_id
        self._agent_id = agent_id

    @property
    def current_state(self) -> AgentLoopState:
        return self._current

    def transition(self, to_state: AgentLoopState) -> None:
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

    def get_state_history(self) -> List[Tuple[AgentLoopState, float]]:
        """Return the full state transition history."""
        return list(self._history)
