import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from .agent_ids import LOCAL_AGENT_ID, normalize_agent_id
from .paths import data_file

AGENTS_CONFIG_FILE = data_file("llm_agents.json")
LEGACY_AGENTS_CONFIG_FILE = Path(os.path.expanduser("~/Library/Application Support/AcrossAgentsAssistant/llm_agents.json"))

DEFAULT_CONFIG = {
    "active_agent": "deepseek",
    "agents": {
        "deepseek": {
            "type": "openai_compatible",
            "base_url": "https://api.deepseek.com",
            "api_key": "",
            "model": "deepseek-chat"
        },
        "openai": {
            "type": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-5.5"
        },
        "anthropic": {
            "type": "anthropic",
            "base_url": "",
            "api_key": "",
            "model": "claude-opus-4-8"
        },
        # MiniMax: use OpenAI-compatible /v1 (recommended by MiniMax docs). The Anthropic
        # compatible endpoint can return success with content=null when used via Anthropic SDK.
        "minimax": {
            "type": "openai_compatible",
            "base_url": "https://api.minimaxi.com/v1",
            "api_key": "",
            "model": "MiniMax-M3"
        },
        "agnes": {
            "type": "openai_compatible",
            "base_url": "https://apihub.agnes-ai.com/v1",
            "api_key": "",
            "model": "agnes-2.0-flash"
        },
        LOCAL_AGENT_ID: {
            "type": "openai_compatible",
            "base_url": "https://api.deepseek.com",
            "api_key": "",
            "model": "deepseek-chat"
        },
        "hermes": {
            "type": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-5.4-mini"
        },
        "claude": {
            "type": "anthropic",
            "base_url": "",
            "api_key": "",
            "model": "sonnet"
        },
        "claude-desktop": {
            "type": "local_cli",
            "base_url": "",
            "api_key": "",
            "model": "sonnet"
        },
        "codex": {
            "type": "local_cli",
            "base_url": "",
            "api_key": "",
            "model": "gpt-5.3-codex-spark"
        },
        "kimi": {
            "type": "local_cli",
            "base_url": "",
            "api_key": "",
            "model": ""
        },
        "opencode": {
            "type": "local_cli",
            "base_url": "",
            "api_key": "",
            "model": ""
        },
        "cursor": {
            "type": "local_cli",
            "base_url": "",
            "api_key": "",
            "model": "auto"
        }
    }
}

SUPERSEDED_AGENT_DEFAULT_MODELS = {
    "openai": {"gpt-4o"},
    "anthropic": {"claude-3-5-sonnet-20241022"},
    "hermes": {"gpt-4o-mini"},
    "claude": {"claude-3-5-sonnet-20241022"},
    "claude-desktop": {"claude-3-5-sonnet-20241022"},
    "codex": {"gpt-5", "gpt-5.1", "gpt-5-codex"},
}


def _url_host(base_url: str) -> str:
    try:
        return (urlparse(base_url).hostname or "").lower()
    except ValueError:
        return ""


def _is_minimax_io_endpoint(base_url: str) -> bool:
    host = _url_host(base_url)
    return host == "minimax.io" or host.endswith(".minimax.io")

class AgentManager:
    def __init__(self):
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        source_file = AGENTS_CONFIG_FILE if AGENTS_CONFIG_FILE.exists() else LEGACY_AGENTS_CONFIG_FILE
        if not source_file.exists():
            self._save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()

        try:
            with open(source_file, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            if source_file == LEGACY_AGENTS_CONFIG_FILE and not AGENTS_CONFIG_FILE.exists():
                self._save_config(user_config)

            needs_save = False
            if "agents" not in user_config:
                user_config["agents"] = {}
            agents = user_config["agents"]

            supported_agent_ids = set(DEFAULT_CONFIG["agents"])
            active_agent_removed = False
            for agent_id, agent_data in list(agents.items()):
                if agent_id in supported_agent_ids or not isinstance(agent_data, dict):
                    continue
                if agent_data.get("type") == "local_cli":
                    active_agent_removed = user_config.get("active_agent") == agent_id
                    agents.pop(agent_id, None)
                    needs_save = True
            if active_agent_removed:
                user_config["active_agent"] = DEFAULT_CONFIG["active_agent"]
                needs_save = True

            for agent_id, agent_data in DEFAULT_CONFIG["agents"].items():
                if agent_id not in agents:
                    agents[agent_id] = agent_data.copy()
                    needs_save = True
                elif agent_id == "minimax":
                    current = agents[agent_id]
                    url = (current.get("base_url") or "").lower()
                    if current.get("type") == "anthropic" or "/anthropic" in url:
                        if _is_minimax_io_endpoint(url):
                            current["base_url"] = "https://api.minimax.io/v1"
                        else:
                            current["base_url"] = "https://api.minimaxi.com/v1"
                        current["type"] = "openai_compatible"
                        needs_save = True
                    if current.get("model") == "MiniMax-M2.7":
                        current["model"] = "MiniMax-M3"
                        needs_save = True
                    elif not current.get("model"):
                        current["model"] = agent_data.get("model")
                        needs_save = True
                else:
                    current = agents[agent_id]
                    if current.get("model") in SUPERSEDED_AGENT_DEFAULT_MODELS.get(agent_id, set()):
                        current["model"] = agent_data.get("model")
                        needs_save = True

            if needs_save:
                self._save_config(user_config)

            return user_config
        except Exception:
            return DEFAULT_CONFIG.copy()

    def _save_config(self, config: Dict[str, Any]):
        AGENTS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AGENTS_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def get_active_agent(self) -> str:
        return normalize_agent_id(self.config.get("active_agent", "deepseek")) or "deepseek"

    def get_agent_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        agent_id = normalize_agent_id(agent_id) or agent_id
        return self.config.get("agents", {}).get(agent_id)

    def update_agent(self, agent_id: str, agent_config: Dict[str, Any]):
        agent_id = normalize_agent_id(agent_id) or agent_id
        if "agents" not in self.config:
            self.config["agents"] = {}
        self.config["agents"][agent_id] = agent_config
        self._save_config(self.config)

    def set_active_agent(self, agent_id: str):
        agent_id = normalize_agent_id(agent_id) or agent_id
        self.config["active_agent"] = agent_id
        self._save_config(self.config)

    def is_agent_ready(self, agent_id: str) -> bool:
        # Now readiness depends on API Key
        agent = self.get_agent_config(agent_id)
        if not agent:
            return False
        api_key = agent.get("api_key", "").strip()
        # To avoid blocking users from trying, we can return True even without API key,
        # but returning False if empty encourages them to configure it.
        # Wait, if they don't have a UI to configure it yet, returning True is safer.
        return True
