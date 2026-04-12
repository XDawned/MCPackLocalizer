# coding: utf-8
"""
Flask API 模块
"""
from flask import Blueprint, jsonify, request
import os
import json

modpack_bp = Blueprint('modpack', __name__)


@modpack_bp.route('/scan', methods=['POST'])
def scan_modpack():
    """扫描整合包目录"""
    data = request.get_json()
    pack_folder = data.get('folder') if data else None
    
    if not pack_folder:
        return jsonify({'error': 'Folder path is required'}), 400
    
    if not os.path.exists(pack_folder):
        return jsonify({'error': 'Folder does not exist'}), 400
    
    try:
        # TODO: 实现整合包扫描逻辑
        result = {
            'mods': [],
            'ftbquests': [],
            'betterquests': [],
            'resourcepacks': []
        }
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@modpack_bp.route('/extract', methods=['POST'])
def extract_modpack():
    """提取整合包待翻译内容"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    pack_folder = data.get('folder')
    work_folder = data.get('work_folder')
    mods = data.get('mods', [])
    ftbquests = data.get('ftbquests', [])
    betterquests = data.get('betterquests', [])
    
    if not pack_folder or not work_folder:
        return jsonify({'error': 'Folder paths are required'}), 400
    
    try:
        # TODO: 实现提取逻辑
        result = {
            'extracted_files': [],
            'lang_files': []
        }
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@modpack_bp.route('/check', methods=['GET'])
def check_status():
    """检查提取状态"""
    return jsonify({'success': True, 'status': 'ready'})