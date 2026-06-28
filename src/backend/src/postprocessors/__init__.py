from abc import ABC, abstractmethod
from typing import Dict


class BasePostprocessor(ABC):
    """翻译后处理器抽象基类。"""

    @abstractmethod
    def process(self, translation: str, original: str, metadata: Dict = None) -> str:
        """对翻译结果进行后处理校验和修复。"""
