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
        self.active_processes = {} # session_id -> subprocess.Popen
        
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

    def cancel(self, session_id: str) -> bool:
        """Cancel a running agent request for a specific session."""
        process = self.active_processes.get(session_id)
        if process:
            try:
                process.kill() # Force kill to ensure it stops immediately
                return True
            except Exception as e:
                import logging
                logging.getLogger("across_agents_assistant").error(f"Failed to cancel process for {session_id}: {e}")
        return False

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

        # Add session id logic only for openclaw
        if agent_id == "openclaw" and session_id and not use_current:
            args.extend(["--session-id", session_id])

        try:
            # Check if there is a file path in the message, if so, we handle it
            import os
            import re
            
            workspace_dir = os.path.expanduser("~/Library/Application Support/AcrossAgentsAssistant/Workspace")
            os.makedirs(workspace_dir, exist_ok=True)
            
            # First expand any ~ in the message
            # e.g., ~/Documents/service -> /Users/didi/Documents/service
            expanded_message = re.sub(r'(~/[^ "\'\n]*)', lambda m: os.path.expanduser(m.group(1)), message)
            
            # Parse attached_files block if present
            attached_files_match = re.search(r'<attached_files>\n(.*?)\n</attached_files>', expanded_message, re.DOTALL)
            inline_files_match = re.search(r'\["(/Users/[^"]+)"\]', expanded_message)
            
            if attached_files_match:
                try:
                    files_json = attached_files_match.group(1)
                    attached_files = json.loads(files_json)
                    if attached_files and isinstance(attached_files, list) and len(attached_files) > 0:
                        first_path = attached_files[0]
                        if os.path.exists(first_path):
                            if os.path.isdir(first_path):
                                workspace_dir = first_path
                            else:
                                workspace_dir = os.path.dirname(first_path)
                            
                            # For claude/dcc
                            if agent_id in ["claude", "dcc"]:
                                args.extend(["--add-dir", workspace_dir])
                except:
                    pass
            elif inline_files_match:
                try:
                    first_path = inline_files_match.group(1)
                    if os.path.exists(first_path):
                        if os.path.isdir(first_path):
                            workspace_dir = first_path
                        else:
                            workspace_dir = os.path.dirname(first_path)
                        
                        # For claude/dcc
                        if agent_id in ["claude", "dcc"]:
                            args.extend(["--add-dir", workspace_dir])
                except:
                    pass
            else:
                path_match = re.search(r'(/Users/[^ "\'\n]+)', expanded_message)
                if path_match:
                    potential_path = path_match.group(1).strip()
                    target_dir = None
                    
                    if os.path.exists(potential_path):
                        if os.path.isdir(potential_path):
                            target_dir = potential_path
                        else:
                            target_dir = os.path.dirname(potential_path)
                    else:
                        # sometimes the match includes a trailing punctuation mark, try stripping it
                        potential_path = potential_path.rstrip('.,:;!?')
                        if os.path.exists(potential_path):
                            if os.path.isdir(potential_path):
                                target_dir = potential_path
                            else:
                                target_dir = os.path.dirname(potential_path)
                                
                    if target_dir:
                        # For claude/dcc, changing cwd breaks their session because they scope sessions by project dir!
                        # Instead, we must use the --add-dir flag to bypass the sandbox while keeping the session stable.
                        if agent_id in ["claude", "dcc"]:
                            args.extend(["--add-dir", target_dir])
                        else:
                            workspace_dir = target_dir
            
            # We use Popen instead of run so we can store the process and cancel it
            process = subprocess.Popen(
                args, 
                env=self.base_env, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                cwd=workspace_dir
            )
            
            if session_id:
                self.active_processes[session_id] = process
                
            stdout, stderr = process.communicate()
            
            if session_id and session_id in self.active_processes:
                del self.active_processes[session_id]
                
            elapsed = time.time() - t0
        except Exception as e:
            import logging
            if session_id and session_id in self.active_processes:
                del self.active_processes[session_id]
            logging.getLogger("across_agents_assistant").error(f"Failed to execute {agent_id}: {e}")
            return OpenClawReply(
                text=f"抱歉，处理失败或已被取消。无法连接到 {agent_id}。", 
                session_id=session_id, 
                elapsed_sec=time.time() - t0
            )

        # Parse output based on configured format
        ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")
        clean = ansi_pattern.sub("", stdout)
        clean_err = ansi_pattern.sub("", stderr or "").strip()
        
        # dcc sometimes returns non-zero code even when it replies correctly,
        # but if the output is just an error, we should return it.
        # We'll first check if there is a valid output payload.
        is_error = process.returncode != 0
        if is_error:
            # Special case for claude/dcc: "No conversation found" usually goes to stdout or stderr
            msg = clean.strip() or clean_err
            if "No conversation found" in msg:
                # If the session was deleted or invalid, we should clear it so next time we start fresh
                return OpenClawReply(
                    text=f"会话已失效或未找到。请发送新消息，我将为你开启一个新的会话。\n\n(底层报错: {msg})", 
                    session_id=None, # Clear the session ID!
                    elapsed_sec=time.time() - t0
                )
            
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
            
            # Clean up DCC / Claude Code verbose headers if present
            header_end_marker = "----------------------------------------"
            if "DCC by DiDi" in text or "Claude Code" in text:
                parts = text.split(header_end_marker)
                if len(parts) >= 3:
                    # We do NOT extract the Session ID from the text!
                    # DCC's wrapper generates a fake UUID that is printed here, 
                    # but the actual Claude session is saved under the UUID we generated and passed via --session-id.
                    
                    # Strip the header out so the UI looks clean
                    text = header_end_marker.join(parts[2:]).strip()

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

    async def send_stream(self, message: str, session_id: Optional[str] = None, target_agent: Optional[str] = None):
        """Stream response from agent. Yields text chunks for SSE."""
        import asyncio
        import json

        agent_id = target_agent or self.manager.get_active_agent()

        # Check if agent supports streaming
        supports_streaming = agent_id in ["claude", "hermes"]

        if not supports_streaming:
            # Fall back to blocking send for OpenClaw
            reply = self.send(message, session_id=session_id, target_agent=target_agent)
            yield reply.text
            return

        # For Claude/Hermes, use streaming mode
        config = self.manager.get_agent_config(agent_id)
        executable_path = config.get("executable_path")

        # Build args with streaming flags
        args = [executable_path]

        if agent_id == "claude":
            # Claude Code: use -p for print mode with streaming
            args.extend(["-p", "--output-format", "stream-json", message])
        elif agent_id == "hermes":
            # Hermes: use -q with stream-json output
            args.extend(["chat", "-q", message, "--output-format", "stream-json", "--include-partial-messages"])

        # Run with asyncio subprocess for async streaming
        process = await asyncio.create_subprocess_exec(
            *args,
            env=self.base_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        if session_id:
            self.active_processes[session_id] = process

        # Read line by line (each line is a JSON object for stream-json)
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                line = line.decode('utf-8').strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if "content" in data:
                        yield data["content"]
                except json.JSONDecodeError:
                    continue
        finally:
            # Wait for process to complete
            await process.wait()
            if session_id and session_id in self.active_processes:
                del self.active_processes[session_id]

# Backward compatibility alias
OpenClawClient = UniversalAgentClient
