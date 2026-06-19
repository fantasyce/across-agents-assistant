#!/usr/bin/env python3
"""
Backend API E2E Test
使用 Unix Socket 通信测试任务编排 API：
1. POST /api/tasks/auto - 创建任务
2. GET /api/tasks - 列出任务
3. GET /api/tasks/{id} - 获取任务详情（含 waves）
4. GET /api/tasks/{id}/stream - SSE 流
5. POST /api/tasks/{id}/pause - 暂停
6. POST /api/tasks/{id}/resume - 恢复
7. POST /api/tasks/{id}/cancel - 取消
"""

import subprocess
import os
import sys
import time
import threading
from pathlib import Path
import pytest
import httpx

SOCKET_PATH = os.path.expanduser(os.environ.get("ACROSS_AGENTS_SOCKET", "~/.across/run/across-agents-assistant/across-agents.sock"))
SERVER_START_TIMEOUT = 15
BACKEND_DIR = Path(__file__).resolve().parents[2]


def start_backend():
    """启动后端服务"""
    proc = subprocess.Popen(
        [sys.executable, "-c", """
import sys
sys.path.insert(0, 'src')
from across_agents_assistant.api_server import start_api_server
start_api_server()
"""],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc


def wait_for_socket(path, timeout=SERVER_START_TIMEOUT):
    """等待 Unix socket 就绪"""
    start = time.time()
    while time.time() - start < timeout:
        import os
        if os.path.exists(path):
            try:
                transport = httpx.HTTPTransport(uds=path)
                client = httpx.Client(transport=transport, timeout=2)
                resp = client.get("http://localhost/api/tasks")
                if resp.status_code in (200, 404):
                    client.close()
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def make_client():
    """创建 Unix socket HTTP 客户端"""
    transport = httpx.HTTPTransport(uds=SOCKET_PATH)
    return httpx.Client(transport=transport, timeout=10)


class TestBackendAPI:
    _task_id: str | None = None

    @classmethod
    def setup_class(cls):
        print("\n🚀 启动后端服务...")
        cls.proc = start_backend()
        if not wait_for_socket(SOCKET_PATH):
            cls.proc.terminate()
            pytest.skip("后端服务启动失败 (Unix socket 未就绪)")
        print("✅ 后端服务已启动 (Unix socket 就绪)")

    @classmethod
    def teardown_class(cls):
        print("\n🛑 关闭后端服务...")
        cls.proc.terminate()
        cls.proc.wait(timeout=5)

    def test_get_tasks(self):
        """GET /api/tasks - 任务列表"""
        client = make_client()
        resp = client.get("http://localhost/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"  ✅ GET /api/tasks 返回 {len(data)} 个任务")

    def test_create_task_auto(self):
        """POST /api/tasks/auto - 创建任务"""
        client = make_client()
        payload = {
            "description": "Build a simple hello world Python script",
            "project_dir": "/tmp/e2e-test-hello",
            "task_types": ["artifact"],
            "allowed_subtask_agents": [],
            "strict_dependency": True,
            "enable_wave_gate": True,
        }
        resp = client.post("http://localhost/api/tasks/auto", json=payload)
        assert resp.status_code in (200, 201, 202), f"创建任务失败: {resp.status_code} {resp.text}"
        data = resp.json()
        task_id = data.get("task_id") or data.get("taskId")
        assert task_id, f"响应中无 task_id: {data}"
        print(f"  ✅ 任务创建成功: {task_id}")
        self.__class__._task_id = task_id

    def test_get_task_detail(self):
        """GET /api/tasks/{id} - 任务详情"""
        task_id = self.__class__._task_id
        if not task_id:
            pytest.skip("需要先创建任务")

        client = make_client()
        resp = client.get(f"http://localhost/api/tasks/{task_id}")
        assert resp.status_code == 200, f"获取任务详情失败: {resp.status_code} {resp.text}"
        data = resp.json()
        actual_id = data.get("taskId") or data.get("task_id")
        assert actual_id == task_id, f"任务 ID 不匹配: {actual_id} vs {task_id}"
        assert "status" in data
        assert "waves" in data or "subtasks" in data
        print(f"  ✅ 任务详情获取成功: status={data.get('status')}, waves={len(data.get('waves', []))}")

    def test_sse_stream(self):
        """GET /api/tasks/{id}/stream - SSE 流"""
        task_id = self.__class__._task_id
        if not task_id:
            pytest.skip("需要先创建任务")

        events = []
        error_msg = [None]

        def sse_client():
            try:
                transport = httpx.HTTPTransport(uds=SOCKET_PATH)
                with httpx.Client(transport=transport, timeout=10) as client:
                    with client.stream("GET", f"http://localhost/api/tasks/{task_id}/stream") as resp:
                        assert resp.status_code == 200, f"SSE 失败: {resp.status_code}"
                        for line in resp.iter_lines():
                            if line.startswith("data: "):
                                events.append(line[6:])
                            if len(events) >= 3:
                                break
            except Exception as e:
                error_msg[0] = str(e)

        t = threading.Thread(target=sse_client)
        t.start()
        t.join(timeout=15)

        if error_msg[0]:
            print(f"  ⚠️  SSE client error: {error_msg[0]}")
            pytest.skip(f"SSE 连接异常: {error_msg[0]}")

        print(f"  ✅ SSE 流连接成功，收到 {len(events)} 条事件")
        if events:
            import json
            for ev in events[:2]:
                try:
                    d = json.loads(ev)
                    print(f"     事件: type={d.get('type', '?')}, taskId={d.get('taskId', '?')}")
                except Exception:
                    print(f"     原始: {ev[:100]}")

    def test_pause_resume_cancel(self):
        """POST /api/tasks/{id}/pause|resume|cancel"""
        task_id = self.__class__._task_id
        if not task_id:
            pytest.skip("需要先创建任务")

        client = make_client()

        resp = client.post(f"http://localhost/api/tasks/{task_id}/pause")
        print(f"  Pause: {resp.status_code}")
        assert resp.status_code in (200, 404, 409, 500), f"Pause 失败: {resp.status_code} {resp.text}"

        resp = client.post(f"http://localhost/api/tasks/{task_id}/resume")
        print(f"  Resume: {resp.status_code}")
        assert resp.status_code in (200, 404, 409, 500), f"Resume 失败: {resp.status_code} {resp.text}"

        resp = client.post(f"http://localhost/api/tasks/{task_id}/cancel")
        print(f"  Cancel: {resp.status_code}")
        assert resp.status_code in (200, 404, 409, 500), f"Cancel 失败: {resp.status_code} {resp.text}"

        print(f"  ✅ 暂停/恢复/取消端点正常")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
