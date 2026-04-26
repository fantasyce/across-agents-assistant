from __future__ import annotations
import logging
import time
import uuid
from typing import Dict, List, Set, Callable, Optional
from dataclasses import dataclass, field

from .models import RiskLevel, ApprovalStatus, ApprovalRequest

logger = logging.getLogger("across_agents_assistant.approval")

# 审批超时时间（秒）
APPROVAL_TIMEOUT_SEC = 300  # 5分钟

class ApprovalService:
    """
    审批服务，管理待审批队列和审批操作。
    """

    def __init__(self):
        self._pending_requests: Dict[str, ApprovalRequest] = {}
        self._always_allowed_tools: Set[str] = set()
        self._approval_callbacks: List[Callable[[ApprovalRequest], None]] = []

    def add_callback(self, callback: Callable[[ApprovalRequest], None]) -> None:
        """添加审批状态变化回调"""
        self._approval_callbacks.append(callback)

    def _notify_callbacks(self, request: ApprovalRequest) -> None:
        """通知所有回调"""
        for callback in self._approval_callbacks:
            try:
                callback(request)
            except Exception as e:
                logger.error(f"审批回调错误: {e}")

    def create_approval_request(
        self,
        task_id: str,
        subtask_id: str,
        agent_id: str,
        tool_name: str,
        tool_params: Dict,
        risk_level: RiskLevel,
        description: str,
        plan_summary: str = "",
        context_sources: Optional[List[str]] = None
    ) -> ApprovalRequest:
        """创建审批请求"""
        # 检查是否在始终允许列表
        if self.is_auto_approved(tool_name):
            logger.info(f"工具 {tool_name} 在始终允许列表，自动批准")
            request = ApprovalRequest(
                request_id=f"auto-{uuid.uuid4().hex[:8]}",
                task_id=task_id,
                subtask_id=subtask_id,
                agent_id=agent_id,
                tool_name=tool_name,
                tool_params=tool_params,
                risk_level=risk_level,
                description=description,
                plan_summary=plan_summary,
                context_sources=context_sources or [],
                status=ApprovalStatus.ALWAYS_ALLOW
            )
        else:
            request = ApprovalRequest(
                request_id=f"req-{uuid.uuid4().hex[:8]}",
                task_id=task_id,
                subtask_id=subtask_id,
                agent_id=agent_id,
                tool_name=tool_name,
                tool_params=tool_params,
                risk_level=risk_level,
                description=description,
                plan_summary=plan_summary,
                context_sources=context_sources or [],
                status=ApprovalStatus.PENDING
            )
            self._pending_requests[request.request_id] = request

        logger.info(f"创建审批请求: {request.request_id} 工具={tool_name} 风险={risk_level.value}")
        self._notify_callbacks(request)
        return request

    def approve(self, request_id: str) -> bool:
        """批准请求"""
        request = self._pending_requests.get(request_id)
        if not request:
            logger.warning(f"审批请求不存在: {request_id}")
            return False

        if request.status != ApprovalStatus.PENDING:
            logger.warning(f"请求状态不是 pending: {request_id} 状态={request.status}")
            return False

        request.status = ApprovalStatus.APPROVED
        del self._pending_requests[request_id]
        logger.info(f"批准审批请求: {request_id}")
        self._notify_callbacks(request)
        return True

    def reject(self, request_id: str) -> bool:
        """拒绝请求"""
        request = self._pending_requests.get(request_id)
        if not request:
            logger.warning(f"审批请求不存在: {request_id}")
            return False

        if request.status != ApprovalStatus.PENDING:
            logger.warning(f"请求状态不是 pending: {request_id} 状态={request.status}")
            return False

        request.status = ApprovalStatus.REJECTED
        del self._pending_requests[request_id]
        logger.info(f"拒绝审批请求: {request_id}")
        self._notify_callbacks(request)
        return True

    def always_allow(self, request_id: str) -> bool:
        """始终允许该工具"""
        request = self._pending_requests.get(request_id)
        if not request:
            logger.warning(f"审批请求不存在: {request_id}")
            return False

        if request.status != ApprovalStatus.PENDING:
            return False

        # 添加到始终允许列表
        self._always_allowed_tools.add(request.tool_name)
        request.status = ApprovalStatus.ALWAYS_ALLOW
        del self._pending_requests[request_id]
        logger.info(f"始终允许工具: {request.tool_name}")
        self._notify_callbacks(request)
        return True

    def get_pending_requests(self) -> List[ApprovalRequest]:
        """获取所有待审批请求"""
        # 清理过期请求
        expired_ids = []
        for req_id, req in self._pending_requests.items():
            if req.is_expired(APPROVAL_TIMEOUT_SEC):
                expired_ids.append(req_id)

        for req_id in expired_ids:
            req = self._pending_requests[req_id]
            req.status = ApprovalStatus.EXPIRED
            del self._pending_requests[req_id]
            self._notify_callbacks(req)
            logger.info(f"审批请求已过期: {req_id}")

        return list(self._pending_requests.values())

    def is_auto_approved(self, tool_name: str) -> bool:
        """检查工具是否自动批准"""
        return tool_name in self._always_allowed_tools

    def get_always_allowed_tools(self) -> Set[str]:
        """获取始终允许的工具列表"""
        return self._always_allowed_tools.copy()

    def remove_always_allow(self, tool_name: str) -> bool:
        """从始终允许列表移除"""
        if tool_name in self._always_allowed_tools:
            self._always_allowed_tools.remove(tool_name)
            return True
        return False