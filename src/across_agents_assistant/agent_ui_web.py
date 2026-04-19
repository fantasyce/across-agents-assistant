import webview
import os
import subprocess

from .agent_manager import AgentManager

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Across-Agents Assistant</title>
    <style>
        :root {
            --bg-color: #f5f5f7;
            --card-bg: #ffffff;
            --text-color: #1d1d1f;
            --secondary-text: #86868b;
            --accent-color: #0071e3;
            --border-radius: 16px;
            --border-color: rgba(0,0,0,0.05);
            --card-shadow: 0 4px 20px rgba(0,0,0,0.04);
            --card-hover-shadow: 0 8px 30px rgba(0,0,0,0.08);
        }

        @media (prefers-color-scheme: dark) {
            :root {
                --bg-color: #000000;
                --card-bg: #1c1c1e;
                --text-color: #f5f5f7;
                --secondary-text: #98989d;
                --accent-color: #0a84ff;
                --border-color: rgba(255,255,255,0.05);
                --card-shadow: 0 4px 20px rgba(0,0,0,0.2);
                --card-hover-shadow: 0 8px 30px rgba(0,0,0,0.4);
            }
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 40px;
            -webkit-font-smoothing: antialiased;
            user-select: none;
        }

        h1 {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 8px;
            text-align: center;
            letter-spacing: -0.01em;
        }

        .subtitle {
            text-align: center;
            color: var(--secondary-text);
            font-size: 14px;
            margin-bottom: 40px;
        }

        .agent-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
            gap: 20px;
            padding-bottom: 80px;
        }

        .agent-card {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 24px 16px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            box-shadow: var(--card-shadow);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            border: 2px solid var(--border-color);
            cursor: pointer;
            position: relative;
        }

        .agent-card:hover {
            transform: translateY(-4px);
            box-shadow: var(--card-hover-shadow);
        }

        .agent-card.active {
            border-color: var(--accent-color);
            background: rgba(0, 113, 227, 0.05);
        }
        
        @media (prefers-color-scheme: dark) {
            .agent-card.active {
                background: rgba(10, 132, 255, 0.1);
            }
        }

        .agent-card.unready {
            opacity: 0.6;
            filter: grayscale(0.5);
        }

        .agent-icon {
            width: 48px;
            height: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            margin-bottom: 12px;
            overflow: hidden;
            background: var(--bg-color);
        }
        
        .agent-icon img, .agent-icon svg {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .agent-name {
            font-size: 15px;
            font-weight: 600;
            text-align: center;
        }

        .agent-status {
            font-size: 11px;
            margin-top: 6px;
            color: var(--secondary-text);
            display: flex;
            align-items: center;
            gap: 4px;
        }
        
        .status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
        }
        
        .ready-dot { background-color: #34c759; }
        .unready-dot { background-color: #ff9f0a; }

        .gear-icon {
            position: absolute;
            top: 10px;
            right: 10px;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            background: var(--bg-color);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            opacity: 0;
            transition: opacity 0.2s;
            color: var(--secondary-text);
        }

        .agent-card:hover .gear-icon {
            opacity: 1;
        }
        
        .gear-icon:hover {
            background: var(--border-color);
            color: var(--text-color);
        }

        .add-card {
            border: 2px dashed var(--border-color);
            background: transparent;
            box-shadow: none;
            color: var(--secondary-text);
        }

        .add-card:hover {
            border-color: var(--accent-color);
            color: var(--accent-color);
            background: transparent;
        }
        
        .add-icon {
            width: 48px;
            height: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            font-weight: 300;
            margin-bottom: 12px;
            background: var(--card-bg);
        }

        /* Modal Styles */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.4);
            backdrop-filter: blur(4px);
            align-items: center;
            justify-content: center;
            z-index: 100;
        }

        .modal {
            background: var(--card-bg);
            padding: 30px;
            border-radius: var(--border-radius);
            width: 90%;
            max-width: 360px;
            box-shadow: var(--card-hover-shadow);
        }

        .modal h2 {
            margin-top: 0;
            font-size: 18px;
            font-weight: 600;
            text-align: center;
            margin-bottom: 24px;
        }

        .form-group {
            margin-bottom: 16px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-size: 12px;
            font-weight: 600;
            color: var(--secondary-text);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .form-group input {
            width: 100%;
            padding: 12px;
            border: 1px solid var(--border-color);
            border-radius: 10px;
            background: var(--bg-color);
            color: var(--text-color);
            font-size: 14px;
            box-sizing: border-box;
            transition: border-color 0.2s;
        }

        .form-group input:focus {
            outline: none;
            border-color: var(--accent-color);
        }

        .modal-actions {
            display: flex;
            justify-content: space-between;
            margin-top: 30px;
        }

        .btn {
            background-color: var(--bg-color);
            color: var(--text-color);
            border: none;
            padding: 10px 20px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .btn:hover {
            background-color: var(--border-color);
        }

        .btn-primary {
            background-color: var(--accent-color);
            color: white;
        }
        
        .btn-primary:hover {
            background-color: #005bb5;
        }

        .path-input-group {
            display: flex;
            gap: 8px;
        }

        /* Toast Notification */
        .toast {
            visibility: hidden;
            min-width: 200px;
            margin-left: -100px;
            background-color: var(--text-color);
            color: var(--bg-color);
            text-align: center;
            border-radius: 20px;
            padding: 12px 20px;
            position: fixed;
            z-index: 1000;
            left: 50%;
            top: 30px;
            font-size: 14px;
            font-weight: 500;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            opacity: 0;
            transition: opacity 0.3s, top 0.3s, transform 0.3s;
            transform: translateY(-10px);
        }

        .toast.show {
            visibility: visible;
            opacity: 1;
            transform: translateY(0);
        }

        /* Bottom fixed bar */
        .bottom-bar {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 20px 30px;
            background: linear-gradient(to top, var(--bg-color) 60%, transparent);
            display: flex;
            justify-content: center;
            z-index: 10;
            pointer-events: none; /* Let clicks pass through gradient */
        }
        
        .btn-finish {
            background-color: var(--text-color);
            color: var(--bg-color);
            font-size: 15px;
            font-weight: 600;
            padding: 12px 32px;
            border-radius: 24px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15);
            pointer-events: auto;
            border: none;
            cursor: pointer;
            transition: transform 0.2s;
        }
        
        .btn-finish:hover {
            transform: scale(1.02);
        }
    </style>
</head>
<body>

    <h1>选择智能体</h1>
    <div class="subtitle">即刻生效，无缝切换</div>
    
    <div class="agent-grid" id="agent-list">
        <!-- Rendered by JS -->
    </div>

    <div class="bottom-bar">
        <button class="btn btn-finish" onclick="finishConfig()">关闭窗口</button>
    </div>

    <!-- Toast Notification -->
    <div id="toast" class="toast"></div>

    <!-- Add Custom Agent Modal -->
    <div class="modal-overlay" id="add-modal">
        <div class="modal">
            <h2>添加自定义智能体</h2>
            <div class="form-group">
                <label>名称</label>
                <input type="text" id="custom-name" placeholder="my_bot">
            </div>
            <div class="form-group">
                <label>执行路径</label>
                <div class="path-input-group">
                    <input type="text" id="custom-path" placeholder="/usr/local/bin/bot">
                    <button class="btn" onclick="browseFile('custom-path')">浏览</button>
                </div>
            </div>
            <div class="form-group">
                <label>参数模板</label>
                <input type="text" id="custom-args" value="--query {message}">
            </div>
            <div class="modal-actions">
                <button class="btn" onclick="closeAddModal()">取消</button>
                <button class="btn btn-primary" onclick="saveCustomAgent()">保存</button>
            </div>
        </div>
    </div>

    <script>
        let config = {};
        let toastTimeout;
        
        const AGENT_DISPLAY_NAMES = {
            'openclaw': 'Openclaw',
            'hermes': 'Hermes',
            'claude': 'Claude Code'
        };

        function getDisplayName(id) {
            return AGENT_DISPLAY_NAMES[id] || id;
        }

        function showToast(message) {
            const toast = document.getElementById("toast");
            toast.innerText = message;
            toast.className = "toast show";
            clearTimeout(toastTimeout);
            toastTimeout = setTimeout(function(){ toast.className = toast.className.replace("show", ""); }, 2500);
        }

        async function loadData() {
            config = await pywebview.api.get_config();
            renderList();
        }

        function renderList() {
            const list = document.getElementById('agent-list');
            list.innerHTML = '';

            const agents = config.agents || {};
            const active = config.active_agent;

            for (const [id, agent] of Object.entries(agents)) {
                const isReady = agent.executable_path && agent.executable_path.trim() !== '';
                const isActive = id === active;
                const displayName = getDisplayName(id);
                
                let iconHtml = '';
                if (config.icons && config.icons[id]) {
                    iconHtml = `<img src="${config.icons[id]}" alt="${displayName}">`;
                } else {
                    let iconText = id.substring(0, 2).toUpperCase();
                    iconHtml = `<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:#e5e5ea;color:#000;">${iconText}</div>`;
                }

                const card = document.createElement('div');
                card.className = `agent-card ${isActive ? 'active' : ''} ${isReady ? 'ready' : 'unready'}`;
                
                card.onclick = () => handleCardClick(id, isReady);
                
                card.innerHTML = `
                    <div class="gear-icon" onclick="event.stopPropagation(); detectOrConfig('${id}')">⚙️</div>
                    <div class="agent-icon">${iconHtml}</div>
                    <div class="agent-name">${displayName}</div>
                    <div class="agent-status">
                        <div class="status-dot ${isReady ? 'ready-dot' : 'unready-dot'}"></div>
                        ${isReady ? (isActive ? '使用中' : '已就绪') : '未配置'}
                    </div>
                `;
                list.appendChild(card);
            }
            
            // Add Custom Card
            const addCard = document.createElement('div');
            addCard.className = 'agent-card add-card';
            addCard.onclick = openAddModal;
            addCard.innerHTML = `
                <div class="add-icon">+</div>
                <div class="agent-name">添加</div>
            `;
            list.appendChild(addCard);
        }

        async function handleCardClick(id, isReady) {
            if (isReady) {
                // Hot swap
                const success = await pywebview.api.set_active(id);
                if (success) {
                    config.active_agent = id;
                    renderList();
                    showToast(`已切换至 ${id}`);
                }
            } else {
                // Try to detect or config
                showToast("检测环境中...");
                await detectOrConfig(id);
            }
        }

        async function detectOrConfig(id) {
            const result = await pywebview.api.detect_or_config(id);
            if (result.success) {
                config = await pywebview.api.get_config();
                renderList();
                if (result.msg) showToast(result.msg);
                
                // Hot swap automatically after detection
                const success = await pywebview.api.set_active(id);
                if (success) {
                    config.active_agent = id;
                    renderList();
                }
            } else if (result.msg) {
                showToast(result.msg);
            }
        }

        function openAddModal() {
            document.getElementById('add-modal').style.display = 'flex';
        }

        function closeAddModal() {
            document.getElementById('add-modal').style.display = 'none';
        }

        async function browseFile(inputId) {
            const path = await pywebview.api.browse_file();
            if (path) {
                document.getElementById(inputId).value = path;
            }
        }

        async function saveCustomAgent() {
            const name = document.getElementById('custom-name').value.trim();
            const path = document.getElementById('custom-path').value.trim();
            const args = document.getElementById('custom-args').value.trim();

            if (!name || !path) {
                showToast("名称和路径不能为空");
                return;
            }

            const success = await pywebview.api.add_custom_agent(name, path, args);
            if (success) {
                closeAddModal();
                config = await pywebview.api.get_config();
                renderList();
                showToast("添加成功！");
            } else {
                showToast("路径无效或文件不存在");
            }
        }

        async function finishConfig() {
            const active = config.active_agent;
            const agent = config.agents[active];
            if (!agent || !agent.executable_path) {
                showToast("请先配置当前选中的智能体！");
                return;
            }
            await pywebview.api.close_window();
        }

        window.addEventListener('pywebviewready', function() {
            loadData();
        });
    </script>
</body>
</html>
"""

class Api:
    def __init__(self, manager: AgentManager, window):
        self.manager = manager
        self.window = window

    def get_config(self):
        # Refresh is_ready status for UI
        from .icons import AGENT_ICONS
        conf = self.manager.config.copy()
        conf["icons"] = AGENT_ICONS
        return conf

    def close_window(self):
        self.window.destroy()
        import os
        os._exit(0)
        return True

    def set_active(self, agent_id):
        self.manager.set_active_agent(agent_id)
        return True

    def browse_file(self):
        file_types = ('All files (*.*)',)
        result = self.window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, directory="/usr/local/bin")
        if result and len(result) > 0:
            return result[0]
        return None

    def detect_or_config(self, agent_id):
        # Auto detection logic
        import shutil
        
        # Try `which` first, which checks system PATH
        path = shutil.which(agent_id)
        
        # If not found, try a common zsh execution to capture user aliases
        if not path:
            try:
                result = subprocess.run(
                    ["/bin/zsh", "-l", "-c", f"which {agent_id}"],
                    capture_output=True, text=True
                )
                output = result.stdout.strip()
                if output and "not found" not in output.lower() and os.path.exists(output):
                    path = output
            except Exception:
                pass
                
        # Also manually check common paths
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
            return {"success": True, "msg": f"成功检测到 {agent_id}！\n路径: {path}"}
            
        # If auto detection fails, open file dialog manually
        self.window.evaluate_js(f"showToast('未能在环境变量中自动找到 {agent_id}。请手动选择可执行文件。')")
        file_path = self.browse_file()
        
        if file_path and os.path.exists(file_path) and os.access(file_path, os.X_OK):
            config = self.manager.get_agent_config(agent_id)
            config["executable_path"] = file_path
            self.manager.update_agent(agent_id, config)
            return {"success": True, "msg": f"已成功配置 {agent_id}！"}
        elif file_path:
            return {"success": False, "msg": "所选文件无效或不可执行！"}
            
        return {"success": False, "msg": ""}

    def add_custom_agent(self, name, path, args):
        if not os.path.exists(path):
            return False
            
        config = {
            "type": "custom",
            "executable_path": path,
            "args_template": args.split(" "),
            "output_format": "raw"
        }
        self.manager.update_agent(name, config)
        return True

def show_agent_ui():
    manager = AgentManager()
    
    # Create window
    window = webview.create_window(
        'Across-Agents Assistant - 智能体配置', 
        html=HTML_CONTENT,
        width=600, 
        height=650,
        resizable=False
    )
    
    # Expose API
    api = Api(manager, window)
    window.expose(api.get_config, api.close_window, api.set_active, api.detect_or_config, api.browse_file, api.add_custom_agent)
    
    def on_closed():
        import os
        os._exit(0)
        
    window.events.closed += on_closed
    
    # Start
    webview.start(debug=False)

if __name__ == "__main__":
    show_agent_ui()
