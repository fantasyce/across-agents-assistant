from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time

from .paths import backend_socket_path


def _watch_parent() -> None:
    parent_pid = os.getppid()
    while True:
        if os.getppid() != parent_pid or os.getppid() == 1:
            print(f"Parent process (PID {parent_pid}) died. Terminating backend.", flush=True)
            os.kill(os.getpid(), signal.SIGTERM)
            return
        time.sleep(2)


def _run_mcp_server(server_name: str, server_args: list[str]) -> int:
    if server_name == "local_kb":
        from across_agents_assistant.mcp_servers import local_kb

        sys.argv = [sys.argv[0], *server_args]
        local_kb.main()
        return 0
    if server_name == "external_rag":
        from across_agents_assistant.mcp_servers import external_rag

        sys.argv = [sys.argv[0], *server_args]
        external_rag.main()
        return 0
    if server_name == "sqlite":
        from across_agents_assistant.mcp_servers import mcp_sqlite

        sys.argv = [sys.argv[0], *server_args]
        mcp_sqlite.main()
        return 0
    if server_name == "filesystem":
        from across_agents_assistant.mcp_servers import mcp_filesystem

        sys.argv = [sys.argv[0], *server_args]
        mcp_filesystem.main()
        return 0
    raise ValueError(f"Unsupported MCP server: {server_name}")


def main(argv: list[str] | None = None) -> int:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    parser = argparse.ArgumentParser(prog="across-agents-assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Start the current AAA backend API server.")
    run_parser.add_argument("--watch-parent", action="store_true", help="Exit when the parent process exits.")
    api_parser = sub.add_parser("api", help="Alias for run.")
    api_parser.add_argument("--watch-parent", action="store_true", help="Exit when the parent process exits.")

    mcp_parser = sub.add_parser("mcp", help="Run one of the bundled MCP compatibility servers.")
    mcp_parser.add_argument("server", choices=["local_kb", "external_rag", "sqlite", "filesystem"])
    mcp_parser.add_argument("server_args", nargs=argparse.REMAINDER)

    adapter_parser = sub.add_parser(
        "orchestrator-agent-adapter",
        help="Run the AAA host command adapter for Across Orchestrator.",
    )
    adapter_parser.add_argument("--agent", required=True)
    adapter_parser.add_argument("--timeout", type=float, default=300.0)

    args = parser.parse_args(argv)

    if args.command in {"run", "api"}:
        from .api_server import start_api_server

        if args.watch_parent:
            threading.Thread(target=_watch_parent, daemon=True).start()
        print(f"Starting Across Agents Assistant API Server on {backend_socket_path()}...", flush=True)
        start_api_server()
        return 0

    if args.command == "mcp":
        return _run_mcp_server(args.server, args.server_args)

    if args.command == "orchestrator-agent-adapter":
        from .orchestrator_agent_adapter import main as adapter_main

        return adapter_main(["--agent", args.agent, "--timeout", str(args.timeout)])

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
