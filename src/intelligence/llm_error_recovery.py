"""
LLM错误恢复器 - 第四阶段智能错误恢复
基于错误分类结果，使用LLM进行智能错误恢复和重新判断
"""

import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from .error_classifier import ErrorType, ErrorSeverity, get_error_classifier

logger = logging.getLogger(__name__)

class LLMErrorRecovery:
    """LLM智能错误恢复器"""
    
    def __init__(self):
        self.error_classifier = get_error_classifier()
        self.vanna_service = None
        self.recovery_prompts = self._load_recovery_prompts()
        
    def _get_vanna_service(self):
        """延迟获取vanna_service以避免循环导入"""
        if self.vanna_service is None:
            try:
                from ..vanna_service import get_vanna_service
                self.vanna_service = get_vanna_service()
            except ImportError as e:
                logger.error(f"无法导入vanna_service: {e}")
                return None
        return self.vanna_service
    
    def _load_recovery_prompts(self) -> Dict[str, str]:
        """加载错误恢复提示词模板"""
        return {
            "parameter_reextraction": """
你是一个智能参数提取专家。用户的原始问题是："{original_question}"

之前的参数提取失败了，错误信息：{error_message}

缺失或错误的参数：{failed_params}

请重新分析用户问题，提取正确的参数。你需要：
1. 分析用户的真实意图
2. 识别时间、地点、查询类型等关键信息
3. 对于模糊或缺失的信息，提供合理的默认值或推理

请返回JSON格式的参数，包含：
- location_name: 地点名称
- start_time: 开始时间 (YYYY-MM-DD)
- end_time: 结束时间 (YYYY-MM-DD)
- query_type: 查询类型
- additional_filters: 其他筛选条件

如果某些参数仍然无法确定，请在need_clarification字段中说明需要用户澄清的内容。
""",
            
            "tool_reselection": """
你是一个智能工具选择专家。用户问题："{original_question}"

之前选择的工具执行失败：{error_message}

可用的工具列表：{available_tools}

请重新分析用户需求，选择更合适的工具。考虑：
1. 用户的查询意图（对比分析、趋势查询、实时数据等）
2. 数据的时间范围和地理范围
3. 工具的适用场景和限制

请返回JSON格式，包含：
- recommended_tool: 推荐工具名称
- reason: 选择理由
- alternative_tools: 备选工具列表
- parameters: 调整后的参数
""",
            
            "time_clarification": """
你是一个时间解析专家。用户提到的时间表达："{time_expression}"

时间解析失败，错误：{error_message}

请帮助解析这个时间表达，考虑：
1. 当前时间是2025年7月
2. 相对时间表达（如"上周"、"本月"）
3. 时间范围的起止时间

请返回JSON格式：
- start_time: 开始时间 (YYYY-MM-DD)
- end_time: 结束时间 (YYYY-MM-DD)
- interpretation: 解析说明
- confidence: 解析置信度 (0-1)
""",
            
            "location_clarification": """
你是一个地理位置解析专家。用户提到的地点："{location_expression}"

地点解析失败，错误：{error_message}

已知的地理映射信息：{geo_mappings}

请帮助解析这个地点，考虑：
1. 可能的同义词或简称
2. 行政区划层级关系
3. 模糊匹配的可能性

请返回JSON格式：
- resolved_location: 解析后的标准地点名称
- location_code: 对应的地点编码（如果有）
- location_type: 地点类型（城市、区县、站点）
- confidence: 解析置信度 (0-1)
- alternatives: 可能的其他匹配项
""",
            
            "comprehensive_analysis": """
你是一个全面的问题分析专家。用户问题："{original_question}"

系统处理过程中出现了错误：{error_message}

错误上下文：{error_context}

请进行全面分析：
1. 用户的真实查询意图
2. 错误的根本原因
3. 推荐的解决方案
4. 是否需要回退到SQL查询

请返回JSON格式：
- intent_analysis: 意图分析结果
- error_diagnosis: 错误诊断
- recovery_plan: 恢复计划
- requires_sql_fallback: 是否需要SQL回退
- user_clarification_needed: 是否需要用户澄清
"""
        }
    
    def recover_from_error(self, error_info: Dict[str, Any], original_question: str, 
                          context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        基于错误信息进行智能恢复
        
        Args:
            error_info: 错误分类信息
            original_question: 用户原始问题
            context: 额外上下文信息
            
        Returns:
            恢复结果
        """
        context = context or {}
        error_type = error_info.get("error_type")
        recovery_strategy = error_info.get("recovery_strategy")
        
        logger.info(f"开始错误恢复：类型={error_type}, 策略={recovery_strategy}")
        
        try:
            if recovery_strategy == "llm_reanalysis":
                return self._llm_parameter_reextraction(error_info, original_question, context)
            elif recovery_strategy == "llm_tool_reselection":
                return self._llm_tool_reselection(error_info, original_question, context)
            elif recovery_strategy == "llm_time_clarification":
                return self._llm_time_clarification(error_info, original_question, context)
            elif recovery_strategy == "llm_location_clarification":
                return self._llm_location_clarification(error_info, original_question, context)
            elif recovery_strategy == "simple_retry":
                return self._simple_retry(error_info, original_question, context)
            elif recovery_strategy == "sql_fallback":
                return self._recommend_sql_fallback(error_info, original_question, context)
            elif recovery_strategy == "comprehensive_llm_analysis":
                return self._comprehensive_llm_analysis(error_info, original_question, context)
            else:
                return self._default_recovery(error_info, original_question, context)
                
        except Exception as e:
            logger.error(f"错误恢复过程中出现异常: {e}")
            return {
                "success": False,
                "error": f"错误恢复失败: {str(e)}",
                "fallback_required": True
            }
    
    def _llm_parameter_reextraction(self, error_info: Dict[str, Any], original_question: str, 
                                   context: Dict[str, Any]) -> Dict[str, Any]:
        """LLM重新提取参数"""
        vanna_service = self._get_vanna_service()
        if not vanna_service:
            return {"success": False, "error": "Vanna服务不可用", "fallback_required": True}
        
        prompt = self.recovery_prompts["parameter_reextraction"].format(
            original_question=original_question,
            error_message=error_info.get("original_message", ""),
            failed_params=json.dumps(error_info.get("error_details", {}), ensure_ascii=False)
        )
        
        try:
            llm_response = vanna_service._call_llm_for_analysis(prompt)
            result = self._parse_llm_json_response(llm_response)
            
            if result and not result.get("need_clarification"):
                return {
                    "success": True,
                    "recovery_type": "parameter_reextraction",
                    "extracted_params": result,
                    "confidence": 0.8
                }
            else:
                return {
                    "success": False,
                    "error": "参数提取仍需要用户澄清",
                    "clarification_needed": result.get("need_clarification", "需要更多信息"),
                    "partial_result": result
                }
                
        except Exception as e:
            logger.error(f"LLM参数重提取失败: {e}")
            return {"success": False, "error": str(e), "fallback_required": True}
    
    def _llm_tool_reselection(self, error_info: Dict[str, Any], original_question: str, 
                             context: Dict[str, Any]) -> Dict[str, Any]:
        """LLM重新选择工具"""
        vanna_service = self._get_vanna_service()
        if not vanna_service:
            return {"success": False, "error": "Vanna服务不可用", "fallback_required": True}
        
        # 获取可用工具列表
        available_tools = context.get("available_tools", self._get_default_tools())
        
        prompt = self.recovery_prompts["tool_reselection"].format(
            original_question=original_question,
            error_message=error_info.get("original_message", ""),
            available_tools=json.dumps(available_tools, ensure_ascii=False)
        )
        
        try:
            llm_response = vanna_service._call_llm_for_analysis(prompt)
            result = self._parse_llm_json_response(llm_response)
            
            if result and result.get("recommended_tool"):
                return {
                    "success": True,
                    "recovery_type": "tool_reselection",
                    "recommended_tool": result.get("recommended_tool"),
                    "reason": result.get("reason"),
                    "parameters": result.get("parameters", {}),
                    "alternatives": result.get("alternative_tools", [])
                }
            else:
                return {"success": False, "error": "无法确定合适的工具", "fallback_required": True}
                
        except Exception as e:
            logger.error(f"LLM工具重选择失败: {e}")
            return {"success": False, "error": str(e), "fallback_required": True}
    
    def _llm_time_clarification(self, error_info: Dict[str, Any], original_question: str, 
                               context: Dict[str, Any]) -> Dict[str, Any]:
        """LLM时间澄清"""
        vanna_service = self._get_vanna_service()
        if not vanna_service:
            return {"success": False, "error": "Vanna服务不可用", "fallback_required": True}
        
        time_expression = context.get("time_expression", original_question)
        
        prompt = self.recovery_prompts["time_clarification"].format(
            time_expression=time_expression,
            error_message=error_info.get("original_message", "")
        )
        
        try:
            llm_response = vanna_service._call_llm_for_analysis(prompt)
            result = self._parse_llm_json_response(llm_response)
            
            if result and result.get("start_time") and result.get("end_time"):
                return {
                    "success": True,
                    "recovery_type": "time_clarification",
                    "start_time": result.get("start_time"),
                    "end_time": result.get("end_time"),
                    "interpretation": result.get("interpretation"),
                    "confidence": result.get("confidence", 0.7)
                }
            else:
                return {"success": False, "error": "时间解析仍然失败", "fallback_required": True}
                
        except Exception as e:
            logger.error(f"LLM时间澄清失败: {e}")
            return {"success": False, "error": str(e), "fallback_required": True}
    
    def _llm_location_clarification(self, error_info: Dict[str, Any], original_question: str, 
                                   context: Dict[str, Any]) -> Dict[str, Any]:
        """LLM地点澄清"""
        vanna_service = self._get_vanna_service()
        if not vanna_service:
            return {"success": False, "error": "Vanna服务不可用", "fallback_required": True}
        
        location_expression = context.get("location_expression", original_question)
        geo_mappings = context.get("geo_mappings", {})
        
        prompt = self.recovery_prompts["location_clarification"].format(
            location_expression=location_expression,
            error_message=error_info.get("original_message", ""),
            geo_mappings=json.dumps(geo_mappings, ensure_ascii=False)
        )
        
        try:
            llm_response = vanna_service._call_llm_for_analysis(prompt)
            result = self._parse_llm_json_response(llm_response)
            
            if result and result.get("resolved_location"):
                return {
                    "success": True,
                    "recovery_type": "location_clarification",
                    "resolved_location": result.get("resolved_location"),
                    "location_code": result.get("location_code"),
                    "location_type": result.get("location_type"),
                    "confidence": result.get("confidence", 0.7),
                    "alternatives": result.get("alternatives", [])
                }
            else:
                return {"success": False, "error": "地点解析仍然失败", "fallback_required": True}
                
        except Exception as e:
            logger.error(f"LLM地点澄清失败: {e}")
            return {"success": False, "error": str(e), "fallback_required": True}
    
    def _comprehensive_llm_analysis(self, error_info: Dict[str, Any], original_question: str, 
                                   context: Dict[str, Any]) -> Dict[str, Any]:
        """LLM全面分析"""
        vanna_service = self._get_vanna_service()
        if not vanna_service:
            return {"success": False, "error": "Vanna服务不可用", "fallback_required": True}
        
        prompt = self.recovery_prompts["comprehensive_analysis"].format(
            original_question=original_question,
            error_message=error_info.get("original_message", ""),
            error_context=json.dumps(context, ensure_ascii=False)
        )
        
        try:
            llm_response = vanna_service._call_llm_for_analysis(prompt)
            result = self._parse_llm_json_response(llm_response)
            
            return {
                "success": True,
                "recovery_type": "comprehensive_analysis",
                "intent_analysis": result.get("intent_analysis"),
                "error_diagnosis": result.get("error_diagnosis"),
                "recovery_plan": result.get("recovery_plan"),
                "requires_sql_fallback": result.get("requires_sql_fallback", False),
                "user_clarification_needed": result.get("user_clarification_needed")
            }
            
        except Exception as e:
            logger.error(f"LLM全面分析失败: {e}")
            return {"success": False, "error": str(e), "fallback_required": True}
    
    def _simple_retry(self, error_info: Dict[str, Any], original_question: str, 
                     context: Dict[str, Any]) -> Dict[str, Any]:
        """简单重试策略"""
        retry_count = context.get("retry_count", 0)
        max_retries = context.get("max_retries", 3)
        
        if retry_count >= max_retries:
            return {"success": False, "error": "达到最大重试次数", "fallback_required": True}
        
        return {
            "success": True,
            "recovery_type": "simple_retry",
            "retry_count": retry_count + 1,
            "wait_seconds": min(2 ** retry_count, 10)  # 指数退避
        }
    
    def _recommend_sql_fallback(self, error_info: Dict[str, Any], original_question: str, 
                               context: Dict[str, Any]) -> Dict[str, Any]:
        """推荐SQL回退"""
        return {
            "success": True,
            "recovery_type": "sql_fallback",
            "reason": f"错误类型{error_info.get('error_type')}建议使用SQL查询",
            "original_question": original_question,
            "fallback_required": True
        }
    
    def _default_recovery(self, error_info: Dict[str, Any], original_question: str, 
                         context: Dict[str, Any]) -> Dict[str, Any]:
        """默认恢复策略"""
        return {
            "success": False,
            "recovery_type": "default",
            "error": "未知的恢复策略",
            "fallback_required": True
        }
    
    def _parse_llm_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """解析LLM的JSON响应"""
        if not response:
            return None
        
        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取JSON部分
            import re
            json_pattern = r'\{.*\}'
            match = re.search(json_pattern, response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            
            logger.warning(f"无法解析LLM响应为JSON: {response}")
            return None
    
    def _get_default_tools(self) -> List[Dict[str, str]]:
        """获取默认工具列表"""
        return [
            {"name": "air_quality_comparison", "description": "空气质量对比查询"},
            {"name": "air_quality_comprehensive", "description": "空气质量综合报表"},
            {"name": "air_quality_real_time", "description": "实时空气质量查询"}
        ]

# 全局错误恢复器实例
_llm_error_recovery = None

def get_llm_error_recovery() -> LLMErrorRecovery:
    """获取全局LLM错误恢复器实例"""
    global _llm_error_recovery
    if _llm_error_recovery is None:
        _llm_error_recovery = LLMErrorRecovery()
    return _llm_error_recovery