import os
import subprocess
import os
import tempfile
try:
    import Foundation
    import Vision
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

from .tool_registry import registry, ToolDefinition

def take_screenshot_and_ocr() -> str:
    if not VISION_AVAILABLE:
        return "❌ 无法执行：系统缺少 pyobjc-framework-Vision 依赖。请在终端运行: pip3 install pyobjc-framework-Vision --break-system-packages"
        
    # 1. Create a temporary file for the screenshot
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
        temp_path = temp_file.name
        
    try:
        # 2. Invoke macOS native interactive screencapture (-i for interactive, -x for no sound)
        # This will pause the python script until the user selects an area
        subprocess.run(['screencapture', '-i', '-x', temp_path], check=True)
        
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            return "截图被取消或未成功保存。"
            
        # 3. Perform OCR using macOS Vision Framework
        file_url = Foundation.NSURL.fileURLWithPath_(temp_path)
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(file_url, None)
        
        results_text = []
        
        def completion_handler(request, error):
            if error:
                results_text.append(f"OCR Error: {error}")
                return
            
            for observation in request.results() or []:
                candidate = observation.topCandidates_(1).firstObject()
                if candidate:
                    results_text.append(candidate.string())
                    
        request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(completion_handler)
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setRecognitionLanguages_(["zh-Hans", "en-US"])
        request.setUsesLanguageCorrection_(True)
        
        success, error = handler.performRequests_error_([request], None)
        
        if not success:
            return f"执行 OCR 请求失败: {error}"
            
        final_text = "\n".join(results_text).strip()
        
        if not final_text:
            return "截图中未识别到任何文本内容。"
            
        return f"【屏幕截图内容识别结果】\n{final_text}"
        
    except subprocess.CalledProcessError:
        return "截图操作被取消或发生系统错误。"
    except Exception as e:
        return f"OCR 处理发生异常: {str(e)}"
    finally:
        # 4. Clean up the temporary image file
        if os.path.exists(temp_path):
            os.remove(temp_path)

registry.register(ToolDefinition(
    name="take_screenshot_and_ocr",
    description="Take an interactive screenshot of a specific area on the user's screen and extract the text using OCR. This tool will pause and wait for the user to draw a box on their screen. Useful when the user asks to 'read this image', 'extract text from the screen', or when normal text selection fails.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    },
    risk_level="low",
    handler=take_screenshot_and_ocr
))

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
