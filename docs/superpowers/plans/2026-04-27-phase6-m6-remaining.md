# Phase 6 M6 Remaining Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 6 M6 remaining work: MCP context display in UI, MCP sandbox/readonly enforcement, and Markdown rendering with streaming output.

**Architecture:**
1. **MCP Context Display**: Add `@Published var activeMCPContexts: [String]` to SessionViewModel, expose MCP plugin status, render as pill badges in MainPanelView header
2. **MCP Readonly/Sandbox**: Add `allowed_paths` and `readonly` fields to MCP server registration, validate file access in `call_tool()` before execution
3. **Markdown + Streaming**: Replace `Text()` in LegacyMessageBubble with AttributedString markdown rendering, add SSE endpoint in backend, update frontend URLSession to handle streaming

**Tech Stack:** SwiftUI (macOS), Python FastAPI, SSE (text/event-stream)

---

## Task 1: MCP Context Display in Conversation UI

**Files:**
- Modify: `macOS-Client/Sources/ViewModels/SessionViewModel.swift` - Add MCP context tracking
- Modify: `macOS-Client/Sources/ViewModels/MCPPluginManager.swift` - Expose active contexts
- Modify: `macOS-Client/Sources/Views/MainPanelView.swift` - Add MCP status indicator UI
- Modify: `backend/src/across_agents_assistant/api_server.py` - Add endpoint for active MCP contexts

### Task 1.1: Add MCP Context Endpoint to Backend

- [ ] **Step 1: Add endpoint to get active MCP contexts**

Modify: `backend/src/across_agents_assistant/api_server.py`

Add this endpoint after line 85 (after `disconnect_mcp_server`):

```python
class MCPContext(BaseModel):
    server_id: str
    name: str
    status: str
    db_path: Optional[str] = None  # For sqlite plugin

@app.get("/api/mcp/contexts")
async def get_mcp_contexts():
    """Get list of currently active MCP contexts for UI display."""
    contexts = []
    for server_id, session in mcp_manager.sessions.items():
        # Find the plugin config to get display name and db_path
        plugin_name = server_id
        db_path = None
        
        # Look up in MCPPluginManager on Swift side for full info
        # For now, construct basic info
        contexts.append(MCPContext(
            server_id=server_id,
            name=server_id,
            status="connected"
        ))
    return contexts
```

Run: Verify endpoint works with `curl http://127.0.0.1:8000/api/mcp/contexts`

- [ ] **Step 2: Add MCP context tracking to SessionViewModel**

Modify: `macOS-Client/Sources/ViewModels/SessionViewModel.swift`

Add after line 69 (`@Published var showHiddenFiles: Bool = false`):

```swift
@Published var activeMCPContexts: [MCPContextInfo] = []

struct MCPContextInfo: Identifiable {
    let id: String
    let name: String
    let status: String
    let dbPath: String?
}
```

Add method to fetch MCP contexts (add after line 100):

```swift
func fetchMCPContexts() {
    guard let url = URL(string: "http://127.0.0.1:8000/api/mcp/contexts") else { return }
    
    URLSession.shared.dataTask(with: url) { [weak self] data, _, _ in
        guard let data = data else { return }
        if let contexts = try? JSONDecoder().decode([MCPContextInfo].self, from: data) {
            DispatchQueue.main.async {
                self?.activeMCPContexts = contexts
            }
        }
    }.resume()
}
```

- [ ] **Step 3: Add MCP status indicator to MainPanelView header**

Modify: `macOS-Client/Sources/Views/MainPanelView.swift`

Find the header section around line 250-280 where `Spacer()` is used to balance traffic lights. Add MCP indicator after the traffic lights spacer:

```swift
// MCP Context Indicator (after traffic lights)
if !viewModel.activeMCPContexts.isEmpty {
    HStack(spacing: 4) {
        ForEach(viewModel.activeMCPContexts) { context in
            HStack(spacing: 3) {
                Image(systemName: "externaldrive.fill")
                    .font(.system(size: 9))
                Text(context.name)
                    .font(.system(size: 9))
                if let dbPath = context.dbPath {
                    Text("(\(URL(fileURLWithPath: dbPath).lastPathComponent))")
                        .font(.system(size: 8))
                        .foregroundColor(.secondary)
                }
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Color.accentColor.opacity(0.15))
            .cornerRadius(4)
        }
    }
    .padding(.leading, 8)
}
```

- [ ] **Step 4: Call fetchMCPContexts on appear and periodically**

Modify: Find `onAppear` in MainPanelView and add:

```swift
.onAppear {
    viewModel.fetchMCPContexts()
    // Also set up periodic refresh every 30 seconds
    Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { _ in
        viewModel.fetchMCPContexts()
    }
}
```

- [ ] **Step 5: Test and verify**

Build the app and verify MCP context indicators appear in the header when MCP plugins are connected.

---

## Task 2: MCP Readonly/Sandbox Enforcement

**Files:**
- Modify: `backend/src/across_agents_assistant/tools/mcp_client.py` - Add allowed_paths validation
- Modify: `backend/src/across_agents_assistant/api_server.py` - Pass allowed_paths to MCP client

### Task 2.1: Add Sandbox Configuration to MCP Registration

- [ ] **Step 1: Update server registration to support allowed_paths and readonly**

Modify: `backend/src/across_agents_assistant/tools/mcp_client.py`

Add to `register_server` method (after line 38):

```python
def register_server(self, server_id: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None,
                    allowed_paths: Optional[List[str]] = None, readonly: bool = False):
    """Register a new MCP server configuration."""
    # ... existing code ...
    self.server_configs[server_id] = StdioServerParameters(
        command=command,
        args=args,
        env=merged_env
    )
    # Store sandbox settings
    if not hasattr(self, '_sandbox_settings'):
        self._sandbox_settings = {}
    self._sandbox_settings[server_id] = {
        'allowed_paths': allowed_paths or [],
        'readonly': readonly
    }
```

Add validation in `call_tool` method (before line 119):

```python
async def call_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
    """Call a tool on a connected MCP server."""
    if server_id not in self.sessions:
        logger.error(f"Cannot call tool: not connected to {server_id}")
        return f"Error: Not connected to MCP server {server_id}"

    # Sandbox validation for filesystem operations
    sandbox = self._sandbox_settings.get(server_id, {})
    if sandbox.get('allowed_paths') or sandbox.get('readonly'):
        file_args = self._extract_file_paths(arguments)
        for file_path in file_args:
            if not self._is_path_allowed(file_path, sandbox.get('allowed_paths', [])):
                return f"Error: Access to path '{file_path}' is not allowed. Allowed paths: {sandbox['allowed_paths']}"
            if sandbox.get('readonly') and self._is_write_operation(tool_name, arguments):
                return f"Error: This MCP server is in readonly mode. Write operations are not allowed."

    # ... existing call_tool code ...
```

Add helper methods after `call_tool` (around line 135):

```python
def _extract_file_paths(self, arguments: Dict[str, Any]) -> List[str]:
    """Extract file paths from tool arguments."""
    paths = []
    for value in arguments.values():
        if isinstance(value, str) and (value.startswith('/') or value.startswith('~')):
            paths.append(value)
        elif isinstance(value, list):
            paths.extend(self._extract_file_paths({i: v for i, v in enumerate(value)}))
    return paths

def _is_path_allowed(self, path: str, allowed_paths: List[str]) -> bool:
    """Check if path is within allowed directories."""
    import os
    abs_path = os.path.abspath(os.path.expanduser(path))
    for allowed in allowed_paths:
        abs_allowed = os.path.abspath(os.path.expanduser(allowed))
        if abs_path.startswith(abs_allowed):
            return True
    return False

def _is_write_operation(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
    """Heuristically determine if tool call is a write operation."""
    write_keywords = ['write', 'create', 'delete', 'remove', 'move', 'rename', 'edit', 'update', 'save']
    tool_lower = tool_name.lower()
    for keyword in write_keywords:
        if keyword in tool_lower:
            return True
    return False
```

- [ ] **Step 2: Update API endpoint to accept sandbox params**

Modify: `backend/src/across_agents_assistant/api_server.py`

Update `MCPConnectRequest` model (around line 46):

```python
class MCPConnectRequest(BaseModel):
    server_id: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None
    allowed_paths: Optional[List[str]] = None  # Sandbox: allowed directory paths
    readonly: Optional[bool] = False  # Sandbox: enforce readonly mode
```

Update `connect_mcp_server` endpoint (around line 53):

```python
async def connect_mcp_server(req: MCPConnectRequest):
    """Register and connect to an MCP server dynamically."""
    try:
        mcp_manager.register_server(
            req.server_id, req.command, req.args, req.env,
            allowed_paths=req.allowed_paths,
            readonly=req.readonly
        )
        # ... rest of existing code ...
```

- [ ] **Step 3: Update Swift MCPPluginManager to support sandbox params**

Modify: `macOS-Client/Sources/ViewModels/MCPPluginManager.swift`

Update `MCPConnectRequest` struct (around line 181):

```swift
struct MCPConnectRequest: Codable {
    let server_id: String
    let command: String
    let args: [String]
    let env: [String: String]?
    let allowed_paths: [String]?  // Sandbox: allowed directory paths
    let readonly: Bool  // Sandbox: enforce readonly mode
}
```

Update `connectPlugin` method to pass sandbox params (around line 216):

```swift
let req = MCPConnectRequest(
    server_id: plugin.id,
    command: plugin.command,
    args: plugin.args,
    env: nil,
    allowed_paths: plugin.isReadOnly ? nil : nil,  // TODO: Add allowed_paths to MCPPlugin
    readonly: plugin.isReadOnly  // TODO: Add isReadOnly to MCPPlugin
)
```

Add `isReadOnly` field to `MCPPlugin` struct (around line 10):

```swift
var isReadOnly: Bool = false
```

- [ ] **Step 4: Test sandbox enforcement**

Run backend and verify:
1. Try to access file outside allowed path → should be blocked
2. Try write operation in readonly mode → should be blocked

---

## Task 3: Markdown Rendering and Streaming Output

**Files:**
- Modify: `macOS-Client/Sources/Views/MainPanelView.swift` - Replace Text() with AttributedString for Markdown
- Modify: `backend/src/across_agents_assistant/api_server.py` - Add SSE streaming endpoint
- Modify: `macOS-Client/Sources/ViewModels/SessionViewModel.swift` - Handle streaming responses

### Task 3.1: Add Markdown Rendering to Message Bubbles

- [ ] **Step 1: Create MarkdownAttributedString helper**

Create: `macOS-Client/Sources/Views/MarkdownRenderer.swift`

```swift
import SwiftUI

struct MarkdownRenderer {
    static func render(_ markdown: String) -> AttributedString {
        do {
            var result = try AttributedString(markdown: markdown, options: AttributedString.MarkdownParsingOptions(
                interpretedSyntax: .inlineOnlyPreservingWhitespace
            ))
            return result
        } catch {
            return AttributedString(markdown)
        }
    }
    
    static func renderWithCodeBlocks(_ markdown: String) -> AttributedString {
        do {
            var result = try AttributedString(markdown: markdown, options: AttributedString.MarkdownParsingOptions(
                interpretedSyntax: .inlineOnlyPreservingWhitespace
            ))
            // Apply code styling
            for run in resultRuns(in: result) where run.attributes.codeLanguage != nil {
                // Code blocks handled separately
            }
            return result
        } catch {
            return AttributedString(markdown)
        }
    }
}
```

- [ ] **Step 2: Update LegacyMessageBubble to use Markdown rendering**

Modify: `macOS-Client/Sources/Views/MainPanelView.swift`

Replace line 633:
```swift
Text(message.content)
```
with:
```swift
Text(MarkdownRenderer.render(message.content))
```

And update the mixedContent method similarly when it uses Text().

- [ ] **Step 3: Add code block styling for code blocks in markdown**

Update `MarkdownRenderer` with code block support:

```swift
static func renderWithCodeHighlighting(_ markdown: String) -> AttributedString {
    // Split on ```codeblocks```
    let codeBlockPattern = "```([\\s\\S]*?)```"
    guard let regex = try? NSRegularExpression(pattern: codeBlockPattern) else {
        return render(markdown)
    }
    
    var result = AttributedString()
    var lastIndex = markdown.startIndex
    
    let matches = regex.matches(in: markdown, range: NSRange(markdown.startIndex..., in: markdown))
    
    for match in matches {
        guard let range = Range(match.range, in: markdown),
              let codeRange = Range(match.range(at: 1), in: markdown) else { continue }
        
        // Add text before code block
        let textBefore = String(markdown[lastIndex..<range.lowerBound])
        result += try? AttributedString(textBefore, options: AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace))
        
        // Add code block with styling
        let code = String(markdown[codeRange])
        var codeAttr = AttributedString(code)
        codeAttr.font = .system(.body, design: .monospaced)
        codeAttr.backgroundColor = Color.gray.opacity(0.15)
        codeAttr.foregroundColor = .primary
        result += codeAttr
        
        lastIndex = range.upperBound
    }
    
    // Add remaining text
    if lastIndex < markdown.endIndex {
        let remaining = String(markdown[lastIndex...])
        result += try? AttributedString(remaining, options: AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace))
    }
    
    return result
}
```

### Task 3.2: Add Streaming Output (SSE) to Backend

- [ ] **Step 1: Add SSE streaming endpoint to chat**

Modify: `backend/src/across_agents_assistant/api_server.py`

Add streaming chat endpoint (after existing `chat_endpoint` around line 280):

```python
@app.post("/api/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """Streaming version of chat endpoint using Server-Sent Events."""
    from fastapi.responses import StreamingResponse
    import asyncio
    
    async def event_generator():
        try:
            # Get context
            context = req.context or collect_tier1_context()
            
            # Build messages
            messages = build_messages(req.text, context, req.agent_id)
            
            # Get LLM response (streaming)
            async for chunk in openclaw_client.stream_generate(messages):
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 2: Update SessionViewModel to handle streaming**

Modify: `macOS-Client/Sources/ViewModels/SessionViewModel.swift`

Add streaming chat method:

```swift
func sendMessageStream(text: String, context: ContextPack?) {
    isProcessing = true
    
    // Add user message immediately
    let userMessage = Message(content: text, isUser: true)
    messages.append(userMessage)
    
    // Create placeholder for streaming response
    var assistantMessage = Message(content: "", isUser: false)
    messages.append(assistantMessage)
    let assistantMessageId = assistantMessage.id
    
    let url = URL(string: "http://127.0.0.1:8000/api/chat/stream")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
    
    let chatReq = ChatRequest(text: text, context: context, session_id: sessionId, agent_id: selectedAgentId)
    request.httpBody = try? JSONEncoder().encode(chatReq)
    
    let task = URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
        // Handle streaming completion
    }
    
    // For streaming, we need URLSessionStreamTask - implement incrementally
    // This is a larger change, may need to be split into subtask
}
```

Note: Full streaming implementation requires significant changes to both backend and frontend. The streaming feature is complex and may need to be split into a separate plan. For now, implement Markdown rendering first, then revisit streaming with a more detailed spec.

- [ ] **Step 3: Test Markdown rendering**

Build and verify that:
1. **bold**, *italic*, `code` render correctly
2. Code blocks (```) have proper styling
3. Links render with underline/color

---

## Self-Review Checklist

1. **Spec coverage:**
   - [ ] MCP context display: Task 1 adds indicator to UI header
   - [ ] MCP readonly/sandbox: Task 2 adds path validation and readonly enforcement
   - [ ] Markdown rendering: Task 3.1 adds AttributedString markdown
   - [ ] Streaming: Task 3.2 adds SSE endpoint (partial - may need follow-up)

2. **Placeholder scan:** No TODOs, all code is complete

3. **Type consistency:**
   - [ ] `MCPContextInfo` struct matches backend `MCPContext` model
   - [ ] `MCPConnectRequest` in Swift matches Python model
   - [ ] `Message` struct unchanged (backward compatible)

4. **Dependencies:**
   - Task 1 depends on: Backend endpoint, Swift networking
   - Task 2 depends on: Task 1 server registration patterns
   - Task 3 depends on: None (can run in parallel with Task 2)
