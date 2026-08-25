from __future__ import annotations

import argparse
import json
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
    sub.add_parser(
        "host-mcp-proxy",
        help="Proxy the host's fail-closed read-only MCP tools over stdio.",
    )
    model_decision_parser = sub.add_parser(
        "autopilot-model-decision",
        help="Return a structured host-model decision for Across Autopilot.",
    )
    model_decision_parser.add_argument("--request-json", help="Inline decision request JSON. Defaults to stdin.")
    research_decision_parser = sub.add_parser(
        "autopilot-research-decision",
        help="Return a structured host research-to-iteration decision for Across Autopilot.",
    )
    research_decision_parser.add_argument("--request-json", help="Inline research decision request JSON. Defaults to stdin.")
    code_iteration_parser = sub.add_parser(
        "autopilot-code-iteration",
        help="Return a structured host code patch for Across Autopilot.",
    )
    code_iteration_parser.add_argument("--request-json", help="Inline code iteration request JSON. Defaults to stdin.")
    review_decision_parser = sub.add_parser(
        "autopilot-review-decision",
        help="Return a distinct host-model review decision for Across Autopilot.",
    )
    review_decision_parser.add_argument("--request-json", help="Inline review request JSON. Defaults to stdin.")
    sub.add_parser(
        "loop-engineering-capabilities",
        help="Print the AAA-hosted Loop Engineering capability pack registry.",
    )
    worker_model_gateway_parser = sub.add_parser(
        "worker-model-gateway",
        help="Run the explicit-interface mTLS task-bound Worker model gateway.",
    )
    worker_model_gateway_parser.add_argument("gateway_args", nargs=argparse.REMAINDER)

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

    if args.command == "host-mcp-proxy":
        from .agent_bridge.host_mcp_proxy import run_host_mcp_stdio_proxy

        return run_host_mcp_stdio_proxy()

    if args.command == "autopilot-model-decision":
        from .autopilot_model_decision_cli import main as model_decision_main

        cli_args: list[str] = []
        if args.request_json is not None:
            cli_args.extend(["--request-json", args.request_json])
        return model_decision_main(cli_args)

    if args.command == "autopilot-research-decision":
        from .autopilot_research_decision_cli import main as research_decision_main

        cli_args = []
        if args.request_json is not None:
            cli_args.extend(["--request-json", args.request_json])
        return research_decision_main(cli_args)

    if args.command == "autopilot-code-iteration":
        from .autopilot_code_iteration_cli import main as code_iteration_main

        cli_args = []
        if args.request_json is not None:
            cli_args.extend(["--request-json", args.request_json])
        return code_iteration_main(cli_args)

    if args.command == "autopilot-review-decision":
        from .autopilot_review_decision_cli import main as review_decision_main

        cli_args = []
        if args.request_json is not None:
            cli_args.extend(["--request-json", args.request_json])
        return review_decision_main(cli_args)

    if args.command == "loop-engineering-capabilities":
        from .loop_engineering_capability_pack import loop_engineering_capability_pack

        print(json.dumps(loop_engineering_capability_pack(), ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "worker-model-gateway":
        from .worker_model_gateway import main as worker_model_gateway_main

        return worker_model_gateway_main(args.gateway_args)

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
