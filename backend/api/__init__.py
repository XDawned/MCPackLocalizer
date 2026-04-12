# coding: utf-8
"""
Flask API 模块初始化
"""
from .modpack import modpack_bp
from .translation import translation_bp
from .resourcepack import resourcepack_bp
from .settings import settings_bp

__all__ = [
    'modpack_bp',
    'translation_bp',
    'resourcepack_bp',
    'settings_bp'
]