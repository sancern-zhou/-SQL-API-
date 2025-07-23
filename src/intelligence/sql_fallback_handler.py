"""
SQL回退处理器 - 第四阶段智能错误恢复
当API处理失败时，智能回退到SQL查询方式
"""

import logging
from typing import Dict, Any, List, Optional
import re

logger = logging.getLogger(__name__)

class SQLFallbackHandler:
    """SQL回退处理器"""
    
    def __init__(self):
        # 回退策略配置
        self.fallback_strategies = {
            "api_execution_failed": {
                "priority": "high",
                "message_template": "外部API服务暂时不可用，系统将使用数据库查询为您提供相关数据。",
                "question_transformation": "api_to_sql"
            },
            "parameter_extraction_failed": {
                "priority": "medium", 
                "message_template": "参数提取遇到困难，系统将尝试通过探索性查询为您获取相关信息。",
                "question_transformation": "exploratory_sql"
            },
            "tool_selection_failed": {
                "priority": "medium",
                "message_template": "工具选择失败，系统将使用数据库查询方式处理您的请求。",
                "question_transformation": "general_sql"
            },
            "authentication_error": {
                "priority": "high",
                "message_template": "外部服务认证失败，系统将使用本地数据库查询为您提供信息。",
                "question_transformation": "local_sql"
            },
            "network_error": {
                "priority": "high",
                "message_template": "网络连接问题，系统将使用本地数据库查询为您提供信息。",
                "question_transformation": "local_sql"
            },
            "data_format_error": {
                "priority": "medium",
                "message_template": "数据格式问题，系统将使用数据库查询重新获取信息。", 
                "question_transformation": "structured_sql"
            }
        }
        
        # 问题转换模式
        self.question_transformations = {
            "api_to_sql": self._transform_api_question_to_sql,
            "exploratory_sql": self._transform_to_exploratory_sql,
            "general_sql": self._transform_to_general_sql,
            "local_sql": self._transform_to_local_sql,
            "structured_sql": self._transform_to_structured_sql
        }
        
        # API参数到SQL概念的映射
        self.api_to_sql_mapping = {
            "location_name": "地点",
            "start_time": "开始时间",
            "end_time": "结束时间", 
            "area_type": "区域类型",
            "time_type": "时间类型",
            "station_codes": "站点",
            "data_source": "数据来源",
            "contrast_time": "对比时间"
        }
        
        # SQL查询提示词
        self.sql_hints = {
            "air_quality": [
                "可以查询空气质量相关的监测数据",
                "包括PM2.5、PM10、SO2、NO2、CO、O3等指标",
                "支持按时间、地点、站点进行筛选"
            ],
            "comparison": [
                "可以进行不同时间段的数据对比",
                "支持同比、环比分析",
                "可以比较不同地区的数据"
            ],
            "trend": [
                "可以分析数据的变化趋势",
                "支持时间序列分析",
                "可以查看长期变化模式"
            ]
        }
    
    def handle_sql_fallback(self, error_info: Dict[str, Any], original_question: str, 
                           api_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        处理SQL回退
        
        Args:
            error_info: 错误分类信息
            original_question: 用户原始问题
            api_context: API上下文信息
            
        Returns:
            SQL回退处理结果
        """
        api_context = api_context or {}
        error_type = error_info.get("error_type", "unknown_error")
        
        logger.info(f"[SQL_FALLBACK] 开始SQL回退处理")
        logger.info(f"[SQL_FALLBACK] 错误类型: {error_type}")
        logger.info(f"[SQL_FALLBACK] 原始问题: {original_question}")
        
        try:
            # 获取回退策略
            fallback_strategy = self._get_fallback_strategy(error_type)
            
            # 转换问题为SQL友好格式
            transformed_question = self._transform_question_for_sql(
                original_question, 
                fallback_strategy,
                api_context
            )
            
            # 生成用户提示信息
            user_message = self._generate_user_message(
                fallback_strategy,
                transformed_question,
                error_info,
                api_context
            )
            
            # 提供SQL查询建议
            sql_suggestions = self._generate_sql_suggestions(
                original_question,
                api_context,
                error_type
            )
            
            return {
                "status": "sql_fallback",
                "response_type": "message",
                "payload": {
                    "format": "text",
                    "value": user_message
                },
                "debug_info": {
                    "execution_path": "SQL_FALLBACK_HANDLER",
                    "fallback_reason": error_type,
                    "original_question": original_question,
                    "transformed_question": transformed_question,
                    "fallback_strategy": fallback_strategy,
                    "sql_suggestions": sql_suggestions,
                    "api_context": api_context
                }
            }
            
        except Exception as e:
            logger.error(f"[SQL_FALLBACK] SQL回退处理失败: {e}")
            return self._create_default_fallback_response(original_question, str(e))
    
    def _get_fallback_strategy(self, error_type: str) -> Dict[str, Any]:
        """获取回退策略"""
        strategy = self.fallback_strategies.get(error_type)
        if not strategy:
            # 使用默认策略
            strategy = {
                "priority": "medium",
                "message_template": "系统遇到问题，将使用数据库查询方式为您提供信息。",
                "question_transformation": "general_sql"
            }
        return strategy
    
    def _transform_question_for_sql(self, question: str, strategy: Dict[str, Any], 
                                   api_context: Dict[str, Any]) -> str:
        """转换问题为SQL友好格式"""
        transformation_type = strategy.get("question_transformation", "general_sql")
        transformer = self.question_transformations.get(transformation_type)
        
        if transformer:
            return transformer(question, api_context)
        else:
            return question
    
    def _transform_api_question_to_sql(self, question: str, api_context: Dict[str, Any]) -> str:
        """将API查询问题转换为SQL查询问题"""
        # 保留原问题的核心信息，但调整表达方式
        transformed = question
        
        # 替换API特定的术语
        api_replacements = {
            "综合报表": "数据查询",
            "对比报表": "数据对比",
            "实时数据": "最新数据",
            "监测站点": "站点"
        }
        
        for api_term, sql_term in api_replacements.items():
            transformed = transformed.replace(api_term, sql_term)
        
        # 如果有API参数信息，尝试整合到问题中
        api_params = api_context.get("original_params", {})
        if api_params:
            param_info = self._extract_param_info(api_params)
            if param_info:
                transformed += f"。请查询{param_info}的相关数据。"
        
        return transformed
    
    def _transform_to_exploratory_sql(self, question: str, api_context: Dict[str, Any]) -> str:
        """转换为探索性SQL查询"""
        # 添加探索性查询的引导词
        exploratory_prefixes = [
            "请查询和分析",
            "请探索",
            "请统计",
            "请汇总"
        ]
        
        # 选择合适的前缀
        if any(word in question for word in ["哪些", "什么", "怎样"]):
            prefix = "请查询和分析"
        elif any(word in question for word in ["对比", "比较"]):
            prefix = "请对比分析"
        elif any(word in question for word in ["趋势", "变化"]):
            prefix = "请分析趋势"
        else:
            prefix = "请查询"
        
        return f"{prefix}{question.replace('。', '')}的相关数据和统计信息。"
    
    def _transform_to_general_sql(self, question: str, api_context: Dict[str, Any]) -> str:
        """转换为通用SQL查询"""
        # 确保问题明确指向数据库查询
        if not any(word in question for word in ["查询", "数据", "信息", "统计"]):
            question = f"查询{question}"
        
        return question
    
    def _transform_to_local_sql(self, question: str, api_context: Dict[str, Any]) -> str:
        """转换为本地SQL查询"""
        # 强调使用本地数据
        return f"从本地数据库{question.replace('。', '')}的相关信息。"
    
    def _transform_to_structured_sql(self, question: str, api_context: Dict[str, Any]) -> str:
        """转换为结构化SQL查询"""
        # 添加结构化查询的指导
        return f"请按照标准格式查询{question.replace('。', '')}，并提供结构化的数据结果。"
    
    def _extract_param_info(self, params: Dict[str, Any]) -> str:
        """从参数中提取信息描述"""
        info_parts = []
        
        # 提取地点信息
        location = params.get("location_name")
        if location:
            if isinstance(location, list):
                location = "、".join(location)
            info_parts.append(f"{location}")
        
        # 提取时间信息
        start_time = params.get("start_time")
        end_time = params.get("end_time")
        if start_time and end_time:
            info_parts.append(f"{start_time}至{end_time}期间")
        elif start_time:
            info_parts.append(f"{start_time}开始")
        elif end_time:
            info_parts.append(f"截至{end_time}")
        
        # 提取其他重要参数
        for param_key, param_value in params.items():
            if param_key in ["area_type", "data_source"] and param_value is not None:
                sql_concept = self.api_to_sql_mapping.get(param_key, param_key)
                info_parts.append(f"{sql_concept}为{param_value}")
        
        return "、".join(info_parts) if info_parts else ""
    
    def _generate_user_message(self, strategy: Dict[str, Any], transformed_question: str, 
                              error_info: Dict[str, Any], api_context: Dict[str, Any]) -> str:
        """生成用户消息"""
        message_parts = []
        
        # 基础消息
        base_message = strategy.get("message_template", "系统将使用数据库查询方式处理您的请求。")
        message_parts.append(base_message)
        
        # 转换后的问题
        if transformed_question != api_context.get("original_question", ""):
            message_parts.append(f"\n转换后的查询：{transformed_question}")
        
        # SQL查询提示
        sql_hints = self._get_relevant_sql_hints(transformed_question)
        if sql_hints:
            message_parts.append(f"\n查询提示：\n" + "\n".join(f"• {hint}" for hint in sql_hints))
        
        # 错误详情（调试模式）
        error_severity = error_info.get("severity", "medium")
        if error_severity == "high":
            message_parts.append(f"\n注意：由于{error_info.get('error_type', '未知')}错误，系统需要使用备用查询方式。")
        
        return "\n".join(message_parts)
    
    def _get_relevant_sql_hints(self, question: str) -> List[str]:
        """获取相关的SQL提示"""
        hints = []
        question_lower = question.lower()
        
        # 根据问题内容提供相关提示
        if any(word in question_lower for word in ["空气质量", "pm2.5", "pm10", "so2", "no2", "co", "o3"]):
            hints.extend(self.sql_hints["air_quality"])
        
        if any(word in question_lower for word in ["对比", "比较", "环比", "同比"]):
            hints.extend(self.sql_hints["comparison"])
        
        if any(word in question_lower for word in ["趋势", "变化", "走势"]):
            hints.extend(self.sql_hints["trend"])
        
        return hints[:3]  # 最多返回3个提示
    
    def _generate_sql_suggestions(self, original_question: str, api_context: Dict[str, Any], 
                                 error_type: str) -> List[Dict[str, str]]:
        """生成SQL查询建议"""
        suggestions = []
        
        # 基于错误类型提供建议
        if error_type == "api_execution_failed":
            suggestions.append({
                "type": "alternative_query",
                "description": "尝试使用数据库查询获取相似数据",
                "suggestion": "重新表述问题，使用更通用的查询方式"
            })
        
        elif error_type == "parameter_extraction_failed":
            suggestions.append({
                "type": "simplified_query", 
                "description": "简化查询条件",
                "suggestion": "尝试使用更简单、更明确的表达方式"
            })
        
        elif error_type == "tool_selection_failed":
            suggestions.append({
                "type": "exploratory_query",
                "description": "使用探索性查询",
                "suggestion": "尝试使用开放性问题进行数据探索"
            })
        
        # 基于问题内容提供建议
        if "对比" in original_question or "比较" in original_question:
            suggestions.append({
                "type": "comparison_query",
                "description": "数据对比查询",
                "suggestion": "明确指定要对比的时间段或地区"
            })
        
        if "趋势" in original_question or "变化" in original_question:
            suggestions.append({
                "type": "trend_query",
                "description": "趋势分析查询",
                "suggestion": "指定分析的时间范围和监测指标"
            })
        
        return suggestions
    
    def _create_default_fallback_response(self, original_question: str, error_message: str) -> Dict[str, Any]:
        """创建默认回退响应"""
        return {
            "status": "sql_fallback",
            "response_type": "message",
            "payload": {
                "format": "text",
                "value": f"系统遇到问题（{error_message}），建议使用数据库查询方式。请重新表述您的问题，系统将通过SQL查询为您提供相关数据。"
            },
            "debug_info": {
                "execution_path": "SQL_FALLBACK_HANDLER",
                "fallback_reason": "default_fallback",
                "original_question": original_question,
                "error_message": error_message
            }
        }
    
    def get_fallback_statistics(self) -> Dict[str, Any]:
        """获取回退统计信息"""
        return {
            "supported_strategies": list(self.fallback_strategies.keys()),
            "transformation_types": list(self.question_transformations.keys()),
            "api_sql_mappings": self.api_to_sql_mapping,
            "available_hints": list(self.sql_hints.keys())
        }

# 全局SQL回退处理器实例
_sql_fallback_handler = None

def get_sql_fallback_handler() -> SQLFallbackHandler:
    """获取全局SQL回退处理器实例"""
    global _sql_fallback_handler
    if _sql_fallback_handler is None:
        _sql_fallback_handler = SQLFallbackHandler()
    return _sql_fallback_handler