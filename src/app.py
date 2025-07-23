#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vanna AI Natural Language to SQL System - Application Factory
使用应用工厂模式重构，解决循环依赖问题
"""
import sys
import os
import json
import uuid
import logging
import atexit
import signal
import traceback
from datetime import datetime
from flask import Flask, request, jsonify, session, current_app

# 导入所有模块的初始化函数和蓝图
from .vanna_service import VannaService
from .uqp_router import uqp_blueprint, initialize_uqp
from .external_api_handler import ExternalAPIHandler, external_api_blueprint

# 全局变量，用于保存VannaService实例
vanna_service_instance = None

# 全局会话存储
conversation_history = {}

def debug_print(message):
    """调试输出函数"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    debug_msg = f"[FLASK-FACTORY {timestamp}] {message}"
    # 使用 current_app.logger 可以在应用上下文中记录日志
    if current_app:
        current_app.logger.info(debug_msg)
    else:
        print(debug_msg)

# 应用工厂函数
def create_app():
    """
    创建并配置Flask应用实例
    """
    debug_print("开始创建Flask应用...")
    
    app = Flask(__name__)
    app.secret_key = 'your-secret-key-here-factory'
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_TYPE'] = 'filesystem'
    
    # 步骤1: 创建核心服务实例
    # 使用with app.app_context()来确保在正确的上下文中操作
    with app.app_context():
        current_app.logger.info("步骤1: 初始化VannaService...")
        vanna_service = VannaService()
        app.vanna_service = vanna_service
        
        # 步骤2: 初始化所有独立的处理器/模块
        current_app.logger.info("步骤2: 初始化外部API处理器...")
        # 修正: ExternalAPIHandler依赖VannaService来获取配置等信息
        external_api_handler = ExternalAPIHandler(vanna_service=vanna_service)
        app.external_api_handler = external_api_handler

        # 步骤3: 初始化依赖于其他服务的模块
        current_app.logger.info("步骤3: 初始化UQP路由器 (注入依赖)...")
        initialize_uqp(vanna_service, external_api_handler)
    
    # 步骤4: 注册所有蓝图
    app.register_blueprint(uqp_blueprint, url_prefix='/api/uqp')
    app.register_blueprint(external_api_blueprint, url_prefix='/api/external')
    
    # 注册核心API路由
    register_core_routes(app)

    debug_print("Flask应用创建成功")
    return app

def register_core_routes(app):
    """
    将核心API路由注册到应用实例
    """
    @app.route('/health', methods=['GET'])
    def health_check():
        """健康检查接口"""
        try:
            vanna_service = current_app.vanna_service
            version_info = vanna_service.get_version_info()
            return jsonify({
                "status": "healthy",
                "version": version_info,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return jsonify({"status": "unhealthy", "error": str(e)}), 500

    @app.route('/nl2sql', methods=['POST'])
    def nl2sql():
        """自然语言转SQL接口"""
        vanna_service = current_app.vanna_service
        try:
            data = request.json
            question = data.get('question')
            if not question:
                return jsonify({"error": "问题不能为空"}), 400
            
            conversation_id = session.get('conversation_id', str(uuid.uuid4()))
            session['conversation_id'] = conversation_id
            
            debug_print(f"收到nl2sql问题: {question} (会话: {conversation_id})")
            
            history = conversation_history.get(conversation_id, [])
            
            sql, llm_response, rag_context = vanna_service.generate_sql(question, history)
            
            conversation_history[conversation_id] = history + [{"role": "user", "content": question}, {"role": "assistant", "content": sql}]
            
            debug_print(f"SQL生成完成: {sql[:100]}...")
            
            return jsonify({
                "sql": sql,
                "llm_response": llm_response,
                "conversation_id": conversation_id
            })
        except Exception as e:
            debug_print(f"nl2sql错误: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/nl2data', methods=['POST'])
    def nl2data():
        """自然语言转数据查询接口"""
        vanna_service = current_app.vanna_service
        try:
            data = request.json
            question = data.get('question')
            if not question:
                return jsonify({"error": "问题不能为空"}), 400
            
            conversation_id = session.get('conversation_id', str(uuid.uuid4()))
            session['conversation_id'] = conversation_id
            
            debug_print(f"收到nl2data问题: {question} (会话: {conversation_id})")
            
            history = conversation_history.get(conversation_id, [])
            
            result, data_results = vanna_service.ask_and_run(question, history)
            
            conversation_history[conversation_id] = history + [{"role": "user", "content": question}, {"role": "assistant", "content": f"SQL: {result.get('sql', '')} | 结果: {result.get('row_count', 0)} 行"}]
            
            debug_print(f"nl2data完成: {result.get('status', 'unknown')}")
            
            result['conversation_id'] = conversation_id
            
            return jsonify(result)
        except Exception as e:
            debug_print(f"nl2data错误: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/db-connection-status', methods=['GET'])
    def db_connection_status():
        """数据库连接状态接口"""
        vanna_service = current_app.vanna_service
        try:
            status = vanna_service.get_db_connection_status()
            return jsonify(status)
        except Exception as e:
            debug_print(f"获取连接状态错误: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/reset-connection-pool', methods=['POST'])
    def reset_connection_pool():
        """重置连接池接口"""
        vanna_service = current_app.vanna_service
        try:
            result = vanna_service.reset_connection_pool()
            return jsonify(result)
        except Exception as e:
            debug_print(f"重置连接池错误: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/version', methods=['GET'])
    def version():
        """获取版本信息"""
        vanna_service = current_app.vanna_service
        return jsonify(vanna_service.get_version_info())

    @app.route('/modules-status', methods=['GET'])
    def modules_status():
        """获取模块状态"""
        vanna_service = current_app.vanna_service
        status = {
            "service_version": vanna_service.get_version_info(),
            "database": vanna_service.get_db_connection_status(),
            "llm": {
                "provider": "Qianwen",
                "model": vanna_service.original_config.get('llm', {}).get('model', 'N/A')
            },
            "rag": {
                "retriever": "active",
                "vector_store_path": vanna_service.original_config.get('vector_store', {}).get('path', 'N/A')
            },
            "sql_generator": "active",
            "sql_executor": "active"
        }
        return jsonify(status)

    @app.route('/debug-service', methods=['GET'])
    def debug_service():
        """调试服务接口"""
        vanna_service = current_app.vanna_service
        try:
            test_question = "查询今天的总用户数"
            debug_print(f"开始调试服务，使用问题: '{test_question}'")
            result, _ = vanna_service.ask_and_run(question=test_question)
            debug_print("调试服务完成")
            return jsonify({"status": "debug_completed", "result": result})
        except Exception as e:
            debug_print(f"调试服务时出错: {e}")
            return jsonify({"status": "debug_error", "error": str(e)}), 500