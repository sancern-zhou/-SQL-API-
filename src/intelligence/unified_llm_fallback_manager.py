#!/usr/bin/env python3
"""
统一LLM兜底管理器
Unified LLM Fallback Manager

负责处理所有类型查询的LLM兜底机制，包括：
- 时间解析兜底
- 对比时间恢复兜底  
- 参数补充兜底
- API错误恢复兜底
- 结果验证兜底
"""

import logging
import yaml
import os
from datetime import datetime
from typing import Dict, Any, Optional
import json

class UnifiedLLMFallbackManager:
    """统一LLM兜底管理器 - 所有查询类型共用"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path or self._get_default_config_path()
        self.fallback_config = self._load_fallback_config()
        
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        return os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'routing_config.yaml')
        
    def _load_fallback_config(self) -> Dict[str, Any]:
        """加载兜底配置"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    return config.get('unified_llm_fallback', {})
            else:
                self.logger.warning(f"[UNIFIED_FALLBACK] 配置文件不存在: {self.config_path}")
                return self._get_default_config()
        except Exception as e:
            self.logger.error(f"[UNIFIED_FALLBACK] 配置加载失败: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'enabled': True,
            'global_settings': {
                'timeout_seconds': 10,
                'max_retry': 2,
                'confidence_threshold': 0.6,
                'debug_mode': True
            },
            'fallback_types': {
                'time_parsing': {'enabled': True, 'priority': 1, 'success_threshold': 0.7},
                'contrast_time_recovery': {'enabled': True, 'priority': 1, 'success_threshold': 0.8},
                'parameter_supplement': {'enabled': True, 'priority': 2, 'success_threshold': 0.8},
                'api_error_recovery': {'enabled': True, 'priority': 3, 'success_threshold': 0.6},
                'result_validation': {'enabled': True, 'priority': 4, 'success_threshold': 0.5},
                'complex_query_processing': {'enabled': True, 'priority': 1, 'success_threshold': 0.7}
            }
        }
        
    def handle_fallback(self, 
                       fallback_type: str,
                       question: str, 
                       context: Dict[str, Any],
                       error_info: str = "") -> Dict[str, Any]:
        """
        统一LLM兜底处理入口
        
        Args:
            fallback_type: 兜底类型
                - 'time_parsing' - 时间解析失败
                - 'contrast_time_recovery' - 对比时间推断失败  
                - 'parameter_supplement' - 参数补充
                - 'api_error_recovery' - API错误恢复
                - 'result_validation' - 结果验证失败
            question: 原始用户查询
            context: 上下文数据
            error_info: 错误详情
            
        Returns:
            统一格式的兜底结果
        """
        self.logger.info(f"[UNIFIED_FALLBACK] 开始{fallback_type}兜底处理")
        
        try:
            # 检查兜底类型是否启用
            if not self._is_fallback_enabled(fallback_type):
                return self._create_fallback_result('disabled', f'{fallback_type}兜底已禁用')
            
            # 构建统一的LLM调用上下文
            llm_context = self._build_llm_context(fallback_type, question, context, error_info)
            
            # 调用统一LLM处理器
            llm_result = self._call_unified_llm_processor(llm_context)
            
            # 解析并标准化LLM响应
            parsed_result = self._parse_llm_response(fallback_type, llm_result)
            
            # 记录兜底结果
            self._log_fallback_result(fallback_type, parsed_result)
            
            return parsed_result
            
        except Exception as e:
            self.logger.error(f"[UNIFIED_FALLBACK] {fallback_type}兜底异常: {e}")
            return self._create_fallback_result('error', f'兜底处理异常: {str(e)}')
    
    def _is_fallback_enabled(self, fallback_type: str) -> bool:
        """检查兜底类型是否启用"""
        if not self.fallback_config.get('enabled', True):
            return False
        
        fallback_types = self.fallback_config.get('fallback_types', {})
        type_config = fallback_types.get(fallback_type, {})
        return type_config.get('enabled', True)
    
    def _build_llm_context(self, fallback_type: str, question: str, 
                          context: Dict[str, Any], error_info: str) -> Dict[str, Any]:
        """构建统一的LLM调用上下文"""
        # 准备统一格式的上下文信息
        context_info = self._prepare_context_info(fallback_type, context)
        issue_description = self._get_issue_description(fallback_type, context, error_info)
        
        # 统一的上下文格式
        return {
            'question': question,
            'fallback_type': self._get_fallback_type_description(fallback_type),
            'issue_description': issue_description,
            'context_info': context_info,
            'timestamp': datetime.now().isoformat()
        }
    
    def _prepare_context_info(self, fallback_type: str, context: Dict[str, Any]) -> str:
        """根据托底类型准备上下文信息"""
        context_parts = []
        
        # 通用上下文信息
        if 'grouped_locations' in context:
            locations = context['grouped_locations']
            if locations:
                context_parts.append(f"地理位置: {locations}")
        
        if 'time_parameters' in context:
            time_params = context['time_parameters']
            if time_params:
                context_parts.append(f"时间参数: {time_params}")
                
        if 'tool_name' in context:
            context_parts.append(f"选择工具: {context['tool_name']}")
        
        # 特定类型的上下文
        if fallback_type == 'time_parsing':
            if 'failed_time_desc' in context:
                context_parts.append(f"解析失败的时间: {context['failed_time_desc']}")
            if 'completed_time' in context:
                context_parts.append(f"年份补全后时间: {context['completed_time']}")
        
        elif fallback_type == 'contrast_time_recovery':
            if 'main_time' in context:
                context_parts.append(f"主时间: {context['main_time']}")
            if 'comparison_type' in context:
                context_parts.append(f"对比类型: {context['comparison_type']}")
        
        elif fallback_type == 'parameter_supplement':
            if 'missing_params' in context:
                context_parts.append(f"缺失参数: {context['missing_params']}")
        
        elif fallback_type == 'api_error_recovery':
            if 'http_status' in context:
                context_parts.append(f"HTTP状态码: {context['http_status']}")
            if 'error_response' in context:
                context_parts.append(f"API错误响应: {context['error_response']}")
            if 'api_params' in context:
                context_parts.append(f"API调用参数: {context['api_params']}")
        
        elif fallback_type == 'result_validation':
            if 'total_records' in context:
                context_parts.append(f"返回记录数: {context['total_records']}")
            if 'quality_issues' in context:
                context_parts.append(f"质量问题: {context['quality_issues']}")
        
        elif fallback_type == 'complex_query_processing':
            if 'complexity_reason' in context:
                context_parts.append(f"复杂性原因: {context['complexity_reason']}")
            if 'time_param_count' in context:
                context_parts.append(f"时间参数数量: {context['time_param_count']}")
        
        return "\n".join(context_parts) if context_parts else "无特定上下文"
    
    def _get_issue_description(self, fallback_type: str, context: Dict[str, Any], error_info: str) -> str:
        """根据托底类型生成问题描述"""
        descriptions = {
            'time_parsing': '时间解析失败，无法识别时间表达式',
            'contrast_time_recovery': '对比查询缺少对比时间参数',
            'parameter_supplement': '查询参数不完整，需要补充',
            'api_error_recovery': f"API调用失败: {error_info or '未知错误'}",
            'result_validation': '返回结果质量不佳或数据异常',
            'complex_query_processing': '检测到复杂查询，包含多个时间参数或复杂分析需求'
        }
        
        return descriptions.get(fallback_type, f'遇到处理问题: {error_info or "未知问题"}')
    
    def _get_fallback_type_description(self, fallback_type: str) -> str:
        """获取托底类型的中文描述"""
        descriptions = {
            'time_parsing': '时间解析托底',
            'contrast_time_recovery': '对比时间恢复托底',
            'parameter_supplement': '参数补充托底',
            'api_error_recovery': 'API错误恢复托底',
            'result_validation': '结果验证托底',
            'complex_query_processing': '复杂查询处理托底'
        }
        return descriptions.get(fallback_type, fallback_type)
    
    def _call_unified_llm_processor(self, llm_context: Dict[str, Any]) -> Dict[str, Any]:
        """调用统一LLM处理器"""
        try:
            # 尝试相对导入，失败则使用绝对导入
            try:
                from ..utils.prompt_loader import get_prompt
            except ImportError:
                from utils.prompt_loader import get_prompt
            
            # 构建统一提示词 - 使用新的统一模板
            prompt = get_prompt(
                'external_api_handler',
                'unified_fallback',
                **llm_context
            )
            
            # 获取VannaService实例
            vanna_service = self._get_vanna_service()
            if not vanna_service:
                return {
                    'status': 'error',
                    'reason': 'LLM服务不可用'
                }
            
            # 调用LLM
            response = vanna_service._call_llm_for_analysis(prompt)
            self.logger.debug(f"[UNIFIED_FALLBACK] LLM原始响应: {response}")
            
            # 解析LLM响应
            result = self._parse_llm_judgment_response(response)
            self.logger.debug(f"[UNIFIED_FALLBACK] LLM解析结果: {result}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"[UNIFIED_FALLBACK] LLM调用异常: {e}")
            return {
                'status': 'error',
                'reason': f'LLM调用异常: {str(e)}'
            }
    
    def _get_vanna_service(self):
        """获取VannaService实例"""
        try:
            from flask import current_app
            return getattr(current_app, 'vanna_service', None)
        except:
            return None
    
    def _parse_llm_judgment_response(self, response: str) -> Dict[str, Any]:
        """解析LLM响应"""
        try:
            import re
            
            # 尝试提取JSON
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                return json.loads(json_str)
            
            # 尝试直接解析JSON
            if response.strip().startswith('{'):
                return json.loads(response.strip())
            
            # 解析失败，返回错误
            return {
                'status': 'error',
                'reason': f'无法解析LLM响应: {response[:200]}...'
            }
            
        except json.JSONDecodeError as e:
            return {
                'status': 'error', 
                'reason': f'JSON解析失败: {str(e)}'
            }
        except Exception as e:
            return {
                'status': 'error',
                'reason': f'响应解析异常: {str(e)}'
            }
    
    def _parse_llm_response(self, fallback_type: str, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """解析并标准化LLM响应"""
        try:
            # 检查LLM调用是否成功
            if llm_result.get('status') == 'error':
                return self._create_fallback_result('failed', llm_result.get('reason', 'LLM调用失败'))
            
            # 统一处理所有类型的响应格式
            return self._parse_unified_response(fallback_type, llm_result)
                
        except Exception as e:
            self.logger.error(f"[UNIFIED_FALLBACK] 响应解析异常: {e}")
            return self._create_fallback_result('error', f'响应解析异常: {str(e)}')
    
    def _parse_time_parsing_response(self, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """解析时间解析响应"""
        if llm_result.get('action') == 'success' and llm_result.get('parameters', {}).get('time_description'):
            time_range = llm_result['parameters']['time_description']
            if isinstance(time_range, list) and len(time_range) == 2:
                return self._create_fallback_result('success', 'LLM时间解析成功', time_range)
        
        if llm_result.get('status') == 'success' and llm_result.get('result_data'):
            return self._create_fallback_result('success', 'LLM时间解析成功', llm_result['result_data'])
        
        return self._create_fallback_result('failed', llm_result.get('reason', 'LLM时间解析失败'))
    
    def _parse_contrast_time_response(self, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """解析对比时间恢复响应"""
        # 处理标准API格式响应
        if llm_result.get('action') == 'success' and llm_result.get('parameters', {}).get('comparison_time_description'):
            comparison_time = llm_result['parameters']['comparison_time_description']
            if isinstance(comparison_time, list) and len(comparison_time) >= 2:
                # 转换为时间描述格式
                start_time = comparison_time[0]
                import re
                time_match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', start_time)
                if time_match:
                    year = time_match.group(1)
                    month = int(time_match.group(2))
                    day = int(time_match.group(3))
                    
                    if day == 1:
                        contrast_time = f"{year}年{month}月"
                    else:
                        contrast_time = f"{year}年{month}月{day}日"
                        
                    return self._create_fallback_result('success', 'LLM对比时间恢复成功', contrast_time)
        
        # 处理标准对比时间分析格式
        if llm_result.get('status') == 'success' and llm_result.get('contrast_time'):
            return self._create_fallback_result('success', 'LLM对比时间恢复成功', llm_result['contrast_time'])
        
        return self._create_fallback_result('failed', llm_result.get('reason', 'LLM对比时间恢复失败'))
    
    def _parse_parameter_supplement_response(self, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """解析参数补充响应"""
        if llm_result.get('action') == 'success' and llm_result.get('parameters'):
            return self._create_fallback_result('success', 'LLM参数补充成功', llm_result['parameters'])
        
        return self._create_fallback_result('failed', llm_result.get('reason', 'LLM参数补充失败'))
    
    def _parse_api_error_recovery_response(self, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """解析API错误恢复响应"""
        # 检查重试响应格式（支持parameters和result_data两种字段）
        if llm_result.get('action') == 'retry' and (llm_result.get('parameters') or llm_result.get('result_data')):
            result_data = llm_result.get('parameters') or llm_result.get('result_data')
            return {
                'status': 'success',
                'action': 'retry',
                'result_data': result_data,
                'reason': 'LLM API错误恢复成功，建议重试',
                'timestamp': datetime.now().isoformat(),
                'fallback_used': True
            }
        elif llm_result.get('action') == 'route_to_sql':
            return {
                'status': 'failed',
                'action': 'route_to_sql',
                'reason': llm_result.get('reason', 'LLM建议转向SQL查询'),
                'timestamp': datetime.now().isoformat(),
                'fallback_used': True
            }
        
        return self._create_fallback_result('failed', llm_result.get('reason', 'LLM API错误恢复失败'))
    
    def _parse_result_validation_response(self, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """解析结果验证响应"""
        if llm_result.get('action') == 'continue':
            return self._create_fallback_result('success', 'LLM结果验证通过')
        elif llm_result.get('action') == 'route_to_sql':
            return {
                'status': 'failed',
                'action': 'route_to_sql',
                'reason': llm_result.get('reason', 'LLM建议转向SQL查询'),
                'timestamp': datetime.now().isoformat(),
                'fallback_used': True
            }
        
        return self._create_fallback_result('failed', llm_result.get('reason', 'LLM结果验证失败'))
    
    def _parse_unified_response(self, fallback_type: str, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """解析统一格式的LLM响应"""
        try:
            status = llm_result.get('status', 'failed')
            action = llm_result.get('action', 'route_to_sql')
            result_data = llm_result.get('result_data')
            reasoning = llm_result.get('reasoning', '')
            confidence = llm_result.get('confidence', 0.6)
            
            # 根据action确定处理结果
            if action == 'direct_answer':
                # 复杂查询直接回答
                return {
                    'status': 'success',
                    'action': 'direct_answer',
                    'result_data': result_data,
                    'reason': f'LLM直接回答: {reasoning}',
                    'confidence': confidence,
                    'timestamp': datetime.now().isoformat(),
                    'fallback_used': True
                }
            elif action == 'retry' and result_data:
                # API参数修复，建议重试
                return {
                    'status': 'success',
                    'action': 'retry',
                    'result_data': result_data,
                    'reason': f'LLM参数修复成功: {reasoning}',
                    'confidence': confidence,
                    'timestamp': datetime.now().isoformat(),
                    'fallback_used': True
                }
            elif action == 'continue' and result_data:
                # 参数补充或时间解析成功
                return {
                    'status': 'success',
                    'action': 'continue',
                    'result_data': result_data,
                    'reason': f'LLM处理成功: {reasoning}',
                    'confidence': confidence,
                    'timestamp': datetime.now().isoformat(),
                    'fallback_used': True
                }
            elif action == 'route_to_sql' or status == 'failed':
                # 转向SQL查询
                return {
                    'status': 'failed',
                    'action': 'route_to_sql',
                    'reason': llm_result.get('reason') or reasoning or 'LLM建议转向SQL查询',
                    'confidence': confidence,
                    'timestamp': datetime.now().isoformat(),
                    'fallback_used': True
                }
            else:
                # 其他情况默认成功
                return {
                    'status': 'success' if status == 'success' else 'failed',
                    'action': 'continue' if status == 'success' else 'route_to_sql',
                    'result_data': result_data,
                    'reason': reasoning or llm_result.get('reason', 'LLM处理完成'),
                    'confidence': confidence,
                    'timestamp': datetime.now().isoformat(),
                    'fallback_used': True
                }
                
        except Exception as e:
            self.logger.error(f"[UNIFIED_FALLBACK] 统一响应解析异常: {e}")
            return self._create_fallback_result('error', f'响应解析异常: {str(e)}')
    
    def _create_fallback_result(self, status: str, reason: str, 
                               result_data: Any = None) -> Dict[str, Any]:
        """创建标准化的兜底结果"""
        return {
            'status': status,  # 'success', 'partial_success', 'failed', 'disabled', 'error'
            'action': self._determine_action(status),  # 'continue', 'route_to_sql', 'retry'
            'result_data': result_data,
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'fallback_used': True
        }
    
    def _determine_action(self, status: str) -> str:
        """根据状态确定后续动作"""
        if status == 'success':
            return 'continue'
        elif status == 'partial_success':
            return 'continue'
        else:
            return 'route_to_sql'
    
    def _log_fallback_result(self, fallback_type: str, result: Dict[str, Any]):
        """记录兜底结果"""
        status = result.get('status', 'unknown')
        reason = result.get('reason', '无原因')
        
        if status == 'success':
            self.logger.info(f"[UNIFIED_FALLBACK] {fallback_type}兜底成功: {reason}")
        elif status == 'failed':
            self.logger.warning(f"[UNIFIED_FALLBACK] {fallback_type}兜底失败: {reason}")
        else:
            self.logger.debug(f"[UNIFIED_FALLBACK] {fallback_type}兜底状态: {status}, 原因: {reason}")

# 全局单例
_unified_fallback_manager = None

def get_unified_llm_fallback_manager() -> UnifiedLLMFallbackManager:
    """获取统一LLM兜底管理器单例"""
    global _unified_fallback_manager
    if _unified_fallback_manager is None:
        _unified_fallback_manager = UnifiedLLMFallbackManager()
    return _unified_fallback_manager