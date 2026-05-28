from __future__ import annotations

import argparse
from pathlib import Path

from .app import AcrossAgentsAssistantApp
from .config import load_config
from .menubar import run_menubar
from .paths import log_dir as app_log_dir


def main():
    import os
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    parser = argparse.ArgumentParser(prog="across-agents-assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run")
    sub.add_parser("menubar")

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    config = load_config(project_root)

    import sys
    import os
    from .logging_setup import setup_logger
    # Keep app-owned logs with the rest of the local app state.
    log_dir = app_log_dir()

    logger = setup_logger(log_dir, config.log_file, debug=True)

    if args.command == "run":
        app = AcrossAgentsAssistantApp(project_root=project_root, config=config)

        # Start backend worker in background
        app.start_background()

        # Run main UI in foreground
        from .main_ui import start_main_ui
        start_main_ui(app)

    elif args.command == "menubar":
        pass

        logger.info("Starting Menubar App...")

        try:
            app = AcrossAgentsAssistantApp(project_root=project_root, config=config)
            logger.info("AcrossAgentsAssistantApp initialized")
            run_menubar(app)
        except Exception as e:
            logger.error(f"Failed to start Menubar App: {e}", exc_info=True)


if __name__ == "__main__":
    main()
