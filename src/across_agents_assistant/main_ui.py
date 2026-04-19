import webview
import os

try:
    import AppKit
except ImportError:
    pass

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Across-Agents Assistant</title>
    <style>
        :root {
            --bg-color: #f9f9f9;
            --sidebar-bg: #ffffff;
            --text-color: #1d1d1f;
            --secondary-text: #86868b;
            --accent-color: #0071e3;
            --border-color: rgba(0,0,0,0.08);
            --msg-user-bg: #007aff;
            --msg-user-text: #ffffff;
            --msg-agent-bg: #e9e9eb;
            --msg-agent-text: #000000;
        }

        @media (prefers-color-scheme: dark) {
            :root {
                --bg-color: #1c1c1e;
                --sidebar-bg: #1c1c1e;
                --text-color: #f5f5f7;
                --secondary-text: #98989d;
                --accent-color: #0a84ff;
                --border-color: rgba(255,255,255,0.1);
                --msg-user-bg: #0a84ff;
                --msg-agent-bg: #2c2c2e;
                --msg-agent-text: #ffffff;
            }
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 0;
            display: flex;
            height: 100vh;
            overflow: hidden;
            -webkit-font-smoothing: antialiased;
        }

        /* Sidebar */
        .sidebar {
            width: 80px;
            background-color: var(--sidebar-bg);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            align-items: center;
            padding-top: 40px;
            gap: 20px;
            z-index: 10;
        }

        .agent-icon {
            width: 44px;
            height: 44px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            cursor: pointer;
            transition: all 0.2s;
            border: 2px solid transparent;
            opacity: 0.6;
            background: var(--bg-color);
            overflow: hidden;
        }

        .agent-icon img, .agent-icon svg {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .agent-icon:hover {
            opacity: 1;
            transform: scale(1.05);
        }

        .agent-icon.active {
            opacity: 1;
            border-color: var(--accent-color);
            box-shadow: 0 4px 12px rgba(0, 113, 227, 0.2);
        }

        .agent-icon.unready {
            filter: grayscale(1);
            opacity: 0.3;
        }

        /* Main Chat Area */
        .main-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            position: relative;
        }

        .header {
            height: 60px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            padding: 0 24px;
            font-size: 16px;
            font-weight: 600;
            background: var(--bg-color);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            z-index: 5;
            justify-content: space-between;
        }
        
        .header-actions {
            display: flex;
            gap: 12px;
            align-items: center;
        }

        .btn-icon {
            background: transparent;
            border: none;
            font-size: 18px;
            cursor: pointer;
            color: var(--secondary-text);
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            border-radius: 8px;
        }
        .btn-icon:hover {
            color: var(--text-color);
            background: var(--border-color);
        }
        
        .btn-icon.active {
            color: var(--accent-color);
            background: rgba(0, 113, 227, 0.1);
        }

        .chat-container {
            flex: 1;
            padding: 24px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .message {
            max-width: 75%;
            padding: 12px 16px;
            border-radius: 18px;
            font-size: 15px;
            line-height: 1.4;
            animation: fadeIn 0.3s ease;
            word-wrap: break-word;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .msg-user {
            align-self: flex-end;
            background-color: var(--msg-user-bg);
            color: var(--msg-user-text);
            border-bottom-right-radius: 4px;
        }

        .msg-agent {
            align-self: flex-start;
            background-color: var(--msg-agent-bg);
            color: var(--msg-agent-text);
            border-bottom-left-radius: 4px;
        }
        
        .msg-system {
            align-self: center;
            background-color: transparent;
            color: var(--secondary-text);
            font-size: 12px;
            text-align: center;
            padding: 4px;
        }

        .input-area {
            padding: 20px 24px;
            background: var(--bg-color);
            border-top: 1px solid var(--border-color);
            display: flex;
            gap: 12px;
            align-items: center;
        }

        .chat-input {
            flex: 1;
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 12px 20px;
            font-size: 15px;
            background: var(--sidebar-bg);
            color: var(--text-color);
            outline: none;
            transition: border-color 0.2s;
        }

        .chat-input:focus {
            border-color: var(--accent-color);
        }

        .btn-send {
            background-color: var(--accent-color);
            color: white;
            border: none;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 18px;
            transition: transform 0.2s;
        }

        .btn-send:hover {
            transform: scale(1.05);
        }

        /* Toast */
        .toast {
            visibility: hidden;
            background-color: var(--text-color);
            color: var(--bg-color);
            text-align: center;
            border-radius: 20px;
            padding: 10px 20px;
            position: fixed;
            z-index: 1000;
            left: 50%;
            top: 20px;
            transform: translateX(-50%) translateY(-10px);
            font-size: 13px;
            font-weight: 500;
            opacity: 0;
            transition: opacity 0.3s, transform 0.3s;
        }

        .toast.show {
            visibility: visible;
            opacity: 1;
            transform: translateX(-50%) translateY(0);
        }
    </style>
</head>
<body>

    <div class="sidebar" id="sidebar">
        <!-- Rendered by JS -->
    </div>

    <div class="main-area">
        <div class="header">
            <span id="current-agent-name">Across-Agents Assistant</span>
            <div class="header-actions">
                <button class="btn-icon" id="btn-continuous" onclick="toggleContinuous()" title="开启持续对话">👄</button>
                <button class="btn-icon" id="btn-speak" onclick="triggerSingleTurn()" title="单次对话 (点击说话)">🎙️</button>
                <button class="btn-icon" id="btn-silent" onclick="toggleSilentMode()" title="静音模式">🔊</button>
                <button class="btn-icon active" id="btn-chatmode" onclick="toggleChatMode()" title="当前: 隔离对话模式">💬</button>
                <button class="btn-icon" onclick="openSettings()" title="配置智能体" style="font-size:20px;">⚙️</button>
            </div>
        </div>
        
        <div class="chat-container" id="chat-container">
            <!-- Messages rendered by JS -->
        </div>

        <div class="input-area">
            <input type="text" class="chat-input" id="chat-input" placeholder="输入消息 (回车发送)..." onkeypress="handleKeyPress(event)">
            <button class="btn-send" onclick="sendManualMessage()">↑</button>
        </div>
    </div>

    <div id="toast" class="toast"></div>

    <script>
        let config = {};
        let toastTimeout;
        let chatMode = 'isolated'; // 'merged' or 'isolated'
        let chatHistory = {
            merged: [],
            // dynamically add agent_id keys
        };

        function showToast(message) {
            const toast = document.getElementById("toast");
            toast.innerText = message;
            toast.className = "toast show";
            clearTimeout(toastTimeout);
            toastTimeout = setTimeout(() => { toast.className = toast.className.replace("show", ""); }, 2500);
        }

        async function loadData() {
            config = await pywebview.api.get_config();
            if (!chatHistory[config.active_agent]) {
                chatHistory[config.active_agent] = [];
            }
            renderSidebar();
            updateHeader();
            renderChat();
            
            // Sync UI states
            const state = await pywebview.api.get_ui_state();
            
            // Continuous Mode (👄/🤐)
            const btnCont = document.getElementById('btn-continuous');
            if (state.continuous_on) {
                btnCont.innerText = '🤐';
                btnCont.title = "关闭持续对话";
                btnCont.classList.add('active');
            } else {
                btnCont.innerText = '👄';
                btnCont.title = "开启持续对话";
                btnCont.classList.remove('active');
            }
            
            // Silent Mode
            const btnSilent = document.getElementById('btn-silent');
            if (state.silent_on) {
                btnSilent.innerText = '🔇';
                btnSilent.title = "关闭静音模式";
                btnSilent.classList.add('active');
            } else {
                btnSilent.innerText = '🔊';
                btnSilent.title = "开启静音模式";
                btnSilent.classList.remove('active');
            }
        }

        function toggleChatMode() {
            const btn = document.getElementById('btn-chatmode');
            if (chatMode === 'merged') {
                chatMode = 'isolated';
                btn.innerText = '💬';
                btn.title = "当前: 隔离对话模式 (仅当前智能体历史)";
                btn.classList.add('active');
            } else {
                chatMode = 'merged';
                btn.innerText = '🗂️';
                btn.title = "当前: 全局对话模式 (显示所有历史)";
                btn.classList.remove('active');
            }
            renderChat();
        }

        let lastRenderedAgents = "";
        
        function renderSidebar() {
            const sidebar = document.getElementById('sidebar');
            const agentsStr = JSON.stringify(config.agents) + config.active_agent;
            if (lastRenderedAgents === agentsStr) {
                return; // Prevent jitter
            }
            lastRenderedAgents = agentsStr;
            
            sidebar.innerHTML = '';

            const agents = config.agents || {};
            const active = config.active_agent;

            for (const [id, agent] of Object.entries(agents)) {
                const isReady = agent.executable_path && agent.executable_path.trim() !== '';
                const isActive = id === active;
                
                let iconHtml = '';
                if (config.icons && config.icons[id]) {
                    iconHtml = `<img src="${config.icons[id]}" alt="${getDisplayName(id)}">`;
                } else {
                    let iconText = id.substring(0, 2).toUpperCase();
                    iconHtml = `<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:#e5e5ea;color:#000;font-size:16px;">${iconText}</div>`;
                }

                const div = document.createElement('div');
                div.className = `agent-icon ${isActive ? 'active' : ''} ${isReady ? '' : 'unready'}`;
                div.title = getDisplayName(id) + (isReady ? '' : ' (未配置)');
                div.onclick = () => handleIconClick(id, isReady);
                div.innerHTML = iconHtml;
                
                sidebar.appendChild(div);
            }
        }

        const AGENT_DISPLAY_NAMES = {
            'openclaw': 'Openclaw',
            'hermes': 'Hermes',
            'claude': 'Claude Code'
        };

        function getDisplayName(id) {
            return AGENT_DISPLAY_NAMES[id] || id;
        }

        function updateHeader() {
            document.getElementById('current-agent-name').innerText = getDisplayName(config.active_agent);
        }

        async function handleIconClick(id, isReady) {
            if (id === config.active_agent) return;
            
            if (isReady) {
                const success = await pywebview.api.set_active(id);
                if (success) {
                    config.active_agent = id;
                    renderSidebar();
                    updateHeader();
                    renderChat();
                }
            } else {
                showToast("该智能体未配置，正在尝试自动检测...");
                const result = await pywebview.api.detect_or_config(id);
                if (result.success) {
                    config = await pywebview.api.get_config();
                    await pywebview.api.set_active(id);
                    config.active_agent = id;
                    renderSidebar();
                    updateHeader();
                    renderChat();
                } else {
                    showToast(result.msg || "检测失败，请点击右上角⚙️手动配置");
                }
            }
        }

        function addMessage(role, text, agentId) {
            // Intercept system messages about toggle state from python
            if (role === 'system') {
                if (text === 'Continuous_Off') {
                    const btn = document.getElementById('btn-continuous');
                    btn.innerText = '👄';
                    btn.title = "开启持续对话";
                    btn.classList.remove('active');
                    return;
                }
                if (text === 'Continuous_On') {
                    const btn = document.getElementById('btn-continuous');
                    btn.innerText = '🤐';
                    btn.title = "关闭持续对话";
                    btn.classList.add('active');
                    return;
                }
            }

            const msg = { role, text };
            chatHistory.merged.push(msg);
            
            // Assign to the correct agent's history
            const targetAgent = agentId || config.active_agent;
            if (targetAgent) {
                if (!chatHistory[targetAgent]) chatHistory[targetAgent] = [];
                chatHistory[targetAgent].push(msg);
            }
            renderChat();
        }

        let renderTimeout = null;
        let lastRenderState = { agent: null, mode: null, length: 0 };
        
        function renderChat() {
            if (renderTimeout) clearTimeout(renderTimeout);
            renderTimeout = setTimeout(() => {
                const container = document.getElementById('chat-container');
                let history = [];
                if (chatMode === 'merged') {
                    history = chatHistory.merged;
                } else {
                    history = chatHistory[config.active_agent] || [];
                }
                
                // If context didn't change and length is same, do nothing
                if (lastRenderState.agent === config.active_agent && 
                    lastRenderState.mode === chatMode && 
                    lastRenderState.length === history.length) {
                    return;
                }
                
                // Full re-render only if context changed
                if (lastRenderState.agent !== config.active_agent || lastRenderState.mode !== chatMode) {
                    container.innerHTML = '';
                    const fragment = document.createDocumentFragment();
                    
                    if (history.length === 0) {
                        const div = document.createElement('div');
                        div.className = 'message msg-system';
                        div.innerText = '💡 提示: 点击 👄 开启持续对话，或点击 🎙️ 进行单次对话';
                        fragment.appendChild(div);
                    }
                    
                    history.forEach(msg => {
                        const div = document.createElement('div');
                        div.className = `message msg-${msg.role}`;
                        div.innerText = msg.text;
                        fragment.appendChild(div);
                    });
                    
                    container.appendChild(fragment);
                    container.scrollTop = container.scrollHeight;
                } else {
                    // Just append the new messages
                    const newMessages = history.slice(lastRenderState.length);
                    const fragment = document.createDocumentFragment();
                    
                    // Remove the empty state prompt if it exists
                    if (lastRenderState.length === 0 && container.firstChild && container.firstChild.classList.contains('msg-system')) {
                        container.innerHTML = '';
                    }
                    
                    newMessages.forEach(msg => {
                        const div = document.createElement('div');
                        div.className = `message msg-${msg.role}`;
                        div.innerText = msg.text;
                        fragment.appendChild(div);
                    });
                    
                    const wasAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 50;
                    container.appendChild(fragment);
                    if (wasAtBottom) {
                        container.scrollTop = container.scrollHeight;
                    }
                }
                
                lastRenderState = { agent: config.active_agent, mode: chatMode, length: history.length };
            }, 10);
        }

        function addSystemMessage(text) {
            addMessage('system', text);
        }

        function handleKeyPress(e) {
            if (e.key === 'Enter') {
                sendManualMessage();
            }
        }

        async function sendManualMessage() {
            const input = document.getElementById('chat-input');
            const text = input.value.trim();
            if (!text) return;
            
            input.value = '';
            
            // Call python backend to process text, specifically target the active agent tab
            await pywebview.api.send_text_message(text, config.active_agent);
        }
        
        function openSettings() {
            pywebview.api.open_settings_window();
        }

        async function toggleSilentMode() {
            const isSilent = await pywebview.api.toggle_silent_mode();
            const btn = document.getElementById('btn-silent');
            if (isSilent) {
                btn.innerText = '🔇';
                btn.title = "关闭静音模式";
                btn.classList.add('active');
                addSystemMessage("🔇 已开启静音模式 (仅文字输出不播报)");
            } else {
                btn.innerText = '🔊';
                btn.title = "开启静音模式";
                btn.classList.remove('active');
                addSystemMessage("🔊 已恢复语音播报");
            }
        }
        
        async function toggleContinuous() {
            const isContinuous = await pywebview.api.toggle_continuous();
            const btn = document.getElementById('btn-continuous');
            if (isContinuous) {
                btn.innerText = '🤐';
                btn.title = "关闭持续对话";
                btn.classList.add('active');
                addSystemMessage("👄 已开启持续对话模式，可以直接说话");
            } else {
                btn.innerText = '👄';
                btn.title = "开启持续对话";
                btn.classList.remove('active');
                addSystemMessage("🤐 已关闭持续对话模式");
            }
        }
        
        async function triggerSingleTurn() {
            addSystemMessage("🎙️ 正在听您说话...");
            await pywebview.api.trigger_single_turn();
        }

        window.addEventListener('pywebviewready', function() {
            loadData();
            // Init toggle states from pywebview if we want to sync, 
            // but we default them to off for now.
        });
    </script>
</body>
</html>
"""

def check_mic_permission() -> bool:
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
        import threading
        
        mic_status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
        
        if mic_status != 3: # 3 is AVAuthorizationStatusAuthorized
            event = threading.Event()
            granted_result = [False]
            def handler(granted):
                granted_result[0] = granted
                event.set()
            AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeAudio, handler)
            event.wait()
            
            if granted_result[0]:
                # PortAudio caches devices on load. If permission was just granted, 
                # we MUST restart the process for it to detect the microphone.
                import subprocess
                import sys
                import os
                import logging
                logging.getLogger("across_agents_assistant").info("Microphone permission granted. Restarting to apply...")
                subprocess.Popen([sys.executable] + sys.argv[1:])
                os._exit(0)
                
            return granted_result[0]
        return True
    except Exception as e:
        import logging
        logging.getLogger("across_agents_assistant").error(f"Permission check failed: {e}")
        return True

class MainApi:
    def __init__(self, app, window):
        self.app = app
        self.window = window
        self.manager = app._agent_manager

    def get_config(self):
        from .icons import AGENT_ICONS
        conf = self.manager.config.copy()
        conf["icons"] = AGENT_ICONS
        return conf
        
    def get_ui_state(self):
        return {
            "voice_on": self.app._voice_mode_enabled.is_set(),
            "continuous_on": self.app._continuous_mode.is_set(),
            "silent_on": self.app._silent_mode.is_set()
        }

    def set_active(self, agent_id):
        self.manager.set_active_agent(agent_id)
        # Hot reload openclaw
        self.app._openclaw.initialized = False
        self.app._openclaw.initialize()
        return True

    def detect_or_config(self, agent_id):
        import subprocess
        import shutil
        path = shutil.which(agent_id)
        if not path:
            try:
                result = subprocess.run(["/bin/zsh", "-l", "-c", f"which {agent_id}"], capture_output=True, text=True)
                output = result.stdout.strip()
                if output and "not found" not in output.lower() and os.path.exists(output):
                    path = output
            except Exception:
                pass
        if not path:
            common_paths = [
                os.path.expanduser(f"~/.local/bin/{agent_id}"),
                os.path.expanduser(f"~/.cargo/bin/{agent_id}"),
                f"/opt/homebrew/bin/{agent_id}",
                f"/usr/local/bin/{agent_id}",
            ]
            for cp in common_paths:
                if os.path.exists(cp) and os.access(cp, os.X_OK):
                    path = cp
                    break
        if path and os.path.exists(path):
            config = self.manager.get_agent_config(agent_id)
            config["executable_path"] = path
            self.manager.update_agent(agent_id, config)
            return {"success": True, "msg": f"成功检测到 {agent_id}！"}
        return {"success": False, "msg": f"未检测到 {agent_id}，请前往设置配置"}

    def trigger_single_turn(self):
        import os
        os.system("afplay /System/Library/Sounds/Glass.aiff &")
        self.app._manual_listen.set()
        return True
    def send_text_message(self, text, target_agent=None):
        # Stop any ongoing TTS and interrupt listening to process text
        self.app._hotkey_interrupt.set()
        
        # Dispatch manually instead of queue to pass the specific target agent
        import threading
        threading.Thread(target=self.app._handle_user_text, args=(text, target_agent), daemon=True).start()
        
    def open_settings_window(self):
        # Open the settings UI in a new process or window
        import subprocess
        import sys
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable, "ui"])
        else:
            import os
            main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"))
            subprocess.Popen([sys.executable, main_py, "ui"])
            
    def toggle_silent_mode(self):
        if self.app._silent_mode.is_set():
            self.app._silent_mode.clear()
            return False
        else:
            self.app._silent_mode.set()
            # Stop ongoing TTS if switching to silent (but don't interrupt the conversation loop)
            self.app._tts_interrupt.set()
            return True
            
    def toggle_continuous(self):
        import os
        if self.app._continuous_mode.is_set():
            self.app._continuous_mode.clear()
            self.app._voice_mode_enabled.clear()
            self.app._hotkey_interrupt.set()
            os.system("afplay /System/Library/Sounds/Funk.aiff &")
            return False
        else:
            if not check_mic_permission():
                return False
            self.app._hotkey_interrupt.clear()
            self.app._continuous_mode.set()
            self.app._voice_mode_enabled.set()
            self.app.ensure_speechcli_running()
            os.system("afplay /System/Library/Sounds/Glass.aiff &")
            return True

_tray_globals = {}

class MacTrayManager:
    pass

try:
    import AppKit
    import objc
    class MacTrayManager(AppKit.NSObject):
        def setupTray_(self, window):
            try:
                app = AppKit.NSApplication.sharedApplication()
                statusbar = AppKit.NSStatusBar.systemStatusBar()
                statusitem = statusbar.statusItemWithLength_(-1)
                
                # Try loading the generated menubar icon first
                import os, sys
                if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                    base_path = sys._MEIPASS
                else:
                    base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                
                icon_path = os.path.join(base_path, "assets", "menubar_icon.png")
                if os.path.exists(icon_path):
                    img = AppKit.NSImage.alloc().initWithContentsOfFile_(icon_path)
                    if img:
                        img.setTemplate_(True) # Automatically invert colors for dark/light mode
                        img.setSize_(AppKit.NSSize(18, 18))
                        statusitem.button().setImage_(img)
                else:
                    # Fallback to system symbol
                    img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("sparkles", None)
                    if img:
                        img.setTemplate_(True) # Adapts to light/dark mode
                        statusitem.button().setImage_(img)
                    else:
                        statusitem.button().setTitle_("AAA")
                    
                menu = AppKit.NSMenu.alloc().init()
                
                class MenuHandler(AppKit.NSObject):
                    def showWindow_(self, sender):
                        window.show()
                        AppKit.NSApp.activateIgnoringOtherApps_(True)
                        
                    def toggleContinuous_(self, sender):
                        app_inst = getattr(window, 'voice_app', None)
                        if app_inst:
                            import os
                            if app_inst._continuous_mode.is_set():
                                app_inst._continuous_mode.clear()
                                app_inst._voice_mode_enabled.clear()
                                app_inst._hotkey_interrupt.set()
                                sender.setTitle_("开启持续对话")
                                os.system("afplay /System/Library/Sounds/Funk.aiff &")
                                app_inst._logger.info("🔴 用户通过菜单栏关闭了持续对话")
                                if app_inst.on_message_callback:
                                    app_inst.on_message_callback("system", "Continuous_Off", None)
                            else:
                                app_inst._continuous_mode.set()
                                app_inst._voice_mode_enabled.set()
                                app_inst.ensure_speechcli_running()
                                sender.setTitle_("关闭持续对话")
                                os.system("afplay /System/Library/Sounds/Glass.aiff &")
                                app_inst._logger.info("🟢 用户通过菜单栏开启了持续对话")
                                if app_inst.on_message_callback:
                                    app_inst.on_message_callback("system", "Continuous_On", None)
                        
                    def toggleSilent_(self, sender):
                        app_inst = getattr(window, 'voice_app', None)
                        if app_inst:
                            if app_inst._silent_mode.is_set():
                                app_inst._silent_mode.clear()
                                sender.setTitle_("开启静音模式")
                            else:
                                app_inst._silent_mode.set()
                                sender.setTitle_("关闭静音模式")
                                app_inst._hotkey_interrupt.set()
                        
                    def quitApp_(self, sender):
                        app_inst = getattr(window, 'voice_app', None)
                        if app_inst:
                            app_inst.is_quitting = True
                        window.destroy()
                        import os
                        os._exit(0)
                        
                handler = MenuHandler.alloc().init()
                
                item_show = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("打开对话窗口", "showWindow:", "")
                item_show.setTarget_(handler)
                menu.addItem_(item_show)
                
                menu.addItem_(AppKit.NSMenuItem.separatorItem())
                
                # We need to set the initial title based on app state
                voice_title = "关闭语音输入"
                initial_title = "切换为单次对话"
                silent_title = "开启静音模式"
                app_inst = getattr(window, 'voice_app', None)
                if app_inst:
                    if not app_inst._voice_mode_enabled.is_set():
                        voice_title = "开启语音输入"
                    if not app_inst._continuous_mode.is_set():
                        initial_title = "切换为连续对话"
                    if app_inst._silent_mode.is_set():
                        silent_title = "关闭静音模式"
                    
                item_voice = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(voice_title, "toggleVoice:", "")
                item_voice.setTarget_(handler)
                menu.addItem_(item_voice)
                
                item_toggle = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(initial_title, "toggleContinuous:", "")
                item_toggle.setTarget_(handler)
                menu.addItem_(item_toggle)
                
                item_silent = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(silent_title, "toggleSilent:", "")
                item_silent.setTarget_(handler)
                menu.addItem_(item_silent)
                
                menu.addItem_(AppKit.NSMenuItem.separatorItem())
                
                item_quit = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("退出小落", "quitApp:", "")
                item_quit.setTarget_(handler)
                menu.addItem_(item_quit)
                
                statusitem.setMenu_(menu)
                
                # Prevent GC
                global _tray_globals
                _tray_globals['statusitem'] = statusitem
                _tray_globals['handler'] = handler
                _tray_globals['menu'] = menu
                
                # Hijack Cmd+Q from the main menu
                mainMenu = app.mainMenu()
                if mainMenu:
                    appMenu = mainMenu.itemAtIndex_(0).submenu()
                    if appMenu:
                        for i in range(appMenu.numberOfItems()):
                            item = appMenu.itemAtIndex_(i)
                            # Override the default "Quit" action with our custom handler
                            if item.keyEquivalent() == "q":
                                item.setTarget_(handler)
                                item.setAction_(objc.selector(handler.quitApp_, signature=b'v@:@'))
            except Exception as e:
                import logging
                logging.getLogger("across_agents_assistant").error(f"Failed to setup tray: {e}")
except ImportError:
    pass

def create_tray(window):
    try:
        import objc
        manager = MacTrayManager.alloc().init()
        # MUST run on main thread, otherwise AppKit UI creation will fail silently or crash
        manager.performSelectorOnMainThread_withObject_waitUntilDone_(objc.selector(manager.setupTray_, signature=b'v@:@'), window, False)
        
        # Keep manager alive just in case
        global _tray_globals
        _tray_globals['manager'] = manager
    except Exception as e:
        import logging
        logging.getLogger("across_agents_assistant").error(f"Failed to initialize tray: {e}")

def start_main_ui(app):
    window = webview.create_window('Across-Agents Assistant', html=HTML_CONTENT, width=900, height=650, text_select=True)
    window.voice_app = app  # Attach to window for tray access
    api = MainApi(app, window)
    window.expose(api.get_config, api.get_ui_state, api.set_active, api.detect_or_config, api.send_text_message, api.open_settings_window, api.toggle_silent_mode, api.toggle_continuous, api.trigger_single_turn)
    
    def on_closing():
        if getattr(app, 'is_quitting', False):
            return True
        window.hide()
        return False
    window.events.closing += on_closing
    
    # Hook app callbacks to UI
    def on_message(role, text, target_agent=None):
        # Use evaluate_js to update UI
        escaped_text = text.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")
        try:
            if target_agent:
                window.evaluate_js(f"addMessage('{role}', '{escaped_text}', '{target_agent}')")
            else:
                window.evaluate_js(f"addMessage('{role}', '{escaped_text}', null)")
        except Exception as e:
            import logging
            logging.getLogger("across_agents_assistant").error(f"UI update failed: {e}")
            
    app.on_message_callback = on_message
    
    # Poll for config changes to update sidebar
    import time
    def poll_config():
        last_agent = api.manager.get_active_agent()
        while True:
            time.sleep(1)
            current_agent = api.manager.get_active_agent()
            if current_agent != last_agent:
                last_agent = current_agent
                try:
                    window.evaluate_js("loadData()")
                except Exception:
                    pass
    import threading
    threading.Thread(target=poll_config, daemon=True).start()
    
    webview.start(create_tray, window)
