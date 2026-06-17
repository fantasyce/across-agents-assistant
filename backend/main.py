import sys
import os
import time
import signal
import threading

if len(sys.argv) > 2 and sys.argv[1] == "mcp":
    if sys.argv[2] == "local_kb":
        from across_agents_assistant.mcp_servers import local_kb
        sys.argv = [sys.argv[0]] + sys.argv[3:]
        local_kb.main()
        sys.exit(0)
    elif sys.argv[2] == "external_rag":
        from across_agents_assistant.mcp_servers import external_rag
        sys.argv = [sys.argv[0]] + sys.argv[3:]
        external_rag.main()
        sys.exit(0)
    elif sys.argv[2] == "sqlite":
        from across_agents_assistant.mcp_servers import mcp_sqlite
        sys.argv = [sys.argv[0]] + sys.argv[3:]
        mcp_sqlite.main()
        sys.exit(0)
    elif sys.argv[2] == "filesystem":
        from across_agents_assistant.mcp_servers import mcp_filesystem
        sys.argv = [sys.argv[0]] + sys.argv[3:]
        mcp_filesystem.main()
        sys.exit(0)

if len(sys.argv) > 1 and sys.argv[1] == "orchestrator-agent-adapter":
    from across_agents_assistant.orchestrator_agent_adapter import main as adapter_main

    sys.exit(adapter_main(sys.argv[2:]))

from across_agents_assistant.api_server import start_api_server
from across_agents_assistant.paths import backend_socket_path

def watch_parent():
    """Watch the parent process and exit if it dies."""
    parent_pid = os.getppid()
    while True:
        # In macOS/Linux, if the parent process dies, the child is re-parented to init (PID 1)
        if os.getppid() != parent_pid or os.getppid() == 1:
            print(f"Parent process (PID {parent_pid}) died. Terminating backend.", flush=True)
            os.kill(os.getpid(), signal.SIGTERM)
            break
        time.sleep(2)

if __name__ == "__main__":

    if "--watch-parent" in sys.argv:
        watcher_thread = threading.Thread(target=watch_parent, daemon=True)
        watcher_thread.start()

    print(f"Starting Across Agents Assistant API Server on {backend_socket_path()}...", flush=True)
    start_api_server()
