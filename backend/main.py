import sys
import multiprocessing
from across_agents_assistant.api_server import start_api_server

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    print("Starting Across Agents Assistant API Server on port 8000...")
    start_api_server()
