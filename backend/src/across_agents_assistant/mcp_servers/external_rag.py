import sys
import os
import requests
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("External RAG Connector")

rag_endpoint = ""

@mcp.tool(name="search_external_knowledge_base")
def search_external_knowledge_base(query: str) -> str:
    """Search the external RAG (Retrieval-Augmented Generation) system for information.
    Args:
        query: The search query to send to the RAG system.
    """
    if not rag_endpoint:
        return "Error: RAG API endpoint is not configured."

    try:
        headers = {"Content-Type": "application/json"}
        payload = {"query": query}

        response = requests.post(rag_endpoint, json=payload, headers=headers, timeout=15)
        response.raise_for_status()

        data = response.json()
        if "answer" in data:
            return data["answer"]
        elif "result" in data:
            return data["result"]
        elif "data" in data:
            return json.dumps(data["data"], ensure_ascii=False)
        else:
            return json.dumps(data, ensure_ascii=False)

    except requests.exceptions.RequestException as e:
        return f"HTTP Request Error: {str(e)}"
    except Exception as e:
        return f"Error connecting to RAG endpoint: {str(e)}"

def main():
    global rag_endpoint
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", type=str, help="URL of the external RAG API")
    args, unknown = parser.parse_known_args()

    if args.endpoint:
        rag_endpoint = args.endpoint

    sys.argv = [sys.argv[0]] + unknown
    mcp.run()

if __name__ == "__main__":
    main()
