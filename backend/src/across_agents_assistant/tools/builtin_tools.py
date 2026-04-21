import os
import subprocess
from .tool_registry import registry, ToolDefinition

def list_directory(path: str) -> str:
    expanded_path = os.path.expanduser(path)
    try:
        items = os.listdir(expanded_path)
        return f"Contents of {path}:\n" + "\n".join(items)
    except Exception as e:
        return f"Error reading directory {path}: {str(e)}"

def create_email_draft(recipient: str, subject: str, body: str) -> str:
    # Use AppleScript to create a draft in macOS Mail app
    applescript = f'''
    tell application "Mail"
        set newMessage to make new outgoing message with properties {{subject:"{subject}", content:"{body}", visible:true}}
        tell newMessage
            make new to recipient at end of to recipients with properties {{address:"{recipient}"}}
        end tell
    end tell
    '''
    try:
        subprocess.run(['osascript', '-e', applescript], check=True)
        return "Successfully created email draft in Mail.app."
    except subprocess.CalledProcessError as e:
        return f"Failed to create draft: {str(e)}"

# Register Tools
registry.register(ToolDefinition(
    name="list_directory",
    description="List the contents of a directory on the user's local file system.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The absolute or relative path (e.g. ~/Documents) to list"}
        },
        "required": ["path"]
    },
    risk_level="low",
    handler=list_directory
))

registry.register(ToolDefinition(
    name="create_email_draft",
    description="Create an email draft in the macOS Mail app.",
    parameters={
        "type": "object",
        "properties": {
            "recipient": {"type": "string", "description": "Email address of the recipient"},
            "subject": {"type": "string", "description": "Subject of the email"},
            "body": {"type": "string", "description": "Body content of the email"}
        },
        "required": ["recipient", "subject", "body"]
    },
    risk_level="medium",
    handler=create_email_draft
))

def create_note_draft(title: str, body: str) -> str:
    # Use AppleScript to create a new note in Apple Notes app
    applescript = f'''
    tell application "Notes"
        set newNote to make new note with properties {{name:"{title}", body:"<h1>{title}</h1><p>{body}</p>"}}
        show newNote
    end tell
    '''
    try:
        subprocess.run(['osascript', '-e', applescript], check=True)
        return "Successfully created note draft in Notes.app."
    except subprocess.CalledProcessError as e:
        return f"Failed to create note: {str(e)}"

registry.register(ToolDefinition(
    name="create_note_draft",
    description="Create a new note in the macOS Notes app.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Title of the note"},
            "body": {"type": "string", "description": "Body content of the note"}
        },
        "required": ["title", "body"]
    },
    risk_level="medium",
    handler=create_note_draft
))

def get_active_browser_url(browser: str = "Chrome") -> str:
    # AppleScript to get URL and Title from Google Chrome or Safari regardless of if they are frontmost
    if browser.lower() == "safari":
        applescript = '''
        tell application "Safari"
            if (count of windows) > 0 then
                set currentURL to URL of front document
                set currentTitle to name of front document
                return "Safari | " & currentTitle & " | " & currentURL
            else
                return "Safari 没有任何打开的窗口"
            end if
        end tell
        '''
    else:
        applescript = '''
        tell application "Google Chrome"
            if (count of windows) > 0 then
                set currentURL to URL of active tab of front window
                set currentTitle to title of active tab of front window
                return "Chrome | " & currentTitle & " | " & currentURL
            else
                return "Chrome 没有任何打开的窗口"
            end if
        end tell
        '''
        
    try:
        result = subprocess.run(['osascript', '-e', applescript], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Failed to get browser URL: {str(e)}"

registry.register(ToolDefinition(
    name="get_active_browser_url",
    description="Get the URL and Title of the currently active tab in Chrome or Safari. Useful for summarizing or reading web pages even if the browser is in the background.",
    parameters={
        "type": "object",
        "properties": {
            "browser": {
                "type": "string",
                "description": "The browser to check, either 'Chrome' or 'Safari'. Defaults to 'Chrome'.",
                "enum": ["Chrome", "Safari"]
            }
        },
        "required": []
    },
    risk_level="low",
    handler=get_active_browser_url
))

def toggle_system_dark_mode() -> str:
    applescript = '''
    tell application "System Events"
        tell appearance preferences
            set dark mode to not dark mode
            return dark mode
        end tell
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', applescript], capture_output=True, text=True, check=True)
        is_dark = result.stdout.strip().lower() == 'true'
        return f"系统外观已切换为: {'深色模式 (Dark Mode)' if is_dark else '浅色模式 (Light Mode)'}"
    except subprocess.CalledProcessError as e:
        return f"Failed to toggle dark mode: {str(e)}"

registry.register(ToolDefinition(
    name="toggle_system_dark_mode",
    description="Toggle the macOS system appearance between Light and Dark mode.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    },
    risk_level="low",
    handler=toggle_system_dark_mode
))

def set_system_volume(level: int) -> str:
    # Ensure level is between 0 and 100
    level = max(0, min(100, level))
    
    try:
        # Check if the current audio device supports volume control
        # External displays (HDMI/DP/TV) return "missing value" because macOS passes raw digital audio to them
        check_script = 'output volume of (get volume settings)'
        check_result = subprocess.run(['osascript', '-e', check_script], capture_output=True, text=True, check=True)
        
        if "missing value" in check_result.stdout:
            return "❌ 操作失败：你当前使用的是外接显示器或电视（HDMI/DisplayPort）输出音频。macOS 无法通过软件控制此类数字音频设备的音量，请使用电视遥控器调节。"
            
        # If supported, unmute first
        subprocess.run(['osascript', '-e', 'set volume output muted false'], capture_output=True, check=True)
        
        # Then set the actual volume
        script = f'set volume output volume {level}'
        subprocess.run(['osascript', '-e', script], capture_output=True, text=True, check=True)
        
        # Verify the new volume
        verify_result = subprocess.run(['osascript', '-e', check_script], capture_output=True, text=True, check=True)
        new_vol = verify_result.stdout.strip()
        
        return f"系统音量已成功设置为 {new_vol}%"
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        return f"无法设置音量。系统权限拦截或底层报错: {error_msg}"

registry.register(ToolDefinition(
    name="set_system_volume",
    description="Set the macOS system audio volume to a specific percentage (0 to 100).",
    parameters={
        "type": "object",
        "properties": {
            "level": {"type": "integer", "description": "Volume level from 0 (mute) to 100 (max)"}
        },
        "required": ["level"]
    },
    risk_level="low",
    handler=set_system_volume
))
