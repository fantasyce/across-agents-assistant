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
            --accent-color: #CBA6F0; /* 饱和度50%的淡紫色 */
            --border-color: rgba(0,0,0,0.08);
            --msg-user-bg: #EBE3F5; /* 亮度合适，饱和度降低（变淡）的浅紫色 */
            --msg-user-text: #000000;
            --msg-agent-bg: transparent; /* 取消Agent背景色 */
            --msg-agent-text: #000000;
            --tree-active-bg: rgba(203, 166, 240, 0.25); /* 左侧目录选中颜色 */
        }

        @media (prefers-color-scheme: dark) {
            :root {
                --bg-color: #1c1c1e;
                --sidebar-bg: #1c1c1e;
                --text-color: #f5f5f7;
                --secondary-text: #98989d;
                --accent-color: #B58AE3; /* 暗色下的淡紫色 */
                --border-color: rgba(255,255,255,0.1);
                --msg-user-bg: #9B82C6; /* 亮度合适，饱和度降低（变淡）的浅紫色 */
                --msg-user-text: #ffffff;
                --msg-agent-bg: transparent; 
                --msg-agent-text: #ffffff;
                --tree-active-bg: rgba(181, 138, 227, 0.25);
            }
        }

        html {
            background: transparent;
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
            border-radius: 10px;
        }

        /* File Explorer (Left) */
        .file-explorer {
            width: 250px;
            min-width: 150px;
            max-width: 50%;
            background-color: var(--sidebar-bg);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            z-index: 10;
            position: relative;
        }
        
        .resizer {
            width: 5px;
            cursor: col-resize;
            position: absolute;
            right: -2px;
            top: 0;
            bottom: 0;
            z-index: 20;
        }
        .resizer:hover {
            background-color: var(--accent-color);
            opacity: 0.5;
        }
        .explorer-header {
            height: 56px;
            padding-top: 8px;
            display: flex;
            align-items: center;
            justify-content: flex-start;
            gap: 10px;
            padding-left: 16px;
            padding-right: 16px;
            font-size: 14px;
            font-weight: normal;
            border-bottom: none;
            flex-shrink: 0;
            -webkit-app-region: drag;
            -webkit-user-select: none;
            user-select: none;
        }
        
        .mac-buttons {
            display: flex;
            gap: 8px;
            align-items: center;
            margin-right: 6px;
            -webkit-app-region: no-drag;
        }

        .mac-btn {
            width: 12px;
            height: 12px;
            border-radius: 3px;
            cursor: pointer;
            transition: background-color 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            color: transparent;
            font-size: 8px;
            font-weight: 800;
            line-height: 1;
        }
        
        .mac-btn svg {
            width: 8px;
            height: 8px;
            opacity: 0;
            transition: opacity 0.2s;
            stroke: rgba(0, 0, 0, 0.55);
            stroke-width: 1.5;
            stroke-linecap: round;
            stroke-linejoin: round;
            fill: none;
        }

        .mac-btn.maximize svg {
            fill: rgba(0, 0, 0, 0.55);
            stroke: none;
            width: 7px;
            height: 7px;
        }

        .mac-buttons:hover .mac-btn svg {
            opacity: 1;
        }

        /* 默认状态加入 60% 白色，让颜色变得更粉嫩柔和 */
        .mac-btn.close { background-color: #FFBFBB; }
        .mac-btn.minimize { background-color: #FFE4AB; }
        .mac-btn.maximize { background-color: #A8E9B2; }

        /* hover 时恢复原本鲜艳的颜色 */
        .mac-btn.close:hover { background-color: #FF5F56; }
        .mac-btn.minimize:hover { background-color: #FFBD2E; }
        .mac-btn.maximize:hover { background-color: #27C93F; }

        .explorer-header .btn-icon {
            font-size: 16px;
            opacity: 1;
            background: transparent;
            -webkit-app-region: no-drag;
        }
        
        .explorer-header .btn-icon:hover {
            background: transparent;
            opacity: 1;
            color: var(--accent-color);
        }
        .tree-container {
            flex: 1;
            overflow-y: auto;
            padding: 0 0 10px 0;
        }
        .tree-item-wrapper {
            display: flex;
            flex-direction: column;
        }
        .tree-item {
            padding: 4px 16px;
            font-size: 12px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            user-select: none;
            white-space: nowrap;
        }
        .tree-item:hover {
            background-color: var(--border-color);
        }
        .tree-item.active-item {
            background-color: var(--tree-active-bg);
            color: var(--accent-color);
        }

        .tree-item-name {
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .tree-children {
            padding-left: 15px;
            display: none;
        }
        .tree-children.open {
            display: block;
        }

        /* Sidebar (Right) */
        .sidebar {
            width: 80px;
            background-color: var(--sidebar-bg);
            border-left: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            align-items: center;
            padding-top: 20px; /* 减小上边距以对齐功能图标 */
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
            min-width: 0; /* Important for flex child */
        }

        .header {
            height: 56px;
            padding-top: 8px;
            border-bottom: none;
            display: flex;
            align-items: center;
            padding-left: 20px;
            padding-right: 20px;
            font-size: 14px;
            font-weight: 600;
            background: var(--bg-color);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            z-index: 5;
            justify-content: space-between;
            -webkit-app-region: drag;
            -webkit-user-select: none;
            user-select: none;
        }
        
        .header-actions {
            display: flex;
            gap: 12px;
            align-items: center;
            -webkit-app-region: no-drag;
        }

        .btn-icon {
            background: transparent;
            border: none;
            cursor: pointer;
            color: var(--secondary-text);
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            border-radius: 6px;
            -webkit-app-region: no-drag;
        }
        
        .btn-icon svg {
            width: 20px;
            height: 20px;
            pointer-events: none;
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
            padding: 8px 24px 24px 24px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            align-items: center; /* 使内容居中 */
        }
        
        .message {
            max-width: 900px;
            width: 100%;
            font-size: 13px;
            line-height: 1.7; /* 增加行距 */
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
            padding: 8px 12px;
            border-radius: 12px;
            border-bottom-right-radius: 4px;
            width: auto; /* 让内容自适应宽度，不超过 100% */
            max-width: 85%;
        }

        .msg-agent {
            align-self: center; /* 铺满居中 */
            width: 100%;
            background-color: transparent;
            color: var(--msg-agent-text);
            padding: 4px 0; /* 没有背景色，直接平铺不需要太多 padding */
            border-radius: 0;
            white-space: pre-wrap; /* 允许换行，但由于容器宽，只有长句自然折行 */
        }
        
        .msg-system {
            align-self: center;
            background-color: transparent;
            color: var(--secondary-text);
            font-size: 11px;
            text-align: center;
            padding: 4px;
        }

                .input-area {
            padding: 12px 24px 16px 24px; /* 底部间距 16px */
            background: var(--bg-color);
            border-top: none;
            display: flex;
            flex-direction: column;
            gap: 8px;
            transition: background 0.2s;
            align-items: center;
        }

        .input-row {
            display: flex;
            gap: 12px;
            align-items: center; /* 解决高低差问题 */
            max-width: 900px;
            margin: 0 auto;
            width: 100%;
        }

        .chat-input-wrapper {
            flex: 1;
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 4px 10px;
            background: var(--sidebar-bg);
            transition: border-color 0.2s, background-color 0.2s;
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 6px;
            min-height: 28px;
            box-sizing: border-box;
            cursor: text;
        }

        .chat-input-wrapper:focus-within {
            border-color: var(--accent-color);
        }

        .chat-input-wrapper.drag-over {
            background-color: rgba(0, 113, 227, 0.05);
            border: 2px dashed var(--accent-color);
        }

        .chat-input-inner {
            border: none;
            background: transparent;
            font-size: 13px;
            line-height: 18px; /* 固定行高，防止插入标签时撑开 */
            color: var(--text-color);
            outline: none;
            flex: 1;
            min-width: 100px;
            padding: 0;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .inline-file-tag {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            background: rgba(0, 113, 227, 0.1);
            border: 1px solid var(--accent-color);
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 12px; 
            color: var(--accent-color);
            vertical-align: baseline; 
            user-select: none; /* 设置为 none 避免光标卡在内部 */
            -webkit-user-select: none;
            cursor: default;
            line-height: 1; /* 防止撑开外部行高 */
        }
        
        .inline-file-tag-icon {
            font-size: 12px;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 14px;
            height: 14px;
            transition: all 0.2s;
        }

        .inline-file-tag-icon svg {
            width: 100%;
            height: 100%;
        }

        .folder-icon svg, .file-icon svg {
            width: 12px;
            height: 12px;
        }
        
        .inline-file-tag-icon:hover::before {
            content: "×";
            color: red;
            font-weight: bold;
            font-size: 16px;
        }
        
        .inline-file-tag-icon.dir-icon:hover {
            color: transparent;
        }
        .inline-file-tag-icon.file-icon:hover {
            color: transparent;
        }

        .btn-send {
            background-color: var(--accent-color);
            color: white;
            border: none;
            width: 28px;
            height: 28px;
            border-radius: 6px; /* 圆角方块 */
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 14px;
            transition: transform 0.2s;
            flex-shrink: 0;
            /* 移除了导致高低差的 margin-bottom */
        }

        .btn-send:hover {
            transform: scale(1.05);
        }

        /* Context Menu */
        .context-menu {
            position: fixed;
            z-index: 10000;
            background: var(--sidebar-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            padding: 4px 0;
            min-width: 140px;
            display: none;
            font-size: 13px;
        }
        .context-menu.show {
            display: block;
        }
        .context-menu-item {
            padding: 8px 16px;
            cursor: pointer;
            color: var(--text-color);
        }
        .context-menu-item:hover {
            background-color: var(--accent-color);
            color: white;
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

    <div class="file-explorer" id="file-explorer">
        <div class="explorer-header pywebview-drag-region" ondblclick="maximizeWindow()">
            <div class="mac-buttons">
                <div class="mac-btn close" onclick="closeWindow(event)" title="关闭">
                    <svg viewBox="0 0 10 10"><line x1="2" y1="2" x2="8" y2="8"/><line x1="8" y1="2" x2="2" y2="8"/></svg>
                </div>
                <div class="mac-btn minimize" onclick="minimizeWindow(event)" title="最小化">
                    <svg viewBox="0 0 10 10"><line x1="1.5" y1="5" x2="8.5" y2="5"/></svg>
                </div>
                <div class="mac-btn maximize" onclick="maximizeWindow(event)" title="最大化">
                    <svg viewBox="0 0 10 10">
                        <polygon points="2.5,4.5 2.5,2.5 4.5,2.5"/>
                        <polygon points="7.5,5.5 7.5,7.5 5.5,7.5"/>
                    </svg>
                </div>
            </div>
            <button class="btn-icon" onclick="collapseAllExplorer()" title="收起全部" id="btn-collapse">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="11 17 6 12 11 7"></polyline><polyline points="18 17 13 12 18 7"></polyline></svg>
            </button>
            <button class="btn-icon" onclick="refreshExplorer()" title="刷新" id="btn-refresh">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
            </button>
        </div>
        <div class="tree-container" id="tree-container">
            <!-- Rendered by JS -->
        </div>
        <div class="resizer" id="resizer"></div>
    </div>

    <div class="main-area">
        <div class="header pywebview-drag-region" ondblclick="maximizeWindow()">
            <span id="current-agent-name"></span>
            <div class="header-actions">
                <button class="btn-icon" id="btn-continuous" onclick="toggleContinuous()" title="开启持续对话">
                    <svg viewBox="1 1 22 22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M 2 12 C 5 5, 9 5, 12 8 C 15 5, 19 5, 22 12"></path><path d="M 2 12 C 6 22, 18 22, 22 12"></path><path d="M 2 12 Q 12 14 22 12"></path></svg>
                </button>
                <button class="btn-icon" id="btn-speak" onclick="triggerSingleTurn()" title="单次对话 (点击说话)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>
                </button>
                <button class="btn-icon" id="btn-silent" onclick="toggleSilentMode()" title="静音模式">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>
                </button>
                <button class="btn-icon active" id="btn-chatmode" onclick="toggleChatMode()" title="当前: 隔离对话模式">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                </button>
                <button class="btn-icon" id="btn-settings" onclick="openSettings()" title="配置智能体">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06-.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1h-.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1h.09a1.65 1.65 0 0 0 1.51-1z"></path></svg>
                </button>
            </div>
        </div>
        
        <div class="chat-container" id="chat-container">
            <!-- Messages rendered by JS -->
        </div>

        <div class="input-area" id="input-area">
            <div class="input-row">
                <div class="chat-input-wrapper" id="chat-input-wrapper">
                    <div class="chat-input-inner" id="chat-input" contenteditable="true" placeholder="输入消息或拖拽文件到此处 (回车发送)..."></div>
                </div>
                <button class="btn-send" onclick="sendManualMessage()">↑</button>
            </div>
        </div>
    </div>

    <div class="sidebar" id="sidebar">
        <!-- Rendered by JS -->
    </div>
    <div id="toast" class="toast"></div>

    <div id="context-menu" class="context-menu">
        <div class="context-menu-item" id="cm-reveal">在 Finder 中显示</div>
        <div class="context-menu-item" id="cm-add">添加到对话</div>
        <div class="context-menu-item" id="cm-copy">复制路径</div>
        <div class="context-menu-item" id="cm-rename">重命名</div>
        <div class="context-menu-item" id="cm-delete">删除</div>
    </div>


    <script>
        let config = {};
        let toastTimeout;
        let chatMode = 'isolated'; // 'merged' or 'isolated'
        let chatHistory = {
            merged: [],
        };
        
        const ICONS = {
            folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>',
            folderOpen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><polyline points="14 10 18 14 22 10"></polyline></svg>',
            file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline></svg>',
            mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>',
            micOff: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="1" y1="1" x2="23" y2="23"></line><path d="M9 9v3a3 3 0 0 0 5.12 1.88M15 9.34V4a3 3 0 0 0-5.94-.6"></path><path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>',
            vol: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>',
            volOff: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line></svg>',
            chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>',
            continuous: '<svg viewBox="1 1 22 22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M 2 12 C 4 2, 10 2, 12 6 C 14 2, 20 2, 22 12"></path><path d="M 2 12 C 6 23, 18 23, 22 12"></path><path d="M 2 12 Q 12 7 22 12"></path><path d="M 2 12 Q 12 17 22 12"></path></svg>',
            continuousOff: '<svg viewBox="1 1 22 22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M 2 12 C 5 5, 9 5, 12 8 C 15 5, 19 5, 22 12"></path><path d="M 2 12 C 6 22, 18 22, 22 12"></path><path d="M 2 12 Q 12 14 22 12"></path></svg>',
            settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06-.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1h-.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1h.09a1.65 1.65 0 0 0 1.51-1z"></path></svg>',
            refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>',
            collapse: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="11 17 6 12 11 7"></polyline><polyline points="18 17 13 12 18 7"></polyline></svg>',
            chatGlobal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 12 12 17 22 12"></polyline><polyline points="2 17 12 22 22 17"></polyline></svg>'
        };

        function showToast(message) {
            const toast = document.getElementById("toast");
            toast.innerText = message;
            toast.className = "toast show";
            clearTimeout(toastTimeout);
            toastTimeout = setTimeout(() => { toast.className = toast.className.replace("show", ""); }, 2500);
        }

        let isExplorerLoaded = false;
        let currentRootPath = null;

        async function loadData() {
            try {
                config = await pywebview.api.get_config();
                if (!chatHistory[config.active_agent]) {
                    chatHistory[config.active_agent] = [];
                }
                renderSidebar();
                updateHeader();
                renderChat();
                
                const state = await pywebview.api.get_ui_state();
                
                document.getElementById('btn-collapse').innerHTML = ICONS.collapse;
            document.getElementById('btn-refresh').innerHTML = ICONS.refresh;
            document.getElementById('btn-speak').innerHTML = ICONS.mic;
            document.getElementById('btn-chatmode').innerHTML = ICONS.chat;
            document.getElementById('btn-settings').innerHTML = ICONS.settings;
            
            const btnCont = document.getElementById('btn-continuous');
            if (state.continuous_on) {
                btnCont.innerHTML = ICONS.continuous;
                btnCont.title = "关闭持续对话";
                btnCont.classList.add('active');
            } else {
                btnCont.innerHTML = ICONS.continuousOff;
                btnCont.title = "开启持续对话";
                btnCont.classList.remove('active');
            }
            
            const btnSilent = document.getElementById('btn-silent');
            if (state.silent_on) {
                btnSilent.innerHTML = ICONS.volOff;
                btnSilent.title = "关闭静音模式";
                btnSilent.classList.add('active');
            } else {
                btnSilent.innerHTML = ICONS.vol;
                btnSilent.title = "开启静音模式";
                btnSilent.classList.remove('active');
            }
                
                // Initialize File Explorer
                if (!isExplorerLoaded) {
                    await loadDirectory(null, document.getElementById('tree-container'));
                    isExplorerLoaded = true;
                }
            } catch (err) {
                console.error("Error in loadData:", err);
                document.body.innerHTML = `<div style="color:red;padding:20px;font-size:20px;">JS Error: ${err.message}<br><pre>${err.stack}</pre></div>`;
            }
        }
        
        
        // Context Menu Logic
        let cmTargetEntry = null;
        let cmTargetElement = null;
        const contextMenu = document.getElementById('context-menu');

        document.addEventListener('click', () => {
            contextMenu.classList.remove('show');
        });

        document.getElementById('cm-reveal').onclick = async () => {
            if (!cmTargetEntry) return;
            await pywebview.api.reveal_in_finder(cmTargetEntry.absolute_path);
        };

        document.getElementById('cm-add').onclick = () => {
            if (!cmTargetEntry) return;
            insertInlineFileTag(cmTargetEntry.name, cmTargetEntry.absolute_path, cmTargetEntry.is_dir);
        };

        document.getElementById('cm-copy').onclick = () => {
            if (!cmTargetEntry) return;
            navigator.clipboard.writeText(cmTargetEntry.absolute_path);
            showToast("已复制路径");
        };

        document.getElementById('cm-rename').onclick = async () => {
            if (!cmTargetEntry) return;
            const newName = prompt("请输入新名称:", cmTargetEntry.name);
            if (newName && newName !== cmTargetEntry.name) {
                const res = await pywebview.api.rename_file(cmTargetEntry.absolute_path, newName);
                if (res.success) {
                    showToast("重命名成功");
                    refreshExplorer();
                } else {
                    showToast("重命名失败: " + res.error);
                }
            }
        };

        document.getElementById('cm-delete').onclick = async () => {
            if (!cmTargetEntry) return;
            if (confirm(`确定要删除 ${cmTargetEntry.name} 吗？
注意：该操作不可恢复！`)) {
                const res = await pywebview.api.delete_file(cmTargetEntry.absolute_path);
                if (res.success) {
                    showToast("删除成功");
                    refreshExplorer();
                } else {
                    showToast("删除失败: " + res.error);
                }
            }
        };

        function showContextMenu(e, entry, itemElement) {
            e.preventDefault();
            cmTargetEntry = entry;
            cmTargetElement = itemElement;
            setActiveItem(itemElement);
            
            contextMenu.style.left = e.clientX + 'px';
            contextMenu.style.top = e.clientY + 'px';
            contextMenu.classList.add('show');
            
            // Adjust position if it goes off screen
            const rect = contextMenu.getBoundingClientRect();
            if (rect.right > window.innerWidth) {
                contextMenu.style.left = (window.innerWidth - rect.width) + 'px';
            }
            if (rect.bottom > window.innerHeight) {
                contextMenu.style.top = (window.innerHeight - rect.height) + 'px';
            }
        }

        function setActiveItem(item) {
            document.querySelectorAll('.tree-item').forEach(el => el.classList.remove('active-item'));
            item.classList.add('active-item');
        }

        async function refreshExplorer() {
            const activeItem = document.querySelector('.tree-item.active-item');
            let targetContainer = document.getElementById('tree-container');
            let targetPath = currentRootPath;
            
            if (activeItem) {
                const isDir = activeItem.querySelector('.folder-icon') !== null;
                if (isDir) {
                    targetContainer = activeItem.nextElementSibling;
                    targetPath = activeItem.querySelector('.tree-item-name').title;
                    if (activeItem.dataset.loaded === "true") {
                        targetContainer.innerHTML = '';
                        await loadDirectory(targetPath, targetContainer);
                    }
                    return;
                }
            }
            
            // Fallback to refresh root
            targetContainer.innerHTML = '';
            await loadDirectory(targetPath, targetContainer);
        }

        function collapseAllExplorer() {
            const items = document.querySelectorAll('#tree-container .tree-item[data-open="true"]');
            items.forEach(item => {
                item.dataset.open = "false";
                const icon = item.querySelector('.folder-icon');
                if (icon) icon.innerHTML = ICONS.folder;
                const children = item.nextElementSibling;
                if (children && children.classList.contains('tree-children')) {
                    children.classList.remove('open');
                }
            });
        }
        
        async function loadDirectory(path, containerElement) {
            if (containerElement.id === 'tree-container') {
                currentRootPath = path;
            }
            const res = await pywebview.api.list_directory(path);
            if (!res.success) {
                showToast("无法读取目录: " + res.error);
                throw new Error("Failed to load directory: " + res.error);
            }
            
            console.log("Loaded directory:", path, "entries:", res.entries.length);
            
            containerElement.innerHTML = '';
            
            res.entries.forEach(entry => {
                const wrapper = document.createElement('div');
                wrapper.className = 'tree-item-wrapper';
                
                const item = document.createElement('div');
                item.className = 'tree-item';
                item.draggable = true;
                
                // Drag start event
                item.addEventListener('contextmenu', (e) => {
                    e.stopPropagation();
                    showContextMenu(e, entry, item);
                });

                item.addEventListener('dragstart', (e) => {
                    e.dataTransfer.setData('text/plain', entry.absolute_path);
                    e.dataTransfer.setData('application/json', JSON.stringify(entry));
                    e.dataTransfer.effectAllowed = 'copy';
                });
                
                const icon = document.createElement('span');
                icon.className = entry.is_dir ? 'folder-icon' : 'file-icon';
                icon.innerHTML = entry.is_dir ? ICONS.folder : ICONS.file;
                
                const name = document.createElement('span');
                name.className = 'tree-item-name';
                name.innerText = entry.name;
                name.title = entry.absolute_path;
                
                item.appendChild(icon);
                item.appendChild(name);
                wrapper.appendChild(item);
                
                if (entry.is_dir) {
                    const childrenContainer = document.createElement('div');
                    childrenContainer.className = 'tree-children';
                    wrapper.appendChild(childrenContainer);
                    
                    item.dataset.loaded = "false";
                    item.dataset.open = "false";
                    
                    item.onclick = async (e) => {
                        e.stopPropagation();
                        setActiveItem(item);
                        
                        if (item.dataset.loaded === "false") {
                            icon.innerHTML = ICONS.folderOpen;
                            try {
                                await loadDirectory(entry.absolute_path, childrenContainer);
                                item.dataset.loaded = "true";
                            } catch (err) {
                                console.error("Error loading directory:", err);
                                icon.innerHTML = ICONS.folder;
                                return;
                            }
                        } else {
                            icon.innerHTML = item.dataset.open === "true" ? ICONS.folder : ICONS.folderOpen;
                        }
                        item.dataset.open = item.dataset.open === "true" ? "false" : "true";
                        if (item.dataset.open === "true") {
                            childrenContainer.classList.add('open');
                        } else {
                            childrenContainer.classList.remove('open');
                        }
                    };
                } else {
                    item.onclick = (e) => {
                        e.stopPropagation();
                        setActiveItem(item);
                    };
                }
                
                containerElement.appendChild(wrapper);
            });
        }

        // Setup Drag and Drop for Input Area
        const inputWrapper = document.getElementById('chat-input-wrapper');
        const inputArea = document.getElementById('chat-input');
        
        // Track last saved cursor position
        let savedRange = null;
        
        inputArea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendManualMessage();
            }
        });
        
        // Save cursor position on blur
        inputArea.addEventListener('blur', () => {
            const sel = window.getSelection();
            if (sel.rangeCount > 0 && inputArea.contains(sel.anchorNode)) {
                savedRange = sel.getRangeAt(0).cloneRange();
            }
        });
        
        // Restore cursor position on focus
        inputArea.addEventListener('focus', () => {
            if (savedRange && inputArea.contains(savedRange.startContainer)) {
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(savedRange);
            }
        });
        
        // Click on wrapper focuses input
        inputWrapper.addEventListener('click', (e) => {
            if (e.target === inputWrapper) {
                inputArea.focus();
            }
        });
        
        // CRITICAL: Do NOT call preventDefault() in dragover
        // This allows the browser to show the caret position automatically
        inputWrapper.addEventListener('dragover', (e) => {
            e.dataTransfer.dropEffect = 'copy';
            inputWrapper.classList.add('drag-over');
        });
        
        inputWrapper.addEventListener('dragleave', (e) => {
            inputWrapper.classList.remove('drag-over');
        });
        
        inputWrapper.addEventListener('drop', (e) => {
            e.preventDefault();
            inputWrapper.classList.remove('drag-over');
            
            const path = e.dataTransfer.getData('text/plain');
            let entryData = null;
            try {
                entryData = JSON.parse(e.dataTransfer.getData('application/json'));
            } catch (err) {}
            
            if (path) {
                const name = entryData ? entryData.name : path.split('/').pop();
                const is_dir = entryData ? entryData.is_dir : !path.includes('.');
                
                // Get drop position immediately using caretRangeFromPoint
                let insertRange = null;
                if (document.caretRangeFromPoint) {
                    insertRange = document.caretRangeFromPoint(e.clientX, e.clientY);
                }
                
                // Create inline file tag
                const tag = document.createElement('span');
                tag.className = 'inline-file-tag';
                tag.setAttribute('data-path', path);
                tag.setAttribute('data-name', name);
                tag.setAttribute('data-is-dir', is_dir);
                tag.contentEditable = false;
                
                const iconWrapper = document.createElement('span');
                iconWrapper.className = `inline-file-tag-icon ${is_dir ? 'dir-icon' : 'file-icon'}`;
                const iconText = document.createElement('span');
                iconText.innerHTML = is_dir ? ICONS.folder : ICONS.file;
                iconText.className = 'icon-emoji';
                iconWrapper.appendChild(iconText);
                
                iconWrapper.onclick = (e) => {
                    e.stopPropagation();
                    tag.remove();
                };
                iconWrapper.onmouseenter = () => { iconText.style.display = 'none'; };
                iconWrapper.onmouseleave = () => { iconText.style.display = 'inline'; };
                
                const nameSpan = document.createElement('span');
                nameSpan.innerText = name;
                
                tag.appendChild(iconWrapper);
                tag.appendChild(nameSpan);
                
                // Determine where to insert
                let range;
                const sel = window.getSelection();
                
                if (insertRange && inputArea.contains(insertRange.startContainer)) {
                    // Check if it's pointing to the container itself (WebKit bug)
                    if (insertRange.startContainer === inputArea && insertRange.startOffset === 0) {
                        // Try to find a better position by checking if there's text
                        if (inputArea.firstChild && inputArea.firstChild.nodeType === Node.TEXT_NODE) {
                            range = document.createRange();
                            range.setStart(inputArea.firstChild, 0);
                            range.setEnd(inputArea.firstChild, 0);
                        } else {
                            range = insertRange;
                        }
                    } else {
                        range = insertRange;
                    }
                } else if (sel.rangeCount > 0 && inputArea.contains(sel.anchorNode)) {
                    range = sel.getRangeAt(0);
                } else if (savedRange && inputArea.contains(savedRange.startContainer)) {
                    range = savedRange;
                } else {
                    range = document.createRange();
                    range.selectNodeContents(inputArea);
                    range.collapse(false);
                }
                
                // Insert the tag
                range.insertNode(tag);
                
                // 为了避免光标卡在无法编辑的元素旁边，在元素前后插入真实的空格或零宽空格
                const spaceAfter = document.createTextNode('\u200B ');
                const spaceBefore = document.createTextNode(' \u200B');
                
                // 将它们插入到DOM中
                range.setStartAfter(tag);
                range.collapse(true);
                range.insertNode(spaceAfter);
                
                range.setStartBefore(tag);
                range.collapse(true);
                range.insertNode(spaceBefore);
                
                // 将光标移动到标签后的空格之后
                range.setStartAfter(spaceAfter);
                range.collapse(true);
                sel.removeAllRanges();
                sel.addRange(range);
                
                // Save the new position
                savedRange = range.cloneRange();
                
                // Focus the input
                inputArea.focus();
            }
        });
        
        function insertInlineFileTag(name, path, is_dir) {
            const tag = document.createElement('span');
            tag.className = 'inline-file-tag';
            tag.setAttribute('data-path', path);
            tag.setAttribute('data-name', name);
            tag.setAttribute('data-is-dir', is_dir);
            tag.contentEditable = false;
            
            const iconWrapper = document.createElement('span');
            iconWrapper.className = `inline-file-tag-icon ${is_dir ? 'dir-icon' : 'file-icon'}`;
            // 使用 span 内部包裹真正的图标文字，方便在 CSS 中隐藏
            const iconText = document.createElement('span');
            iconText.innerHTML = is_dir ? ICONS.folder : ICONS.file;
            iconText.className = 'icon-emoji';
            iconWrapper.appendChild(iconText);
            
            iconWrapper.onclick = (e) => {
                e.stopPropagation();
                tag.remove();
            };
            
            // 悬停时隐藏原始表情
            iconWrapper.onmouseenter = () => { iconText.style.display = 'none'; };
            iconWrapper.onmouseleave = () => { iconText.style.display = 'inline'; };
            
            const nameSpan = document.createElement('span');
            nameSpan.innerText = name;
            
            tag.appendChild(iconWrapper);
            tag.appendChild(nameSpan);
            
            let range;
            const sel = window.getSelection();
            if (sel.rangeCount > 0 && inputArea.contains(sel.anchorNode)) {
                range = sel.getRangeAt(0);
            } else if (savedRange && inputArea.contains(savedRange.startContainer)) {
                range = savedRange;
            } else {
                range = document.createRange();
                range.selectNodeContents(inputArea);
                range.collapse(false);
            }
            
            range.insertNode(tag);
            
            const spaceAfter = document.createTextNode('\u200B ');
            const spaceBefore = document.createTextNode(' \u200B');
            
            range.setStartAfter(tag);
            range.collapse(true);
            range.insertNode(spaceAfter);
            
            range.setStartBefore(tag);
            range.collapse(true);
            range.insertNode(spaceBefore);
            
            range.setStartAfter(spaceAfter);
            range.collapse(true);
            sel.removeAllRanges();
            sel.addRange(range);
            savedRange = range.cloneRange();
            inputArea.focus();
        }
        
        function getInlineFileTags() {
            const tags = inputArea.querySelectorAll('.inline-file-tag');
            return Array.from(tags).map(tag => ({
                name: tag.getAttribute('data-name'),
                path: tag.getAttribute('data-path'),
                is_dir: tag.getAttribute('data-is-dir') === 'true'
            }));
        }
        
        function clearInlineFileTags() {
            const tags = inputArea.querySelectorAll('.inline-file-tag');
            tags.forEach(tag => tag.remove());
        }

        function toggleChatMode() {
            const btn = document.getElementById('btn-chatmode');
            if (chatMode === 'merged') {
                chatMode = 'isolated';
                btn.innerHTML = ICONS.chat;
                btn.title = "当前: 隔离对话模式 (仅当前智能体历史)";
                btn.classList.add('active');
            } else {
                chatMode = 'merged';
                btn.innerHTML = ICONS.chatGlobal;
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
                return;
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
            if (role === 'system') {
                if (text === 'Continuous_Off') {
                    const btn = document.getElementById('btn-continuous');
                    btn.innerHTML = ICONS.continuousOff;
                    btn.title = "开启持续对话";
                    btn.classList.remove('active');
                    return;
                }
                if (text === 'Continuous_On') {
                    const btn = document.getElementById('btn-continuous');
                    btn.innerHTML = ICONS.continuous;
                    btn.title = "关闭持续对话";
                    btn.classList.add('active');
                    return;
                }
            }

            const msg = { role, text };
            chatHistory.merged.push(msg);
            
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
                
                if (lastRenderState.agent === config.active_agent && 
                    lastRenderState.mode === chatMode && 
                    lastRenderState.length === history.length) {
                    return;
                }
                
                if (lastRenderState.agent !== config.active_agent || lastRenderState.mode !== chatMode) {
                    container.innerHTML = '';
                    const fragment = document.createDocumentFragment();
                    
                    if (history.length === 0) {
                        const div = document.createElement('div');
                        div.className = 'message msg-system';
                        div.innerText = '💡 提示: 点击 开启持续对话 或 单次对话 进行语音输入';
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
                    const newMessages = history.slice(lastRenderState.length);
                    const fragment = document.createDocumentFragment();
                    
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

        async function sendManualMessage() {
            const input = document.getElementById('chat-input');
            
            // Get text content and inline file tags
            const inlineTags = getInlineFileTags();
            
            // Extract the text structure to maintain the order of text and file references
            let structuredContent = [];
            
            // Iterate over child nodes to preserve order
            for (let node of input.childNodes) {
                if (node.nodeType === Node.TEXT_NODE) {
                    const text = node.textContent.replace(/[\u200B]/g, '');
                    if (text) {
                        structuredContent.push({ type: 'text', content: text });
                    }
                } else if (node.nodeType === Node.ELEMENT_NODE) {
                    if (node.classList.contains('inline-file-tag')) {
                        structuredContent.push({
                            type: 'file',
                            name: node.getAttribute('data-name'),
                            path: node.getAttribute('data-path'),
                            is_dir: node.getAttribute('data-is-dir') === 'true'
                        });
                    } else if (node.tagName === 'BR') {
                        structuredContent.push({ type: 'text', content: '\\n' });
                    } else if (node.tagName === 'DIV') {
                        structuredContent.push({ type: 'text', content: '\\n' + node.innerText });
                    }
                }
            }
            
            // Ensure we have some content
            let rawText = input.innerText || "";
            rawText = rawText.replace(/[\u200B]/g, '').trim();
            if (structuredContent.length === 0 && rawText) {
                structuredContent.push({ type: 'text', content: rawText });
            }
            
            // If completely empty, do nothing
            const hasContent = structuredContent.some(item => 
                (item.type === 'text' && item.content.trim() !== '') || 
                item.type === 'file'
            );
            
            if (!hasContent) return;
            
            // Clear input
            input.innerHTML = '';
            savedRange = null;
            
            // Call Python backend with the structured content
            await pywebview.api.send_structured_message(structuredContent, config.active_agent);
        }
        
        function openSettings() {
            pywebview.api.open_settings_window();
        }

        function closeWindow(event) {
            if (event) event.stopPropagation();
            pywebview.api.close_window();
        }

        function minimizeWindow(event) {
            if (event) event.stopPropagation();
            pywebview.api.minimize_window();
        }

        function maximizeWindow(event) {
            if (event) event.stopPropagation();
            pywebview.api.maximize_window();
        }

        async function toggleSilentMode() {
            const isSilent = await pywebview.api.toggle_silent_mode();
            const btn = document.getElementById('btn-silent');
            if (isSilent) {
                btn.innerHTML = ICONS.volOff;
                btn.title = "关闭静音模式";
                btn.classList.add('active');
                addSystemMessage("静音模式已开启");
            } else {
                btn.innerHTML = ICONS.vol;
                btn.title = "开启静音模式";
                btn.classList.remove('active');
                addSystemMessage("已恢复语音播报");
            }
        }
        
        async function toggleContinuous() {
            const isContinuous = await pywebview.api.toggle_continuous();
            const btn = document.getElementById('btn-continuous');
            if (isContinuous) {
                btn.innerHTML = ICONS.continuous;
                btn.title = "关闭持续对话";
                btn.classList.add('active');
                addSystemMessage("已开启持续对话模式");
            } else {
                btn.innerHTML = ICONS.continuousOff;
                btn.title = "开启持续对话";
                btn.classList.remove('active');
                addSystemMessage("已关闭持续对话模式");
            }
        }
        
        async function triggerSingleTurn() {
            addSystemMessage("🎙️ 正在听您说话...");
            await pywebview.api.trigger_single_turn();
        }

        window.addEventListener('pywebviewready', function() {
            loadData();
            
            const resizer = document.getElementById('resizer');
            const fileExplorer = document.getElementById('file-explorer');
            let isResizing = false;
            
            resizer.addEventListener('mousedown', (e) => {
                isResizing = true;
                document.body.style.cursor = 'col-resize';
                e.preventDefault();
            });
            
            document.addEventListener('mousemove', (e) => {
                if (!isResizing) return;
                // Calculate new width, min 150px, max 50% of window width
                const newWidth = e.clientX;
                const maxWidth = window.innerWidth * 0.5;
                if (newWidth >= 150 && newWidth <= maxWidth) {
                    fileExplorer.style.width = newWidth + 'px';
                }
            });
            
            document.addEventListener('mouseup', () => {
                if (isResizing) {
                    isResizing = false;
                    document.body.style.cursor = 'default';
                }
            });
        });
        // Global shortcuts
        document.addEventListener('keydown', (e) => {
            // Command + 1..0 to switch agents
            if (e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey) {
                const key = e.key;
                if (key >= '0' && key <= '9') {
                    const index = key === '0' ? 9 : parseInt(key) - 1;
                    const icons = document.querySelectorAll('.agent-icon');
                    if (index < icons.length) {
                        e.preventDefault();
                        icons[index].click();
                    }
                }
            }
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
        self.is_maximized = False

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
                result = subprocess.run(
                    ["/bin/zsh", "-l", "-c", "npm config get prefix"],
                    capture_output=True, text=True
                )
                npm_prefix = result.stdout.strip()
                if npm_prefix:
                    potential_path = os.path.join(npm_prefix, "bin", agent_id)
                    if os.path.exists(potential_path) and os.access(potential_path, os.X_OK):
                        path = potential_path
                if not path:
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
                f"/usr/bin/{agent_id}",
                f"/bin/{agent_id}",
                f"/opt/homebrew/lib/node_modules/@didi/{agent_id}/dist/cli.mjs",
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
    def send_structured_message(self, structured_content, target_agent=None):
        # Stop any ongoing TTS and interrupt listening to process text
        self.app._hotkey_interrupt.set()
        
        import threading
        threading.Thread(target=self.app._handle_user_structured_text, args=(structured_content, target_agent), daemon=True).start()

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
            
    def close_window(self):
        self.window.destroy()

    def minimize_window(self):
        self.window.minimize()

    def maximize_window(self):
        import sys
        if sys.platform == 'darwin':
            try:
                import AppKit
                from PyObjCTools import AppHelper
                import webview.platforms.cocoa as cocoa
                
                i = cocoa.BrowserView.instances.get(self.window.uid)
                if i and i.window:
                    # Native zoom toggles between maximize and restore automatically
                    AppHelper.callAfter(i.window.zoom_, None)
                    return
            except Exception as e:
                import logging
                logging.getLogger("across_agents_assistant").error(f"Native zoom failed: {e}")
                
        # Fallback for non-macOS or if native fails
        try:
            if self.is_maximized:
                self.window.restore()
                self.is_maximized = False
            else:
                self.window.maximize()
                self.is_maximized = True
        except:
            pass

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

    def list_directory(self, path=None):
        import os
        import logging
        logger = logging.getLogger("across_agents_assistant")
        if not path:
            path = os.path.expanduser("~")
            
        logger.info(f"list_directory called for path: {path}")
        try:
            entries = []
            for entry in os.scandir(path):
                # Skip hidden files
                if entry.name.startswith('.'):
                    continue
                    
                is_dir = entry.is_dir()
                entries.append({
                    "name": entry.name,
                    "is_dir": is_dir,
                    "absolute_path": entry.path
                })
                
            # Sort: directories first, then alphabetically
            entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            logger.info(f"list_directory success: {len(entries)} items")
            return {"success": True, "entries": entries}
        except Exception as e:
            logger.error(f"list_directory error: {e}")
            return {"success": False, "error": str(e)}

    def reveal_in_finder(self, path):
        import subprocess
        try:
            subprocess.run(['open', '-R', path])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def rename_file(self, old_path, new_name):
        import os
        try:
            dir_name = os.path.dirname(old_path)
            new_path = os.path.join(dir_name, new_name)
            os.rename(old_path, new_path)
            return {"success": True, "new_path": new_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_file(self, path):
        import os
        import shutil
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

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
                    base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                
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
        _tray_globals['manager'] = manager
    except Exception as e:
        import logging
        logging.getLogger("across_agents_assistant").error(f"Failed to initialize tray: {e}")

def start_main_ui(app):
    window = webview.create_window('', html=HTML_CONTENT, width=1200, height=800, text_select=True, frameless=True, transparent=True, easy_drag=False)
    window.voice_app = app  # Attach to window for tray access
    api = MainApi(app, window)
    window.expose(api.get_config, api.get_ui_state, api.set_active, api.detect_or_config, api.send_text_message, api.send_structured_message, api.open_settings_window, api.close_window, api.minimize_window, api.maximize_window, api.toggle_silent_mode, api.toggle_continuous, api.trigger_single_turn, api.list_directory, api.reveal_in_finder, api.rename_file, api.delete_file)
    
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
    
    webview.start(create_tray, window, debug=False)
