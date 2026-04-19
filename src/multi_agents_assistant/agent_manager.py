import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

AGENTS_CONFIG_FILE = Path(os.path.expanduser("~/Library/Application Support/MultiAgentsAssistant/agents.json"))

DEFAULT_CONFIG = {
    "active_agent": "openclaw",
    "agents": {
        "openclaw": {
            "type": "builtin",
            "executable_path": "",
            "args_template": ["agent", "--agent", "main", "--message", "用户说: {message}", "--json"],
            "output_format": "json"
        },
        "hermes": {
            "type": "builtin",
            "executable_path": "",
            "args_template": ["chat", "-q", "{message}", "-Q"],
            "output_format": "raw"
        },
        "claude": {
            "type": "builtin",
            "executable_path": "",
            "args_template": ["-p", "{message}"],
            "output_format": "raw"
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
                
            # Merge missing builtin agents into user config
            needs_save = False
            if "agents" not in user_config:
                user_config["agents"] = {}
                
            # Remove aider if it exists in user config
            if "aider" in user_config["agents"]:
                del user_config["agents"]["aider"]
                needs_save = True
                if user_config.get("active_agent") == "aider":
                    user_config["active_agent"] = "openclaw"
                
            for agent_id, agent_data in DEFAULT_CONFIG["agents"].items():
                if agent_id not in user_config["agents"]:
                    user_config["agents"][agent_id] = agent_data.copy()
                    needs_save = True
                else:
                    # Update args_template if builtin args change
                    if user_config["agents"][agent_id].get("type") == "builtin":
                        if user_config["agents"][agent_id].get("args_template") != agent_data.get("args_template"):
                            user_config["agents"][agent_id]["args_template"] = agent_data.get("args_template")
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
        return self.config.get("active_agent", "openclaw")
        
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
        agent = self.get_agent_config(agent_id)
        if not agent:
            return False
        path = agent.get("executable_path", "")
        return bool(path and os.path.exists(path) and os.access(path, os.X_OK))
