#!/usr/bin/env python3
"""
UQP统一查询协议路由器
Unified Query Protocol (UQP) Router - Blueprint Implementation
简化版本：使用API优先策略，直接通过路由决策引擎进行分流
"""

import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Tuple
from flask import Blueprint, request, jsonify, current_app

from .external_api_handler import ExternalAPIHandler
from .routing.decision_engine import get_routing_engine
from .routing.routing_monitor import get_routing_monitor

# 1. 创建蓝图实例
uqp_blueprint = Blueprint('uqp_router', __name__)

# 全局的路由器实例
uqp_router_instance = None

def get_uqp_router():
    """获取UQP路由器单例"""
    global uqp_router_instance
    if uqp_router_instance is None:
        # 从应用上下文中获取依赖项
        vanna_service = getattr(current_app, 'vanna_service', None)
        external_api_handler = getattr(current_app, 'external_api_handler', None)

        if not vanna_service or not external_api_handler:
            # 这个错误通常意味着应用没有通过create_app正确启动
            raise RuntimeError(
                "Application context not properly configured. "
                "Ensure vanna_service and external_api_handler are attached to the app object in the factory."
            )
        
        uqp_router_instance = UQPRouter(vanna_service, external_api_handler)
    return uqp_router_instance

def initialize_uqp(vanna_service, external_api_handler):
    """
    初始化UQP模块，主要是创建一个UQPRouter实例。
    这个函数在应用工厂中被调用。
    """
    global uqp_router_instance
    if uqp_router_instance is None:
        uqp_router_instance = UQPRouter(vanna_service, external_api_handler)
        current_app.logger.info("UQPRouter instance created and initialized with dependencies.")

class UQPRouter:
    """
    统一查询协议路由器
    简化版本：直接使用API优先策略进行路由分流
    - 包含SQL关键词 → NL2SQL处理器
    - 不包含SQL关键词 → 外部API处理器
    """
    
    def __init__(self, vanna_service, external_api_handler):
        """
        初始化路由器
        
        Args:
            vanna_service: Vanna服务实例，用于NL2SQL查询
            external_api_handler: 外部API处理器实例
        """
        self.vanna_service = vanna_service
        self.external_api_handler = external_api_handler
        self.logger = logging.getLogger(__name__)
        
        # 意图到处理器的映射
        self.intent_handlers = {
            'EXTERNAL_API': self._handle_external_api,
            'NL2SQL': self._handle_nl2sql,
        }
        
        # 初始化路由决策引擎
        self.routing_engine = get_routing_engine()
        
        # 初始化监控器
        self.monitor = get_routing_monitor()
        
        
    
    def classify_intent(self, question: str) -> Tuple[str, float]:
        """
        简化路由机制：直接使用路由决策引擎（API优先策略）
        
        Returns:
            Tuple[str, float]: (意图类型, 置信度分数)
        """
        start_time = time.time()
        
        try:
            # 使用路由决策引擎进行分类
            route, confidence, decision_info = self.routing_engine.decide_route(question)
            
            # 记录决策信息
            self.logger.debug(f"路由决策引擎结果: {route} (置信度: {confidence:.3f})")
            self.logger.debug(f"决策信息: {decision_info}")
            
            # 记录监控信息
            response_time = time.time() - start_time
            self.monitor.record_routing_decision(
                question, route, confidence, decision_info, response_time
            )
            
            self.logger.info(f"问题 '{question}' 分类为 {route} (置信度: {confidence:.3f})")
            return route, confidence
            
        except Exception as e:
            self.logger.error(f"路由决策失败: {e}")
            # 记录错误
            self.monitor.record_error(e, {'question': question, 'step': 'classify_intent'})
            # 默认使用API处理
            self.logger.warning(f"路由决策失败，默认使用EXTERNAL_API处理")
            return 'EXTERNAL_API', 0.5
    
        if any(keyword in question for keyword in air_quality_keywords):
            self.logger.info(f"问题 '{question}' 通过关键词匹配分类为 EXTERNAL_API")
            return "EXTERNAL_API"
        
        # 默认路由到NL2SQL
        self.logger.info(f"问题 '{question}' 通过关键词匹配分类为 NL2SQL")
        return "NL2SQL"
    
    
    def route_query(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        路由查询请求到合适的处理器
        
        Args:
            request_data: UQP格式的请求数据
            
        Returns:
            UQP格式的响应数据
        """
        question = request_data.get('question', '')
        client_intent_hint = request_data.get('intent_hint', 'UNKNOWN')
        history = request_data.get('history') or [] # 修正: 使用 or [] 来健壮地处理None值
        
        self.logger.debug(f"开始路由查询 - 问题: {question}")
        self.logger.debug(f"客户端意图提示: {client_intent_hint}")
        self.logger.debug(f"历史记录长度: {len(history)}")
        
        try:
            # [核心修改] 无论客户端提示是什么，都由后端进行最终的意图分类
            final_intent, confidence = self.classify_intent(question)
            self.logger.debug(f"后端最终分类意图: {final_intent}, 置信度: {confidence:.3f}")
            
            # 选择合适的处理器
            handler = self.intent_handlers.get(final_intent, self._handle_nl2sql)
            self.logger.debug(f"选择处理器: {handler.__name__}")
            
            # 调用处理器
            result = handler(request_data)
            self.logger.debug(f"处理器返回状态: {result.get('status', 'unknown')}")
            
            # 确保返回的结果符合UQP格式
            final_result = self._ensure_uqp_format(result)
            
            return final_result
            
        except Exception as e:
            self.logger.error(f"路由查询异常: {type(e).__name__}: {str(e)}")
            
            return {
                "status": "error",
                "response_type": "message",
                "payload": {
                    "format": "text",
                    "value": f"查询路由失败: {str(e)}"
                },
                "debug_info": {
                    "execution_path": "UQP_ROUTER",
                    "error": str(e),
                    "intent_hint": client_intent_hint,
                    "question": question
                }
            }
    
    def _handle_external_api(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理外部API查询
        如果API处理器返回route_to_sql状态，则自动转向NL2SQL处理
        """
        try:
            result = self.external_api_handler.handle_external_api_query(request_data)
            
            # 检查是否需要转向SQL查询
            if result.get('status') == 'route_to_sql':
                self.logger.info(f"[UQP_ROUTER] API处理器建议转向SQL查询: {result.get('reason', '未知原因')}")
                
                # 记录转向原因
                original_reason = result.get('reason', 'API参数不足')
                
                # 转向NL2SQL处理
                self.logger.info(f"[UQP_ROUTER] 自动转向NL2SQL处理")
                nl2sql_result = self._handle_nl2sql(request_data)
                
                # 在NL2SQL结果中添加转向说明
                if nl2sql_result.get('status') == 'success':
                    # 在成功结果中添加转向说明
                    debug_info = nl2sql_result.get('debug_info', {})
                    debug_info['route_from_api'] = {
                        'original_handler': 'external_api',
                        'route_reason': original_reason,
                        'auto_routed_to': 'nl2sql'
                    }
                    nl2sql_result['debug_info'] = debug_info
                    
                    self.logger.info(f"[UQP_ROUTER] 成功转向NL2SQL处理")
                    return nl2sql_result
                else:
                    # NL2SQL也失败了，返回组合错误信息
                    return {
                        "status": "error",
                        "response_type": "message",
                        "payload": {
                            "format": "text",
                            "value": f"API查询参数不足（{original_reason}），转向SQL查询也失败。请提供更具体的查询信息。"
                        },
                        "debug_info": {
                            "execution_path": "UQP_ROUTER",
                            "route_from_api": original_reason,
                            "nl2sql_result": nl2sql_result
                        }
                    }
            
            # 正常API处理结果
            return result
            
        except Exception as e:
            self.logger.error(f"外部API处理失败: {str(e)}")
            return {
                "status": "error",
                "response_type": "message",
                "payload": {
                    "format": "text",
                    "value": f"外部API查询失败: {str(e)}"
                },
                "debug_info": {
                    "execution_path": "EXTERNAL_API_HANDLER",
                    "error": str(e)
                }
            }
    
    def _handle_nl2sql(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理NL2SQL查询
        """
        if not self.vanna_service:
            self.logger.error("vanna_service未初始化")
            return {
                "status": "error",
                "response_type": "message",
                "payload": {
                    "format": "text",
                    "value": "NL2SQL服务未初始化"
                },
                "debug_info": {
                    "execution_path": "NL2SQL_HANDLER",
                    "error": "vanna_service_not_initialized"
                }
            }
        
        try:
            question = request_data.get('question', '')
            self.logger.debug(f"NL2SQL处理问题: {question}")
            
            try:
                # 修正: 确保将history传递下去
                history_to_pass = request_data.get("history") or []
                result_dict, data_obj = self.vanna_service.ask_and_run(question=question, history=history_to_pass)
                self.logger.debug("ask_and_run调用成功")
            except Exception as e:
                self.logger.error(f"ask_and_run调用失败: {type(e).__name__}: {str(e)}")
                raise
            
            # [修复] 将正确的结果字典传递给转换函数
            uqp_result = self._convert_nl2sql_to_uqp(result_dict, question)
            
            return uqp_result
            
        except Exception as e:
            self.logger.error(f"NL2SQL处理异常: {type(e).__name__}: {str(e)}")
            
            return {
                "status": "error",
                "response_type": "message",
                "payload": {
                    "format": "text",
                    "value": f"NL2SQL查询失败: {str(e)}"
                },
                "debug_info": {
                    "execution_path": "NL2SQL_HANDLER",
                    "error": str(e)
                }
            }
    
    def _convert_nl2sql_to_uqp(self, nl2sql_result: Any, question: str) -> Dict[str, Any]:
        """
        将NL2SQL处理器的结果转换为UQP格式
        """
        # 检查是否为None或非字典类型
        if not isinstance(nl2sql_result, dict):
            return {
                "status": "success",
                "response_type": "message",
                "payload": {
                    "format": "text",
                    "value": str(nl2sql_result) if nl2sql_result is not None else "执行了操作，但没有返回文本结果。"
                },
                "debug_info": {"execution_path": "NL2SQL_HANDLER", "nl2sql_status": "raw_string_response"}
            }


        # 处理成功或包含数据的其他情况
        # 即使'results'是None或空列表，也应被视为一种有效的数据响应
        if 'sql' in nl2sql_result and 'results' in nl2sql_result:
            results_data = nl2sql_result['results']
            sql_query = nl2sql_result.get('sql', 'N/A')
            
            # 对结果是None的情况进行健壮性处理
            if results_data is None:
                results_data = []

            # 如果没有数据，返回一个消息
            if not results_data:
                return {
                    "status": "success",
                    "response_type": "message",
                    "payload": {
                        "format": "text",
                        "value": "查询已执行，但没有返回任何数据。"
                    },
                    "debug_info": {
                        "execution_path": "NL2SQL_HANDLER",
                        "nl2sql_status": "success_no_data",
                        "sql_generated": sql_query,
                        "original_question": question
                    }
                }
            
            # 如果有数据，格式化为表格
            return {
                "status": "success",
                "response_type": "data",
                "payload": {
                    "format": "json",
                    "value": results_data
                },
                "debug_info": {
                    "execution_path": "NL2SQL_HANDLER",
                    "nl2sql_status": "success_with_data",
                    "sql_generated": sql_query,
                    "original_question": question
                }
            }
        
        # 对于不符合上述任何一种情况的字典，将其作为通用消息返回
        return {
            "status": "success",
            "response_type": "message",
            "payload": {
                "format": "text",
                "value": f"操作完成，但返回了非标准格式的结果: {str(nl2sql_result)}"
            },
            "debug_info": {"execution_path": "NL2SQL_HANDLER", "nl2sql_status": "unhandled_dict_format"}
        }

    def _ensure_uqp_format(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        确保结果符合UQP格式
        """
        # 检查必需字段
        if 'status' not in result:
            result['status'] = 'success'
        
        if 'response_type' not in result:
            result['response_type'] = 'message'
        
        if 'payload' not in result:
            result['payload'] = {
                "format": "text",
                "value": str(result)
            }
        
        # 确保payload有正确的格式
        if isinstance(result['payload'], dict):
            if 'format' not in result['payload']:
                result['payload']['format'] = 'text'
            if 'value' not in result['payload']:
                result['payload']['value'] = ''
        
        return result
    
    def test_handlers(self) -> Dict[str, Any]:
        """
        测试各个处理器的连接状态
        """
        results = {}
        
        # 测试外部API连接
        try:
            api_result = self.external_api_handler.test_connection()
            results['external_api'] = api_result['status']
        except Exception as e:
            results['external_api'] = f"error: {str(e)}"
        
        # 测试NL2SQL连接
        try:
            if self.vanna_service:
                # 简单测试查询
                test_result = self.vanna_service.ask_and_run("测试查询")
                results['nl2sql'] = 'success' if test_result else 'error'
            else:
                results['nl2sql'] = 'not_initialized'
        except Exception as e:
            results['nl2sql'] = f"error: {str(e)}"
        
        return {
            "status": "success",
            "response_type": "message",
            "payload": {
                "format": "text",
                "value": f"处理器测试结果: {results}"
            },
            "debug_info": {
                "execution_path": "UQP_ROUTER",
                "test_results": results
            }
        }

@uqp_blueprint.route('/query', methods=['POST'])
def handle_query():
    """UQP统一查询接口"""
    router = get_uqp_router()
    request_data = request.json
    response_data = router.route_query(request_data)
    return jsonify(response_data)

@uqp_blueprint.route('/status', methods=['GET'])
def handle_status():
    """获取UQP路由器状态接口"""
    router = get_uqp_router()
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "vanna_service_initialized": router.vanna_service is not None
    })