import sys
import os
import time
import signal
import threading
import multiprocessing

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

from across_agents_assistant.api_server import start_api_server

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
    multiprocessing.freeze_support()
    
    # Only start watcher if we are running as a bundled child process 
    # (checking if parent is not a terminal or launchd can be tricky, but checking if we were spawned by our Swift app works. 
    # We can pass an arg or just always watch).
    if "--watch-parent" in sys.argv:
        watcher_thread = threading.Thread(target=watch_parent, daemon=True)
        watcher_thread.start()
    
    print("Starting Across Agents Assistant API Server on port 8000...", flush=True)
    start_api_server()
