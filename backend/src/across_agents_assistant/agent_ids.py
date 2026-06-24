OPENCLAW_AGENT_ID = "openclaw"
CLOUDCODE_DESKTOP_AGENT_ID = "cloudcode-desktop"
LOCAL_AGENT_ID = OPENCLAW_AGENT_ID
LOCAL_CLI_AGENT_IDS = (
    OPENCLAW_AGENT_ID,
    "hermes",
    "claude",
    CLOUDCODE_DESKTOP_AGENT_ID,
    "codex",
    "opencode",
    "cursor",
)


def normalize_agent_id(agent_id: str | None) -> str | None:
    if agent_id is None:
        return None
    return agent_id
