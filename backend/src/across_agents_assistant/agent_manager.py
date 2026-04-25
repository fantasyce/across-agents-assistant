import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

AGENTS_CONFIG_FILE = Path(os.path.expanduser("~/Library/Application Support/AcrossAgentsAssistant/llm_agents.json"))

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
            "model": "gpt-4o"
        },
        "anthropic": {
            "type": "anthropic",
            "base_url": "",
            "api_key": "",
            "model": "claude-3-5-sonnet-20241022"
        },
        # For backward compatibility with macOS-Client hardcoded IDs
                "minimax": {
            "type": "anthropic",
            "base_url": "https://api.minimaxi.com/anthropic",
            "api_key": "",
            "model": "MiniMax-M2.7"
        },
        "openclaw": {
            "type": "openai_compatible",
            "base_url": "https://api.deepseek.com",
            "api_key": "",
            "model": "deepseek-chat"
        },
        "hermes": {
            "type": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-4o-mini"
        },
        "claude": {
            "type": "anthropic",
            "base_url": "",
            "api_key": "",
            "model": "claude-3-5-sonnet-20241022"
        }
    }
}

class AgentManager:
    def __init__(self):
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        if not AGENTS_CONFIG_FILE.exists():
            self._save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
            
        try:
            with open(AGENTS_CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                
            needs_save = False
            if "agents" not in user_config:
                user_config["agents"] = {}
                
            for agent_id, agent_data in DEFAULT_CONFIG["agents"].items():
                if agent_id not in user_config["agents"]:
                    user_config["agents"][agent_id] = agent_data.copy()
                    needs_save = True
                elif agent_id == "minimax":
                    # Force update minimax config to new anthropic compatible endpoint
                    current = user_config["agents"][agent_id]
                    if current.get("type") != "anthropic" or current.get("model") != "MiniMax-M2.7":
                        user_config["agents"][agent_id]["type"] = "anthropic"
                        user_config["agents"][agent_id]["base_url"] = "https://api.minimaxi.com/anthropic"
                        user_config["agents"][agent_id]["model"] = "MiniMax-M2.7"
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
        return self.config.get("active_agent", "deepseek")
        
    def get_agent_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        return self.config.get("agents", {}).get(agent_id)
        
    def update_agent(self, agent_id: str, agent_config: Dict[str, Any]):
        if "agents" not in self.config:
            self.config["agents"] = {}
        self.config["agents"][agent_id] = agent_config
        self._save_config(self.config)
        
    def set_active_agent(self, agent_id: str):
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
