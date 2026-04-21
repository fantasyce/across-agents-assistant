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
