import asyncio
from src.across_agents_assistant.api_server import chat_endpoint, ChatRequest

async def main():
    req = ChatRequest(
        text="检索本地知识库，告诉我有关 hermes agent 安装流程",
        session_id="test_one_shot_session",
        agent_id="openclaw"
    )
    print("Sending request...")
    res = await chat_endpoint(req)
    print("Response:")
    print(res.text)

if __name__ == "__main__":
    asyncio.run(main())
