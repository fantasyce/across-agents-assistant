import os
import subprocess
import os
import tempfile
import re
import fnmatch
from pathlib import Path
try:
    import Foundation
    import Vision
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

from .tool_registry import registry, ToolDefinition
from ..attachments import extract_image_ocr

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
            "path": {"type": "string", "description": "The absolute or relative path to list"}
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

def get_finder_context() -> str:
    # AppleScript to get the current directory and selected files in Finder
    applescript = '''
    tell application "Finder"
        set currentDir to ""
        set selectedFiles to ""

        -- Get current directory
        if exists Finder window 1 then
            try
                set currentDir to POSIX path of (target of Finder window 1 as alias)
            on error
                set currentDir to POSIX path of (desktop as alias)
            end try
        else
            set currentDir to POSIX path of (desktop as alias)
        end if

        -- Get selected files
        set theSelection to selection
        if (count of theSelection) > 0 then
            set pathList to {}
            repeat with anItem in theSelection
                set end of pathList to POSIX path of (anItem as text)
            end repeat

            set AppleScript's text item delimiters to ", "
            set selectedFiles to pathList as text
            set AppleScript's text item delimiters to ""
        else
            set selectedFiles to "未选中任何文件"
        end if

        return "【当前目录】 " & currentDir & "\\n【选中的文件】 " & selectedFiles
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', applescript], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Failed to get Finder context: {str(e)}"

registry.register(ToolDefinition(
    name="get_finder_context",
    description="Get the current directory path and the paths of any selected files in the macOS Finder. Useful when the user asks to operate on 'these files' or 'this folder'.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    },
    risk_level="low",
    handler=get_finder_context
))

def get_xcode_context() -> str:
    # AppleScript to get the active document path in Xcode
    applescript = '''
    tell application "Xcode"
        if (count of documents) > 0 then
            set docPath to path of document 1
            return "【Xcode 当前文件】 " & docPath
        else
            return "Xcode 中没有打开的文件"
        end if
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', applescript], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Failed to get Xcode context: {str(e)}"

registry.register(ToolDefinition(
    name="get_xcode_context",
    description="Get the absolute file path of the currently active document in Xcode.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    },
    risk_level="low",
    handler=get_xcode_context
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

def read_image_text(path: str) -> str:
    expanded_path = Path(os.path.expanduser(path))
    if not expanded_path.is_file():
        return f"Image file not found: {expanded_path}"
    return extract_image_ocr(expanded_path)

registry.register(ToolDefinition(
    name="read_image_text",
    description="Extract readable text from a local image or screenshot using OCR. Useful when the user references an attached screenshot or image file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the local image file"}
        },
        "required": ["path"]
    },
    risk_level="low",
    handler=read_image_text
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


# ─────────────────────────────────────────────────────────────
# File Operation Tools (for Cloud LLM)
# ─────────────────────────────────────────────────────────────

_DEFAULT_IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode", "build", "dist"}


def _is_binary(filepath: str) -> bool:
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return True
            if not chunk:
                return False
            text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})
            non_text = sum(1 for byte in chunk if byte not in text_chars)
            return non_text / len(chunk) > 0.30
    except Exception:
        return True


def read_file(path: str, offset: int = 1, limit: int = 200) -> str:
    expanded_path = os.path.expanduser(path)
    if not os.path.exists(expanded_path):
        return f"Error: File not found: {path}"
    if os.path.isdir(expanded_path):
        return f"Error: Path is a directory: {path}"
    if _is_binary(expanded_path):
        return f"Error: Binary file, cannot display content: {path}"

    try:
        with open(expanded_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        start = max(0, offset - 1)
        end = min(total, start + limit)
        selected = lines[start:end]
        output_lines = [f"{start + i + 1} | {line.rstrip()}" for i, line in enumerate(selected)]
        header = f"File: {expanded_path} (Lines {start + 1}-{end} of {total})"
        return header + "\n" + "─" * 40 + "\n" + "\n".join(output_lines)
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        return f"Error reading file {path}: {str(e)}"


registry.register(ToolDefinition(
    name="read_file",
    description="Read the contents of a file. Supports pagination with offset and limit to handle large files.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The path to the file (supports ~/ expansion)"},
            "offset": {"type": "integer", "description": "Starting line number (1-based). Default: 1", "default": 1},
            "limit": {"type": "integer", "description": "Maximum number of lines to read. Default: 200", "default": 200}
        },
        "required": ["path"]
    },
    risk_level="low",
    handler=read_file
))


def write_file(path: str, content: str, append: bool = False) -> str:
    expanded_path = os.path.expanduser(path)
    try:
        parent = os.path.dirname(expanded_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        mode = "a" if append else "w"
        with open(expanded_path, mode, encoding="utf-8") as f:
            f.write(content)
        byte_count = len(content.encode("utf-8"))
        mode_str = "append" if append else "overwrite"
        return f"Successfully wrote to {expanded_path} (mode: {mode_str}, {byte_count} bytes)"
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        return f"Error writing file {path}: {str(e)}"


registry.register(ToolDefinition(
    name="write_file",
    description="Write content to a file. Creates the file if it does not exist, or overwrites/appends to an existing file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The path to the file (supports ~/ expansion)"},
            "content": {"type": "string", "description": "The content to write"},
            "append": {"type": "boolean", "description": "If true, append to the file instead of overwriting. Default: false", "default": False}
        },
        "required": ["path", "content"]
    },
    risk_level="high",
    handler=write_file
))


def edit_file(path: str, old_string: str, new_string: str) -> str:
    expanded_path = os.path.expanduser(path)
    if not os.path.exists(expanded_path):
        return f"Error: File not found: {path}"
    if os.path.isdir(expanded_path):
        return f"Error: Path is a directory: {path}"

    try:
        with open(expanded_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        return f"Error reading file {path}: {str(e)}"

    count = content.count(old_string)
    if count == 0:
        return f"Error: old_string not found in file. File content unchanged.\nFile: {expanded_path}"
    if count > 1:
        return f"Error: old_string matched {count} times. Please provide more context to make it unique.\nFile: {expanded_path}"

    new_content = content.replace(old_string, new_string, 1)
    try:
        with open(expanded_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return (
            f"Successfully edited {expanded_path}\n"
            f"Replaced 1 occurrence:\n"
            f"- old: {repr(old_string)}\n"
            f"+ new: {repr(new_string)}"
        )
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        return f"Error writing file {path}: {str(e)}"


registry.register(ToolDefinition(
    name="edit_file",
    description="Edit a file by replacing a unique string. The old_string must appear exactly once in the file. This is the recommended way to modify code.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The path to the file (supports ~/ expansion)"},
            "old_string": {"type": "string", "description": "The exact text to replace (must be unique in the file)"},
            "new_string": {"type": "string", "description": "The new text to insert"}
        },
        "required": ["path", "old_string", "new_string"]
    },
    risk_level="high",
    handler=edit_file
))


def grep(path: str = ".", pattern: str = "", file_pattern: str = "*", max_depth: int = 5) -> str:
    expanded_path = os.path.expanduser(path)
    if not os.path.exists(expanded_path):
        return f"Error: Directory not found: {path}"
    if not os.path.isdir(expanded_path):
        return f"Error: Path is not a directory: {path}"

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: Invalid regex pattern: {e}"

    matches = []
    for root, dirs, files in os.walk(expanded_path):
        depth = root[len(expanded_path):].count(os.sep)
        if depth >= max_depth:
            del dirs[:]
            continue
        dirs[:] = [d for d in dirs if d not in _DEFAULT_IGNORE_DIRS]
        for filename in files:
            if not fnmatch.fnmatch(filename, file_pattern):
                continue
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                for i, line in enumerate(lines):
                    if regex.search(line):
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        context = []
                        for j in range(start, end):
                            marker = ">>>" if j == i else "   "
                            context.append(f"{marker}{j + 1:4d} | {lines[j].rstrip()}")
                        matches.append((filepath, i + 1, "\n".join(context)))
            except (PermissionError, OSError):
                continue
            except Exception:
                continue

    if not matches:
        return f"No matches found for pattern '{pattern}' in {expanded_path}"

    output = [f"Found {len(matches)} match(es):\n"]
    seen_files = set()
    for filepath, line_no, context in matches:
        if filepath not in seen_files:
            seen_files.add(filepath)
            output.append(f"\n{filepath}")
        output.append(f"  Line {line_no}:")
        output.append(context)
    return "\n".join(output)


registry.register(ToolDefinition(
    name="grep",
    description="Search file contents using regex. Recursively searches a directory and returns matching lines with context.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory to search. Default: current directory", "default": "."},
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "file_pattern": {"type": "string", "description": "Glob pattern for filenames (e.g. '*.py'). Default: '*'", "default": "*"},
            "max_depth": {"type": "integer", "description": "Maximum recursion depth. Default: 5", "default": 5}
        },
        "required": ["pattern"]
    },
    risk_level="low",
    handler=grep
))


def search_files(path: str = ".", pattern: str = "*", max_depth: int = 5) -> str:
    expanded_path = os.path.expanduser(path)
    if not os.path.exists(expanded_path):
        return f"Error: Directory not found: {path}"
    if not os.path.isdir(expanded_path):
        return f"Error: Path is not a directory: {path}"

    matches = []
    for root, dirs, files in os.walk(expanded_path):
        depth = root[len(expanded_path):].count(os.sep)
        if depth >= max_depth:
            del dirs[:]
            continue
        dirs[:] = [d for d in dirs if d not in _DEFAULT_IGNORE_DIRS]
        for filename in files:
            if fnmatch.fnmatch(filename, pattern):
                matches.append(os.path.join(root, filename))

    if not matches:
        return f"No files matching '{pattern}' found in {expanded_path}"
    return f"Found {len(matches)} file(s):\n" + "\n".join(matches)


registry.register(ToolDefinition(
    name="search_files",
    description="Search for files by name pattern (glob). Recursively lists matching files in a directory.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory to search. Default: current directory", "default": "."},
            "pattern": {"type": "string", "description": "Glob pattern for filenames (e.g. '*.py'). Default: '*'", "default": "*"},
            "max_depth": {"type": "integer", "description": "Maximum recursion depth. Default: 5", "default": 5}
        },
        "required": []
    },
    risk_level="low",
    handler=search_files
))
