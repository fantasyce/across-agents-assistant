from abc import ABC, abstractmethod
from typing import Dict, Any

class ContextCollector(ABC):
    """上下文采集器基类"""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """数据来源名称"""
        pass

    @abstractmethod
    def collect(self) -> Dict[str, Any]:
        """采集上下文"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查是否可用"""
        pass