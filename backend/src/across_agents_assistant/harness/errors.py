class HarnessError(Exception):
    """Base exception for harness layer errors."""
    pass


class PoisonedOutputError(HarnessError):
    """LLM produced degenerate output (mentions tool in text but no structured tool_calls)."""
    def __init__(self, message: str, classification: str = "poisoned_output"):
        super().__init__(message)
        self.classification = classification


class InfraError(HarnessError):
    """Infrastructure error that may be retryable (timeout, connection, crash)."""
    def __init__(self, message: str, error_type: str = "infra"):
        super().__init__(message)
        self.error_type = error_type


class LogicError(HarnessError):
    """Logic error that should not be retried (bad args, data error)."""
    def __init__(self, message: str, error_type: str = "logic"):
        super().__init__(message)
        self.error_type = error_type


class UserCancelledError(HarnessError):
    """User cancelled the operation."""
    pass


class IterationLimitError(HarnessError):
    """Agent loop reached maximum iteration count."""
    pass


def classify_error(exc: Exception) -> HarnessError:
    """Classify a raw exception into a harness error type."""
    import httpx
    import subprocess

    if isinstance(exc, HarnessError):
        return exc

    # Infrastructure / retryable errors
    if isinstance(exc, httpx.TimeoutException):
        return InfraError(str(exc), error_type="timeout")
    if isinstance(exc, subprocess.CalledProcessError):
        return InfraError(str(exc), error_type="subprocess_crash")
    if isinstance(exc, OSError):
        return InfraError(str(exc), error_type="runtime_offline")
    if isinstance(exc, ConnectionError):
        return InfraError(str(exc), error_type="connection_error")

    # Logic / non-retryable errors
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return LogicError(str(exc), error_type="data_error")

    # Default: treat unknown as logic error (safer than infinite retry)
    return LogicError(str(exc), error_type="agent_logic_error")
