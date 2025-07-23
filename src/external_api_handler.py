#!/usr/bin/env python3
"""
外部API处理器 - 广东省站点数据接口集成
External API Handler for Guangdong Province Station Data
"""
import requests
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import time
from flask import Blueprint, jsonify, current_app, request
import os
import yaml
import re

from .utils.external_api_config_loader import (
    get_external_api_config, 
    get_external_api_mock_data, 
    is_test_mode
)
from .api_registry import EXTERNAL_API_TOOLS
from .utils.param_converter import get_param_converter
from .routing.tool_selector import get_tool_selector
from .utils.parameter_deduplicator import get_parameter_deduplicator
from .intelligence.error_classifier import get_error_classifier
from .intelligence.llm_error_recovery import get_llm_error_recovery
from .intelligence.enhanced_param_extractor import get_enhanced_param_extractor
from .intelligence.smart_tool_reselection import get_smart_tool_reselection
from .intelligence.sql_fallback_handler import get_sql_fallback_handler
from .intelligence.error_monitoring_system import get_error_monitoring_system
from .intelligence.unified_llm_fallback_manager import get_unified_llm_fallback_manager
from .intelligence.api_error_classifier import get_api_error_classifier
from .utils.prompt_loader import get_prompt

# 1. 创建蓝图实例
external_api_blueprint = Blueprint('external_api', __name__)

# 全局的处理器实例
external_api_handler_instance = None

def get_external_api_handler():
    """获取外部API处理器单例"""
    global external_api_handler_instance
    if external_api_handler_instance is None:
        external_api_handler_instance = ExternalAPIHandler()
    return external_api_handler_instance

def initialize_external_api_handler():
    """
    初始化外部API处理器模块。
    这个函数在应用工厂中被调用。
    """
    global external_api_handler_instance
    if external_api_handler_instance is None:
        external_api_handler_instance = ExternalAPIHandler()
        current_app.logger.info("ExternalAPIHandler instance created and initialized.")

class ExternalAPIHandler:
    """
    广东省站点数据接口代理处理器
    处理与外部API的交互，并转换为UQP格式
    """
    
    def __init__(self, vanna_service=None):
        self.vanna_service = vanna_service
        self.logger = logging.getLogger(__name__)
        
        # 加载外部API配置
        config = get_external_api_config()
        self.base_url = config["base_url"]
        self.sys_code = config["sys_code"]
        self.username = config["username"]
        self.password = config["password"]
        self.api_endpoints = config["endpoints"]
        self.timeout = config["timeout"]
        self.token_cache_time = config["token_cache_time"]
        self.test_mode = is_test_mode()
        
        # 初始化token相关属性
        self.token = None
        self.token_expires_at = None
        
        # 意图到API的映射
        self.intent_to_api = {
            'station_info': 'stations',
            'detection_items': 'detection_items',
            'instruments': 'instruments',
            'station_data': 'station_data',
            'summary_report': 'summary_report',
            'comparison_report': 'comparison_report'
        }
        
        # 加载配置
        self._load_configs()
        
        # 初始化统一兜底管理器和错误分类器
        self.fallback_manager = get_unified_llm_fallback_manager()
        self.error_classifier = get_api_error_classifier()
        
        # 工具选择模式统计
        self.mode_stats = {
            'keyword_matching_success': 0,
            'keyword_matching_failed': 0,
            'llm_analysis_success': 0,
            'llm_analysis_failed': 0,
            'auto_upgrade_count': 0,
            'auto_downgrade_count': 0
        }
    
    def _determine_time_type_from_query(self, question: str) -> int:
        """根据用户查询智能选择TimeType
        
        Args:
            question (str): 用户查询问题
            
        Returns:
            int: TimeType值 (3=周报, 4=月报, 5=季报, 7=年报, 8=任意时间)
        """
        if not question:
            return 8  # 默认任意时间
        
        # 检查是否包含报表类型关键词
        if re.search(r'周报|每周报|周[度期]报', question, re.IGNORECASE):
            self.logger.info(f"[TIME_TYPE] 检测到周报需求，设置TimeType=3")
            return 3  # 周报
        elif re.search(r'月报|每月报|月[度期]报', question, re.IGNORECASE):
            self.logger.info(f"[TIME_TYPE] 检测到月报需求，设置TimeType=4")
            return 4  # 月报
        elif re.search(r'季报|每季报|季[度期]报', question, re.IGNORECASE):
            self.logger.info(f"[TIME_TYPE] 检测到季报需求，设置TimeType=5")
            return 5  # 季报
        elif re.search(r'年报|每年报|年[度期]报', question, re.IGNORECASE):
            self.logger.info(f"[TIME_TYPE] 检测到年报需求，设置TimeType=7")
            return 7  # 年报
        else:
            # 默认任意时间，适用于大多数查询
            return 8
    
    def _get_fallback_time_type(self, original_time_type: int, error_message: str = "") -> int:
        """获取TimeType的兼容性回退值
        
        Args:
            original_time_type (int): 原始TimeType值
            error_message (str): 错误信息
            
        Returns:
            int: 回退的TimeType值，优先使用8（任意时间）
        """
        if original_time_type == 8:
            # 已经是最兼容的值，无需回退
            return 8
        
        self.logger.warning(f"[TIME_TYPE_FALLBACK] TimeType={original_time_type}可能不被支持，回退到TimeType=8（任意时间）")
        if error_message:
            self.logger.debug(f"[TIME_TYPE_FALLBACK] 错误信息: {error_message}")
        
        return 8  # 回退到任意时间

    def _load_configs(self):
        """加载配置文件"""
        try:
            # 加载主配置文件
            config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 加载LLM配置
            self.llm_config = config.get('llm', {})
            
            # 加载外部API配置
            self.external_api_config = config.get('external_api', {
                'primary_mode': 'keyword_matching',
                'fallback_mode': 'llm_analysis',
                'auto_upgrade_enabled': True,
                'auto_downgrade_enabled': False,
                'keyword_failure_conditions': [
                    'no_tool_matched',
                    'parameter_extraction_failed',
                    'ambiguous_results',
                    'time_precision_insufficient'
                ],
                'llm_timeout': 10,
                'retry_attempts': 2,
                'force_mode': None
            })
            
            self.logger.info(f"[API_TRACE] 配置加载完成")
            self.logger.info(f"[API_TRACE] 主模式: {self.external_api_config['primary_mode']}")
            self.logger.info(f"[API_TRACE] 降级模式: {self.external_api_config['fallback_mode']}")
            self.logger.info(f"[API_TRACE] 自动升级: {self.external_api_config['auto_upgrade_enabled']}")
            
        except Exception as e:
            self.logger.error(f"[API_TRACE] 配置加载失败: {e}")
            # 使用默认配置
            self.llm_config = {}
            self.external_api_config = {
                'primary_mode': 'keyword_matching',
                'fallback_mode': 'llm_analysis',
                'auto_upgrade_enabled': True,
                'auto_downgrade_enabled': False,
                'force_mode': None
            }
    
    def _get_token(self) -> str:
        """
        获取API访问token，实现智能缓存和自动续期
        """
        # 检查token是否还有效（提前5分钟刷新，避免临界时刻失效）
        buffer_time = 5 * 60  # 5分钟缓冲
        if (self.token and self.token_expires_at and 
            time.time() < (self.token_expires_at - buffer_time)):
            self.logger.debug("使用缓存的Token")
            return self.token
        
        # Token无效或即将过期，重新获取
        self.logger.info("Token无效或即将过期，重新获取")
        return self._fetch_new_token()
    
    def _fetch_new_token(self) -> str:
        """
        获取新的Token，支持重试机制
        """
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                # 构建获取token的URL
                token_url = f"{self.base_url}{self.api_endpoints['token']}"
                params = {
                    'UserName': self.username,
                    'Pwd': self.password
                }
                
                self.logger.info(f"获取新Token (尝试 {attempt + 1}/{max_retries})")
                
                response = requests.get(token_url, params=params, timeout=self.timeout)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        self.token = data.get('result')
                        self.token_expires_at = time.time() + self.token_cache_time
                        self.logger.info("成功获取新Token")
                        return self.token
                    else:
                        raise Exception(f"API返回失败: {data.get('msg', 'Unknown error')}")
                else:
                    raise Exception(f"HTTP错误: {response.status_code}")
                    
            except Exception as e:
                self.logger.warning(f"获取Token失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    self.logger.error(f"获取Token失败，已重试{max_retries}次: {e}")
                    raise
    
    def _call_unified_llm_processor(self, question: str, processing_mode: str, 
                                   geo_info: Dict = None, existing_params: Dict = None, 
                                   error_info: str = "") -> Dict[str, Any]:
        """
        统一的LLM处理器调用方法
        
        Args:
            question: 用户查询
            processing_mode: 处理模式 (initial_extraction, parameter_supplement, error_recovery, contrast_time_analysis)
            geo_info: 智能地理位置提取器的结果
            existing_params: 现有参数
            error_info: 错误信息
            
        Returns:
            统一格式的处理结果
        """
        try:
            from datetime import datetime
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 构建统一提示词
            prompt = get_prompt(
                'external_api_handler',
                'unified_api_processor',
                current_time=current_time,
                question=question,
                processing_mode=processing_mode,
                geo_info=geo_info or {},
                existing_params=existing_params or {},
                error_info=error_info
            )
            
            # 调用LLM
            vanna = self._get_vanna_service()
            if not vanna:
                return {
                    'status': 'error',
                    'reason': 'LLM服务不可用'
                }
            
            # 获取LLM响应
            response = vanna._call_llm_for_analysis(prompt)
            self.logger.debug(f"[UNIFIED_LLM] 原始响应: {response}")
            
            # 解析LLM响应
            result = self._parse_llm_judgment_response(response)
            self.logger.debug(f"[UNIFIED_LLM] 解析结果: {result}")
            
            # 统一格式处理
            if result.get('action') == 'success':
                return {
                    'status': 'success',
                    'tool_name': result.get('tool_name'),
                    'parameters': result.get('parameters'),
                    'reason': result.get('reason', ''),
                    'processing_mode': processing_mode
                }
            elif result.get('action') == 'route_to_sql':
                return {
                    'status': 'route_to_sql',
                    'reason': result.get('reason', 'LLM建议转向SQL查询'),
                    'processing_mode': processing_mode
                }
            else:
                # 兼容旧格式
                if result.get('action') == 'supplement':
                    return {
                        'status': 'success',
                        'tool_name': existing_params.get('tool_name', 'get_summary_report'),
                        'parameters': result.get('supplemented_params', {}),
                        'reason': result.get('reason', ''),
                        'processing_mode': processing_mode
                    }
                else:
                    return {
                        'status': 'error',
                        'reason': f'LLM返回了未知的action: {result.get("action")}',
                        'processing_mode': processing_mode
                    }
                    
        except Exception as e:
            self.logger.error(f"[UNIFIED_LLM] 统一LLM处理器调用失败: {e}")
            return {
                'status': 'error',
                'reason': f'LLM调用异常: {str(e)}',
                'processing_mode': processing_mode
            }

    def handle_external_api_query(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        统一的外部API查询处理器 - 集成统一LLM兜底机制和复杂性检测
        
        新的统一架构：
        1. 地理位置提取和分组
        2. 工具选择和时间参数提取  
        3. 复杂性检测（基于完整上下文）
        4. 统一参数验证和LLM兜底
        5. 多层级参数转换
        6. 多层级API调用和错误恢复
        7. 结果合并和验证
        
        Args:
            request_data: 包含用户查询的请求数据
            
        Returns:
            Dict[str, Any]: 统一格式的响应结果
        """
        question = request_data.get('question', '')
        
        try:
            self.logger.info(f"[UNIFIED_API] 开始统一API处理: {question}")
            
            # 1. 地理位置提取和智能分组
            grouped_locations = self._extract_and_group_locations(question)
            if not grouped_locations:
                self.logger.warning("[UNIFIED_API] 未提取到有效的地理位置")
                return self._route_to_sql_query(question, "未找到有效的地理位置信息")
            
            # 2. 工具选择和时间参数提取
            tool_name = self._select_tool_for_question(question)
            
            # 为时间参数提取传递必要的上下文信息，支持LLM成功后直接API调用
            try:
                time_params = self._extract_time_params_with_unified_fallback(question, tool_name, grouped_locations)
            except Exception as e:
                # 捕获SuccessfulAPIResponse异常，直接返回API结果
                if hasattr(e, 'result'):
                    self.logger.info("[UNIFIED_API] LLM时间解析成功，直接返回API调用结果")
                    return e.result
                else:
                    # 其他异常继续抛出
                    raise
            
            # 3. 复杂性检测（基于完整上下文）
            complexity_result = self._detect_query_complexity_with_context(question, grouped_locations, time_params, tool_name)
            if complexity_result['is_complex']:
                self.logger.info(f"[COMPLEXITY_DETECT] 检测到复杂查询，尝试LLM托底处理")
                
                # 尝试LLM托底处理复杂查询
                fallback_result = self.fallback_manager.handle_fallback(
                    fallback_type='complex_query_processing',
                    question=question,
                    context={
                        'grouped_locations': grouped_locations,
                        'time_parameters': time_params,
                        'tool_name': tool_name,
                        'complexity_reason': complexity_result['complexity_reason'],
                        'time_param_count': complexity_result.get('time_param_count', 0)
                    },
                    error_info=complexity_result['complexity_reason']
                )
                
                if fallback_result.get('status') == 'success' and fallback_result.get('action') == 'continue':
                    self.logger.info(f"[COMPLEXITY_DETECT] LLM托底生成API参数成功，使用统一解析")
                    # LLM生成了参数，使用统一解析入口处理
                    llm_params = fallback_result.get('result_data', {})
                    
                    # 使用专用的LLM托底处理器
                    from .intelligence.llm_fallback_processor import get_llm_fallback_processor
                    llm_processor = get_llm_fallback_processor()
                    
                    result = llm_processor.process_llm_fallback_result(llm_params, question, tool_name)
                    
                    if result['status'] == 'route_to_sql':
                        return self._route_to_sql_query(result['question'], result['reason'])
                    else:
                        return result
                else:
                    self.logger.info(f"[COMPLEXITY_DETECT] LLM托底处理失败，转向SQL查询")
                    return self._route_to_sql_query(question, 
                        f"复杂查询LLM托底失败: {fallback_result.get('reason', '未知原因')}")
            
            # 4. 统一参数验证和补充
            validation_result = self._unified_parameter_validation(question, tool_name, time_params, grouped_locations)
            if validation_result['status'] == 'route_to_sql':
                return self._route_to_sql_query(question, validation_result['reason'])
            elif validation_result['status'] == 'api_completed':
                # LLM托底成功完成API调用，直接返回结果
                self.logger.info("[UNIFIED_API] LLM托底API调用完成，直接返回结果")
                return validation_result['api_result']
            
            # 更新参数
            if validation_result['status'] == 'success':
                time_params = validation_result.get('updated_params', time_params)
            
            # 5. 多层级参数转换
            converted_params = self._convert_multi_level_params(grouped_locations, time_params, tool_name)
            if converted_params.get('status') == 'error':
                self.logger.error("[UNIFIED_API] 多层级参数转换失败")
                return self._route_to_sql_query(question, f"参数转换失败: {converted_params.get('errors', [])}")
            
            # 6. 执行多层级API调用（带统一错误恢复）
            return self._execute_api_calls_with_unified_recovery(converted_params, question, tool_name)
                
        except Exception as e:
            self.logger.error(f"[UNIFIED_API] 统一API处理异常: {str(e)}")
            return {
                "status": "error",
                "response_type": "message", 
                "payload": {
                    "format": "text",
                    "value": f"API处理异常: {str(e)}"
                },
                "debug_info": {
                    "execution_path": "UNIFIED_API_HANDLER",
                    "error": str(e)
                }
            }
    
    def _call_llm_for_tool_selection(self, question: str) -> Dict[str, Any]:
        """
        LLM统一工具选择和参数提取流程：
        1. 使用关键词匹配选择工具（对比报表 vs 综合报表）
        2. 调用LLM进行智能参数提取和判断
        3. 如果LLM判断无法进行API查询，则转向SQL查询
        """
        start_time = time.time()
        
        try:
            self.logger.info(f"[API_TRACE] 开始LLM统一工具选择流程 - 问题: {question}")
            
            # Step 1: 使用关键词匹配选择工具
            tool_selector = get_tool_selector()
            selection_result = tool_selector.select_tool(question)
            
            if selection_result['status'] == 'error':
                self.logger.error(f"[API_TRACE] 工具选择失败: {selection_result.get('message')}")
                return self._route_to_sql_query(question, "工具选择失败")
            
            selected_tool = selection_result['selected_tool']
            self.logger.info(f"[API_TRACE] 选择的工具: {selected_tool}")
            
            # Step 2: 使用传统参数提取，失败后才使用LLM托底
            llm_result = self._call_llm_for_unified_extraction(question, selected_tool)
            
            # Step 3: 处理传统提取结果
            if llm_result.get('action') == 'route_to_sql':
                self.logger.info(f"[API_TRACE] 传统提取建议转向SQL查询: {llm_result.get('reason')}")
                return self._route_to_sql_query(question, llm_result.get('reason', '参数提取失败'))
            
            # Step 4: 传统方法成功提取参数，继续API调用
            if llm_result.get('status') == 'success':
                total_time = time.time() - start_time
                self.logger.info(f"[API_TRACE] 传统参数提取完成，总耗时: {total_time:.4f}s")
                
                return {
                    "status": "success",
                    "tool_name": selected_tool,
                    "tool_params": llm_result.get('tool_params', {}),
                    "original_question": question,
                    "selection_info": {
                        "method": "traditional_with_llm_fallback",
                        "matched_keywords": selection_result.get('matched_keywords', []),
                        "confidence": 1.0,
                        "selection_time": selection_result.get('selection_time', 0),
                        "total_time": total_time
                    }
                }
            else:
                # 传统方法提取失败，转向SQL查询
                reason = llm_result.get('reason', '传统参数提取失败')
                self.logger.warning(f"[API_TRACE] 传统方法提取失败: {reason}")
                return self._route_to_sql_query(question, reason)
                
        except Exception as e:
            self.logger.error(f"[API_TRACE] 传统参数提取流程异常: {e}")
            return self._route_to_sql_query(question, f"流程异常: {str(e)}")
    
    def _call_llm_for_unified_extraction(self, question: str, selected_tool: str) -> Dict[str, Any]:
        """
        使用现有参数提取器进行参数提取，然后LLM判断是否足够
        
        Args:
            question: 用户问题
            selected_tool: 已选择的工具名称
            
        Returns:
            LLM判断结果
        """
        try:
            self.logger.info(f"[API_TRACE] 开始LLM统一参数提取，工具: {selected_tool}")
            
            # 使用现有的参数提取器
            from .utils.param_extractor import get_param_extractor
            param_extractor = get_param_extractor()
            
            # 获取工具定义
            tool_selector = get_tool_selector()
            tool_info = tool_selector.get_tool_info(selected_tool)
            
            # 构建工具定义（用于参数提取）
            tool_def = {
                "function": {
                    "name": selected_tool,
                    "description": tool_info.get('description', ''),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "locations": {"type": "array", "items": {"type": "string"}},
                            "time_description": {"type": "string"},
                            "comparison_time_description": {"type": "string"},
                            "area_type": {"type": "string"},
                            "data_source": {"type": "string"}
                        },
                        "required": ["locations", "time_description", "area_type"]
                    }
                }
            }
            
            # 提取参数
            extracted_params = param_extractor.extract_tool_params(question, tool_def)
            
            # 检查参数是否足够
            if self._are_params_sufficient(extracted_params, selected_tool):
                self.logger.info(f"[API_TRACE] 参数提取成功: {extracted_params}")
                
                return {
                    "status": "success",
                    "tool_params": extracted_params
                }
            else:
                # 参数不足，使用LLM进行智能补充（特别是时间参数和工具重选择）
                self.logger.info(f"[API_TRACE] 参数不足，启用LLM智能补充")
                llm_judgment = self._llm_judge_params(question, extracted_params, selected_tool)
                
                # 检查LLM判断结果
                if llm_judgment.get('status') == 'success':
                    # LLM成功补充了参数
                    return {
                        "status": "success",
                        "tool_params": llm_judgment.get('tool_params', extracted_params)
                    }
                else:
                    # LLM建议转向SQL查询或工具重选择
                    return {
                        "status": "route_to_sql",
                        "reason": llm_judgment.get('reason', '参数不足，LLM建议转向SQL查询')
                    }
            
        except Exception as e:
            self.logger.error(f"[API_TRACE] LLM统一参数提取失败: {e}")
            return {
                "status": "error",
                "action": "route_to_sql",
                "reason": f"参数提取失败: {str(e)}"
            }
    
    def _are_params_sufficient(self, params: Dict[str, Any], tool_name: str) -> bool:
        """检查参数是否足够进行API调用"""
        # 检查必要参数
        required_params = ['locations', 'time_description', 'area_type']
        if tool_name == 'get_comparison_report':
            required_params.append('comparison_time_description')
        
        for param in required_params:
            if param not in params or not params[param]:
                return False
        
        # 检查地理位置是否有效
        locations = params.get('locations', [])
        if not locations or (isinstance(locations, list) and len(locations) == 0):
            return False
        
        return True
    
    def _llm_handle_conversion_failure(self, question: str, failure_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        LLM处理参数转换失败 - 使用统一LLM处理器智能修复参数问题
        
        Args:
            question: 用户问题
            failure_context: 失败上下文信息
            
        Returns:
            Dict[str, Any]: LLM修复结果
        """
        try:
            # 获取失败上下文信息
            original_params = failure_context.get('original_params', {})
            errors = failure_context.get('errors', [])
            clarifications = failure_context.get('clarifications', [])
            tool_name = failure_context.get('tool_name', '')
            
            # 构建积极的指导信息
            error_info_parts = []
            if errors:
                # 将消极的错误描述转换为积极的指导信息
                positive_guidance = []
                for error in errors:
                    if "无法解析的时间描述" in error:
                        positive_guidance.append("传统提取无法解析的时间描述，请发挥你的推理能力解析API查询所需的时间参数")
                    elif "地理位置" in error:
                        positive_guidance.append("传统提取遇到地理位置问题，请基于上下文智能推理正确的地理位置参数")
                    else:
                        positive_guidance.append("传统参数提取遇到困难，请重新分析用户问题并智能推理所需参数")
                
                if positive_guidance:
                    error_info_parts.extend(positive_guidance)
            
            # 不包含澄清信息，直接让LLM发挥推理能力
            error_info = "; ".join(error_info_parts) if error_info_parts else "请重新分析用户问题并智能推理API查询所需的参数"
            
            # 获取智能地理位置信息（如果可用）
            geo_info = {}
            try:
                from .utils.smart_geo_extractor import get_smart_geo_extractor
                smart_geo_extractor = get_smart_geo_extractor()
                geo_results = smart_geo_extractor.extract_locations(question)
                if geo_results:
                    geo_info = []
                    for location in geo_results:
                        location_details = smart_geo_extractor._find_location_info(location)
                        if location_details:
                            geo_info.append({
                                'name': location,
                                'type': location_details.get('type', 'unknown'),
                                'code': location_details.get('code', ''),
                                'source': 'smart_geo_extractor'
                            })
            except Exception as e:
                self.logger.warning(f"[UNIFIED_LLM] 参数转换失败修复时获取地理信息失败: {e}")
                geo_info = {}
            
            # 准备现有参数，包含工具名称
            existing_params_with_tool = original_params.copy()
            existing_params_with_tool['tool_name'] = tool_name
            
            # 调用统一LLM处理器进行错误恢复
            result = self._call_unified_llm_processor(
                question=question,
                processing_mode='error_recovery',
                geo_info=geo_info,
                existing_params=existing_params_with_tool,
                error_info=error_info
            )
            
            # 处理统一LLM处理器的结果
            if result.get('status') == 'success':
                self.logger.info(f"[API_TRACE] LLM修复参数成功: {result.get('parameters', {})}")
                return {
                    "status": "success",
                    "tool_params": result.get('parameters', original_params)
                }
            else:
                return {
                    "status": "route_to_sql",
                    "reason": result.get('reason', '无法修复参数问题')
                }
                
        except Exception as e:
            self.logger.error(f"[API_TRACE] 参数转换失败处理异常: {e}")
            return {"status": "route_to_sql", "reason": f"参数修复异常: {str(e)}"}
    
    def _llm_supplement_time_params(self, question: str, extracted_params: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        """
        LLM智能补充时间参数 - 使用统一LLM处理器
        """
        try:
            # 获取智能地理位置信息
            geo_info = {}
            try:
                from .utils.smart_geo_extractor import get_smart_geo_extractor
                smart_geo_extractor = get_smart_geo_extractor()
                geo_results = smart_geo_extractor.extract_locations(question)
                if geo_results:
                    geo_info = []
                    for location in geo_results:
                        location_details = smart_geo_extractor._find_location_info(location)
                        if location_details:
                            geo_info.append({
                                'name': location,
                                'type': location_details.get('type', 'unknown'),
                                'code': location_details.get('code', ''),
                                'source': 'smart_geo_extractor'
                            })
            except Exception as e:
                self.logger.warning(f"[UNIFIED_LLM] 时间补充时获取地理信息失败: {e}")
                geo_info = {}
            
            # 准备现有参数，包含工具名称
            existing_params_with_tool = extracted_params.copy()
            existing_params_with_tool['tool_name'] = tool_name
            
            # 调用统一LLM处理器进行时间参数补充
            result = self._call_unified_llm_processor(
                question=question,
                processing_mode='parameter_supplement',
                geo_info=geo_info,
                existing_params=existing_params_with_tool,
                error_info="缺少时间参数"
            )
            
            # 处理统一LLM处理器的结果
            if result.get('status') == 'success':
                self.logger.info(f"[API_TRACE] LLM智能补充时间参数成功: {result.get('parameters', {})}")
                return {
                    "status": "success",
                    "tool_params": result.get('parameters', extracted_params)
                }
            else:
                return {
                    "status": "route_to_sql",
                    "reason": result.get('reason', '无法智能推断时间参数')
                }
                
        except Exception as e:
            self.logger.error(f"[API_TRACE] 时间参数补充失败: {e}")
            return {"status": "route_to_sql", "reason": f"时间参数补充异常: {str(e)}"}
    
    def _llm_consider_tool_reselection(self, question: str, extracted_params: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        """
        LLM考虑工具重选择 - 当缺少地理位置时
        """
        try:
            prompt = get_prompt(
                'external_api_handler',
                'tool_reselection',
                question=question,
                current_tool=tool_name,
                extracted_params=extracted_params
            )
            
            # 调用LLM
            response = self._call_vanna_llm_analysis(prompt)
            
            if not response:
                return {"status": "route_to_sql", "reason": "LLM调用失败"}
            
            # 解析LLM响应
            result = self._parse_llm_judgment_response(response)
            
            if result.get('action') == 'keep_api':
                # 保持API工具，但可能需要特殊处理
                self.logger.info(f"[API_TRACE] LLM建议保持API工具: {result.get('reason')}")
                return {
                    "status": "success",
                    "tool_params": extracted_params  # 使用原参数，后续会有默认值处理
                }
            else:
                return {
                    "status": "route_to_sql",
                    "reason": result.get('reason', 'LLM建议转向SQL查询')
                }
                
        except Exception as e:
            self.logger.error(f"[API_TRACE] 工具重选择分析失败: {e}")
            return {"status": "route_to_sql", "reason": f"工具选择分析异常: {str(e)}"}
    
    def _call_vanna_llm_analysis(self, prompt: str) -> str:
        """
        调用Vanna服务的LLM分析功能
        """
        try:
            if hasattr(self, 'vanna_service') and self.vanna_service:
                return self.vanna_service._call_llm_for_analysis(prompt)
            else:
                self.logger.warning("[API_TRACE] Vanna服务不可用")
                return None
        except Exception as e:
            self.logger.error(f"[API_TRACE] Vanna LLM调用失败: {e}")
            return None
    
    def _parse_llm_judgment_response(self, response: str) -> Dict[str, Any]:
        """
        解析LLM判断响应
        """
        try:
            import json
            import re
            
            # 尝试提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                # 如果没有找到JSON，返回默认响应
                return {"action": "route_to_sql", "reason": "LLM响应格式无效"}
                
        except json.JSONDecodeError as e:
            self.logger.error(f"[API_TRACE] LLM响应JSON解析失败: {e}")
            return {"action": "route_to_sql", "reason": f"JSON解析失败: {str(e)}"}
    
    def _call_llm_for_direct_param_extraction(self, question: str, selected_tool: str) -> Dict[str, Any]:
        """
        直接调用LLM进行完整的参数提取，充分利用api_tool_use_prompt.txt的指导
        
        Args:
            question: 用户问题
            selected_tool: 选择的工具名称
            
        Returns:
            Dict[str, Any]: LLM提取结果
        """
        try:
            from datetime import datetime
            import os
            
            # 读取API工具使用提示词模板
            prompt_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'external_api_prompts.yaml')
            
            if os.path.exists(prompt_file):
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    prompt_template = config['api_tool_selection_main']
            else:
                self.logger.error(f"[LLM_EXTRACT] 找不到提示词文件: {prompt_file}")
                return {"status": "error", "reason": "提示词文件缺失"}
            
            # 获取当前系统时间信息
            now = datetime.now()
            current_time = now.strftime('%Y-%m-%d %H:%M:%S')
            current_date = now.strftime('%Y-%m-%d')
            current_year = now.strftime('%Y')
            current_month = now.strftime('%m')
            
            # 替换提示词模板中的时间占位符
            prompt = prompt_template.format(
                current_time=current_time,
                current_date=current_date,
                current_year=current_year,
                current_month=current_month
            )
            
            # 构建LLM请求消息
            user_prompt = f"""
根据用户查询，请智能提取并优化参数，直接输出符合API接口要求的完整参数。

用户查询: "{question}"
目标工具: {selected_tool}

请严格按照提示词指导，直接输出完整的工具调用JSON格式，确保：
1. locations必须是单个元素的数组（选择最精确的位置）
2. time_point必须是API格式的时间数组 ["YYYY-MM-DD 00:00:00", "YYYY-MM-DD 23:59:59"]
3. 对于对比查询，contrast_time也必须是API格式的时间数组
4. area_type根据位置类型智能判断
5. data_source默认使用"审核实况"

输出格式：
{{
  "tool_name": "{selected_tool}",
  "parameters": {{
    "locations": ["具体位置名称"],
    "time_point": ["YYYY-MM-DD 00:00:00", "YYYY-MM-DD 23:59:59"],
    "contrast_time": ["YYYY-MM-DD 00:00:00", "YYYY-MM-DD 23:59:59"],  // 仅对比查询需要
    "area_type": "站点/区县/城市",
    "data_source": "审核实况"
  }}
}}

如果无法确定关键信息，请返回：
{{
  "action": "route_to_sql",
  "reason": "具体原因"
}}
"""
            
            # 组合完整的提示
            full_prompt = prompt + "\n\n" + user_prompt
            
            # 调用LLM
            response = self.vanna_service.call_llm_analysis(full_prompt)
            
            if not response:
                return {"status": "error", "reason": "LLM调用失败"}
            
            # 解析LLM响应
            import json
            import re
            
            # 尝试提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    
                    if result.get('action') == 'route_to_sql':
                        return {
                            "status": "route_to_sql", 
                            "reason": result.get('reason', 'LLM建议使用SQL查询')
                        }
                    elif 'parameters' in result:
                        # 转换参数格式以匹配现有API接口
                        params = result['parameters']
                        
                        # 确保locations是列表格式
                        if isinstance(params.get('locations'), str):
                            params['locations'] = [params['locations']]
                        
                        return {
                            "status": "success",
                            "tool_params": params
                        }
                    else:
                        return {"status": "error", "reason": "LLM响应格式错误"}
                        
                except json.JSONDecodeError as e:
                    self.logger.error(f"[LLM_EXTRACT] JSON解析失败: {e}")
                    return {"status": "error", "reason": f"JSON解析失败: {str(e)}"}
            else:
                self.logger.error(f"[LLM_EXTRACT] 未找到有效JSON响应: {response}")
                return {"status": "error", "reason": "LLM响应格式无效"}
                
        except Exception as e:
            self.logger.error(f"[LLM_EXTRACT] 直接参数提取失败: {e}")
            return {"status": "error", "reason": f"参数提取异常: {str(e)}"}
    
    def _llm_judge_params(self, question: str, extracted_params: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        """使用统一LLM处理器判断是否可以智能补充参数或需要转向SQL"""
        try:
            self.logger.info(f"[API_TRACE] 参数不足，启用LLM智能判断")
            
            # 获取智能地理位置提取器的结果（如果可用）
            geo_info = {}
            try:
                from .utils.smart_geo_extractor import get_smart_geo_extractor
                smart_geo_extractor = get_smart_geo_extractor()
                geo_results = smart_geo_extractor.extract_locations(question)
                if geo_results:
                    # 构建详细的地理信息
                    geo_info = []
                    for location in geo_results:
                        # 查询详细信息
                        location_details = smart_geo_extractor._find_location_info(location)
                        if location_details:
                            geo_info.append({
                                'name': location,
                                'type': location_details.get('type', 'unknown'),
                                'code': location_details.get('code', ''),
                                'source': 'smart_geo_extractor'
                            })
                    self.logger.debug(f"[UNIFIED_LLM] 获取到地理信息: {geo_info}")
            except Exception as e:
                self.logger.warning(f"[UNIFIED_LLM] 获取地理信息失败: {e}")
                geo_info = {}
            
            # 准备现有参数，包含工具名称
            existing_params_with_tool = extracted_params.copy()
            existing_params_with_tool['tool_name'] = tool_name
            
            # 调用统一LLM处理器
            result = self._call_unified_llm_processor(
                question=question,
                processing_mode='parameter_supplement',
                geo_info=geo_info,
                existing_params=existing_params_with_tool,
                error_info=""
            )
            
            # 处理统一LLM处理器的结果
            if result.get('status') == 'success':
                self.logger.info(f"[API_TRACE] LLM智能补充参数成功: {result.get('parameters', {})}")
                return {
                    "status": "success",
                    "tool_params": result.get('parameters', extracted_params)
                }
            elif result.get('status') == 'route_to_sql':
                self.logger.info(f"[API_TRACE] LLM建议转向SQL查询: {result.get('reason', '参数不足')}")
                return {
                    "action": "route_to_sql",
                    "reason": result.get('reason', '参数不足，建议使用SQL查询')
                }
            else:
                # LLM处理失败，降级到简单规则判断
                self.logger.warning(f"[API_TRACE] 统一LLM处理器失败: {result.get('reason', '未知错误')}")
                # 分析缺失的参数（用于降级处理）
                missing_params = []
                if not extracted_params.get('locations'):
                    missing_params.append('地理位置')
                if not extracted_params.get('time_description'):
                    missing_params.append('时间描述')
                if tool_name == 'get_comparison_report' and not extracted_params.get('comparison_time_description'):
                    missing_params.append('对比时间')
                
                return self._simple_param_judgment(extracted_params, missing_params, tool_name)
            
        except Exception as e:
            self.logger.error(f"[API_TRACE] LLM参数判断失败: {e}")
            return {
                "action": "route_to_sql",
                "reason": f"参数判断失败: {str(e)}"
            }
    
    def _simple_param_judgment(self, extracted_params: Dict[str, Any], missing_params: List[str], tool_name: str) -> Dict[str, Any]:
        """简单的参数判断规则（LLM不可用时的降级方案）"""
        # 完全没有地理位置，无法进行API查询
        if '地理位置' in missing_params:
            return {
                "action": "route_to_sql",
                "reason": "缺少地理位置信息，无法进行API查询"
            }
        
        # 只缺少时间信息，可以智能补充
        if missing_params == ['时间描述']:
            self.logger.info(f"[API_TRACE] 智能补充时间信息为'今天'")
            extracted_params['time_description'] = '今天'
            return {
                "status": "success",
                "tool_params": extracted_params
            }
        
        # 对比查询缺少对比时间，可以智能补充
        if missing_params == ['对比时间']:
            # 根据主时间智能推断对比时间
            main_time = extracted_params.get('time_description', '')
            comparison_time = self._infer_comparison_time(main_time)
            
            self.logger.info(f"[API_TRACE] 智能补充对比时间: {main_time} -> {comparison_time}")
            extracted_params['comparison_time_description'] = comparison_time
            return {
                "status": "success",
                "tool_params": extracted_params
            }
        
        # 其他情况转向SQL查询
        return {
            "action": "route_to_sql",
            "reason": f"缺少必要参数: {', '.join(missing_params)}"
        }
    
    def _infer_comparison_time(self, main_time: str) -> str:
        """根据主时间智能推断对比时间"""
        import re
        from datetime import datetime
        
        # 提取年月信息
        if re.match(r'\d{4}年\d{1,2}月', main_time):
            match = re.match(r'(\d{4})年(\d{1,2})月', main_time)
            if match:
                year = int(match.group(1))
                month = int(match.group(2))
                # 生成去年同期
                last_year_same_period = f"{year-1}年{month}月"
                return last_year_same_period
        
        # 提取年份信息
        elif re.match(r'\d{4}年', main_time):
            match = re.match(r'(\d{4})年', main_time)
            if match:
                year = int(match.group(1))
                return f"{year-1}年"
        
        # 相对时间推断
        elif main_time in ["今年", "this year"]:
            return "去年"
        elif main_time in ["这个月", "this month"]:
            return "上月"
        elif main_time in ["本周", "this week"]:
            return "上周"
        elif main_time in ["本季度", "this quarter"]:
            return "上季度"
        else:
            # 默认返回去年同期
            return "去年同期"
    
    def _parse_llm_judgment_response(self, response: str) -> Dict[str, Any]:
        """解析LLM判断响应"""
        try:
            import json
            
            # 尝试提取JSON内容
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                # 如果没有找到JSON，尝试整个响应解析
                return json.loads(response)
                
        except json.JSONDecodeError as e:
            self.logger.error(f"[API_TRACE] LLM判断响应解析失败: {e}")
            self.logger.debug(f"[API_TRACE] 原始响应: {response}")
            
            # 返回默认的转向SQL响应
            return {
                "action": "route_to_sql",
                "reason": "LLM响应解析失败，建议使用SQL查询"
            }
    
    
    def _route_to_sql_query(self, question: str, reason: str) -> Dict[str, Any]:
        """转向SQL查询的响应"""
        self.logger.info(f"[API_TRACE] 转向SQL查询 - 问题: {question}, 原因: {reason}")
        
        return {
            "status": "route_to_sql",
            "original_question": question,
            "reason": reason,
            "message": f"API查询参数不足，建议使用探索性查询（SQL查询）获取相关信息。原因：{reason}",
            "suggestion": "您可以尝试使用更具体的查询，或者让系统进行数据探索分析。"
        }

    def _parse_parameters_unified(self, params_source: Any, question: str) -> Dict[str, Any]:
        """
        统一参数解析入口 - 处理LLM输出和传统提取的参数
        
        Args:
            params_source: LLM生成的参数dict 或 传统提取的参数
            question: 原始用户问题
        
        Returns:
            解析后的标准API参数
        """
        try:
            if isinstance(params_source, dict) and 'locations' in params_source:
                # LLM生成的新格式参数 - 需要解析地理位置名称
                self.logger.info(f"[UNIFIED_PARSE] 解析LLM新格式参数")
                return self._parse_llm_generated_params(params_source, question)
            elif isinstance(params_source, dict) and 'StationCode' in params_source:
                # LLM生成的旧格式参数 - 直接使用（兼容性）
                self.logger.info(f"[UNIFIED_PARSE] 使用LLM旧格式参数（兼容）")
                return params_source
            else:
                # 传统提取的参数 - 使用现有解析流程
                self.logger.info(f"[UNIFIED_PARSE] 使用传统参数解析流程")
                return self._parse_traditional_params(params_source, question)
                
        except Exception as e:
            self.logger.error(f"[UNIFIED_PARSE] 统一参数解析失败: {e}")
            raise
    
    def _parse_llm_generated_params(self, llm_params: Dict[str, Any], question: str) -> Dict[str, Any]:
        """解析LLM生成的新格式参数"""
        try:
            self.logger.info(f"[LLM_PARSE] 开始解析LLM参数: {llm_params}")
            
            # 双格式兼容适配
            adapted_params = dict(llm_params)
            
            # 格式兼容1：中间格式 -> API格式
            if 'time_description' in adapted_params and 'TimePoint' not in adapted_params:
                adapted_params['TimePoint'] = adapted_params['time_description']
                self.logger.info(f"[DUAL_FORMAT] 兼容中间格式: time_description -> TimePoint")
                
            if 'comparison_time_description' in adapted_params and 'ContrastTime' not in adapted_params:
                adapted_params['ContrastTime'] = adapted_params['comparison_time_description']
                self.logger.info(f"[DUAL_FORMAT] 兼容中间格式: comparison_time_description -> ContrastTime")
            
            # 1. 时间参数直接使用（LLM已格式化）
            time_point = adapted_params.get('TimePoint')
            contrast_time = adapted_params.get('ContrastTime') 
            
            # 2. 地理位置需要通过地理信息库解析
            locations = llm_params.get('locations', [])
            area_type_str = llm_params.get('area_type', '区县')
            
            if not locations:
                raise ValueError("LLM参数缺少地理位置信息")
            
            # 调用现有的地理编码解析逻辑
            location_result = self._resolve_locations_from_names(locations, area_type_str)
            
            # 3. 智能选择TimeType：优先使用LLM指定值，否则根据查询内容智能判断
            time_type = llm_params.get('TimeType')
            if time_type is None:
                time_type = self._determine_time_type_from_query(question)
                self.logger.info(f"[LLM_PARSE] LLM未指定TimeType，根据查询智能选择: {time_type}")
            else:
                self.logger.info(f"[LLM_PARSE] 使用LLM指定的TimeType: {time_type}")
            
            # 3. 组装最终API参数
            api_params = {
                'TimePoint': time_point,
                'StationCode': location_result['codes'],
                'AreaType': location_result['area_type_code'],
                'TimeType': time_type,
                'DataSource': llm_params.get('DataSource', 1)
            }
            
            if contrast_time:
                api_params['ContrastTime'] = contrast_time
                
            self.logger.info(f"[LLM_PARSE] LLM参数解析完成: {api_params}")
            return api_params
            
        except Exception as e:
            self.logger.error(f"[LLM_PARSE] LLM参数解析失败: {e}")
            raise
    
    def _resolve_locations_from_names(self, location_names: List[str], area_type: str) -> Dict[str, Any]:
        """
        从地理位置名称解析出编码 - 复用现有逻辑
        """
        try:
            self.logger.info(f"[GEO_RESOLVE] 解析地理位置: {location_names}, 类型: {area_type}")
            
            # 复用现有的地理位置提取器
            from .utils.smart_geo_extractor import get_smart_geo_extractor
            geo_extractor = get_smart_geo_extractor()
            
            resolved_locations = []
            for name in location_names:
                # 使用现有的地理编码查表逻辑
                location_info = geo_extractor.extract_locations(name)
                if location_info:
                    resolved_locations.extend(location_info)
            
            if not resolved_locations:
                raise ValueError(f"无法解析地理位置: {location_names}")
            
            # 转换为API需要的格式
            area_type_mapping = {
                '站点': 0,
                '区县': 1, 
                '城市': 2
            }
            
            area_type_code = area_type_mapping.get(area_type, 1)
            
            # 提取编码
            codes = []
            for loc in resolved_locations:
                if area_type == '站点' and 'station_code' in loc:
                    codes.append(loc['station_code'])
                elif area_type == '区县' and 'district_code' in loc:
                    codes.append(loc['district_code'])
                elif area_type == '城市' and 'city_code' in loc:
                    codes.append(loc['city_code'])
            
            if not codes:
                # 如果没有找到对应类型的编码，使用第一个可用的编码
                for loc in resolved_locations:
                    if 'station_code' in loc:
                        codes.append(loc['station_code'])
                        area_type_code = 0
                        break
                    elif 'district_code' in loc:
                        codes.append(loc['district_code'])
                        area_type_code = 1
                        break
                    elif 'city_code' in loc:
                        codes.append(loc['city_code'])
                        area_type_code = 2
                        break
            
            result = {
                'codes': codes,
                'area_type_code': area_type_code
            }
            
            self.logger.info(f"[GEO_RESOLVE] 地理位置解析完成: {result}")
            return result
            
        except Exception as e:
            self.logger.error(f"[GEO_RESOLVE] 地理位置解析失败: {e}")
            raise
    
    def _parse_traditional_params(self, params_source: Any, question: str) -> Dict[str, Any]:
        """处理传统提取的参数 - 保持现有逻辑不变"""
        # 这里可以调用现有的参数处理逻辑
        # 目前先抛出异常，表示需要使用现有流程
        raise NotImplementedError("传统参数解析应使用现有流程")

    def _is_complete_api_params(self, llm_params: Dict[str, Any]) -> bool:
        """检查LLM生成的参数是否是完整的API参数格式"""
        try:
            # 检查是否包含API必需字段
            required_fields = ['TimePoint', 'StationCode', 'AreaType', 'TimeType', 'DataSource']
            for field in required_fields:
                if field not in llm_params:
                    self.logger.debug(f"[LLM_PARAMS] 缺少必需字段: {field}")
                    return False
            
            # 检查时间参数格式
            time_point = llm_params.get('TimePoint')
            if not isinstance(time_point, list) or len(time_point) != 2:
                self.logger.debug(f"[LLM_PARAMS] TimePoint格式不正确: {time_point}")
                return False
            
            # 检查站点编码格式
            station_code = llm_params.get('StationCode')
            if not isinstance(station_code, list) or len(station_code) == 0:
                self.logger.debug(f"[LLM_PARAMS] StationCode格式不正确: {station_code}")
                return False
            
            self.logger.info(f"[LLM_PARAMS] 检测到完整的API参数格式")
            return True
        except Exception as e:
            self.logger.error(f"[LLM_PARAMS] 参数检查异常: {e}")
            return False

    def _execute_api_call_with_llm_params(self, llm_params: Dict[str, Any], question: str, tool_name: str) -> Dict[str, Any]:
        """直接使用LLM生成的API参数执行API调用"""
        try:
            self.logger.info(f"[LLM_API] 直接使用LLM参数调用API: {tool_name}")
            
            # 获取工具信息
            tool_selector = get_tool_selector()
            tool_info = tool_selector.get_tool_info(tool_name)
            if not tool_info:
                return self._route_to_sql_query(question, f"未找到工具定义: {tool_name}")
            
            # 直接调用API
            endpoint = tool_info.get('endpoint') or tool_info.get('api_endpoint', '')
            if not endpoint:
                return self._route_to_sql_query(question, f"工具{tool_name}缺少endpoint配置")
            api_response = self._call_api_directly(endpoint, llm_params)
            
            if api_response.get('success'):
                self.logger.info("[LLM_API] API调用成功")
                return {
                    "status": "success",
                    "response_type": "data",
                    "payload": {
                        "format": "json",
                        "value": api_response['data']
                    },
                    "debug_info": {
                        "execution_path": "LLM_DIRECT_API",
                        "tool_name": tool_name,
                        "processing_method": "llm_generated_params",
                        "api_params": llm_params
                    }
                }
            else:
                # API调用失败，尝试错误恢复
                self.logger.warning(f"[LLM_API] API调用失败: {api_response.get('error')}")
                return self._handle_api_error_with_fallback(api_response, question, tool_name, llm_params)
                
        except Exception as e:
            self.logger.error(f"[LLM_API] 直接API调用异常: {e}")
            return self._route_to_sql_query(question, f"API调用异常: {str(e)}")

    def _execute_api_call_with_parsed_params(self, parsed_params: Dict[str, Any], question: str, tool_name: str, from_llm_fallback: bool = False) -> Dict[str, Any]:
        """使用已解析的标准API参数执行API调用
        
        Args:
            parsed_params: 已解析的API参数
            question: 用户问题
            tool_name: 工具名称
            from_llm_fallback: 是否来自LLM托底，如果是，失败时直接转SQL
        """
        try:
            self.logger.info(f"[PARSED_API] 使用已解析参数调用API: {tool_name}")
            self.logger.debug(f"[PARSED_API] API参数: {parsed_params}")
            
            # 获取工具信息
            tool_selector = get_tool_selector()
            tool_info = tool_selector.get_tool_info(tool_name)
            if not tool_info:
                return self._route_to_sql_query(question, f"未找到工具定义: {tool_name}")
            
            # 获取API端点
            endpoint = tool_info.get('endpoint') or tool_info.get('api_endpoint', '')
            if not endpoint:
                return self._route_to_sql_query(question, f"工具{tool_name}缺少endpoint配置")
            
            # 直接调用API
            api_response = self._call_api_directly(endpoint, parsed_params)
            
            if api_response.get('success'):
                self.logger.info("[PARSED_API] API调用成功")
                return {
                    "status": "success",
                    "response_type": "data",
                    "payload": {
                        "format": "json",
                        "value": api_response['data']
                    },
                    "debug_info": {
                        "execution_path": "PARSED_PARAMS_API",
                        "tool_name": tool_name,
                        "processing_method": "unified_parsed_params",
                        "api_params": parsed_params
                    }
                }
            else:
                # API调用失败处理
                self.logger.warning(f"[PARSED_API] API调用失败: {api_response.get('error')}")
                
                if from_llm_fallback:
                    # 来自LLM托底，失败时直接转SQL，不再错误恢复
                    self.logger.info("[PARSED_API] LLM托底后API失败，直接转SQL")
                    return self._route_to_sql_query(question, f"LLM托底后API调用失败: {api_response.get('error')}")
                else:
                    # 传统流程，尝试错误恢复
                    return self._handle_api_error_with_fallback(api_response, question, tool_name, parsed_params)
                
        except Exception as e:
            self.logger.error(f"[PARSED_API] API调用异常: {e}")
            if from_llm_fallback:
                self.logger.info("[PARSED_API] LLM托底后发生异常，直接转SQL")
            return self._route_to_sql_query(question, f"API调用异常: {str(e)}")

    def _integrate_llm_params_to_standard_flow(self, llm_params: Dict[str, Any], time_params: Dict[str, Any], grouped_locations: Dict[str, Any]) -> None:
        """将LLM参数整合到标准处理流程中"""
        try:
            self.logger.info("[LLM_INTEGRATION] 整合LLM参数到标准流程")
            
            # 将LLM的TimePoint转换为time_description格式
            if 'TimePoint' in llm_params:
                time_point = llm_params['TimePoint']
                if isinstance(time_point, list) and len(time_point) >= 2:
                    time_params['time_description'] = time_point
                    self.logger.info(f"[LLM_INTEGRATION] 整合主时间参数: {time_point}")
            
            # 将LLM的ContrastTime转换为contrast_time_description格式
            if 'ContrastTime' in llm_params:
                contrast_time = llm_params['ContrastTime']
                if isinstance(contrast_time, list) and len(contrast_time) >= 2:
                    time_params['contrast_time_description'] = contrast_time
                    self.logger.info(f"[LLM_INTEGRATION] 整合对比时间参数: {contrast_time}")
            
            # 更新地理位置信息（如果LLM提供了更好的位置信息）
            if 'StationCode' in llm_params:
                station_codes = llm_params['StationCode']
                if isinstance(station_codes, list) and len(station_codes) > 0:
                    # 创建虚拟的地理位置分组，使用LLM提供的站点编码
                    area_type = llm_params.get('AreaType', 0)
                    level_name = {0: '站点', 1: '区县', 2: '城市'}.get(area_type, '站点')
                    grouped_locations[level_name] = [f"编码_{code}" for code in station_codes]
                    self.logger.info(f"[LLM_INTEGRATION] 整合地理位置: {level_name}={grouped_locations[level_name]}")
                    
        except Exception as e:
            self.logger.error(f"[LLM_INTEGRATION] 参数整合异常: {e}")

    def _call_api_directly(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """直接调用API接口"""
        try:
            # 获取token
            token = self._get_token()
            if not token:
                return {"success": False, "error": "Token获取失败"}
            
            # 构建请求 - 添加API路径前缀
            if endpoint.startswith('http'):
                url = endpoint  # 完整URL
            elif endpoint.startswith('/'):
                url = f"{self.base_url}{endpoint}"  # 绝对路径
            else:
                # 相对路径，需要添加API前缀
                api_path = "/api/airprovinceproduct/dataanalysis/ReportDataQuery"
                url = f"{self.base_url}{api_path}/{endpoint}"
            headers = {
                'Authorization': f'Bearer {token}',
                'SysCode': self.sys_code,
                'Content-Type': 'application/json'
            }
            
            # 发送请求
            response = requests.post(url, headers=headers, json=params, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success', False):
                    return {"success": True, "data": data}
                else:
                    return {"success": False, "error": data.get('msg', '未知API错误')}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
                
        except Exception as e:
            return {"success": False, "error": f"API请求异常: {str(e)}"}

    def _handle_api_error_with_fallback(self, api_response: Dict[str, Any], question: str, 
                                       tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理API错误并尝试LLM错误恢复"""
        try:
            self.logger.info(f"[ERROR_RECOVERY] 尝试API错误恢复")
            
            # 使用统一LLM托底进行错误恢复
            fallback_result = self.fallback_manager.handle_fallback(
                fallback_type='api_error_recovery',
                question=question,
                context={
                    'api_error': api_response.get('error', ''),
                    'api_params': params,
                    'tool_name': tool_name,
                    'http_status': 'API调用失败'
                },
                error_info=api_response.get('error', 'API调用失败')
            )
            
            if fallback_result.get('status') == 'success' and fallback_result.get('action') == 'retry':
                # LLM建议重试，使用统一解析处理修正参数
                llm_params = fallback_result.get('result_data', {})
                self.logger.info(f"[ERROR_RECOVERY] LLM生成修正参数，使用统一解析")
                
                # 使用专用的LLM托底处理器
                from .intelligence.llm_fallback_processor import get_llm_fallback_processor
                llm_processor = get_llm_fallback_processor()
                
                result = llm_processor.process_llm_fallback_result(llm_params, question, tool_name)
                
                if result['status'] == 'route_to_sql':
                    return self._route_to_sql_query(result['question'], result['reason'])
                else:
                    return result
            else:
                # LLM错误恢复失败，转向SQL
                return self._route_to_sql_query(question, 
                    f"LLM错误恢复失败: {fallback_result.get('reason', '未知原因')}")
                
        except Exception as e:
            self.logger.error(f"[ERROR_RECOVERY] 错误恢复异常: {e}")
            return self._route_to_sql_query(question, f"错误恢复异常: {str(e)}")

    def _format_llm_fallback_result(self, fallback_result: Dict[str, Any]) -> Dict[str, Any]:
        """格式化LLM托底的结果为UQP格式"""
        return {
            "status": "success",
            "response_type": "message",
            "payload": {
                "format": "text",
                "value": fallback_result.get('result_data', '处理完成')
            },
            "debug_info": {
                "execution_path": "EXTERNAL_API_HANDLER",
                "processing_method": "llm_fallback_complex_query",
                "complexity_handling": "llm_direct_answer",
                "confidence": fallback_result.get('confidence', 0.0),
                "reasoning": fallback_result.get('reason', '')
            }
        }

    def _detect_query_complexity_with_context(self, question: str, grouped_locations: Dict, time_params: List, tool_name: str) -> Dict[str, Any]:
        """
        基于完整上下文检测查询复杂性
        
        Args:
            question: 用户查询文本
            grouped_locations: 已提取的地理位置分组
            time_params: 已提取的时间参数
            tool_name: 已选择的工具名称
            
        Returns:
            Dict: 复杂性检测结果
        """
        try:
            # 获取基础的时间参数复杂性检测
            param_converter = get_param_converter()
            base_complexity = param_converter.detect_query_complexity(question)
            
            # 如果基础检测就是复杂查询，直接返回，但增强原因说明
            if base_complexity['is_complex']:
                # 构建增强的上下文信息
                context_info = {
                    'locations': grouped_locations,
                    'time_parameters': base_complexity['time_parameters'],
                    'tool_name': tool_name,
                    'location_count': sum(len(locs) for locs in grouped_locations.values()) if grouped_locations else 0
                }
                
                enhanced_reason = (
                    f"{base_complexity['complexity_reason']}。"
                    f"上下文信息: 地理位置{context_info['location_count']}个，"
                    f"工具选择为{tool_name}，建议使用LLM处理复杂查询"
                )
                
                self.logger.debug(f"[COMPLEXITY_DETECT] 上下文增强: {context_info}")
                
                return {
                    'is_complex': True,
                    'time_param_count': base_complexity['time_param_count'],
                    'time_parameters': base_complexity['time_parameters'],
                    'complexity_reason': enhanced_reason,
                    'context_info': context_info
                }
            
            # 如果基础检测是简单查询，返回简单查询结果
            return {
                'is_complex': False,
                'time_param_count': base_complexity['time_param_count'],
                'time_parameters': base_complexity['time_parameters'], 
                'complexity_reason': f"{base_complexity['complexity_reason']}，继续API处理流程",
                'context_info': {
                    'locations': grouped_locations,
                    'tool_name': tool_name
                }
            }
            
        except Exception as e:
            self.logger.error(f"[COMPLEXITY_DETECT] 复杂性检测异常: {e}")
            # 发生异常时，默认为简单查询，继续API处理流程
            return {
                'is_complex': False,
                'time_param_count': 0,
                'time_parameters': [],
                'complexity_reason': f'复杂性检测异常，默认为简单查询: {e}',
                'context_info': {
                    'error': str(e)
                }
            }
    
    def _get_api_tool_use_prompt(self) -> str:
        """获取API工具使用提示词 - 使用统一处理器"""
        try:
            return get_prompt('external_api_handler', 'unified_api_processor')
        except Exception as e:
            self.logger.error(f"[API_TRACE] 加载统一API提示词失败: {e}")
            return "你是专业的空气质量API参数分析专家，负责工具选择、参数提取、参数补充和错误修复。"
    
    def _get_vanna_service(self):
        """获取VannaService实例"""
        if self.vanna_service is None:
            try:
                from .vanna_service import get_vanna_service
                self.vanna_service = get_vanna_service()
            except ImportError:
                self.logger.error("[API_TRACE] 无法导入VannaService")
                return None
        return self.vanna_service
    
    # 阶段2优化：已经被简化工具选择器替代
    # def _keyword_matching_mode(self, question: str) -> Dict[str, Any]:
    #     """快速匹配模式（使用增强版VannaService）"""
    #     此方法已被 SimplifiedToolSelector 替代
    
    # 阶段2优化：已被简化工具选择器替代
    # def _is_keyword_matching_successful(self, result: Dict[str, Any], original_question: str) -> bool:
    #     """判断快速匹配是否成功"""
    #     此方法已被 SimplifiedToolSelector 替代

    # 阶段2优化：已被简化工具选择器替代
    # def _is_time_extraction_imprecise(self, extracted_time: str, original_question: str) -> bool:
    #     """检查时间提取是否精度不足"""
    #     此方法已被 SimplifiedToolSelector 替代
    
    def _llm_analysis_mode_with_fallback(self, question: str, keyword_result: Dict[str, Any], modes_tried: List[str], start_time: float) -> Dict[str, Any]:
        """大模型分析模式，支持降级回快速匹配"""
        
        self.logger.info(f"[API_TRACE] 步骤2: 执行大模型分析模式")
        
        try:
            # 调用真正的LLM
            llm_result = self._llm_analysis_mode(question)
            modes_tried.append("llm_analysis")
            
            # 检查LLM结果
            if llm_result.get("status") == "success":
                self.logger.info(f"[API_TRACE] 大模型分析成功")
                self.mode_stats['llm_analysis_success'] += 1
                return self._finalize_result(llm_result, modes_tried, start_time, "llm_analysis")
            else:
                raise Exception(llm_result.get("message", "LLM分析失败"))
                
        except Exception as e:
            self.logger.error(f"[API_TRACE] 大模型分析失败: {e}")
            self.mode_stats['llm_analysis_failed'] += 1
            
            # 检查是否启用自动降级
            if self.external_api_config.get('auto_downgrade_enabled', False):
                self.logger.info(f"[API_TRACE] 启用自动降级，返回快速匹配结果")
                self.mode_stats['auto_downgrade_count'] += 1
                # 标记这是降级结果
                keyword_result["fallback_info"] = {
                    "primary_mode": "keyword_matching",
                    "fallback_reason": "llm_analysis_failed",
                    "llm_error": str(e)
                }
                return self._finalize_result(keyword_result, modes_tried, start_time, "keyword_matching_fallback")
            else:
                self.logger.info(f"[API_TRACE] 自动降级已禁用，返回LLM错误")
                return self._finalize_result({
                    "status": "error",
                    "message": f"大模型分析失败: {str(e)}",
                    "keyword_matching_result": keyword_result,
                    "suggestion": "建议启用 auto_downgrade_enabled 或检查LLM配置"
                }, modes_tried, start_time, "llm_analysis_failed")
    
    def _llm_analysis_mode(self, question: str) -> Dict[str, Any]:
        """真正的大模型分析模式（直接调用LLM API）"""
        self.logger.info(f"[API_TRACE] 使用真正的大模型分析模式")
        
        try:
            # 检查LLM配置
            if not self.llm_config.get('api_key'):
                raise Exception("LLM API密钥未配置")
            
            # 读取工具使用提示词
            prompt_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'external_api_prompts.yaml')
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    system_prompt = config['api_tool_selection_main']
            except FileNotFoundError:
                system_prompt = get_prompt('external_api_handler', 'system_default')
            
            # 构建消息
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
            
            self.logger.info(f"[API_TRACE] 直接调用LLM API进行工具选择")
            self.logger.info(f"[API_TRACE] 使用模型: {self.llm_config.get('model', 'unknown')}")
            self.logger.info(f"[API_TRACE] API端点: {self.llm_config.get('base_url', 'unknown')}")
            
            # 调用真正的LLM API
            response = self._call_real_llm_with_tools(messages, EXTERNAL_API_TOOLS)
            
            # 解析LLM响应
            if response and hasattr(response, 'choices') and response.choices:
                choice = response.choices[0]
                message = choice.message
                
                # 检查是否有工具调用
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    tool_call = message.tool_calls[0]
                    tool_name = tool_call.function.name
                    tool_params = json.loads(tool_call.function.arguments)
                    
                    self.logger.info(f"[API_TRACE] LLM分析工具选择成功:")
                    self.logger.info(f"[API_TRACE]   - 选择的工具: {tool_name}")
                    self.logger.info(f"[API_TRACE]   - 提取的参数: {tool_params}")
                    
                    return {
                        "status": "success",
                        "tool_name": tool_name,
                        "tool_params": tool_params,
                        "mode": "llm_analysis",
                        "llm_response": {
                            "content": message.content,
                            "finish_reason": choice.finish_reason
                        }
                    }
                else:
                    # LLM没有调用工具
                    self.logger.warning(f"[API_TRACE] LLM分析未选择任何工具")
                    return {
                        "status": "no_tool_matched",
                        "message": "LLM分析未找到合适的工具",
                        "mode": "llm_analysis",
                        "llm_response": {
                            "content": message.content if hasattr(message, 'content') else None,
                            "finish_reason": choice.finish_reason
                        }
                    }
            else:
                raise Exception("LLM API返回无效响应")
                
        except Exception as e:
            self.logger.error(f"[API_TRACE] LLM分析模式失败: {e}")
            return {
                "status": "error",
                "message": f"LLM分析模式失败: {str(e)}",
                "mode": "llm_analysis"
            }
    
    def _call_real_llm_with_tools(self, messages: List[Dict], tools: List[Dict]) -> Any:
        """调用真正的LLM工具选择API"""
        try:
            # 尝试导入OpenAI库
            try:
                import openai
            except ImportError:
                raise Exception("需要安装openai库: pip install openai")
            
            # 创建OpenAI客户端
            client = openai.OpenAI(
                api_key=self.llm_config.get('api_key'),
                base_url=self.llm_config.get('base_url')
            )
            
            # 设置超时时间
            timeout = self.external_api_config.get('llm_timeout', 10)
            
            self.logger.info(f"[API_TRACE] 发送LLM API请求")
            self.logger.info(f"[API_TRACE] 超时设置: {timeout}秒")
            self.logger.info(f"[API_TRACE] 工具数量: {len(tools)}")
            
            # 调用API
            response = client.chat.completions.create(
                model=self.llm_config.get('model', 'gpt-3.5-turbo'),
                messages=messages,
                tools=tools,
                tool_choice="auto",
                timeout=timeout
            )
            
            self.logger.info(f"[API_TRACE] LLM API调用成功")
            if hasattr(response, 'usage') and response.usage:
                self.logger.info(f"[API_TRACE] Token使用情况: {response.usage}")
            
            return response
            
        except Exception as e:
            self.logger.error(f"[API_TRACE] LLM API调用失败: {e}")
            raise
    
    def _finalize_result(self, result: Dict[str, Any], modes_tried: List[str], start_time: float, final_mode: str) -> Dict[str, Any]:
        """结果最终化处理，添加性能监控信息"""
        
        total_duration = time.time() - start_time
        self.logger.info(f"[API_TRACE] 工具选择完成统计:")
        self.logger.info(f"[API_TRACE]   - 总耗时: {total_duration:.2f}秒")
        self.logger.info(f"[API_TRACE]   - 尝试模式: {modes_tried}")
        self.logger.info(f"[API_TRACE]   - 最终成功模式: {final_mode}")
        
        # 添加性能信息到结果
        result["performance_info"] = {
            "total_duration": total_duration,
            "modes_tried": modes_tried,
            "final_mode": final_mode,
            "mode_stats": self.mode_stats.copy()
        }
        
        return result
    
    def _execute_mode(self, mode: str, question: str, modes_tried: List[str], start_time: float) -> Dict[str, Any]:
        """执行指定的模式"""
        if mode == "keyword_matching":
            result = self._keyword_matching_mode(question)
            modes_tried.append("keyword_matching")
            return self._finalize_result(result, modes_tried, start_time, "keyword_matching_forced")
        elif mode == "llm_analysis":
            result = self._llm_analysis_mode(question)
            modes_tried.append("llm_analysis")
            return self._finalize_result(result, modes_tried, start_time, "llm_analysis_forced")
        else:
            return self._finalize_result({
                "status": "error",
                "message": f"未知的强制模式: {mode}"
            }, modes_tried, start_time, "error")
    
    def _handle_summary_report_request(self, tool_params: Dict[str, Any], 
                                      question: str = "") -> Dict[str, Any]:
        """
        处理综合报表请求 - 支持LLM智能补充
        """
        try:
            selected_tool = "get_summary_report"  # 明确定义工具名称，供错误处理使用
            self.logger.info(f"[API_TRACE] 开始处理综合报表请求")
            self.logger.info(f"[API_TRACE] 原始工具参数: {tool_params}")
            self.logger.info(f"[API_TRACE] 用户问题: {question}")
            
            # 阶段2优化：先进行参数去重处理
            param_deduplicator = get_parameter_deduplicator()
            self.logger.info(f"[API_TRACE] 开始参数去重处理")
            dedup_result = param_deduplicator.deduplicate_and_validate(tool_params)
            
            if dedup_result['status'] == 'clarification_needed':
                # 参数去重失败，转向SQL查询
                self.logger.info(f"[API_TRACE] 参数去重失败，转向SQL查询: {dedup_result.get('message', '参数去重失败')}")
                return self._route_to_sql_query(question, f"参数去重失败: {dedup_result.get('message', '参数去重失败')}")
            elif dedup_result['status'] == 'error':
                # 参数去重失败
                return {
                    "status": "error",
                    "response_type": "message",
                    "payload": {
                        "format": "text",
                        "value": f"参数处理失败：{dedup_result['message']}"
                    },
                    "debug_info": {
                        "execution_path": "EXTERNAL_API_HANDLER",
                        "deduplication_result": dedup_result,
                        "original_params": tool_params
                    }
                }
            
            # 使用去重后的参数进行转换
            deduplicated_params = dedup_result['params']
            self.logger.info(f"[API_TRACE] 参数去重完成，应用去重: {dedup_result['deduplication_applied']}")
            if dedup_result['issues_found']:
                self.logger.info(f"[API_TRACE] 去重处理信息: {dedup_result['issues_found']}")
            
            # 使用参数转换器验证和转换参数（启用LLM智能补充）
            param_converter = get_param_converter()
            self.logger.info(f"[API_TRACE] 开始参数转换与验证（支持LLM智能补充）")
            conversion_result = param_converter.validate_and_convert_params(
                deduplicated_params, enable_llm_completion=True
            )
            
            self.logger.info(f"[API_TRACE] 参数转换结果状态: {conversion_result['status']}")
            if conversion_result['status'] != 'clarification_needed':
                self.logger.info(f"[API_TRACE] 转换后的参数: {conversion_result.get('converted_params', {})}")
            
            if conversion_result["status"] == "clarification_needed":
                # 参数转换失败，先尝试LLM托底处理
                self.logger.info(f"[API_TRACE] 参数转换失败，尝试LLM智能处理")
                
                clarifications = conversion_result.get("clarifications", [])
                errors = conversion_result.get("errors", [])
                
                # 构建LLM托底上下文
                failure_context = {
                    "original_params": tool_params,
                    "clarifications": clarifications,
                    "errors": errors,
                    "tool_name": selected_tool
                }
                
                llm_recovery = self._llm_handle_conversion_failure(question, failure_context)
                
                if llm_recovery.get('status') == 'success':
                    # LLM成功修复了参数
                    self.logger.info(f"[API_TRACE] LLM成功修复参数转换问题")
                    tool_params = llm_recovery.get('tool_params')
                    
                    # 重新尝试参数转换
                    retry_conversion = param_converter.validate_and_convert_params(
                        tool_params, enable_llm_completion=True
                    )
                    
                    if retry_conversion["status"] == "success":
                        conversion_result = retry_conversion
                        self.logger.info(f"[API_TRACE] LLM修复后参数转换成功")
                    else:
                        # LLM修复后仍然失败，转向SQL
                        reason_parts = []
                        if errors:
                            reason_parts.extend(errors)
                        if clarifications:
                            reason_parts.extend(clarifications)
                        reason = "参数转换失败: " + "; ".join(reason_parts) if reason_parts else "参数转换失败"
                        self.logger.info(f"[API_TRACE] LLM修复后仍然失败，转向SQL查询: {reason}")
                        return self._route_to_sql_query(question, reason)
                else:
                    # LLM也无法处理，转向SQL查询
                    reason_parts = []
                    if errors:
                        reason_parts.extend(errors)
                    if clarifications:
                        reason_parts.extend(clarifications)
                    reason = "参数转换失败: " + "; ".join(reason_parts) if reason_parts else "参数转换失败"
                    self.logger.info(f"[API_TRACE] LLM无法修复，转向SQL查询: {reason}")
                    return self._route_to_sql_query(question, reason)
            
            elif conversion_result["status"] == "error":
                # 转换错误
                errors = conversion_result.get("errors", ["参数转换失败"])
                return {
                    "status": "error",
                    "response_type": "message",
                    "payload": {
                        "format": "text",
                        "value": f"参数转换失败：{'; '.join(errors)}"
                    },
                    "debug_info": {
                        "execution_path": "EXTERNAL_API_HANDLER",
                        "conversion_result": conversion_result,
                        "original_params": tool_params
                    }
                }
            
            # 参数转换成功，再次对转换后参数进行去重（阶段2优化）
            converted_params = conversion_result["converted_params"]
            
            # 对转换后的参数进行去重（解决HTTP 500错误）
            self.logger.info(f"[API_TRACE] 开始转换参数去重处理")
            final_dedup_result = param_deduplicator.deduplicate_converted_params(converted_params)
            
            if final_dedup_result['status'] == 'error':
                return {
                    "status": "error",
                    "response_type": "message",
                    "payload": {
                        "format": "text",
                        "value": f"转换参数去重失败：{final_dedup_result['message']}"
                    },
                    "debug_info": {
                        "execution_path": "EXTERNAL_API_HANDLER",
                        "final_dedup_result": final_dedup_result,
                        "converted_params": converted_params
                    }
                }
            
            # 使用最终去重后的参数
            final_params = final_dedup_result['params']
            if final_dedup_result['deduplication_applied']:
                self.logger.info(f"[API_TRACE] 转换参数去重应用: {final_dedup_result['fixes_applied']}")
            
            # 如果有警告，记录日志
            if conversion_result["status"] == "warning":
                warnings = conversion_result.get("clarifications", [])
                self.logger.warning(f"[API_TRACE] 参数转换警告: {warnings}")
            
            # 调用实际的API执行函数
            self.logger.info(f"[API_TRACE] 开始调用综合报表API")
            self.logger.info(f"[API_TRACE] API参数:")
            self.logger.info(f"[API_TRACE]   - 区域类型: {final_params['area_type']}")
            self.logger.info(f"[API_TRACE]   - 时间类型: {final_params['time_type']}")
            self.logger.info(f"[API_TRACE]   - 时间范围: {final_params['time_point']}")
            self.logger.info(f"[API_TRACE]   - 站点编码: {final_params['station_codes']}")
            self.logger.info(f"[API_TRACE]   - 数据源: {final_params['data_source']}")
            
            return self._execute_summary_report(
                area_type=final_params["area_type"],
                time_type=final_params["time_type"],
                time_point=final_params["time_point"],
                station_codes=final_params["station_codes"],
                data_source=final_params["data_source"]
            )
            
        except Exception as e:
            self.logger.error(f"处理综合报表请求失败: {str(e)}")
            return self._handle_api_error(e, "summary_report", tool_params, question)
    
    def _handle_comparison_report_request(self, tool_params: Dict[str, Any], question: str = "") -> Dict[str, Any]:
        """
        处理对比报表请求
        """
        try:
            selected_tool = "get_comparison_report"  # 明确定义工具名称，供错误处理使用
            self.logger.info(f"[API_TRACE] 开始处理对比报表请求")
            self.logger.info(f"[API_TRACE] 原始工具参数: {tool_params}")
            
            # 阶段2优化：先进行参数去重处理
            param_deduplicator = get_parameter_deduplicator()
            self.logger.info(f"[API_TRACE] 开始参数去重处理")
            dedup_result = param_deduplicator.deduplicate_and_validate(tool_params)
            
            if dedup_result['status'] == 'clarification_needed':
                # 参数去重失败，转向SQL查询
                self.logger.info(f"[API_TRACE] 参数去重失败，转向SQL查询: {dedup_result.get('message', '参数去重失败')}")
                return self._route_to_sql_query(question, f"参数去重失败: {dedup_result.get('message', '参数去重失败')}")
            elif dedup_result['status'] == 'error':
                # 参数去重失败
                return {
                    "status": "error",
                    "response_type": "message",
                    "payload": {
                        "format": "text",
                        "value": f"参数处理失败：{dedup_result['message']}"
                    },
                    "debug_info": {
                        "execution_path": "EXTERNAL_API_HANDLER",
                        "deduplication_result": dedup_result,
                        "original_params": tool_params
                    }
                }
            
            # 使用去重后的参数进行转换
            deduplicated_params = dedup_result['params']
            self.logger.info(f"[API_TRACE] 参数去重完成，应用去重: {dedup_result['deduplication_applied']}")
            if dedup_result['issues_found']:
                self.logger.info(f"[API_TRACE] 去重处理信息: {dedup_result['issues_found']}")
            
            # 使用参数转换器验证和转换参数（启用LLM智能补充）
            param_converter = get_param_converter()
            self.logger.info(f"[API_TRACE] 开始参数转换与验证（支持LLM智能补充）")
            conversion_result = param_converter.validate_and_convert_params(
                deduplicated_params, enable_llm_completion=True
            )
            
            self.logger.info(f"[API_TRACE] 参数转换结果状态: {conversion_result['status']}")
            if conversion_result['status'] != 'clarification_needed':
                self.logger.info(f"[API_TRACE] 转换后的参数: {conversion_result.get('converted_params', {})}")
            
            if conversion_result["status"] == "clarification_needed":
                # 参数转换失败，先尝试LLM托底处理
                self.logger.info(f"[API_TRACE] 参数转换失败，尝试LLM智能处理")
                
                clarifications = conversion_result.get("clarifications", [])
                errors = conversion_result.get("errors", [])
                
                # 构建LLM托底上下文
                failure_context = {
                    "original_params": tool_params,
                    "clarifications": clarifications,
                    "errors": errors,
                    "tool_name": selected_tool
                }
                
                llm_recovery = self._llm_handle_conversion_failure(question, failure_context)
                
                if llm_recovery.get('status') == 'success':
                    # LLM成功修复了参数
                    self.logger.info(f"[API_TRACE] LLM成功修复参数转换问题")
                    tool_params = llm_recovery.get('tool_params')
                    
                    # 重新尝试参数转换
                    retry_conversion = param_converter.validate_and_convert_params(
                        tool_params, enable_llm_completion=True
                    )
                    
                    if retry_conversion["status"] == "success":
                        conversion_result = retry_conversion
                        self.logger.info(f"[API_TRACE] LLM修复后参数转换成功")
                    else:
                        # LLM修复后仍然失败，转向SQL
                        reason_parts = []
                        if errors:
                            reason_parts.extend(errors)
                        if clarifications:
                            reason_parts.extend(clarifications)
                        reason = "参数转换失败: " + "; ".join(reason_parts) if reason_parts else "参数转换失败"
                        self.logger.info(f"[API_TRACE] LLM修复后仍然失败，转向SQL查询: {reason}")
                        return self._route_to_sql_query(question, reason)
                else:
                    # LLM也无法处理，转向SQL查询
                    reason_parts = []
                    if errors:
                        reason_parts.extend(errors)
                    if clarifications:
                        reason_parts.extend(clarifications)
                    reason = "参数转换失败: " + "; ".join(reason_parts) if reason_parts else "参数转换失败"
                    self.logger.info(f"[API_TRACE] LLM无法修复，转向SQL查询: {reason}")
                    return self._route_to_sql_query(question, reason)
            
            elif conversion_result["status"] == "error":
                # 转换错误
                errors = conversion_result.get("errors", ["参数转换失败"])
                return {
                    "status": "error",
                    "response_type": "message",
                    "payload": {
                        "format": "text",
                        "value": f"参数转换失败：{'; '.join(errors)}"
                    },
                    "debug_info": {
                        "execution_path": "EXTERNAL_API_HANDLER",
                        "conversion_result": conversion_result,
                        "original_params": tool_params
                    }
                }
            
            # 参数转换成功，再次对转换后参数进行去重（阶段2优化）
            converted_params = conversion_result["converted_params"]
            
            # 对转换后的参数进行去重（解决HTTP 500错误）
            self.logger.info(f"[API_TRACE] 开始转换参数去重处理")
            final_dedup_result = param_deduplicator.deduplicate_converted_params(converted_params)
            
            if final_dedup_result['status'] == 'error':
                return {
                    "status": "error",
                    "response_type": "message",
                    "payload": {
                        "format": "text",
                        "value": f"转换参数去重失败：{final_dedup_result['message']}"
                    },
                    "debug_info": {
                        "execution_path": "EXTERNAL_API_HANDLER",
                        "final_dedup_result": final_dedup_result,
                        "converted_params": converted_params
                    }
                }
            
            # 使用最终去重后的参数
            final_params = final_dedup_result['params']
            if final_dedup_result['deduplication_applied']:
                self.logger.info(f"[API_TRACE] 转换参数去重应用: {final_dedup_result['fixes_applied']}")
            
            # 阶段2优化：自动生成对比时间（默认为去年同期）
            if "contrast_time" not in final_params:
                self.logger.info(f"[API_TRACE] 对比时间缺失，尝试自动生成去年同期时间")
                
                # 使用工具选择器自动生成对比时间
                tool_selector = get_tool_selector()
                if 'time_point' in final_params:
                    generated_contrast_time = tool_selector.generate_comparison_time(final_params['time_point'])
                    
                    if generated_contrast_time:
                        final_params['contrast_time'] = generated_contrast_time
                        self.logger.info(f"[API_TRACE] 自动生成对比时间成功: {generated_contrast_time}")
                    else:
                        # 生成失败，自动转向SQL查询
                        self.logger.info(f"[API_TRACE] 对比时间生成失败，自动转向SQL查询")
                        return {
                            "status": "route_to_sql",
                            "reason": "对比时间无法自动生成，转向SQL查询处理"
                        }
                else:
                    # 没有基础时间范围，自动转向SQL查询
                    self.logger.info(f"[API_TRACE] 缺少基础时间范围，自动转向SQL查询")
                    return {
                        "status": "route_to_sql",
                        "reason": "缺少必要的时间范围参数，转向SQL查询处理"
                    }
            
            # 如果有警告，记录日志
            if conversion_result["status"] == "warning":
                warnings = conversion_result.get("clarifications", [])
                self.logger.warning(f"[API_TRACE] 参数转换警告: {warnings}")
            
            # 调用实际的API执行函数
            self.logger.info(f"[API_TRACE] 开始调用对比报表API")
            self.logger.info(f"[API_TRACE] API参数:")
            self.logger.info(f"[API_TRACE]   - 区域类型: {final_params['area_type']}")
            self.logger.info(f"[API_TRACE]   - 时间类型: {final_params['time_type']}")
            self.logger.info(f"[API_TRACE]   - 时间范围: {final_params['time_point']}")
            self.logger.info(f"[API_TRACE]   - 对比时间: {final_params['contrast_time']} {"自动生成" if 'contrast_time' in final_params else "手动指定"}")
            self.logger.info(f"[API_TRACE]   - 站点编码: {final_params['station_codes']}")
            self.logger.info(f"[API_TRACE]   - 数据源: {final_params['data_source']}")
            
            return self._execute_comparison_report(
                area_type=final_params["area_type"],
                time_type=final_params["time_type"],
                time_point=final_params["time_point"],
                contrast_time=final_params["contrast_time"],
                station_codes=final_params["station_codes"],
                data_source=final_params["data_source"],
                auto_generated_contrast_time=True  # 标记对比时间是否为自动生成
            )
            
        except Exception as e:
            self.logger.error(f"处理对比报表请求失败: {str(e)}")
            return self._handle_api_error(e, "comparison_report", tool_params, question)
    
    
    def _get_stations(self) -> Dict[str, Any]:
        """
        获取站点信息
        """
        try:
            # 测试模式：返回模拟数据
            if self.test_mode:
                self.logger.info("测试模式：返回模拟站点数据")
                mock_data = get_external_api_mock_data()
                stations = mock_data["stations"]
                return {
                    "status": "success",
                    "response_type": "data",
                    "payload": {
                        "format": "dataframe",
                        "value": stations
                    },
                    "debug_info": {
                        "execution_path": "EXTERNAL_API_HANDLER",
                        "api_endpoint": "GetStation (Mock)",
                        "record_count": len(stations),
                        "test_mode": True
                    }
                }
            
            # 正式模式：调用真实API
            url = f"{self.base_url}{self.api_endpoints['stations']}"
            headers = {
                "Authorization": f"Bearer {self._get_token()}",
                "SysCode": self.sys_code,
                "Content-Type": "application/json"
            }
            
            self.logger.info(f"请求站点信息: {url}")
            
            response = requests.post(url, headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    stations = data.get('result', [])
                    return {
                        "status": "success",
                        "response_type": "data",
                        "payload": {
                            "format": "dataframe",
                            "value": stations
                        },
                        "debug_info": {
                            "execution_path": "EXTERNAL_API_HANDLER",
                            "api_endpoint": "GetStation",
                            "record_count": len(stations)
                        }
                    }
                else:
                    raise Exception(f"API返回错误: {data.get('msg', 'Unknown error')}")
            else:
                raise Exception(f"HTTP请求失败: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"获取站点信息失败: {str(e)}")
            raise
    
    def _get_detection_items(self) -> Dict[str, Any]:
        """
        获取监测项目信息
        """
        try:
            # 测试模式：返回模拟数据
            if self.test_mode:
                self.logger.info("测试模式：返回模拟监测项目数据")
                mock_data = get_external_api_mock_data()
                items = mock_data["detection_items"]
                return {
                    "status": "success",
                    "response_type": "data",
                    "payload": {
                        "format": "dataframe",
                        "value": items
                    },
                    "debug_info": {
                        "execution_path": "EXTERNAL_API_HANDLER",
                        "api_endpoint": "GetDetectionItem (Mock)",
                        "record_count": len(items),
                        "test_mode": True
                    }
                }
            
            # 正式模式：调用真实API
            url = f"{self.base_url}{self.api_endpoints['detection_items']}"
            headers = {
                "Authorization": f"Bearer {self._get_token()}",
                "SysCode": self.sys_code,
                "Content-Type": "application/json"
            }
            
            self.logger.info(f"请求监测项目信息: {url}")
            
            response = requests.post(url, headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    items = data.get('result', [])
                    return {
                        "status": "success",
                        "response_type": "data",
                        "payload": {
                            "format": "dataframe",
                            "value": items
                        },
                        "debug_info": {
                            "execution_path": "EXTERNAL_API_HANDLER",
                            "api_endpoint": "GetDetectionItem",
                            "record_count": len(items)
                        }
                    }
                else:
                    raise Exception(f"API返回错误: {data.get('msg', 'Unknown error')}")
            else:
                raise Exception(f"HTTP请求失败: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"获取监测项目信息失败: {str(e)}")
            raise
    
    def _get_instruments(self, question: str) -> Dict[str, Any]:
        """
        获取仪器信息
        """
        try:
            # 测试模式：返回模拟数据
            if self.test_mode:
                self.logger.info("测试模式：返回模拟仪器数据")
                mock_data = get_external_api_mock_data()
                instruments = mock_data["instruments"]
                return {
                    "status": "success",
                    "response_type": "data",
                    "payload": {
                        "format": "dataframe",
                        "value": instruments
                    },
                    "debug_info": {
                        "execution_path": "EXTERNAL_API_HANDLER",
                        "api_endpoint": "GetDetectionItemType (Mock)",
                        "record_count": len(instruments),
                        "test_mode": True
                    }
                }
            
            # 正式模式：调用真实API
            url = f"{self.base_url}{self.api_endpoints['instruments']}"
            headers = {
                "Authorization": f"Bearer {self._get_token()}",
                "SysCode": self.sys_code,
                "Content-Type": "application/json"
            }
            
            # 尝试从问题中提取仪器名称
            instrument_name = self._extract_instrument_name(question)
            
            payload = {}
            if instrument_name:
                payload['name'] = instrument_name
            
            self.logger.info(f"请求仪器信息: {url}, payload: {payload}")
            
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    instruments = data.get('result', [])
                    return {
                        "status": "success",
                        "response_type": "data",
                        "payload": {
                            "format": "dataframe",
                            "value": instruments
                        },
                        "debug_info": {
                            "execution_path": "EXTERNAL_API_HANDLER",
                            "api_endpoint": "GetDetectionItemType",
                            "record_count": len(instruments),
                            "filter_name": instrument_name
                        }
                    }
                else:
                    raise Exception(f"API返回错误: {data.get('msg', 'Unknown error')}")
            else:
                raise Exception(f"HTTP请求失败: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"获取仪器信息失败: {str(e)}")
            raise
    
    def _get_station_data(self, question: str) -> Dict[str, Any]:
        """
        获取站点数据（暂时返回提示信息，需要更多参数）
        """
        return {
            "status": "clarification_needed",
            "response_type": "message",
            "payload": {
                "format": "text",
                "value": "获取站点数据需要以下参数：\n• 开始时间（格式：YYYY-MM-DD）\n• 结束时间（格式：YYYY-MM-DD）\n• 站点代码\n• 监测因子代码\n• 数据类型（0：原始，4：初审，5：复审，7：混合）\n• 时间类型（1：小时，2：日，3：月）"
            },
            "debug_info": {
                "execution_path": "EXTERNAL_API_HANDLER",
                "api_endpoint": "GetDataSource",
                "status": "parameters_needed"
            }
        }
    
    def _execute_summary_report(self, 
                               area_type: str,
                               time_type: int,
                               time_point: List[str],
                               station_codes: List[str],
                               data_source: int) -> Dict[str, Any]:
        """
        执行综合报表查询API
        
        Args:
            area_type: 区域类型 (0: 站点, 1: 区县, 2: 城市)
            time_type: 时间类型 (3: 周报, 4: 月报, 5: 季报, 7: 年报, 8: 任意时间)
            time_point: 时间点数组 ["2025-07-09 00:00:00", "2025-07-16 00:00:00"]
            station_codes: 站点编码数组 ["1001A", "1002A"]
            data_source: 数据来源 (0: 原始实况, 1: 审核实况, 2: 原始标况, 3: 审核标况)
        """
        try:
            # 构建请求URL
            url = f"{self.base_url}{self.api_endpoints['summary_report']}"
            
            # 构建请求头
            headers = {
                "Authorization": f"Bearer {self._get_token()}",
                "SysCode": self.sys_code,
                "Content-Type": "application/json"
            }
            
            # 构建请求体
            payload = {
                "AreaType": area_type,
                "TimeType": time_type,
                "TimePoint": time_point,
                "StationCode": station_codes,
                "DataSource": data_source
            }
            
            self.logger.info(f"[API_TRACE] 发送HTTP请求到综合报表API")
            self.logger.info(f"[API_TRACE] 请求URL: {url}")
            self.logger.info(f"[API_TRACE] 请求负载: {payload}")
            
            # 发送POST请求
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    result = data.get('result', {})
                    items = result.get('items', [])
                    total_count = result.get('totalCount', 0)
                    
                    self.logger.info(f"[API_TRACE] 综合报表API调用成功")
                    self.logger.info(f"[API_TRACE] 返回数据条数: {len(items)}")
                    self.logger.info(f"[API_TRACE] 总记录数: {total_count}")
                    
                    return {
                        "status": "success",
                        "response_type": "data",
                        "payload": {
                            "format": "dataframe",
                            "value": items,
                            "total_count": total_count
                        },
                        "debug_info": {
                            "execution_path": "EXTERNAL_API_HANDLER",
                            "api_endpoint": "GetReportForRangePagedListAsync",
                            "record_count": len(items),
                            "total_count": total_count,
                            "request_params": payload
                        }
                    }
                else:
                    raise Exception(f"API返回错误: {data.get('msg', 'Unknown error')}")
            else:
                raise Exception(f"HTTP请求失败: {response.status_code}, 响应: {response.text}")
                
        except Exception as e:
            self.logger.error(f"综合报表查询失败: {str(e)}")
            raise
    
    def _execute_comparison_report(self, 
                                  area_type: str,
                                  time_type: int,
                                  time_point: List[str],
                                  contrast_time: List[str],
                                  station_codes: List[str],
                                  data_source: int,
                                  auto_generated_contrast_time: bool = False) -> Dict[str, Any]:
        """
        执行对比报表查询API
        
        Args:
            area_type: 区域类型 (0: 站点, 1: 区县, 2: 城市)
            time_type: 时间类型 (4: 月报, 8: 任意时间)
            time_point: 时间点数组 ["2025-07-09 00:00:00", "2025-07-16 00:00:00"]
            contrast_time: 对比时间数组 ["2025-06-09 00:00:00", "2025-06-16 00:00:00"]
            station_codes: 站点编码数组 ["1001A", "1002A"]
            data_source: 数据来源 (0: 原始实况, 1: 审核实况, 2: 原始标况, 3: 审核标况)
        """
        try:
            # 构建请求URL
            url = f"{self.base_url}{self.api_endpoints['comparison_report']}"
            
            # 构建请求头
            headers = {
                "Authorization": f"Bearer {self._get_token()}",
                "SysCode": self.sys_code,
                "Content-Type": "application/json"
            }
            
            # 构建请求体
            payload = {
                "AreaType": area_type,
                "TimeType": time_type,
                "TimePoint": time_point,
                "ContrastTime": contrast_time,
                "StationCode": station_codes,
                "DataSource": data_source
            }
            
            self.logger.info(f"[API_TRACE] 发送HTTP请求到对比报表API")
            self.logger.info(f"[API_TRACE] 请求URL: {url}")
            self.logger.info(f"[API_TRACE] 请求负载: {payload}")
            
            # 发送POST请求
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    result = data.get('result', [])
                    
                    self.logger.info(f"[API_TRACE] 对比报表API调用成功")
                    self.logger.info(f"[API_TRACE] 返回数据条数: {len(result)}")
                    
                    return {
                        "status": "success",
                        "response_type": "data",
                        "payload": {
                            "format": "dataframe",
                            "value": result
                        },
                        "debug_info": {
                            "execution_path": "EXTERNAL_API_HANDLER",
                            "api_endpoint": "GetReportForRangeCompareListAsync",
                            "record_count": len(result),
                            "request_params": payload,
                            "auto_generated_contrast_time": auto_generated_contrast_time
                        }
                    }
                else:
                    raise Exception(f"API返回错误: {data.get('msg', 'Unknown error')}")
            else:
                raise Exception(f"HTTP请求失败: {response.status_code}, 响应: {response.text}")
                
        except Exception as e:
            self.logger.error(f"对比报表查询失败: {str(e)}")
            raise
    
    def _extract_instrument_name(self, question: str) -> Optional[str]:
        """
        从问题中提取仪器名称
        """
        # 这里可以实现更复杂的NLP提取逻辑
        # 暂时返回None，表示不过滤
        return None
    
    def test_connection(self) -> Dict[str, Any]:
        """
        测试外部API连接
        """
        try:
            if self.test_mode:
                return {
                    "status": "success",
                    "response_type": "message",
                    "payload": {
                        "format": "text",
                        "value": "外部API连接测试成功（测试模式）"
                    },
                    "debug_info": {
                        "execution_path": "EXTERNAL_API_HANDLER",
                        "test_result": "connection_ok",
                        "test_mode": True
                    }
                }
            
            token = self._get_token()
            token_status = self.get_token_status()
            
            return {
                "status": "success",
                "response_type": "message",
                "payload": {
                    "format": "text",
                    "value": f"外部API连接测试成功，Token: {token[:20]}..."
                },
                "debug_info": {
                    "execution_path": "EXTERNAL_API_HANDLER",
                    "test_result": "connection_ok",
                    "test_mode": False,
                    "token_status": token_status
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "response_type": "message",
                "payload": {
                    "format": "text",
                    "value": f"外部API连接测试失败: {str(e)}"
                },
                "debug_info": {
                    "execution_path": "EXTERNAL_API_HANDLER",
                    "test_result": "connection_failed",
                    "error": str(e),
                    "test_mode": self.test_mode
                }
            }
    
    # ==================== 新增的多层级支持方法 ====================
    
    def _extract_and_group_locations(self, question: str) -> Dict[str, List[str]]:
        """
        提取并分组地理位置
        
        Args:
            question: 用户查询
            
        Returns:
            Dict[str, List[str]]: 按层级分组的地理位置
        """
        try:
            self.logger.info(f"[EXTRACT_GROUP] 开始地理位置提取和分组")
            
            # 1. 使用SmartGeoExtractor提取地理位置
            from .utils.smart_geo_extractor import get_smart_geo_extractor
            geo_extractor = get_smart_geo_extractor()
            extracted_locations = geo_extractor.extract_locations(question)
            
            if not extracted_locations:
                self.logger.warning(f"[EXTRACT_GROUP] 未提取到地理位置")
                return {}
            
            self.logger.info(f"[EXTRACT_GROUP] 提取到 {len(extracted_locations)} 个地理位置")
            
            # 2. 使用GeoLevelGrouper进行智能分组
            from .utils.geo_level_grouper import get_geo_level_grouper
            grouper = get_geo_level_grouper()
            grouped_locations = grouper.group_by_levels(extracted_locations)
            
            self.logger.info(f"[EXTRACT_GROUP] 分组结果: {grouped_locations}")
            return grouped_locations
            
        except Exception as e:
            self.logger.error(f"[EXTRACT_GROUP] 地理位置提取分组失败: {e}")
            return {}
    
    def _select_tool_for_question(self, question: str) -> str:
        """
        为查询选择合适的API工具
        
        Args:
            question: 用户查询
            
        Returns:
            str: 工具名称
        """
        # 简化的工具选择逻辑，基于关键词判断
        comparison_keywords = ['对比', '比较', '变化', '增长', '下降', '同比', '环比', '相比']
        
        if any(keyword in question for keyword in comparison_keywords):
            self.logger.info(f"[TOOL_SELECT] 检测到对比关键词，选择对比报表工具")
            return 'get_comparison_report'
        else:
            self.logger.info(f"[TOOL_SELECT] 选择综合报表工具")
            return 'get_summary_report'
    
    def _extract_time_params(self, question: str) -> Dict[str, Any]:
        """
        提取时间参数（使用新的统一方法）
        
        Args:
            question: 用户查询
            
        Returns:
            Dict[str, Any]: 时间参数字典
        """
        try:
            from .utils.param_extractor import get_param_extractor
            param_extractor = get_param_extractor()
            
            # 使用新的专用时间参数提取方法
            return param_extractor.extract_time_params_only(question)
            
        except Exception as e:
            self.logger.error(f"[TIME_EXTRACT] 时间参数提取失败: {e}")
            return {}
    
    def _llm_supplement_params(self, question: str, grouped_locations: Dict[str, List[str]], 
                              tool_name: str, time_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用LLM智能补充参数
        
        Args:
            question: 用户查询
            grouped_locations: 分组的地理位置
            tool_name: 工具名称
            time_params: 已提取的时间参数
            
        Returns:
            Dict[str, Any]: LLM补充结果
        """
        try:
            self.logger.info(f"[LLM_SUPPLEMENT] 开始LLM智能参数补充")
            
            # 准备LLM输入信息
            geo_info = []
            for level, locations in grouped_locations.items():
                for location in locations:
                    geo_info.append({
                        'name': location,
                        'type': level,
                        'source': 'smart_geo_extractor'
                    })
            
            # 调用统一LLM处理器
            result = self._call_unified_llm_processor(
                question=question,
                processing_mode='parameter_supplement',
                geo_info=geo_info,
                existing_params={
                    'locations': [loc for locs in grouped_locations.values() for loc in locs],
                    'area_type': list(grouped_locations.keys())[0] if grouped_locations else '城市',
                    'data_source': time_params.get('data_source', '审核实况'),
                    'tool_name': tool_name,
                    **time_params
                },
                error_info=""
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"[LLM_SUPPLEMENT] LLM参数补充失败: {e}")
            return {'status': 'error', 'reason': f'LLM补充异常: {str(e)}'}
    
    def _validate_comparison_params(self, tool_name: str, time_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        对比查询参数完整性校验
        
        Args:
            tool_name: 工具名称
            time_params: 时间参数字典
            
        Returns:
            Dict: {'valid': bool, 'missing_params': List[str], 'action': str}
        """
        if tool_name != 'get_comparison_report':
            return {'valid': True, 'action': 'proceed'}
        
        missing_params = []
        
        # 检查主时间参数
        if not time_params.get('time_description'):
            missing_params.append('time_description')
        
        # 检查对比时间参数 - 关键校验点
        contrast_time = time_params.get('contrast_time_description')
        if not contrast_time or contrast_time.strip() == '':
            missing_params.append('contrast_time_description')
            self.logger.debug(f"[COMPARISON_VALIDATION] 对比时间参数缺失或为空: '{contrast_time}'")
        
        if missing_params:
            self.logger.info(f"[COMPARISON_VALIDATION] 对比查询参数不完整，缺失: {missing_params}")
            return {
                'valid': False, 
                'missing_params': missing_params,
                'action': 'need_recovery'
            }
        
        self.logger.debug(f"[COMPARISON_VALIDATION] 对比查询参数校验通过")
        return {'valid': True, 'action': 'proceed'}
    
    def _smart_recover_contrast_time(self, question: str, main_time: str, tool_name: str) -> Dict[str, Any]:
        """
        智能恢复对比时间
        
        Args:
            question: 原始问题
            main_time: 主时间描述
            tool_name: 工具名称
            
        Returns:
            Dict: 恢复结果
        """
        try:
            self.logger.info(f"[CONTRAST_RECOVERY] 开始智能恢复对比时间")
            self.logger.info(f"[CONTRAST_RECOVERY] 原始问题: {question}")
            self.logger.info(f"[CONTRAST_RECOVERY] 主时间: {main_time}")
            
            # 1. 首先尝试基于规则的推断（使用增强后的参数提取器）
            rule_result = self._rule_based_contrast_inference(question, main_time)
            if rule_result['success']:
                self.logger.info(f"[CONTRAST_RECOVERY] 规则推断成功: {rule_result['contrast_time']}")
                return rule_result
            
            # 2. 规则推断失败，尝试LLM智能分析
            self.logger.info(f"[CONTRAST_RECOVERY] 规则推断失败，尝试LLM分析")
            llm_result = self._llm_contrast_time_analysis(question, main_time)
            if llm_result['success']:
                self.logger.info(f"[CONTRAST_RECOVERY] LLM分析成功: {llm_result['contrast_time']}")
                return llm_result
            
            # 3. 都失败了，返回失败结果
            reason = f"规则推断和LLM分析都无法恢复对比时间。规则推断: {rule_result.get('reason', '未知')}，LLM分析: {llm_result.get('reason', '未知')}"
            self.logger.warning(f"[CONTRAST_RECOVERY] 对比时间恢复失败: {reason}")
            return {
                'success': False,
                'reason': reason,
                'action': 'route_to_sql'
            }
            
        except Exception as e:
            self.logger.error(f"[CONTRAST_RECOVERY] 智能恢复对比时间异常: {e}")
            return {
                'success': False,
                'reason': f'对比时间恢复异常: {str(e)}',
                'action': 'route_to_sql'
            }
    
    def _rule_based_contrast_inference(self, question: str, main_time: str) -> Dict[str, Any]:
        """
        基于规则的对比时间推断
        
        Args:
            question: 原始问题
            main_time: 主时间描述
            
        Returns:
            Dict: 推断结果
        """
        try:
            from .utils.param_extractor import get_param_extractor
            param_extractor = get_param_extractor()
            
            # 使用增强后的智能推断方法
            contrast_time = param_extractor._infer_intelligent_contrast_time(question, main_time)
            
            if contrast_time:
                self.logger.info(f"[RULE_INFERENCE] 规则推断成功: {main_time} → {contrast_time}")
                return {
                    'success': True,
                    'contrast_time': contrast_time,
                    'method': 'rule_based',
                    'confidence': 0.9
                }
            else:
                self.logger.debug(f"[RULE_INFERENCE] 规则推断失败，无法处理时间格式: {main_time}")
                return {
                    'success': False,
                    'reason': f'无法通过规则推断处理时间格式: {main_time}',
                    'method': 'rule_based'
                }
                
        except Exception as e:
            self.logger.error(f"[RULE_INFERENCE] 规则推断异常: {e}")
            return {
                'success': False,
                'reason': f'规则推断异常: {str(e)}',
                'method': 'rule_based'
            }
    
    def _llm_contrast_time_analysis(self, question: str, main_time: str) -> Dict[str, Any]:
        """
        LLM智能对比时间分析
        
        Args:
            question: 原始问题
            main_time: 主时间描述
            
        Returns:
            Dict: 分析结果
        """
        try:
            self.logger.info(f"[LLM_CONTRAST] 开始LLM对比时间分析")
            
            # 检测对比类型
            comparison_type = self._detect_comparison_type(question)
            
            # 调用统一LLM处理器进行对比时间分析
            result = self._call_unified_llm_processor(
                question=question,
                processing_mode='contrast_time_analysis',
                geo_info=[],
                existing_params={
                    'main_time': main_time,
                    'comparison_type': comparison_type,
                    'tool_name': 'get_comparison_report'
                },
                error_info=f"规则推断无法处理时间格式: {main_time}"
            )
            
            # 处理LLM在对比时间分析模式下的特殊响应格式
            if result.get('action') == 'success' and result.get('parameters', {}).get('comparison_time_description'):
                # LLM返回了标准API格式，需要提取对比时间
                comparison_time = result.get('parameters', {}).get('comparison_time_description')
                if comparison_time and isinstance(comparison_time, list) and len(comparison_time) >= 2:
                    # 转换为时间描述格式
                    start_time = comparison_time[0]
                    end_time = comparison_time[1]
                    
                    # 简化时间描述（从"2025-01-01 00:00:00"提取"2025年1月"）
                    import re
                    time_match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', start_time)
                    if time_match:
                        year = time_match.group(1)
                        month = int(time_match.group(2))
                        day = int(time_match.group(3))
                        
                        if day == 1:
                            # 如果是月初，简化为"YYYY年MM月"
                            contrast_time = f"{year}年{month}月"
                        else:
                            # 否则保持"YYYY年MM月DD日"
                            contrast_time = f"{year}年{month}月{day}日"
                    else:
                        contrast_time = f"{start_time} - {end_time}"
                    
                    reasoning = result.get('reason', 'LLM成功推断对比时间')
                    
                    self.logger.info(f"[LLM_CONTRAST] LLM分析成功: {contrast_time}")
                    self.logger.debug(f"[LLM_CONTRAST] 推理过程: {reasoning}")
                    
                    return {
                        'success': True,
                        'contrast_time': contrast_time,
                        'method': 'llm_analysis',
                        'confidence': 0.8,
                        'reasoning': reasoning
                    }
            
            # 处理标准的对比时间分析响应格式
            elif result.get('status') == 'success' and result.get('contrast_time'):
                contrast_time = result.get('contrast_time')
                confidence = result.get('confidence', 0.7)
                reasoning = result.get('reasoning', '无推理信息')
                
                self.logger.info(f"[LLM_CONTRAST] LLM分析成功: {contrast_time} (置信度: {confidence})")
                self.logger.debug(f"[LLM_CONTRAST] 推理过程: {reasoning}")
                
                return {
                    'success': True,
                    'contrast_time': contrast_time,
                    'method': 'llm_analysis',
                    'confidence': confidence,
                    'reasoning': reasoning
                }
            else:
                reason = result.get('reason', 'LLM分析未返回有效对比时间')
                self.logger.warning(f"[LLM_CONTRAST] LLM分析失败: {reason}")
                return {
                    'success': False,
                    'reason': reason,
                    'method': 'llm_analysis'
                }
                
        except Exception as e:
            self.logger.error(f"[LLM_CONTRAST] LLM对比时间分析异常: {e}")
            return {
                'success': False,
                'reason': f'LLM分析异常: {str(e)}',
                'method': 'llm_analysis'
            }
    
    def _detect_comparison_type(self, question: str) -> str:
        """
        检测对比类型
        
        Args:
            question: 原始问题
            
        Returns:
            str: 对比类型 ('环比', '同比', '对比')
        """
        question_lower = question.lower()
        
        # 环比关键词
        if any(keyword in question_lower for keyword in ['环比', '较上期', '上月', '上期', '上周']):
            return '环比'
        
        # 同比关键词
        elif any(keyword in question_lower for keyword in ['同比', '较去年', '去年同期', '上年同期']):
            return '同比'
        
        # 通用对比关键词
        elif any(keyword in question_lower for keyword in ['对比', '比较', '变化', '相比']):
            # 进一步分析上下文来判断
            if any(keyword in question_lower for keyword in ['去年', '上年']):
                return '同比'
            else:
                return '环比'  # 默认为环比
        
        return '对比'  # 通用对比
    
    def _convert_multi_level_params(self, grouped_locations: Dict[str, List[str]], 
                                   time_params: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        """
        多层级参数转换
        
        Args:
            grouped_locations: 分组的地理位置
            time_params: 时间参数
            tool_name: 工具名称
            
        Returns:
            Dict[str, Any]: 转换结果
        """
        try:
            from .utils.param_converter import get_param_converter
            converter = get_param_converter()
            
            result = converter.convert_multi_level_params(grouped_locations, time_params, tool_name)
            return result
            
        except Exception as e:
            self.logger.error(f"[MULTI_CONVERT] 多层级参数转换异常: {e}")
            return {
                'status': 'error',
                'errors': [f'参数转换异常: {str(e)}']
            }
    
    def _execute_multi_level_api_calls(self, converted_params: Dict[str, Any], 
                                      question: str) -> Dict[str, Any]:
        """
        执行多层级API调用并合并结果
        
        Args:
            converted_params: 转换后的参数
            question: 用户原始查询
            
        Returns:
            Dict[str, Any]: 合并后的结果
        """
        try:
            self.logger.info(f"[MULTI_EXECUTE] 开始多层级API调用")
            
            level_results = {}
            tool_name = converted_params.get('tool_name')
            time_params = converted_params.get('time_params', {})
            
            # 为每个层级的每个地理位置分别执行API调用
            location_call_index = 0
            for level, level_data in converted_params.get('levels', {}).items():
                if not level_data.get('success'):
                    self.logger.warning(f"[MULTI_EXECUTE] 跳过失败的层级: {level}")
                    continue
                
                self.logger.info(f"[MULTI_EXECUTE] 执行层级 {level} 的API调用，包含 {len(level_data.get('station_codes', []))} 个地理位置")
                
                # 为该层级内的每个地理位置分别调用API
                level_location_names = level_data.get('location_names', [])
                level_station_codes = level_data.get('station_codes', [])
                
                for i, station_code in enumerate(level_station_codes):
                    location_name = level_location_names[i] if i < len(level_location_names) else f"位置{i+1}"
                    location_call_key = f"{level}_{i}"
                    location_call_index += 1
                    
                    self.logger.info(f"[MULTI_EXECUTE] 调用 {location_call_index}: 层级 {level}, 位置 '{location_name}', 编码 '{station_code}'")
                    
                    # 智能选择TimeType：优先使用参数指定值，否则根据查询内容智能判断
                    time_type = time_params.get('time_type')
                    if time_type is None:
                        time_type = self._determine_time_type_from_query(question)
                        self.logger.info(f"[MULTI_EXECUTE] 未指定time_type，根据查询智能选择: {time_type}")
                    else:
                        self.logger.info(f"[MULTI_EXECUTE] 使用参数指定的time_type: {time_type}")
                    
                    # 构建API参数（每次调用只包含一个地理位置）
                    api_params = {
                        'AreaType': level_data['area_type_code'],
                        'StationCode': [station_code],  # 单个地理位置编码
                        'TimeType': time_type,
                        'TimePoint': self._extract_time_point_from_params(time_params),
                        'DataSource': self._convert_data_source_to_code(time_params.get('data_source', '审核实况'))
                    }
                    
                    # 对比查询添加对比时间
                    if tool_name == 'get_comparison_report':
                        api_params['ContrastTime'] = self._extract_contrast_time_from_params(time_params)
                    
                    # 调用具体API
                    try:
                        if tool_name == 'get_comparison_report':
                            api_result = self._execute_comparison_report(
                                area_type=api_params['AreaType'],
                                time_type=api_params['TimeType'], 
                                time_point=api_params['TimePoint'],
                                contrast_time=api_params['ContrastTime'],
                                station_codes=api_params['StationCode'],
                                data_source=api_params['DataSource']
                            )
                        else:
                            api_result = self._execute_summary_report(
                                area_type=api_params['AreaType'],
                                time_type=api_params['TimeType'],
                                time_point=api_params['TimePoint'], 
                                station_codes=api_params['StationCode'],
                                data_source=api_params['DataSource']
                            )
                        
                        level_results[location_call_key] = {
                            'data': api_result,
                            'locations': [location_name],  # 单个位置
                            'level': level,
                            'area_type_code': level_data['area_type_code'],
                            'success': True,
                            'station_code': station_code,
                            'location_name': location_name
                        }
                        
                        self.logger.info(f"[MULTI_EXECUTE] 位置 '{location_name}' API调用成功")
                        
                    except Exception as e:
                        self.logger.error(f"[MULTI_EXECUTE] 位置 '{location_name}' API调用失败: {e}")
                        level_results[location_call_key] = {
                            'data': [],
                            'locations': [location_name],  # 单个位置
                            'level': level,
                            'area_type_code': level_data['area_type_code'],
                            'success': False,
                            'error': str(e),
                            'api_params': api_params,  # 保存实际使用的API参数
                            'station_code': station_code,
                            'location_name': location_name
                        }
            
            # 检查是否有成功的调用
            successful_levels = [level for level, result in level_results.items() if result.get('success')]
            if not successful_levels:
                self.logger.error("[MULTI_EXECUTE] 所有层级的API调用都失败")
                
                # 检查是否有HTTP错误信息可以用于错误恢复
                http_error_info = self._extract_http_error_info(level_results)
                if http_error_info:
                    self.logger.info("[MULTI_EXECUTE] 检测到HTTP错误，返回错误信息供统一错误恢复处理")
                    return {
                        "status": "error",
                        "response_type": "message",
                        "payload": {
                            "format": "text", 
                            "value": http_error_info['error_response']
                        },
                        "debug_info": {
                            "execution_path": "MULTI_LEVEL_API_HANDLER",
                            "http_status": http_error_info['http_status'],
                            "error_type": "api_call_failed",
                            "failed_levels": list(level_results.keys()),
                            "api_params": http_error_info.get('api_params', {})  # 包含实际使用的API参数
                        }
                    }
                
                # 如果没有可恢复的HTTP错误，直接转向SQL
                return self._route_to_sql_query(question, "所有层级的API调用都失败")
            
            # 合并结果
            return self._merge_multi_level_results(level_results, tool_name)
            
        except Exception as e:
            self.logger.error(f"[MULTI_EXECUTE] 多层级API执行异常: {e}")
            return self._route_to_sql_query(question, f"多层级API执行异常: {str(e)}")
    
    def _merge_multi_level_results(self, level_results: Dict[str, Dict], tool_name: str) -> Dict[str, Any]:
        """
        合并多层级API调用结果
        
        Args:
            level_results: 各层级的调用结果
            tool_name: 工具名称
            
        Returns:
            Dict[str, Any]: 合并后的统一格式结果
        """
        try:
            self.logger.info(f"[MERGE_RESULTS] 开始合并多层级结果")
            
            merged_data = []
            levels_info = {}
            total_records = 0
            
            for level, result_info in level_results.items():
                if not result_info.get('success'):
                    continue
                
                # 获取数据 - 处理底层API返回的完整响应格式
                api_response = result_info.get('data', {})
                level_data = []
                
                if isinstance(api_response, dict):
                    if api_response.get('status') == 'success':
                        payload = api_response.get('payload', {})
                        if isinstance(payload, dict):
                            level_data = payload.get('value', [])
                    else:
                        self.logger.warning(f"[MERGE_RESULTS] 层级 {level} API响应不成功: {api_response.get('status')}")
                        continue
                elif isinstance(api_response, list):
                    # 直接是数据数组
                    level_data = api_response
                
                # 为每条数据添加层级标识
                for item in level_data:
                    if isinstance(item, dict):
                        item['_level'] = level
                        item['_area_type'] = result_info['area_type_code']
                        merged_data.append(item)
                
                # 记录层级信息
                levels_info[level] = {
                    'locations': result_info['locations'],
                    'record_count': len(level_data),
                    'area_type_code': result_info['area_type_code']
                }
                
                total_records += len(level_data)
                self.logger.info(f"[MERGE_RESULTS] 层级 {level}: {len(level_data)} 条记录")
            
            self.logger.info(f"[MERGE_RESULTS] 合并完成，总记录数: {total_records}")
            
            return {
                "status": "success",
                "response_type": "data",
                "payload": {
                    "format": "dataframe",
                    "value": merged_data
                },
                "debug_info": {
                    "execution_path": "MULTI_LEVEL_API_HANDLER",
                    "tool_used": tool_name,
                    "levels_processed": list(levels_info.keys()),
                    "total_records": total_records,
                    "levels_info": levels_info
                }
            }
            
        except Exception as e:
            self.logger.error(f"[MERGE_RESULTS] 结果合并异常: {e}")
            return {
                "status": "error",
                "response_type": "message",
                "payload": {
                    "format": "text", 
                    "value": f"结果合并失败: {str(e)}"
                },
                "debug_info": {
                    "execution_path": "MULTI_LEVEL_API_HANDLER",
                    "error": str(e)
                }
            }
    
    # ==================== 原有方法继续 ====================
    
    def _handle_api_error(self, error: Exception, api_type: str, 
                         params: Dict[str, Any], question: str = "") -> Dict[str, Any]:
        """
        第四阶段智能API错误处理 - 集成完整的错误恢复机制
        
        Args:
            error: API异常
            api_type: API类型 (summary_report, comparison_report等)
            params: 执行参数
            question: 用户原始问题
            
        Returns:
            处理结果
        """
        start_time = time.time()
        error_monitor = get_error_monitoring_system()
        error_id = None
        
        try:
            self.logger.info(f"[API_ERROR_V4] 开始第四阶段智能错误处理")
            self.logger.info(f"[API_ERROR_V4] 错误类型: {type(error).__name__}")
            self.logger.info(f"[API_ERROR_V4] 错误信息: {str(error)}")
            self.logger.info(f"[API_ERROR_V4] API类型: {api_type}")
            
            # 第一步：错误分类
            classification_start = time.time()
            error_classifier = get_error_classifier()
            error_context = {
                "stage": "api_execution",
                "api_type": api_type,
                "original_params": params,
                "retry_count": params.get("_retry_count", 0),
                "user_question": question
            }
            
            error_classification = error_classifier.classify_error(str(error), error_context)
            classification_time = time.time() - classification_start
            
            self.logger.info(f"[API_ERROR_V4] 错误分类: {error_classification['error_type']}")
            self.logger.info(f"[API_ERROR_V4] 严重性: {error_classification['severity']}")
            self.logger.info(f"[API_ERROR_V4] 恢复策略: {error_classification['recovery_strategy']}")
            
            # 记录错误到监控系统
            error_id = error_monitor.record_error(error_classification, error_context)
            error_monitor.record_classification_time(classification_time)
            
            # 第二步：基于分类结果进行智能恢复
            recovery_start = time.time()
            llm_recovery = get_llm_error_recovery()
            recovery_context = {
                "available_tools": [api_type, "get_summary_report", "get_comparison_report"],
                "original_params": params,
                "retry_count": params.get("_retry_count", 0),
                "max_retries": 2,
                "error_id": error_id
            }
            
            recovery_result = llm_recovery.recover_from_error(
                error_classification, 
                question, 
                recovery_context
            )
            recovery_time = time.time() - recovery_start
            
            self.logger.info(f"[API_ERROR_V4] 恢复结果: {recovery_result.get('success', False)}")
            if recovery_result.get("success"):
                self.logger.info(f"[API_ERROR_V4] 恢复类型: {recovery_result.get('recovery_type', 'unknown')}")
            
            # 记录恢复时间
            error_monitor.record_recovery_time(recovery_time)
            
            # 第三步：根据恢复结果执行相应操作
            if recovery_result.get("success"):
                final_result = self._execute_recovery_action(recovery_result, api_type, params, question)
                
                # 记录成功恢复
                total_time = time.time() - start_time
                processing_times = {
                    "classification_time": classification_time,
                    "recovery_time": recovery_time,
                    "total_time": total_time
                }
                error_monitor.record_recovery_attempt(
                    error_id, 
                    recovery_result.get("recovery_type", "unknown"),
                    {"success": True, "final_result": final_result},
                    processing_times
                )
                error_monitor.record_total_processing_time(total_time)
                
                return final_result
            else:
                # 恢复失败，检查是否需要SQL回退
                if recovery_result.get("fallback_required"):
                    fallback_result = self._recommend_sql_fallback(error_classification, question, 
                                                                  {"original_params": params, "api_type": api_type})
                    
                    # 记录SQL回退
                    total_time = time.time() - start_time
                    processing_times = {
                        "classification_time": classification_time,
                        "recovery_time": recovery_time,
                        "total_time": total_time
                    }
                    error_monitor.record_recovery_attempt(
                        error_id,
                        "sql_fallback",
                        {"success": False, "fallback_result": fallback_result},
                        processing_times
                    )
                    error_monitor.record_total_processing_time(total_time)
                    
                    return fallback_result
                else:
                    clarification_result = self._create_clarification_response(recovery_result)
                    
                    # 记录澄清需求
                    total_time = time.time() - start_time
                    processing_times = {
                        "classification_time": classification_time,
                        "recovery_time": recovery_time,
                        "total_time": total_time
                    }
                    error_monitor.record_recovery_attempt(
                        error_id,
                        "clarification_required",
                        {"success": False, "clarification_result": clarification_result},
                        processing_times
                    )
                    error_monitor.record_total_processing_time(total_time)
                    
                    return clarification_result
                    
        except Exception as recovery_error:
            self.logger.error(f"[API_ERROR_V4] 错误恢复过程异常: {recovery_error}")
            
            # 记录恢复异常
            if error_id:
                total_time = time.time() - start_time
                error_monitor.record_recovery_attempt(
                    error_id,
                    "recovery_exception",
                    {"success": False, "exception": str(recovery_error)},
                    {"total_time": total_time}
                )
                error_monitor.record_total_processing_time(total_time)
            
            # 降级到传统错误处理
            return self._create_traditional_error_response(error, api_type)
    
    def _execute_recovery_action(self, recovery_result: Dict[str, Any], api_type: str, 
                               params: Dict[str, Any], question: str) -> Dict[str, Any]:
        """
        执行恢复操作
        
        Args:
            recovery_result: 恢复结果
            api_type: 原始API类型
            params: 原始参数
            question: 用户问题
            
        Returns:
            执行结果
        """
        recovery_type = recovery_result.get("recovery_type", "unknown")
        
        try:
            if recovery_type == "parameter_reextraction":
                # 参数重提取恢复
                return self._handle_parameter_reextraction_recovery(recovery_result, api_type, question)
            
            elif recovery_type == "tool_reselection":
                # 工具重选择恢复
                return self._handle_tool_reselection_recovery(recovery_result, question)
            
            elif recovery_type == "simple_retry":
                # 简单重试恢复
                return self._handle_simple_retry_recovery(recovery_result, api_type, params, question)
            
            elif recovery_type == "time_clarification":
                # 时间澄清恢复
                return self._handle_time_clarification_recovery(recovery_result, api_type, params, question)
            
            elif recovery_type == "location_clarification":
                # 地点澄清恢复
                return self._handle_location_clarification_recovery(recovery_result, api_type, params, question)
            
            elif recovery_type == "comprehensive_analysis":
                # 全面分析恢复
                return self._handle_comprehensive_analysis_recovery(recovery_result, question)
            
            else:
                self.logger.warning(f"[API_ERROR_V4] 未知恢复类型: {recovery_type}")
                return self._create_traditional_error_response(Exception(f"未知恢复类型: {recovery_type}"), api_type)
                
        except Exception as e:
            self.logger.error(f"[API_ERROR_V4] 执行恢复操作失败: {e}")
            return self._create_traditional_error_response(e, api_type)
    
    def _handle_parameter_reextraction_recovery(self, recovery_result: Dict[str, Any], 
                                              api_type: str, question: str) -> Dict[str, Any]:
        """处理参数重提取恢复"""
        extracted_params = recovery_result.get("extracted_params", {})
        
        self.logger.info(f"[API_ERROR_V4] 执行参数重提取恢复")
        self.logger.info(f"[API_ERROR_V4] 重提取的参数: {extracted_params}")
        
        # 根据API类型重新执行
        if api_type == "summary_report":
            return self._handle_summary_report_request(extracted_params, question)
        elif api_type == "comparison_report":
            return self._handle_comparison_report_request(extracted_params, question)
        else:
            # 默认使用综合报表
            return self._handle_summary_report_request(extracted_params, question)
    
    def _handle_tool_reselection_recovery(self, recovery_result: Dict[str, Any], question: str) -> Dict[str, Any]:
        """处理工具重选择恢复"""
        recommended_tool = recovery_result.get("recommended_tool")
        parameters = recovery_result.get("parameters", {})
        reason = recovery_result.get("reason", "")
        
        self.logger.info(f"[API_ERROR_V4] 执行工具重选择恢复")
        self.logger.info(f"[API_ERROR_V4] 推荐工具: {recommended_tool}")
        self.logger.info(f"[API_ERROR_V4] 选择理由: {reason}")
        
        # 执行新选择的工具
        if recommended_tool == "get_summary_report":
            return self._handle_summary_report_request(parameters, question)
        elif recommended_tool == "get_comparison_report":
            return self._handle_comparison_report_request(parameters, question)
        else:
            return self._create_clarification_response({
                "error": f"推荐的工具 {recommended_tool} 暂不支持"
            })
    
    def _handle_simple_retry_recovery(self, recovery_result: Dict[str, Any], api_type: str, 
                                    params: Dict[str, Any], question: str) -> Dict[str, Any]:
        """处理简单重试恢复"""
        retry_count = recovery_result.get("retry_count", 1)
        wait_seconds = recovery_result.get("wait_seconds", 0)
        
        self.logger.info(f"[API_ERROR_V4] 执行简单重试恢复")
        self.logger.info(f"[API_ERROR_V4] 重试次数: {retry_count}")
        self.logger.info(f"[API_ERROR_V4] 等待时间: {wait_seconds}秒")
        
        # 添加重试计数
        retry_params = params.copy()
        retry_params["_retry_count"] = retry_count
        
        # 如果需要等待，这里可以添加等待逻辑
        if wait_seconds > 0:
            import time
            time.sleep(min(wait_seconds, 5))  # 最多等待5秒
        
        # 重新执行原始API调用
        if api_type == "summary_report":
            return self._handle_summary_report_request(retry_params, question)
        elif api_type == "comparison_report":
            return self._handle_comparison_report_request(retry_params, question)
        else:
            return self._create_traditional_error_response(Exception("不支持的API类型重试"), api_type)
    
    def _handle_time_clarification_recovery(self, recovery_result: Dict[str, Any], api_type: str, 
                                          params: Dict[str, Any], question: str) -> Dict[str, Any]:
        """处理时间澄清恢复"""
        start_time = recovery_result.get("start_time")
        end_time = recovery_result.get("end_time")
        interpretation = recovery_result.get("interpretation", "")
        
        self.logger.info(f"[API_ERROR_V4] 执行时间澄清恢复")
        self.logger.info(f"[API_ERROR_V4] 澄清后时间范围: {start_time} 到 {end_time}")
        self.logger.info(f"[API_ERROR_V4] 解释: {interpretation}")
        
        # 更新参数中的时间信息
        updated_params = params.copy()
        updated_params["start_time"] = start_time
        updated_params["end_time"] = end_time
        
        # 重新执行API调用
        if api_type == "summary_report":
            return self._handle_summary_report_request(updated_params, question)
        elif api_type == "comparison_report":
            return self._handle_comparison_report_request(updated_params, question)
        else:
            return self._create_traditional_error_response(Exception("不支持的API类型"), api_type)
    
    def _handle_location_clarification_recovery(self, recovery_result: Dict[str, Any], api_type: str, 
                                              params: Dict[str, Any], question: str) -> Dict[str, Any]:
        """处理地点澄清恢复"""
        resolved_location = recovery_result.get("resolved_location")
        location_code = recovery_result.get("location_code")
        location_type = recovery_result.get("location_type")
        confidence = recovery_result.get("confidence", 0.0)
        
        self.logger.info(f"[API_ERROR_V4] 执行地点澄清恢复")
        self.logger.info(f"[API_ERROR_V4] 澄清后地点: {resolved_location}")
        self.logger.info(f"[API_ERROR_V4] 地点编码: {location_code}")
        self.logger.info(f"[API_ERROR_V4] 置信度: {confidence}")
        
        # 更新参数中的地点信息
        updated_params = params.copy()
        updated_params["location_name"] = resolved_location
        if location_code:
            updated_params["location_code"] = location_code
        
        # 重新执行API调用
        if api_type == "summary_report":
            return self._handle_summary_report_request(updated_params, question)
        elif api_type == "comparison_report":
            return self._handle_comparison_report_request(updated_params, question)
        else:
            return self._create_traditional_error_response(Exception("不支持的API类型"), api_type)
    
    def _handle_comprehensive_analysis_recovery(self, recovery_result: Dict[str, Any], question: str) -> Dict[str, Any]:
        """处理全面分析恢复"""
        requires_sql_fallback = recovery_result.get("requires_sql_fallback", False)
        user_clarification_needed = recovery_result.get("user_clarification_needed")
        recovery_plan = recovery_result.get("recovery_plan", {})
        
        self.logger.info(f"[API_ERROR_V4] 执行全面分析恢复")
        self.logger.info(f"[API_ERROR_V4] 需要SQL回退: {requires_sql_fallback}")
        self.logger.info(f"[API_ERROR_V4] 需要用户澄清: {bool(user_clarification_needed)}")
        
        if requires_sql_fallback:
            return {
                "status": "error",
                "response_type": "message",
                "payload": {
                    "format": "text",
                    "value": "外部服务暂时不可用，建议使用数据库查询方式。您可以尝试更改问题表达方式，系统将通过SQL查询为您提供相关数据。"
                },
                "debug_info": {
                    "execution_path": "EXTERNAL_API_HANDLER",
                    "error_type": "comprehensive_analysis_sql_fallback",
                    "recovery_plan": recovery_plan,
                    "sql_fallback_recommended": True
                }
            }
        elif user_clarification_needed:
            return {
                "status": "clarification_needed",
                "response_type": "message",
                "payload": {
                    "format": "text",
                    "value": user_clarification_needed
                },
                "debug_info": {
                    "execution_path": "EXTERNAL_API_HANDLER",
                    "error_type": "comprehensive_analysis_clarification",
                    "recovery_plan": recovery_plan
                }
            }
        else:
            # 尝试使用恢复计划中的建议
            if recovery_plan:
                return {
                    "status": "error",
                    "response_type": "message",
                    "payload": {
                        "format": "text",
                        "value": f"系统分析建议：{recovery_plan.get('suggestion', '请尝试重新表述问题或使用更具体的描述')}"
                    },
                    "debug_info": {
                        "execution_path": "EXTERNAL_API_HANDLER",
                        "error_type": "comprehensive_analysis_suggestion",
                        "recovery_plan": recovery_plan
                    }
                }
            else:
                return self._create_traditional_error_response(Exception("全面分析恢复无法确定处理方案"), "comprehensive_analysis")
    
    def _recommend_sql_fallback(self, error_classification: Dict[str, Any], question: str, 
                               api_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """推荐SQL回退 - 使用智能SQL回退处理器"""
        try:
            self.logger.info(f"[SQL_FALLBACK] 开始智能SQL回退处理")
            
            # 使用SQL回退处理器
            sql_fallback_handler = get_sql_fallback_handler()
            
            # 构建API上下文
            fallback_context = api_context or {}
            fallback_context.update({
                "original_question": question,
                "error_classification": error_classification,
                "api_handler": "external_api_handler"
            })
            
            # 执行SQL回退处理
            fallback_result = sql_fallback_handler.handle_sql_fallback(
                error_classification, 
                question, 
                fallback_context
            )
            
            self.logger.info(f"[SQL_FALLBACK] 智能回退处理完成")
            return fallback_result
            
        except Exception as e:
            self.logger.error(f"[SQL_FALLBACK] 智能回退处理失败: {e}")
            # 降级到传统回退消息
            return {
                "status": "error",
                "response_type": "message",
                "payload": {
                    "format": "text",
                    "value": f"外部API服务暂时不可用（错误类型：{error_classification.get('error_type', 'unknown')}）。建议使用数据库查询方式，请重新表述问题，系统将通过SQL查询为您提供数据。"
                },
                "debug_info": {
                    "execution_path": "EXTERNAL_API_HANDLER",
                    "error_type": "sql_fallback_recommended",
                    "error_classification": error_classification,
                    "original_question": question,
                    "fallback_reason": "api_error_recovery_failed",
                    "intelligent_fallback_failed": True,
                    "fallback_error": str(e)
                }
            }
    
    def _create_clarification_response(self, recovery_result: Dict[str, Any]) -> Dict[str, Any]:
        """创建澄清响应"""
        error_message = recovery_result.get("error", "需要更多信息来解决问题")
        clarification_needed = recovery_result.get("clarification_needed", error_message)
        
        return {
            "status": "clarification_needed",
            "response_type": "message",
            "payload": {
                "format": "text",
                "value": clarification_needed
            },
            "debug_info": {
                "execution_path": "EXTERNAL_API_HANDLER",
                "error_type": "recovery_clarification_needed",
                "recovery_result": recovery_result
            }
        }
    
    def _retry_summary_report(self, fixed_params: Dict[str, Any], question: str) -> Dict[str, Any]:
        """重试综合报表请求"""
        try:
            self.logger.info(f"[API_RETRY] 重试综合报表请求")
            return self._handle_summary_report_request(fixed_params, question)
        except Exception as e:
            self.logger.error(f"[API_RETRY] 重试失败: {e}")
            return self._create_traditional_error_response(e, "summary_report")
    
    def _retry_comparison_report(self, fixed_params: Dict[str, Any], question: str) -> Dict[str, Any]:
        """重试对比报表请求"""
        try:
            self.logger.info(f"[API_RETRY] 重试对比报表请求")
            return self._handle_comparison_report_request(fixed_params, question)
        except Exception as e:
            self.logger.error(f"[API_RETRY] 重试失败: {e}")
            return self._create_traditional_error_response(e, "comparison_report")
    
    def _create_fallback_response(self, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """创建降级响应"""
        fallback_message = llm_result.get('fallback_suggestion', 
                                        '外部服务暂时不可用。您可以尝试使用探索式查询（数据库查询）获取相关信息。')
        
        return {
            "status": "error",
            "response_type": "message", 
            "payload": {
                "format": "text",
                "value": fallback_message
            },
            "debug_info": {
                "execution_path": "EXTERNAL_API_HANDLER",
                "error_type": "api_failure_with_fallback",
                "llm_analysis": llm_result
            }
        }
    
    def _create_traditional_error_response(self, error: Exception, api_type: str) -> Dict[str, Any]:
        """创建传统错误响应"""
        return {
            "status": "error",
            "response_type": "message",
            "payload": {
                "format": "text",
                "value": f"外部API调用失败: {str(error)}"
            },
            "debug_info": {
                "execution_path": "EXTERNAL_API_HANDLER",
                "error_type": "api_failure_traditional",
                "api_type": api_type,
                "original_error": str(error)
            }
        }
    
    def get_token_status(self) -> Dict[str, Any]:
        """
        获取Token状态信息，用于诊断
        """
        if not self.token:
            return {
                "has_token": False,
                "token_preview": None,
                "expires_at": None,
                "is_valid": False,
                "time_to_expire": None,
                "status": "no_token"
            }
        
        current_time = time.time()
        time_to_expire = self.token_expires_at - current_time if self.token_expires_at else None
        buffer_time = 5 * 60  # 5分钟缓冲
        is_valid = (self.token_expires_at and 
                   current_time < (self.token_expires_at - buffer_time))
        
        return {
            "has_token": True,
            "token_preview": self.token[:20] + '...' if self.token else None,
            "expires_at": self.token_expires_at,
            "expires_at_readable": time.strftime('%Y-%m-%d %H:%M:%S', 
                                               time.localtime(self.token_expires_at)) if self.token_expires_at else None,
            "is_valid": is_valid,
            "time_to_expire": time_to_expire,
            "time_to_expire_readable": f"{int(time_to_expire // 3600)}h {int((time_to_expire % 3600) // 60)}m" if time_to_expire else None,
            "status": "valid" if is_valid else "expired_or_expiring"
        }
    
    def _handle_tool_selection_error(self, error: Exception, question: str) -> Dict[str, Any]:
        """
        第四阶段工具选择错误处理 - 集成智能恢复机制
        
        Args:
            error: 异常对象
            question: 用户问题
            
        Returns:
            Dict: 统一的错误响应格式
        """
        error_str = str(error)
        self.logger.error(f"[TOOL_ERROR_V4] 工具选择失败: {error_str}")
        
        try:
            # 第一步：错误分类
            error_classifier = get_error_classifier()
            error_context = {
                "stage": "tool_selection",
                "original_question": question,
                "retry_count": 0
            }
            
            error_classification = error_classifier.classify_error(error_str, error_context)
            self.logger.info(f"[TOOL_ERROR_V4] 错误分类: {error_classification['error_type']}")
            
            # 第二步：尝试智能工具重选择
            if error_classification['error_type'] == 'tool_selection_failed':
                smart_reselection = get_smart_tool_reselection()
                reselection_result = smart_reselection.reselect_tool(
                    original_tool="unknown",
                    failure_reason=error_str,
                    question=question,
                    parameters={},
                    context={"error_classification": error_classification}
                )
                
                if reselection_result.get("success"):
                    recommended_tool = reselection_result.get("recommended_tool")
                    confidence = reselection_result.get("confidence", 0.0)
                    
                    self.logger.info(f"[TOOL_ERROR_V4] 智能重选择成功: {recommended_tool} (置信度: {confidence})")
                    
                    return {
                        "status": "success",
                        "tool_name": recommended_tool,
                        "tool_params": {},
                        "original_question": question,
                        "selection_info": {
                            "method": "smart_reselection_recovery",
                            "confidence": confidence,
                            "selection_reason": reselection_result.get("selection_reason", ""),
                            "recovery_applied": True,
                            "original_error": error_str
                        }
                    }
            
            # 第三步：使用LLM错误恢复
            llm_recovery = get_llm_error_recovery()
            recovery_context = {
                "available_tools": ["get_summary_report", "get_comparison_report"],
                "original_question": question,
                "error_stage": "tool_selection"
            }
            
            recovery_result = llm_recovery.recover_from_error(
                error_classification, 
                question, 
                recovery_context
            )
            
            if recovery_result.get("success") and recovery_result.get("recovery_type") == "tool_reselection":
                recommended_tool = recovery_result.get("recommended_tool")
                if recommended_tool:
                    self.logger.info(f"[TOOL_ERROR_V4] LLM恢复成功，推荐工具: {recommended_tool}")
                    
                    return {
                        "status": "success",
                        "tool_name": recommended_tool,
                        "tool_params": recovery_result.get("parameters", {}),
                        "original_question": question,
                        "selection_info": {
                            "method": "llm_recovery",
                            "confidence": recovery_result.get("confidence", 0.7),
                            "recovery_type": "tool_reselection",
                            "recovery_applied": True,
                            "original_error": error_str
                        }
                    }
            
            # 第四步：传统降级方案
            self.logger.warning(f"[TOOL_ERROR_V4] 智能恢复失败，使用传统降级方案")
            
        except Exception as recovery_error:
            self.logger.error(f"[TOOL_ERROR_V4] 智能恢复过程异常: {recovery_error}")
        
        # 降级到传统方案
        fallback_tool = "get_summary_report"
        
        # 根据问题内容智能选择降级工具
        if any(keyword in question for keyword in ['对比', '比较', '环比', '同比']):
            fallback_tool = "get_comparison_report"
        
        return {
            "status": "error",
            "message": f"工具选择失败：{error_str}",
            "fallback_tool": fallback_tool,
            "fallback_suggestion": f"系统将使用默认工具（{fallback_tool}）处理您的查询。如果结果不理想，可以尝试重新表述问题或使用探索式查询。",
            "debug_info": {
                "execution_path": "EXTERNAL_API_HANDLER",
                "error_type": "tool_selection_failed_v4",
                "original_error": error_str,
                "original_question": question,
                "fallback_applied": True,
                "intelligent_recovery_attempted": True
            }
        }
    
    # === 统一LLM兜底机制实施方法 ===
    
    def _extract_time_params_with_unified_fallback(self, question: str, tool_name: str = None, grouped_locations: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        使用统一兜底机制的时间参数提取
        注意：LLM托底成功后会直接进行API调用并抛出SuccessfulAPIResponse异常来跳出流程
        """
        try:
            param_converter = get_param_converter()
            
            # 尝试传统时间解析
            time_range, error_info = param_converter.parse_time_with_unified_fallback(question, question)
            
            if time_range:
                return {
                    'time_description': time_range,
                    'extraction_method': 'traditional'
                }
            
            # 传统方法失败，使用统一LLM兜底
            self.logger.info("[UNIFIED_FALLBACK] 传统时间解析失败，启用LLM兜底")
            fallback_result = self.fallback_manager.handle_fallback(
                'time_parsing',
                question,
                {
                    'failed_time_desc': error_info or '无法解析时间',
                    'parsing_attempts': ['traditional_parsing'],
                    'tool_name': tool_name,
                    'grouped_locations': grouped_locations
                },
                error_info or '传统时间解析失败'
            )
            
            if fallback_result['status'] == 'success' and fallback_result.get('action') == 'continue':
                # LLM成功生成完整API参数，使用统一解析并直接API调用
                if tool_name and grouped_locations is not None:
                    llm_params = fallback_result.get('result_data', {})
                    self.logger.info("[UNIFIED_FALLBACK] LLM时间解析成功，直接进行API调用")
                    
                    # 使用专用的LLM托底处理器
                    from .intelligence.llm_fallback_processor import get_llm_fallback_processor
                    llm_processor = get_llm_fallback_processor()
                    
                    result = llm_processor.process_llm_fallback_result(llm_params, question, tool_name)
                    
                    if result['status'] == 'route_to_sql':
                        return {
                            'extraction_method': 'route_to_sql',
                            'error': result['reason']
                        }
                    else:
                        # 抛出特殊异常，携带API成功结果，上层捕获后直接返回
                        class SuccessfulAPIResponse(Exception):
                            def __init__(self, result):
                                self.result = result
                        
                        raise SuccessfulAPIResponse(result)
                else:
                    # 缺少必要上下文，无法直接API调用，降级处理
                    self.logger.warning("[UNIFIED_FALLBACK] LLM时间解析成功但缺少上下文信息，降级返回时间参数")
                    return {
                        'time_description': fallback_result['result_data'],
                        'extraction_method': 'llm_fallback_degraded'
                    }
            else:
                # LLM托底失败，转SQL
                return {
                    'extraction_method': 'route_to_sql',
                    'error': fallback_result.get('reason', 'LLM时间解析失败')
                }
                
        except Exception as e:
            if hasattr(e, 'result'):  # SuccessfulAPIResponse异常
                # 重新抛出，让调用方处理
                raise
            self.logger.error(f"[UNIFIED_FALLBACK] 时间参数提取异常: {e}")
            return {
                'extraction_method': 'error',
                'error': str(e)
            }
    
    def _unified_parameter_validation(self, question: str, tool_name: str, 
                                    time_params: Dict[str, Any], 
                                    grouped_locations: Dict[str, Any]) -> Dict[str, Any]:
        """统一参数验证和LLM兜底补充"""
        try:
            self.logger.info(f"[UNIFIED_VALIDATION] 开始参数验证: {tool_name}")
            
            # 检查基础参数
            missing_params = []
            
            # 检查时间参数
            if not time_params.get('time_description'):
                missing_params.append('time_description')
            
            # 检查对比查询的特殊参数
            if tool_name == 'get_comparison_report':
                if not time_params.get('contrast_time_description'):
                    missing_params.append('contrast_time_description')
            
            # 如果有缺失参数，尝试LLM补充
            if missing_params:
                self.logger.info(f"[UNIFIED_VALIDATION] 检测到缺失参数: {missing_params}")
                
                # 使用统一LLM兜底进行参数补充
                fallback_result = self.fallback_manager.handle_fallback(
                    'parameter_supplement',
                    question,
                    {
                        'missing_params': missing_params,
                        'tool_name': tool_name,
                        'grouped_locations': grouped_locations,
                        'existing_time_params': time_params
                    },
                    f'缺失关键参数: {missing_params}'
                )
                
                if fallback_result['status'] == 'success' and fallback_result.get('action') == 'continue':
                    # LLM成功补充参数，使用统一解析并直接API调用
                    llm_params = fallback_result.get('result_data', {})
                    self.logger.info(f"[UNIFIED_VALIDATION] LLM参数补充成功，使用统一解析")
                    
                    # 使用专用的LLM托底处理器
                    from .intelligence.llm_fallback_processor import get_llm_fallback_processor
                    llm_processor = get_llm_fallback_processor()
                    
                    result = llm_processor.process_llm_fallback_result(llm_params, question, tool_name)
                    
                    if result['status'] == 'route_to_sql':
                        return {
                            'status': 'route_to_sql',
                            'reason': result['reason']
                        }
                    else:
                        # 返回特殊状态，指示已完成API调用
                        return {
                            'status': 'api_completed',
                            'api_result': result,
                            'fallback_used': True
                        }
                else:
                    # LLM参数补充失败，转向SQL
                    return {
                        'status': 'route_to_sql',
                        'reason': fallback_result.get('reason', 'LLM参数补充失败')
                    }
            
            # 如果是对比查询且对比时间缺失，尝试智能恢复
            if (tool_name == 'get_comparison_report' and 
                not time_params.get('contrast_time_description')):
                
                contrast_result = self.fallback_manager.handle_fallback(
                    'contrast_time_recovery',
                    question,
                    {
                        'main_time': time_params.get('time_description', ''),
                        'comparison_type': self._detect_comparison_type(question),
                        'rule_inference_result': {}
                    },
                    '缺失对比时间参数'
                )
                
                if contrast_result['status'] == 'success' and contrast_result.get('action') == 'continue':
                    # LLM成功恢复对比时间，使用统一解析并直接API调用
                    llm_params = contrast_result.get('result_data', {})
                    self.logger.info(f"[UNIFIED_VALIDATION] LLM对比时间恢复成功，使用统一解析")
                    
                    try:
                        # 统一解析LLM输出的完整API参数
                        parsed_params = self._parse_parameters_unified(llm_params, question)
                        api_result = self._execute_api_call_with_parsed_params(parsed_params, question, tool_name)
                        
                        # 返回特殊状态，指示已完成API调用
                        return {
                            'status': 'api_completed',
                            'api_result': api_result,
                            'fallback_used': True
                        }
                    except Exception as e:
                        # LLM参数解析失败，直接转SQL
                        self.logger.error(f"[UNIFIED_VALIDATION] LLM对比时间恢复后解析失败: {e}")
                        return {
                            'status': 'route_to_sql',
                            'reason': f'LLM对比时间恢复解析失败: {str(e)}'
                        }
                else:
                    # LLM对比时间恢复失败，转向SQL
                    return {
                        'status': 'route_to_sql',
                        'reason': contrast_result.get('reason', 'LLM对比时间恢复失败')
                    }
            
            return {
                'status': 'success',
                'updated_params': time_params,
                'fallback_used': False
            }
            
        except Exception as e:
            self.logger.error(f"[UNIFIED_VALIDATION] 参数验证异常: {e}")
            return {
                'status': 'route_to_sql',
                'reason': f'参数验证异常: {str(e)}'
            }
    
    def _execute_api_calls_with_unified_recovery(self, converted_params: Dict[str, Any], 
                                               question: str, tool_name: str) -> Dict[str, Any]:
        """执行API调用并集成统一错误恢复机制"""
        try:
            self.logger.info(f"[UNIFIED_RECOVERY] 开始API调用: {tool_name}")
            
            # 执行原有的多层级API调用
            result = self._execute_multi_level_api_calls(converted_params, question)
            
            # 检查是否有HTTP错误需要恢复
            if result.get('status') == 'error' and 'http_status' in result.get('debug_info', {}):
                http_status = result['debug_info']['http_status']
                error_response = result.get('payload', {}).get('value', {})
                # 从错误信息中提取实际使用的API参数
                api_params = result.get('debug_info', {}).get('api_params', {})
                
                # 使用API错误分类器分析错误
                error_analysis = self.error_classifier.classify_api_error(
                    http_status, error_response, api_params
                )
                
                self.logger.info(f"[UNIFIED_RECOVERY] 错误分析结果: {error_analysis}")
                
                # 如果错误可恢复，尝试LLM恢复
                if error_analysis.get('recoverable', False):
                    recovery_result = self.fallback_manager.handle_fallback(
                        'api_error_recovery',
                        question,
                        {
                            'http_status': http_status,
                            'error_response': error_response,
                            'api_params': api_params,
                            'tool_name': tool_name,
                            'error_analysis': error_analysis
                        },
                        f'HTTP {http_status} 错误'
                    )
                    
                    if recovery_result['status'] == 'success' and recovery_result.get('action') == 'retry':
                        # 重试API调用
                        self.logger.info("[UNIFIED_RECOVERY] 错误恢复成功，重试API调用")
                        
                        # 更新参数并重试
                        updated_params = recovery_result.get('result_data', {})
                        if updated_params:
                            # 重新转换参数
                            updated_converted_params = self._update_converted_params(
                                converted_params, updated_params
                            )
                            # 重试调用
                            retry_result = self._execute_multi_level_api_calls(
                                updated_converted_params, question
                            )
                            
                            if retry_result.get('status') == 'success':
                                return retry_result
                
                # 错误无法恢复或恢复失败，转向SQL
                self.logger.warning(f"[UNIFIED_RECOVERY] API错误无法恢复，转向SQL查询")
                return self._route_to_sql_query(question, error_analysis.get('suggested_action', 'API调用失败'))
            
            return result
            
        except Exception as e:
            self.logger.error(f"[UNIFIED_RECOVERY] API调用恢复异常: {e}")
            return self._route_to_sql_query(question, f'API调用异常: {str(e)}')
    
    def _detect_comparison_type(self, question: str) -> str:
        """检测对比类型"""
        if any(kw in question for kw in ['环比', '上月', '上期', '上周']):
            return '环比'
        elif any(kw in question for kw in ['同比', '去年', '上年', '同期']):
            return '同比'
        else:
            return '对比'
    
    def _update_converted_params(self, original_params: Dict[str, Any], 
                               updated_params: Dict[str, Any]) -> Dict[str, Any]:
        """更新转换后的参数"""
        try:
            # 复制原参数
            new_params = original_params.copy()
            
            # 更新API参数
            if 'api_params_all_levels' in new_params:
                for level_key, level_params in new_params['api_params_all_levels'].items():
                    if isinstance(level_params, dict):
                        level_params.update(updated_params)
            
            return new_params
            
        except Exception as e:
            self.logger.error(f"[UNIFIED_RECOVERY] 参数更新异常: {e}")
            return original_params
    
    def _extract_time_point_from_params(self, time_params: Dict[str, Any]) -> List[str]:
        """从时间参数中提取TimePoint数组"""
        try:
            # 优先从main_time_range获取（LLM兜底的结果）
            if 'main_time_range' in time_params:
                time_range = time_params['main_time_range']
                if isinstance(time_range, list) and len(time_range) >= 2:
                    return time_range
            
            # 其次从time_description获取
            if 'time_description' in time_params:
                time_desc = time_params['time_description']
                if isinstance(time_desc, list):
                    return time_desc
                elif isinstance(time_desc, str):
                    # 尝试解析字符串格式的时间
                    return [time_desc]
            
            # 默认返回空数组
            self.logger.warning("[API_PARAMS] 无法提取有效的TimePoint参数")
            return []
            
        except Exception as e:
            self.logger.error(f"[API_PARAMS] TimePoint提取异常: {e}")
            return []
    
    def _convert_data_source_to_code(self, data_source: str) -> int:
        """将数据源字符串转换为API编码"""
        mapping = {
            '原始实况': 0,
            '审核实况': 1,
            '原始标况': 2,
            '审核标况': 3
        }
        
        code = mapping.get(data_source, 1)  # 默认为审核实况
        self.logger.debug(f"[API_PARAMS] 数据源转换: '{data_source}' -> {code}")
        return code
    
    def _extract_contrast_time_from_params(self, time_params: Dict[str, Any]) -> List[str]:
        """从时间参数中提取ContrastTime数组"""
        try:
            # 优先从contrast_time_range获取（LLM兜底的结果）
            if 'contrast_time_range' in time_params:
                contrast_range = time_params['contrast_time_range']
                if isinstance(contrast_range, list) and len(contrast_range) >= 2:
                    return contrast_range
            
            # 其次从contrast_time_description获取
            if 'contrast_time_description' in time_params:
                contrast_desc = time_params['contrast_time_description']
                if isinstance(contrast_desc, list):
                    return contrast_desc
                elif isinstance(contrast_desc, str):
                    # 尝试解析字符串格式的对比时间
                    return [contrast_desc]
            
            # 默认返回空数组
            self.logger.warning("[API_PARAMS] 无法提取有效的ContrastTime参数")
            return []
            
        except Exception as e:
            self.logger.error(f"[API_PARAMS] ContrastTime提取异常: {e}")
            return []
    
    def _extract_http_error_info(self, level_results: Dict[str, Dict]) -> Optional[Dict[str, Any]]:
        """从层级结果中提取HTTP错误信息"""
        try:
            for level, result in level_results.items():
                if not result.get('success') and 'error' in result:
                    error_str = result['error']
                    
                    # 解析HTTP错误信息
                    # 格式: "HTTP请求失败: 500, 响应: {...}"
                    import re
                    http_match = re.search(r'HTTP请求失败:\s*(\d+),\s*响应:\s*(.+)', error_str)
                    if http_match:
                        http_status = int(http_match.group(1))
                        error_response_str = http_match.group(2)
                        
                        # 尝试解析JSON响应
                        try:
                            import json
                            error_response = json.loads(error_response_str)
                        except:
                            error_response = {"raw_error": error_response_str}
                        
                        self.logger.debug(f"[HTTP_ERROR_EXTRACT] 提取到HTTP错误: {http_status}")
                        return {
                            'http_status': http_status,
                            'error_response': error_response,
                            'level': level,
                            'api_params': result.get('api_params', {})  # 包含实际使用的API参数
                        }
            
            return None
            
        except Exception as e:
            self.logger.error(f"[HTTP_ERROR_EXTRACT] HTTP错误信息提取异常: {e}")
            return None

@external_api_blueprint.route('/status', methods=['GET'])
def handle_status():
    """获取外部API处理器状态接口"""
    handler = get_external_api_handler()
    return jsonify(handler.get_token_status())

@external_api_blueprint.route('/test-connection', methods=['POST'])
def handle_test_connection():
    """测试外部API连接接口"""
    handler = get_external_api_handler()
    return jsonify(handler.test_connection())

@external_api_blueprint.route('/error-monitoring/statistics', methods=['GET'])
def handle_error_statistics():
    """获取错误统计信息接口"""
    try:
        time_range = request.args.get('time_range', '24h')
        error_monitor = get_error_monitoring_system()
        statistics = error_monitor.get_error_statistics(time_range)
        return jsonify({
            "status": "success",
            "data": statistics
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@external_api_blueprint.route('/error-monitoring/performance', methods=['GET'])
def handle_performance_metrics():
    """获取性能指标接口"""
    try:
        error_monitor = get_error_monitoring_system()
        metrics = error_monitor.get_performance_metrics()
        return jsonify({
            "status": "success",
            "data": metrics
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@external_api_blueprint.route('/error-monitoring/health', methods=['GET'])
def handle_system_health():
    """获取系统健康度接口"""
    try:
        error_monitor = get_error_monitoring_system()
        health = error_monitor.get_system_health()
        return jsonify({
            "status": "success",
            "data": health
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@external_api_blueprint.route('/error-monitoring/recovery-analysis', methods=['GET'])
def handle_recovery_analysis():
    """获取恢复策略分析接口"""
    try:
        error_monitor = get_error_monitoring_system()
        analysis = error_monitor.get_recovery_strategy_analysis()
        return jsonify({
            "status": "success",
            "data": analysis
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@external_api_blueprint.route('/error-monitoring/trend', methods=['GET'])
def handle_hourly_trend():
    """获取小时级趋势接口"""
    try:
        hours = int(request.args.get('hours', 24))
        error_monitor = get_error_monitoring_system()
        trend = error_monitor.get_hourly_trend(hours)
        return jsonify({
            "status": "success",
            "data": trend
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@external_api_blueprint.route('/error-monitoring/export', methods=['GET'])
def handle_export_statistics():
    """导出统计信息接口"""
    try:
        format_type = request.args.get('format', 'json')
        error_monitor = get_error_monitoring_system()
        exported_data = error_monitor.export_statistics(format_type)
        
        if format_type == 'csv':
            return exported_data, 200, {
                'Content-Type': 'text/csv',
                'Content-Disposition': 'attachment; filename=error_statistics.csv'
            }
        else:
            return exported_data, 200, {'Content-Type': 'application/json'}
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500