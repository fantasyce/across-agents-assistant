import sys
import multiprocessing
from across_agents_assistant.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    # Check if we need to run UI independently to avoid NSApplication conflicts
    if len(sys.argv) > 1 and sys.argv[1] == "ui":
        from across_agents_assistant.agent_ui_web import show_agent_ui
        show_agent_ui()
        sys.exit(0)
        
    # Force run mode ONLY if running as a bundled PyInstaller app
    if getattr(sys, 'frozen', False):
        sys.argv = ["across-agents-assistant", "run"]
    main()
