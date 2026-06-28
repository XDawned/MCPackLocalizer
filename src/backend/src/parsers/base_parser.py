from abc import ABC, abstractmethod
from typing import Dict


class BaseParser(ABC):
    """解析器抽象基类：统一接口，所有格式解析器继承此类。"""

    @abstractmethod
    def can_parse(self, file_path: str) -> bool:
        """判断此解析器是否支持给定的文件路径。"""

    @abstractmethod
    def extract(self, file_path: str) -> Dict[str, str]:
        """从文件路径提取待翻译内容，返回 key→原文 字典。"""
