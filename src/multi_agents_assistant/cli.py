from __future__ import annotations

import argparse
from pathlib import Path

from .app import MultiAgentsAssistantApp
from .config import load_config
from .menubar import run_menubar


def main():
    import os
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    parser = argparse.ArgumentParser(prog="multi-agents-assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run")
    sub.add_parser("menubar")

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    config = load_config(project_root)
    
    import sys
    import os
    from .logging_setup import setup_logger
    # Use a stable log directory for bundled app
    if getattr(sys, 'frozen', False):
        log_dir = Path(os.path.expanduser("~/Library/Logs/MultiAgentsAssistant"))
    else:
        log_dir = project_root / config.log_dir
        
    logger = setup_logger(log_dir, config.log_file, debug=True)

    if args.command == "run":
        app = MultiAgentsAssistantApp(project_root=project_root, config=config)
        
        # Start backend worker in background
        app.start_background()
        
        # Run main UI in foreground
        from .main_ui import start_main_ui
        start_main_ui(app)
        
    elif args.command == "menubar":
        pass
        
        logger.info("Starting Menubar App...")
            
        try:
            from .agent_manager import AgentManager
            manager = AgentManager()
            
            # Show configuration UI on first run if no active agent is fully configured
            if not manager.is_agent_ready(manager.get_active_agent()):
                logger.info("首次启动或当前智能体未配置，显示引导界面...")
                
                # To prevent NSApplication runloop conflicts between pywebview and rumps,
                # we run the UI in a separate short-lived subprocess.
                import subprocess
                if getattr(sys, 'frozen', False):
                    subprocess.run([sys.executable, "ui"])
                else:
                    import os
                    main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"))
                    subprocess.run([sys.executable, main_py, "ui"])
                
                # Check again after UI closes
                manager.config = manager._load_config()
                if not manager.is_agent_ready(manager.get_active_agent()):
                    logger.warning("用户未配置有效的智能体，继续在待配置模式下运行。")

            app = MultiAgentsAssistantApp(project_root=project_root, config=config)
            logger.info("MultiAgentsAssistantApp initialized")
            run_menubar(app)
        except Exception as e:
            logger.error(f"Failed to start Menubar App: {e}", exc_info=True)


if __name__ == "__main__":
    main()
