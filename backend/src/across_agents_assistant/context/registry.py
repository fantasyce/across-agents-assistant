# backend/src/across_agents_assistant/context/registry.py
from typing import Dict, List, Any, Optional
import logging

from .base import ContextCollector

logger = logging.getLogger("across_agents_assistant.context")

class ContextCollectorRegistry:
    """上下文采集器注册表"""

    def __init__(self):
        self._collectors: Dict[str, ContextCollector] = {}

    def register(self, collector: ContextCollector) -> None:
        """注册采集器"""
        self._collectors[collector.source_name] = collector
        logger.info(f"注册上下文采集器: {collector.source_name}")

    def unregister(self, source_name: str) -> bool:
        """取消注册"""
        if source_name in self._collectors:
            del self._collectors[source_name]
            return True
        return False

    def get_collector(self, source_name: str) -> Optional[ContextCollector]:
        """获取采集器"""
        return self._collectors.get(source_name)

    def collect_all(self) -> Dict[str, Any]:
        """采集所有可用上下文"""
        result = {}
        for name, collector in self._collectors.items():
            try:
                if collector.is_available():
                    result[name] = collector.collect()
                else:
                    result[name] = {"error": f"{name} 不可用"}
            except Exception as e:
                logger.error(f"采集 {name} 失败: {e}")
                result[name] = {"error": str(e)}
        return result

    def collect_by_source(self, source_name: str) -> Optional[Dict[str, Any]]:
        """采集指定来源"""
        collector = self.get_collector(source_name)
        if not collector:
            return None
        if not collector.is_available():
            return {"error": f"{source_name} 不可用"}
        try:
            return collector.collect()
        except Exception as e:
            logger.error(f"采集 {source_name} 失败: {e}")
            return {"error": str(e)}

    def get_available_sources(self) -> List[str]:
        """获取所有可用来源"""
        return [name for name, c in self._collectors.items() if c.is_available()]

    def get_all_sources(self) -> List[str]:
        """获取所有已注册来源"""
        return list(self._collectors.keys())


# 全局注册表实例
registry = ContextCollectorRegistry()