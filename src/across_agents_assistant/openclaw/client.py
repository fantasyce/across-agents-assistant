import json
import os
import subprocess
import time
import re
from typing import Optional
from ..agent_manager import AgentManager

class OpenClawReply:
    def __init__(self, text: str, session_id: Optional[str] = None, elapsed_sec: float = 0.0):
        self.text = text
        self.session_id = session_id
        self.elapsed_sec = elapsed_sec

class UniversalAgentClient:
    def __init__(self, manager: AgentManager):
        self.manager = manager
        # Cache environments for agents
        self.envs = {}
        
        try:
            result = subprocess.run(
                ["/bin/zsh", "-l", "-c", "echo $PATH"],
                capture_output=True, text=True
            )
            real_path = result.stdout.strip().split("\n")[-1]
            path_parts = [p for p in real_path.split(":") if p]
            extras = [
                "/opt/homebrew/bin",
                "/usr/local/bin",
                os.path.expanduser("~/.local/bin"),
                os.path.expanduser("~/.cargo/bin"),
            ]
            for extra in extras:
                if os.path.isdir(extra) and extra not in path_parts:
                    path_parts.insert(0, extra)
            self.base_env = os.environ.copy()
            self.base_env["PATH"] = ":".join(path_parts)
            self.base_env["HOME"] = os.path.expanduser("~")
        except Exception as e:
            self.base_env = os.environ.copy()
            import logging
            logging.getLogger("across_agents_assistant").error(f"Failed to get real PATH: {e}")

    def initialize(self):
        # Kept for backward compatibility, not needed anymore
        pass

    def send(self, message: str, session_id: Optional[str] = None, use_current: bool = True, target_agent: Optional[str] = None) -> OpenClawReply:
        t0 = time.time()
        
        agent_id = target_agent or self.manager.get_active_agent()
        
        if not self.manager.is_agent_ready(agent_id):
            return OpenClawReply(
                text=f"本地尚未配置 {agent_id} 智能体，请在菜单栏点击【配置智能体】进行设置。",
                session_id=session_id,
                elapsed_sec=time.time() - t0
            )
            
        config = self.manager.get_agent_config(agent_id)
        executable_path = config.get("executable_path")
        args_template = config.get("args_template", [])
        output_format = config.get("output_format", "raw")

        # Build args from template
        args = [executable_path]
        for arg in args_template:
            if "{message}" in arg:
                args.append(arg.replace("{message}", message))
            else:
                args.append(arg)

        # Add session id logic only for openclaw as fallback
        if agent_id == "openclaw" and session_id and not use_current:
            args.extend(["--session-id", session_id])

        try:
            # Check if there is a file path in the message, if so, use its directory as cwd
            import os
            import re
            
            workspace_dir = os.path.expanduser("~/Library/Application Support/AcrossAgentsAssistant/Workspace")
            
            # Very basic heuristic: if the message contains an absolute path to a file or directory
            # try to use its directory as the workspace so the agent can access it
            path_match = re.search(r'(/Users/[^ \n]+)', message)
            if path_match:
                potential_path = path_match.group(1).strip()
                if os.path.exists(potential_path):
                    if os.path.isdir(potential_path):
                        workspace_dir = potential_path
                    else:
                        workspace_dir = os.path.dirname(potential_path)
            
            os.makedirs(workspace_dir, exist_ok=True)
            
            result = subprocess.run(args, env=self.base_env, capture_output=True, text=True, cwd=workspace_dir)
            elapsed = time.time() - t0
        except Exception as e:
            import logging
            logging.getLogger("across_agents_assistant").error(f"Failed to execute {agent_id}: {e}")
            return OpenClawReply(
                text=f"抱歉，处理失败。我无法连接到 {agent_id}，请检查配置是否正确。", 
                session_id=session_id, 
                elapsed_sec=time.time() - t0
            )

        # Parse output based on configured format
        ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")
        clean = ansi_pattern.sub("", result.stdout)
        clean_err = ansi_pattern.sub("", result.stderr or "").strip()
        if result.returncode != 0:
            msg = clean.strip() or clean_err
            if not msg:
                msg = f"{agent_id} 执行失败 (exit code: {result.returncode})"
            return OpenClawReply(text=msg, session_id=session_id, elapsed_sec=elapsed)
        if (not clean or not clean.strip()) and clean_err:
            clean = clean_err
        
        if output_format == "json":
            start_idx = clean.find("{")
            if start_idx == -1:
                import logging
                logging.getLogger("across_agents_assistant").error(f"{agent_id} 返回了非 JSON 数据. Output: {result.stdout}\nErrors: {result.stderr}")
                return OpenClawReply(text="抱歉，大脑返回了无法解析的信息。", session_id=session_id, elapsed_sec=elapsed)
                
            try:
                data = json.loads(clean[start_idx:])
                
                # Default parsing logic
                reply_text = data.get("text")
                returned_session = data.get("session_id", session_id)
                
                # Special parsing for OpenClaw's nested structure
                if agent_id == "openclaw" or "result" in data:
                    payloads = data.get("result", {}).get("payloads", [])
                    reply_text = ""
                    for p in payloads:
                        if p.get("text"):
                            reply_text += p["text"]
                    if not reply_text:
                        reply_text = data.get("result", {}).get("text")
                        
                    returned_session = (
                        data.get("result", {})
                        .get("meta", {})
                        .get("agentMeta", {})
                        .get("sessionId")
                        or returned_session
                    )
                
                if not reply_text:
                    reply_text = "抱歉，没有返回文本内容。"
                    
                return OpenClawReply(text=reply_text, session_id=returned_session, elapsed_sec=elapsed)
            except json.JSONDecodeError as e:
                import logging
                logging.getLogger("across_agents_assistant").error(f"Failed to parse JSON: {e}")
                return OpenClawReply(text="抱歉，大脑返回了格式错误的信息。", session_id=session_id, elapsed_sec=elapsed)
        else:
            # Raw output parsing (like Hermes or Claude)
            text = clean.strip()
            
            # Remove any prefix like "Hermes: " if needed, or just return raw
            # For hermes, strip the trailing session_id string
            session_id_idx = text.rfind("session_id:")
            if session_id_idx != -1:
                # Try to extract the session_id
                extracted_session = text[session_id_idx:].replace("session_id:", "").strip()
                if extracted_session:
                    session_id = extracted_session
                # Remove the session_id line from the spoken text
                text = text[:session_id_idx].strip()
                
            return OpenClawReply(text=text if text else "抱歉，大脑没有返回任何内容。", session_id=session_id, elapsed_sec=elapsed)

# Backward compatibility alias
OpenClawClient = UniversalAgentClient
