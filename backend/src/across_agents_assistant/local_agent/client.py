import json
import os
import signal
import subprocess
import time
import re
import threading
from pathlib import Path
from typing import Optional
from ..agent_manager import AgentManager
from ..agent_ids import CLAUDE_DESKTOP_AGENT_ID, LOCAL_AGENT_ID, normalize_agent_id
from ..credentials.validation import is_usable_secret
from ..paths import app_subdir

CLAUDE_FAMILY_AGENT_IDS = {"claude", CLAUDE_DESKTOP_AGENT_ID}


def default_local_agent_workspace() -> Path:
    return app_subdir("workspace")

class LocalAgentReply:
    def __init__(
        self,
        text: str,
        session_id: Optional[str] = None,
        elapsed_sec: float = 0.0,
        requires_approval: bool = False,
        approval_request: Optional[dict] = None,
        timed_out: bool = False,
        error_code: Optional[str] = None,
        timeout_kind: Optional[str] = None,
    ):
        self.text = text
        self.session_id = session_id
        self.elapsed_sec = elapsed_sec
        self.requires_approval = requires_approval
        self.approval_request = approval_request
        self.timed_out = timed_out
        self.error_code = error_code
        self.timeout_kind = timeout_kind

class UniversalAgentClient:
    def __init__(self, manager: AgentManager):
        self.manager = manager
        # Cache environments for agents
        self.envs = {}
        self.active_processes = {} # session_id -> subprocess.Popen
        self.session_workspaces = {} # session_id -> workspace_dir
        self.claude_sessions = {}    # app_session_id -> claude_session_id
        self.hermes_sessions = {}    # app_session_id -> hermes_session_id
        self.local_sessions = {}     # app_session_id -> local backend session_id

        try:
            result = subprocess.run(
                ["/bin/zsh", "-l", "-c", "/usr/bin/env -0"],
                capture_output=True,
                check=False,
            )
            shell_env = {}
            for item in result.stdout.split(b"\0"):
                if not item or b"=" not in item:
                    continue
                key, value = item.split(b"=", 1)
                shell_env[key.decode("utf-8", errors="ignore")] = value.decode("utf-8", errors="ignore")

            self.base_env = {**os.environ, **shell_env}
            real_path = self.base_env.get("PATH") or os.environ.get("PATH", "")
            path_parts = [p for p in real_path.split(":") if p]
            extras = [
                "/opt/homebrew/bin",
                "/usr/local/bin",
                os.path.expanduser("~/.local/bin"),
                os.path.expanduser("~/.kimi-code/bin"),
                os.path.expanduser("~/.cargo/bin"),
            ]
            for extra in extras:
                if os.path.isdir(extra) and extra not in path_parts:
                    path_parts.insert(0, extra)
            full_path = ":".join(path_parts)
            self.base_env["PATH"] = full_path
            self.base_env["HOME"] = os.path.expanduser("~")
            # Also update os.environ so that shutil.which() sees the real PATH
            os.environ["PATH"] = full_path
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

    @staticmethod
    def _is_claude_family(agent_id: str) -> bool:
        return agent_id in CLAUDE_FAMILY_AGENT_IDS

    @staticmethod
    def _agent_display_name(agent_id: str) -> str:
        if agent_id == CLAUDE_DESKTOP_AGENT_ID:
            return "Claude Desktop"
        if agent_id == "claude":
            return "Claude Code"
        if agent_id == "kimi":
            return "Kimi Code"
        return agent_id

    @staticmethod
    def _sanitize_agent_env(env: dict) -> None:
        for key in list(env.keys()):
            upper_key = key.upper()
            if not (upper_key.endswith("API_KEY") or upper_key.endswith("_TOKEN")):
                continue
            value = str(env.get(key) or "").strip()
            if not is_usable_secret(value):
                env.pop(key, None)

    @staticmethod
    def _resolve_agent_timeout(timeout: Optional[float] = None) -> float:
        if timeout is not None:
            return float(timeout)
        try:
            return float(os.environ.get("ACROSS_AGENTS_AGENT_TIMEOUT", "600"))
        except (TypeError, ValueError):
            return 600.0

    @staticmethod
    def _resolve_agent_idle_timeout(timeout: Optional[float], max_wall_timeout: float) -> float:
        if timeout is not None:
            return float(timeout)
        try:
            configured = float(os.environ.get("ACROSS_AGENTS_AGENT_IDLE_TIMEOUT", "300"))
        except (TypeError, ValueError):
            configured = 300.0
        if max_wall_timeout > 0:
            return min(configured, max_wall_timeout)
        return configured

    def send(
        self,
        message: str,
        session_id: Optional[str] = None,
        use_current: bool = True,
        target_agent: Optional[str] = None,
        project_dir: Optional[str] = None,
        timeout: Optional[float] = None,
        idle_timeout: Optional[float] = None,
        max_wall_timeout: Optional[float] = None,
        model: Optional[str] = None,
    ) -> LocalAgentReply:
        t0 = time.time()

        agent_id = normalize_agent_id(target_agent or self.manager.get_active_agent()) or LOCAL_AGENT_ID
        config = self.manager.get_agent_config(agent_id) or {}
        from ..local_agent_health import codex_model_is_available, get_configured_agent_model, resolve_local_agent_executable

        executable_path = resolve_local_agent_executable(agent_id)

        # Fallback for agent-manager provided executable overrides.
        if not executable_path:
            configured_path = config.get("executable_path")
            if configured_path and os.path.isfile(os.path.expanduser(configured_path)) and os.access(os.path.expanduser(configured_path), os.X_OK):
                executable_path = os.path.abspath(os.path.expanduser(configured_path))

        if not executable_path:
            return LocalAgentReply(
                text=f"本地未找到 {agent_id} 可执行文件，请在菜单栏点击【配置智能体】进行设置。",
                session_id=session_id,
                elapsed_sec=time.time() - t0,
                error_code="agent_not_found",
            )

        args_template = config.get("args_template", [])
        output_format = config.get("output_format", "raw")

        # Default args for agents without explicit args_template in config
        if not args_template:
            if agent_id == "hermes":
                args_template = ["chat", "-q", "{message}", "-Q", "--yolo"]
            elif self._is_claude_family(agent_id):
                args_template = ["-p", "--permission-mode", "acceptEdits", "--output-format", "json", "{message}"]
            elif agent_id == "codex":
                args_template = [
                    "exec",
                    "--sandbox",
                    "workspace-write",
                    "--skip-git-repo-check",
                    "{message}",
                ]
            elif agent_id == "kimi":
                args_template = ["-p", "{message}", "--output-format", "stream-json"]
            elif agent_id == "opencode":
                args_template = ["run", "{message}"]
            elif agent_id == "cursor":
                args_template = ["-p", "{message}"]
            elif agent_id == LOCAL_AGENT_ID:
                # The gateway-compatible local CLI requires --agent, --to, or
                # --session-id. Use --to with a fixed E.164 number for task
                # scenario.
                args_template = ["agent", "--to", "+10000000000", "--message", "{message}", "--json"]
            else:
                args_template = ["{message}"]

        # Build args from template
        args = [executable_path]
        for arg in args_template:
            if "{message}" in arg:
                args.append(arg.replace("{message}", message))
            else:
                args.append(arg)

        requested_model = str(model or "").strip()
        configured_model = requested_model or get_configured_agent_model(agent_id) or (config.get("model") or "").strip()
        if configured_model and configured_model.lower() != "auto" and agent_id == "codex":
            model_available = codex_model_is_available(configured_model)
            if model_available is False:
                if requested_model:
                    return LocalAgentReply(
                        text=f"Codex model is not available on this machine: {configured_model}",
                        session_id=session_id,
                        elapsed_sec=time.time() - t0,
                        error_code="unsupported_model",
                    )
                configured_model = ""
        if configured_model and configured_model.lower() != "auto":
            if agent_id == "codex" and "exec" in args:
                exec_index = args.index("exec")
                args[exec_index + 1:exec_index + 1] = ["--model", configured_model]
            elif agent_id == "hermes" and "chat" in args:
                chat_index = args.index("chat")
                args[chat_index + 1:chat_index + 1] = ["--model", configured_model]
            elif self._is_claude_family(agent_id):
                args[1:1] = ["--model", configured_model]
            elif agent_id == "kimi":
                args[1:1] = ["--model", configured_model]
            elif agent_id == "opencode" and "run" in args:
                run_index = args.index("run")
                args[run_index + 1:run_index + 1] = ["--model", configured_model]
            elif agent_id == "cursor":
                args[1:1] = ["--model", configured_model]
            elif agent_id == LOCAL_AGENT_ID and "agent" in args:
                agent_index = args.index("agent")
                args[agent_index + 1:agent_index + 1] = ["--model", configured_model]

        if agent_id == "codex":
            if "exec" in args and "--json" not in args:
                exec_index = args.index("exec")
                args[exec_index + 1:exec_index + 1] = ["--json"]
            if project_dir and os.path.isdir(project_dir):
                prompt_index = len(args) - 1
                args[prompt_index:prompt_index] = ["--cd", project_dir]

        # Add session id logic for OpenClaw (override --to if session_id provided)
        if agent_id == LOCAL_AGENT_ID and session_id and not use_current:
            # Remove --to and its value if present, then add --session-id
            if "--to" in args:
                to_idx = args.index("--to")
                if to_idx + 1 < len(args) and args[to_idx + 1] == "+10000000000":
                    args.pop(to_idx)  # Remove --to
                    args.pop(to_idx)  # Remove +10000000000
            args.extend(["--session-id", session_id])

        try:
            default_workspace = str(default_local_agent_workspace())
            os.makedirs(default_workspace, exist_ok=True)

            # Resolve workspace: first check session-tracked workspace, then detect from message
            workspace_dir = None

            if session_id and session_id in self.session_workspaces:
                workspace_dir = self.session_workspaces[session_id]
            else:
                # First expand any ~ in the message
                expanded_message = re.sub(r'(~/[^ "\'\n]*)', lambda m: os.path.expanduser(m.group(1)), message)

                # Parse attached_files block if present
                attached_files_match = re.search(r'<attached_files>\n(.*?)\n</attached_files>', expanded_message, re.DOTALL)
                inline_files_match = re.search(r'\["((?:~|/)[^"]+)"\]', expanded_message)

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
                    except:
                        pass
                elif inline_files_match:
                    try:
                        first_path = os.path.expanduser(inline_files_match.group(1))
                        if os.path.exists(first_path):
                            if os.path.isdir(first_path):
                                workspace_dir = first_path
                            else:
                                workspace_dir = os.path.dirname(first_path)
                    except:
                        pass
                else:
                    path_match = re.search(r'((?:~|/)[^ "\'\n]+)', expanded_message)
                    if path_match:
                        potential_path = os.path.expanduser(path_match.group(1).strip())
                        target_dir = None

                        if os.path.exists(potential_path):
                            if os.path.isdir(potential_path):
                                target_dir = potential_path
                            else:
                                target_dir = os.path.dirname(potential_path)
                        else:
                            potential_path = potential_path.rstrip('.,:;!?')
                            if os.path.exists(potential_path):
                                if os.path.isdir(potential_path):
                                    target_dir = potential_path
                                else:
                                    target_dir = os.path.dirname(potential_path)

                        if target_dir:
                            workspace_dir = target_dir

                # Track the resolved workspace for this session
                if workspace_dir and session_id:
                    self.session_workspaces[session_id] = workspace_dir

            if not workspace_dir:
                workspace_dir = default_workspace

            # Task scenario: run inside project_dir without writing agent
            # metadata into the user's deliverable tree.
            is_task_scenario = bool(project_dir and os.path.isdir(project_dir))

            if self._is_claude_family(agent_id):
                if is_task_scenario:
                    process_cwd = project_dir
                else:
                    # Chat session: grant access to workspace directory via --add-dir
                    # When cwd == --add-dir, --resume fails with "No conversation found".
                    # Workaround: use default_workspace as cwd, project dir as --add-dir.
                    if workspace_dir != default_workspace:
                        args.extend(["--add-dir", workspace_dir])
                    process_cwd = default_workspace
            else:
                if is_task_scenario:
                    process_cwd = project_dir
                else:
                    process_cwd = workspace_dir

            # For Claude Code, --resume resumes the previous CLI session.
            # Tracked via claude_sessions dict (app session -> Claude session UUID).
            if self._is_claude_family(agent_id) and session_id and session_id in self.claude_sessions:
                args[1:1] = ["--resume", self.claude_sessions[session_id]]

            # For hermes, --resume resumes the previous hermes session
            if agent_id == "hermes" and session_id and session_id in self.hermes_sessions:
                args.extend(["--resume", self.hermes_sessions[session_id]])

            # Merge current environment with the login-shell environment captured
            # at startup. The shell environment wins so local CLIs see the same
            # provider configuration they get in Terminal, while stale app-level
            # placeholder keys cannot poison agent startup.
            process_env = {**os.environ, **self.base_env}
            self._sanitize_agent_env(process_env)

            # Provide the project directory via environment for all agents in task scenario
            if is_task_scenario:
                process_env["ACROSS_AGENTS_PROJECT_DIR"] = str(project_dir)

            # We use Popen instead of run so we can store the process and cancel it
            process = subprocess.Popen(
                args,
                env=process_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=process_cwd,
                start_new_session=(os.name != "nt"),
            )

            if session_id:
                self.active_processes[session_id] = process

            agent_timeout = self._resolve_agent_timeout(max_wall_timeout if max_wall_timeout is not None else timeout)
            if agent_id == "codex":
                agent_idle_timeout = self._resolve_agent_idle_timeout(idle_timeout, agent_timeout)
                stdout, stderr, timeout_kind, timeout_seconds = self._communicate_with_activity_timeout(
                    process,
                    max_wall_timeout=agent_timeout,
                    idle_timeout=agent_idle_timeout,
                )
                if timeout_kind:
                    if session_id and session_id in self.active_processes:
                        del self.active_processes[session_id]
                    elapsed = time.time() - t0
                    return LocalAgentReply(
                        text=(
                            f"抱歉，{agent_id} 执行超时（{timeout_kind} 超过 {timeout_seconds:g} 秒），"
                            "已自动终止。"
                        ),
                        session_id=session_id,
                        elapsed_sec=elapsed,
                        timed_out=True,
                        error_code=timeout_kind,
                        timeout_kind=timeout_kind,
                    )
            else:
                stdout, stderr = process.communicate(timeout=agent_timeout)

            # PinTaskSession: Detect and persist session_id from output immediately
            # This ensures session_id is saved even if the process crashes later
            if session_id and self._is_claude_family(agent_id):
                claude_sid = self._extract_claude_session_id(stdout)
                if claude_sid:
                    self.claude_sessions[session_id] = claude_sid
            elif session_id and agent_id == "hermes":
                hermes_sid = self._extract_hermes_session_id(stdout)
                if hermes_sid:
                    self.hermes_sessions[session_id] = hermes_sid

            if session_id and session_id in self.active_processes:
                del self.active_processes[session_id]

            elapsed = time.time() - t0
        except subprocess.TimeoutExpired:
            self._terminate_process_tree(process)
            if session_id and session_id in self.active_processes:
                del self.active_processes[session_id]
            elapsed = time.time() - t0
            return LocalAgentReply(
                text=f"抱歉，{agent_id} 执行超时（超过 {agent_timeout:g} 秒），已自动终止。",
                session_id=session_id,
                elapsed_sec=elapsed,
                timed_out=True,
                error_code="timeout",
                timeout_kind="max_wall_timeout",
            )
        except Exception as e:
            import logging
            if session_id and session_id in self.active_processes:
                del self.active_processes[session_id]
            logging.getLogger("across_agents_assistant").error(f"Failed to execute {agent_id}: {e}")
            return LocalAgentReply(
                text=f"抱歉，处理失败或已被取消。无法连接到 {agent_id}。",
                session_id=session_id,
                elapsed_sec=time.time() - t0,
                error_code="execution_failed",
            )

        # Parse output based on configured format
        ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")
        clean = ansi_pattern.sub("", stdout)
        clean_err = ansi_pattern.sub("", stderr or "").strip()

        is_error = process.returncode != 0
        if is_error:
            # Claude Code reports expired sessions as "No conversation found".
            msg = clean.strip() or clean_err
            if "No conversation found" in msg:
                # Clear tracked sessions so next message starts fresh
                if session_id:
                    self.claude_sessions.pop(session_id, None)
                    self.hermes_sessions.pop(session_id, None)
                return LocalAgentReply(
                    text=f"会话已失效或未找到。请发送新消息，我将为你开启一个新的会话。",
                    session_id=None,
                    elapsed_sec=time.time() - t0
                )

            if not msg:
                msg = f"{agent_id} 执行失败 (exit code: {process.returncode})"
            return LocalAgentReply(text=msg, session_id=session_id, elapsed_sec=elapsed, error_code="exit_error")

        if (not clean or not clean.strip()) and clean_err:
            clean = clean_err

        if agent_id == "codex":
            codex_answer = self._extract_codex_jsonl_text(clean)
            if codex_answer:
                return LocalAgentReply(text=codex_answer, session_id=session_id, elapsed_sec=elapsed)

        if agent_id == "kimi":
            reply_parts = []
            returned_session = session_id
            for line in clean.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("role") == "assistant":
                    content = event.get("content")
                    if isinstance(content, str) and content.strip():
                        reply_parts.append(content.strip())
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                text = item.get("text") or item.get("content")
                                if isinstance(text, str) and text.strip():
                                    reply_parts.append(text.strip())
                elif event.get("role") == "meta" and event.get("session_id") and session_id:
                    returned_session = session_id
            if reply_parts:
                return LocalAgentReply(text="\n".join(reply_parts), session_id=returned_session, elapsed_sec=elapsed)
            return LocalAgentReply(text=clean.strip() or "抱歉，大脑没有返回任何内容。", session_id=session_id, elapsed_sec=elapsed)

        if output_format == "json" or agent_id == LOCAL_AGENT_ID or self._is_claude_family(agent_id):
            start_idx = clean.find("{")
            if start_idx == -1:
                import logging
                logging.getLogger("across_agents_assistant").error(f"{agent_id} 返回了非 JSON 数据. Output: {stdout}\nErrors: {stderr}")
                return LocalAgentReply(text="抱歉，大脑返回了无法解析的信息。", session_id=session_id, elapsed_sec=elapsed)

            try:
                data = json.loads(clean[start_idx:])

                # Default parsing logic
                reply_text = data.get("text")
                returned_session = data.get("session_id", session_id)

                # OpenClaw nested structure
                if agent_id == LOCAL_AGENT_ID and "result" in data and isinstance(data.get("result"), dict):
                    result = data.get("result", {})
                    payloads = result.get("payloads", [])
                    reply_text = ""
                    for p in payloads:
                        if p.get("text"):
                            reply_text += p["text"]
                    if not reply_text:
                        reply_text = result.get("text")

                    returned_session = (
                        result.get("meta", {})
                        .get("agentMeta", {})
                        .get("sessionId")
                        or returned_session
                    )

                    # Track local's internal session ID for reference
                    if returned_session and session_id:
                        self.local_sessions[session_id] = returned_session

                    # Check for local errors
                    status = data.get("status", "ok")
                    if status in ("error", "timeout"):
                        error_msg = data.get("error", f"OpenClaw 执行失败 (status: {status})")
                        reply_text = error_msg

                # Claude Code JSON format: {"result": "text", "session_id": "..."}
                elif self._is_claude_family(agent_id):
                    raw_result = data.get("result")
                    if isinstance(raw_result, str):
                        reply_text = raw_result
                    elif isinstance(raw_result, dict):
                        reply_text = raw_result.get("text", "")
                    claude_sid = data.get("session_id")
                    if claude_sid and session_id:
                        self.claude_sessions[session_id] = claude_sid
                    returned_session = session_id

                    # Parse permission denials for approval notification
                    permission_denials = data.get("permission_denials", [])
                    if permission_denials:
                        denial = permission_denials[0]
                        tool_name = denial.get("tool_name", "unknown")
                        apr = {
                            "tool_name": tool_name,
                            "risk_level": "medium",
                            "tool_args": denial.get("tool_input", {}),
                            "description": denial.get("tool_input", {}).get(
                                "description",
                                f"{self._agent_display_name(agent_id)} 需要执行 {tool_name}",
                            )
                        }
                        return LocalAgentReply(
                            text=reply_text, session_id=returned_session, elapsed_sec=elapsed,
                            requires_approval=True, approval_request=apr
                        )

                if not reply_text:
                    reply_text = "抱歉，没有返回文本内容。"

                return LocalAgentReply(text=reply_text, session_id=returned_session, elapsed_sec=elapsed)
            except json.JSONDecodeError as e:
                import logging
                logging.getLogger("across_agents_assistant").error(f"Failed to parse JSON: {e}")
                return LocalAgentReply(text="抱歉，大脑返回了格式错误的信息。", session_id=session_id, elapsed_sec=elapsed)
        else:
            # Raw output parsing (like Hermes or Claude)
            text = clean.strip()
            # Clean up Claude Code verbose headers if present
            header_end_marker = "----------------------------------------"
            if "Claude Code" in text:
                parts = text.split(header_end_marker)
                if len(parts) >= 3:
                    # We do NOT extract the Session ID from the text!
                    # The actual Claude session is saved under the UUID we
                    # generated and passed via --session-id.

                    # Strip the header out so the UI looks clean
                    text = header_end_marker.join(parts[2:]).strip()

            # Remove any prefix like "Hermes: " if needed, or just return raw
            # For hermes, strip the trailing session_id string
            session_id_idx = text.rfind("session_id:")
            if session_id_idx != -1:
                # Extract the hermes session ID and track it for --resume
                extracted_session = text[session_id_idx:].replace("session_id:", "").strip()
                if extracted_session and session_id:
                    self.hermes_sessions[session_id] = extracted_session
                # Remove the session_id line from the spoken text
                text = text[:session_id_idx].strip()

            return LocalAgentReply(text=text if text else "抱歉，大脑没有返回任何内容。", session_id=session_id, elapsed_sec=elapsed)

    async def send_stream(self, message: str, session_id: Optional[str] = None, target_agent: Optional[str] = None, project_dir: Optional[str] = None):
        """Stream response from agent. Yields text chunks for SSE."""
        import asyncio
        import json

        agent_id = normalize_agent_id(target_agent or self.manager.get_active_agent()) or LOCAL_AGENT_ID

        # Check if agent supports streaming
        supports_streaming = self._is_claude_family(agent_id) or agent_id in {"hermes", "codex"}

        if not supports_streaming:
            # Fall back to blocking send for OpenClaw
            reply = self.send(message, session_id=session_id, target_agent=target_agent, project_dir=project_dir)
            yield reply.text
            return

        # For Claude/Hermes, use streaming mode
        config = self.manager.get_agent_config(agent_id) or {}
        from ..local_agent_health import get_configured_agent_model, resolve_local_agent_executable

        executable_path = resolve_local_agent_executable(agent_id)

        # Fallback for agent-manager provided executable overrides.
        if not executable_path:
            configured_path = config.get("executable_path")
            if configured_path and os.path.isfile(os.path.expanduser(configured_path)) and os.access(os.path.expanduser(configured_path), os.X_OK):
                executable_path = os.path.abspath(os.path.expanduser(configured_path))

        if not executable_path:
            yield f"本地未找到 {agent_id} 可执行文件，请在菜单栏点击【配置智能体】进行设置。"
            return

        # Resolve workspace for streaming (same logic as send())
        import os as _os
        import re as _re
        default_workspace = str(default_local_agent_workspace())
        _os.makedirs(default_workspace, exist_ok=True)

        if session_id and session_id in self.session_workspaces:
            workspace_dir = self.session_workspaces[session_id]
        else:
            workspace_dir = default_workspace

        # Task scenario: run inside project_dir without writing agent metadata
        # into the user's deliverable tree.
        is_task_scenario = bool(project_dir and _os.path.isdir(project_dir))

        # Build args with streaming flags
        args = [executable_path]

        if self._is_claude_family(agent_id):
            if is_task_scenario:
                stream_cwd = project_dir
            else:
                # Chat session: grant access via --add-dir
                if workspace_dir != default_workspace:
                    args.extend(["--add-dir", workspace_dir])
                stream_cwd = default_workspace

            # --resume resumes the previous Claude Code session
            if session_id and session_id in self.claude_sessions:
                args.extend(["--resume", self.claude_sessions[session_id]])
            configured_model = get_configured_agent_model(agent_id) or (config.get("model") or "").strip()
            if configured_model and configured_model.lower() != "auto":
                args.extend(["--model", configured_model])
            args.extend(["-p", "--permission-mode", "acceptEdits", "--output-format", "stream-json", message])
        elif agent_id == "hermes":
            if session_id and session_id in self.hermes_sessions:
                args.extend(["--resume", self.hermes_sessions[session_id]])
            args.extend(["chat", "-q", message, "--output-format", "stream-json", "--include-partial-messages", "--yolo"])
            stream_cwd = workspace_dir
        elif agent_id == "codex":
            configured_model = get_configured_agent_model(agent_id) or (config.get("model") or "").strip()
            args.extend(["exec", "--json"])
            if configured_model:
                args.extend(["--model", configured_model])
            args.extend(["--sandbox", "workspace-write", "--skip-git-repo-check"])
            if project_dir:
                args.extend(["--cd", project_dir])
            args.append(message)
            stream_cwd = project_dir if is_task_scenario else workspace_dir
        else:
            stream_cwd = workspace_dir

        process_env = {**os.environ, **self.base_env}
        self._sanitize_agent_env(process_env)

        # Issue 39: Reset umask before spawning agent subprocess to ensure
        # Run with asyncio subprocess for async streaming
        process = await asyncio.create_subprocess_exec(
            *args,
            env=process_env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=stream_cwd
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
                    # Track session_id from init message
                    if data.get("type") == "system" and data.get("subtype") == "init":
                        sid = data.get("session_id")
                        if sid and session_id:
                            if self._is_claude_family(agent_id):
                                self.claude_sessions[session_id] = sid
                            elif agent_id == "hermes":
                                self.hermes_sessions[session_id] = sid
                    if data.get("type") == "item.completed":
                        item = data.get("item") if isinstance(data.get("item"), dict) else {}
                        if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                            yield item["text"]
                    if "content" in data:
                        yield data["content"]
                except json.JSONDecodeError:
                    continue
        finally:
            # Wait for process to complete
            await process.wait()
            # PinTaskSession: Also try to extract session_id from complete stdout if not already tracked
            if session_id:
                if self._is_claude_family(agent_id) and session_id not in self.claude_sessions:
                    # For streaming, session_id might be in the accumulated output
                    pass  # Streaming mode already tracks via init message above
                elif agent_id == "hermes" and session_id not in self.hermes_sessions:
                    pass  # Streaming mode already tracks via init message above
            if session_id and session_id in self.active_processes:
                del self.active_processes[session_id]

    @staticmethod
    def _terminate_process_tree(process) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            else:
                process.terminate()
        except Exception:
            try:
                process.kill()
            except Exception:
                return
        try:
            process.wait(timeout=2.0)
            return
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            return
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
        except Exception:
            try:
                process.kill()
            except Exception:
                return
        try:
            process.wait(timeout=1.0)
        except Exception:
            pass

    @staticmethod
    def _communicate_with_activity_timeout(process, *, max_wall_timeout: float, idle_timeout: float):
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        lock = threading.Lock()
        started = time.monotonic()
        last_activity = started

        progress_logger = None
        if os.environ.get("ACROSS_AAA_HOST_CLI_PROGRESS_LOG_FILE"):
            try:
                from ..autopilot_host_cli_progress import host_cli_activity

                progress_logger = host_cli_activity
            except Exception:
                progress_logger = None

        def reader(stream, parts, stream_name: str):
            nonlocal last_activity
            pending_chars = 0
            pending_lines = 0
            total_chars = 0
            last_emit = time.monotonic()

            def emit_activity(force: bool = False) -> None:
                nonlocal pending_chars, pending_lines, last_emit
                if not progress_logger or pending_chars <= 0:
                    return
                now = time.monotonic()
                if not force and pending_chars < 4096 and pending_lines < 1 and now - last_emit < 2.0:
                    return
                try:
                    progress_logger(
                        "local_agent.activity",
                        stream=stream_name,
                        chars=pending_chars,
                        lines=pending_lines,
                        total_chars=total_chars,
                        elapsed_sec=round(now - started, 3),
                    )
                except Exception:
                    pass
                pending_chars = 0
                pending_lines = 0
                last_emit = now

            try:
                while True:
                    chunk = stream.read(1)
                    if not chunk:
                        break
                    with lock:
                        parts.append(chunk)
                        last_activity = time.monotonic()
                    pending_chars += len(chunk)
                    total_chars += len(chunk)
                    if chunk == "\n":
                        pending_lines += 1
                    emit_activity()
            except Exception:
                return
            finally:
                emit_activity(force=True)

        threads = [
            threading.Thread(target=reader, args=(process.stdout, stdout_parts, "stdout"), daemon=True),
            threading.Thread(target=reader, args=(process.stderr, stderr_parts, "stderr"), daemon=True),
        ]
        for thread in threads:
            thread.start()

        timeout_kind = None
        timeout_seconds = None
        while process.poll() is None:
            now = time.monotonic()
            if max_wall_timeout > 0 and now - started > max_wall_timeout:
                timeout_kind = "max_wall_timeout"
                timeout_seconds = max_wall_timeout
                UniversalAgentClient._terminate_process_tree(process)
                break
            if idle_timeout > 0 and now - last_activity > idle_timeout:
                timeout_kind = "idle_timeout"
                timeout_seconds = idle_timeout
                UniversalAgentClient._terminate_process_tree(process)
                break
            time.sleep(0.1)

        if process.poll() is None:
            process.wait()
        for thread in threads:
            thread.join(timeout=1.0)
        return "".join(stdout_parts), "".join(stderr_parts), timeout_kind, timeout_seconds

    @staticmethod
    def _extract_codex_jsonl_text(text: str) -> str:
        chunks: list[str] = []
        for line in str(text or "").splitlines():
            stripped = line.strip()
            if not stripped.startswith("{"):
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "item.completed":
                continue
            item = event.get("item") if isinstance(event.get("item"), dict) else {}
            if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                content = item["text"].strip()
                if content:
                    chunks.append(content)
        return "\n".join(chunks).strip()

    def _extract_claude_session_id(self, stdout: str) -> Optional[str]:
        """Extract Claude session ID from JSON output."""
        try:
            start_idx = stdout.find("{")
            if start_idx == -1:
                return None
            data = json.loads(stdout[start_idx:])
            sid = data.get("session_id")
            if sid:
                return sid
            # Try nested structure
            result = data.get("result", {})
            if isinstance(result, dict):
                sid = result.get("session_id")
                if sid:
                    return sid
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    def _extract_hermes_session_id(self, stdout: str) -> Optional[str]:
        """Extract Hermes session ID from raw output."""
        session_id_idx = stdout.rfind("session_id:")
        if session_id_idx != -1:
            extracted = stdout[session_id_idx:].replace("session_id:", "").strip()
            # Remove ANSI codes
            ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")
            clean = ansi_pattern.sub("", extracted)
            return clean.split()[0] if clean else None
        return None
