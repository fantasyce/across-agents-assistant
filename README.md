# Across-Agents Assistant 🤖

一款为 macOS 打造的多智能体语音助手，常驻菜单栏，支持全局快捷键唤醒、离线语音识别 (ASR)、云端语音合成 (TTS) 以及动态切换多个 AI 核心（Agents）。

## ✨ 核心特性

- 🖥 **原生集成**：常驻 macOS 菜单栏，极简星芒图标，支持深色/浅色模式自适应。
- 🎙 **离线语音识别**：内置基于 `faster-whisper` 的本地离线语音识别，极速响应，保护隐私。
- 🗣 **智能语音交互**：基于大模型的对话能力，结合高质量 TTS（支持 Minimax 和 Edge-TTS）。
- ⌨️ **全局快捷键**：随时随地通过全局快捷键（默认双击 Control）唤醒助手。
- ⚙️ **多智能体配置**：提供精美的 Webview 桌面配置界面，轻松管理、切换和定制不同的 AI 智能体。

## 📦 安装与使用 (普通用户)

1. 前往本仓库的 [Releases](#) 页面。
2. 下载最新版本的 `AcrossAgentsAssistant.dmg` 文件。
3. 双击打开 `.dmg`，将 `Across-Agents Assistant.app` 拖入 `Applications`（应用程序）文件夹。
4. 启动应用。首次运行时请在系统设置中授予**麦克风权限**和**辅助功能权限**（用于全局快捷键）。

## 🛠 开发与构建 (开发者)

如果你希望在本地运行或二次开发本项目，请按照以下步骤操作：

### 1. 环境准备

确保你的 Mac 上安装了 Python 3.10+。

```bash
# 克隆仓库
git clone <your_github_repo_url>
cd tiny-project/across-agents-assistant

# 安装依赖
pip install -r requirements.txt
```

### 2. 下载离线模型

为了保证体积，仓库中不包含庞大的本地离线模型文件。在运行或打包前，你需要手动下载 `faster-whisper` 的模型：

1. 前往 HuggingFace 下载 [faster-whisper-small](https://huggingface.co/Systran/faster-whisper-small) 的 CTranslate2 格式模型文件。
2. 将下载的 `model.bin`, `config.json`, `tokenizer.json`, `vocabulary.txt` 放入本项目的 `models/whisper-small/` 目录下。
   （如果你想升级为识别率更高的模型，可下载 `large-v3-turbo` 并替换该目录内的文件）。

### 3. 本地运行

```bash
# 以 GUI 模式运行主程序
python3 main.py run

# 仅运行配置界面
python3 main.py ui
```

### 4. 打包为 macOS 应用 (.app / .dmg)

项目提供了基于 PyInstaller 的自动化打包脚本：

```bash
# 清理并开始构建
rm -rf build dist AcrossAgentsAssistant.spec
python3 build.py

# 构建完成后，打包 DMG
mkdir -p dist/dmg
cp -r dist/AcrossAgentsAssistant.app dist/dmg/
ln -s /Applications dist/dmg/Applications
hdiutil create -volname "AcrossAgentsAssistant" -srcfolder dist/dmg -ov -format UDZO dist/AcrossAgentsAssistant.dmg
```
打包成功后，你可以在 `dist/` 目录下找到 `.app` 和 `.dmg` 文件。

## 🔐 环境变量与 API Key

- **TTS (Minimax)**: 默认会尝试从系统环境变量或 Keychain (`openclaw.minimax.api`) 中读取 `MINIMAX_API_KEY`。如果未配置，将自动降级使用免费的微软 Edge-TTS。
- **大模型 API**: 智能体的对话核心基于 OpenClaw 客户端调用，你需要配置对应大模型提供商的 API Key。

## 📄 许可证

MIT License
