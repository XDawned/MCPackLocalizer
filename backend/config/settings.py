# coding: utf-8
"""
Flask 配置类
"""
import os


class Config:
    """Flask 配置类"""
    
    # 安全密钥
    SECRET_KEY = os.environ.get('SECRET_KEY', 'modpack-localization-tools-secret-key')
    
    # 文件上传配置
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # 文件夹配置
    CACHE_FOLDER = os.path.join(os.path.dirname(__file__), 'cache')
    WORK_FOLDER = os.path.join(os.path.dirname(__file__), 'work')
    
    # 翻译 API 配置
    BAIDU_TRANSLATE_URL = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
    OPENAI_API_URL = 'https://api.openai.com/v1'
    
    # 跨域配置
    CORS_ORIGINS = ['http://localhost:5173', 'http://127.0.0.1:5173']
    
    # 确保目录存在
    @staticmethod
    def init_folders():
        """初始化必要的文件夹"""
        for folder in [Config.UPLOAD_FOLDER, Config.CACHE_FOLDER, Config.WORK_FOLDER]:
            os.makedirs(folder, exist_ok=True)


# 初始化文件夹
Config.init_folders()