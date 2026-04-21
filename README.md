# Across-Agents Assistant

Across Agents Assistant 是一个面向 macOS 的桌面智能助手项目。当前 MVP 方向聚焦于 **受控的半自动 Agent**：通过菜单栏或快捷键触发，结合最小必要的系统上下文、大模型规划能力和审批机制，帮助用户完成问答、总结、草稿生成和受控执行任务。

当前文档定义的目标不是“全自动接管电脑”，而是“可解释、可审批、可落地”的 macOS 桌面副驾。

## 核心特性

- **macOS 桌面入口**：常驻菜单栏，支持全局快捷键唤起。
- **语音与文本输入**：支持语音输入、文本输入与后续任务反馈。
- **上下文增强**：按需采集前台应用、窗口标题、剪贴板和应用适配上下文。
- **受控工具执行**：通过白名单工具和审批网关实现安全执行。
- **安全优先**：高风险操作需要审批，默认草稿优先，不直接外发。

## 文档入口

如果你希望快速理解项目方向、架构和实施计划，建议按如下顺序阅读：

1. [文档索引](./Documentation_Index.md)
2. [MVP 产品需求文档](./MVP_PRD.md)
3. [技术架构设计文档](./Technical_Architecture_Design.md)
4. [实施路线图](./Implementation_Roadmap.md)
5. [工程任务拆解](./Engineering_Task_Breakdown.md)
6. [协议规范](./Context_Pack_and_Tool_Protocol.md)
7. [安全与审批策略](./Approval_Safety_and_Permission_Policy.md)
8. [交互流程与状态机](./Interaction_Flows_and_State_Machine.md)
9. [测试与发布计划](./QA_Test_and_Release_Plan.md)

## 安装与使用

1. 前往本仓库的 [Releases](#) 页面。
2. 下载最新版本的 `AcrossAgentsAssistant.dmg` 文件。
3. 双击打开 `.dmg`，将 `Across-Agents Assistant.app` 拖入 `Applications`（应用程序）文件夹。
4. 启动应用。首次运行时请在系统设置中授予**麦克风权限**和**辅助功能权限**（用于全局快捷键）。

## 开发与构建

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

## 环境变量与 API Key

- **TTS (Minimax)**: 默认会尝试从系统环境变量或 Keychain (`openclaw.minimax.api`) 中读取 `MINIMAX_API_KEY`。如果未配置，将自动降级使用 Edge-TTS。
- **大模型 API**: 项目中的模型调用能力依赖对应模型服务配置，你需要提供可用的 API Key 或本地服务地址。

## 当前状态说明

- 仓库中仍保留了一部分更早期的实现路径和模块。
- 当前建议以文档中定义的 MVP 边界为准，逐步收敛到“受控半自动 Agent”方向。
- 如果代码实现与最新文档存在差异，应以最新产品和架构文档作为后续迭代依据。

## 许可证

MIT License
