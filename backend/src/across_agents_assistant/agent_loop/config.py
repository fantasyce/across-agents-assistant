from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class LoopConfig:
    """Agent Loop 配置"""
    max_iterations: int = 5
    iteration_timeout_sec: float = 120.0
    tool_result_summary: bool = True

@dataclass
class LoopResult:
    """Agent Loop 执行结果"""
    final_answer: str
    iterations: int
    tool_calls: list
    success: bool
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
