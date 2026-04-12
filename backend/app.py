# coding: utf-8
"""
Flask Backend for Modpack Localization Tools
"""
import os
import sys
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# 添加后端目录到路径
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

from api.modpack import modpack_bp
from api.translation import translation_bp
from api.resourcepack import resourcepack_bp
from api.settings import settings_bp
from config.settings import Config


def create_app():
    """应用工厂函数"""
    app = Flask(__name__)
    app.config.from_object(Config)

    # 启用 CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })

    # 注册蓝图
    app.register_blueprint(modpack_bp, url_prefix='/api/modpack')
    app.register_blueprint(translation_bp, url_prefix='/api/translation')
    app.register_blueprint(resourcepack_bp, url_prefix='/api/resourcepack')
    app.register_blueprint(settings_bp, url_prefix='/api/settings')

    @app.route('/api/health', methods=['GET'])
    def health_check():
        """健康检查接口"""
        return jsonify({'status': 'ok', 'message': 'Flask server is running'})

    @app.route('/api/version', methods=['GET'])
    def get_version():
        """获取版本信息"""
        return jsonify({
            'version': '2.0.0',
            'flask_version': '2.0.0'
        })

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found', 'message': str(error)}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error', 'message': str(error)}), 500

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({'error': 'Bad request', 'message': str(error)}), 400

    return app


app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'production') == 'development'
    print(f'Starting Flask server on port {port} (debug={debug})')
    app.run(host='127.0.0.1', port=port, debug=debug)