OPENCLAW_AGENT_ID = "openclaw"
LOCAL_AGENT_ID = OPENCLAW_AGENT_ID
LEGACY_LOCAL_AGENT_ID = "local"
LOCAL_CLI_AGENT_IDS = (OPENCLAW_AGENT_ID, "hermes", "claude")

LEGACY_AGENT_ID_MAP = {
    LEGACY_LOCAL_AGENT_ID: LOCAL_AGENT_ID,
}


def normalize_agent_id(agent_id: str | None) -> str | None:
    if agent_id is None:
        return None
    return LEGACY_AGENT_ID_MAP.get(agent_id, agent_id)
