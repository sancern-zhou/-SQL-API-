"""
错误分类器 - 第四阶段智能错误恢复
负责识别和分类各种类型的错误，为后续的智能恢复提供基础
"""

import logging
import re
from typing import Dict, Any, List, Tuple, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class ErrorType(Enum):
    """错误类型枚举"""
    PARAMETER_EXTRACTION_FAILED = "parameter_extraction_failed"
    PARAMETER_VALIDATION_FAILED = "parameter_validation_failed"
    TOOL_SELECTION_FAILED = "tool_selection_failed"
    API_EXECUTION_FAILED = "api_execution_failed"
    TIME_PARSING_FAILED = "time_parsing_failed"
    LOCATION_PARSING_FAILED = "location_parsing_failed"
    NETWORK_ERROR = "network_error"
    AUTHENTICATION_ERROR = "authentication_error"
    DATA_FORMAT_ERROR = "data_format_error"
    UNKNOWN_ERROR = "unknown_error"

class ErrorSeverity(Enum):
    """错误严重性枚举"""
    LOW = "low"         # 可以通过简单重试解决
    MEDIUM = "medium"   # 需要LLM重新分析
    HIGH = "high"       # 需要SQL回退
    CRITICAL = "critical"  # 系统性错误

class ErrorClassifier:
    """智能错误分类器"""
    
    def __init__(self):
        self.parameter_error_patterns = [
            r"缺少必需参数",
            r"参数.*不能为空",
            r"无法解析.*参数",
            r"参数格式不正确",
            r"missing required parameter",
            r"parameter.*is required"
        ]
        
        self.time_error_patterns = [
            r"无法解析.*时间",
            r"时间格式.*错误",
            r"时间范围.*无效",
            r"不支持的时间格式",
            r"invalid time format",
            r"time parsing failed"
        ]
        
        self.location_error_patterns = [
            r"无法确定位置",
            r"地理位置.*不存在",
            r"站点.*未找到",
            r"区域.*无效",
            r"location not found",
            r"invalid location"
        ]
        
        self.api_error_patterns = [
            r"API调用失败",
            r"连接超时",
            r"网络错误",
            r"服务不可用",
            r"认证失败",
            r"权限不足",
            r"API rate limit",
            r"connection timeout",
            r"network error",
            r"service unavailable"
        ]
        
        # 错误严重性映射
        self.severity_mapping = {
            ErrorType.PARAMETER_EXTRACTION_FAILED: ErrorSeverity.MEDIUM,
            ErrorType.PARAMETER_VALIDATION_FAILED: ErrorSeverity.MEDIUM,
            ErrorType.TOOL_SELECTION_FAILED: ErrorSeverity.HIGH,
            ErrorType.API_EXECUTION_FAILED: ErrorSeverity.MEDIUM,
            ErrorType.TIME_PARSING_FAILED: ErrorSeverity.MEDIUM,
            ErrorType.LOCATION_PARSING_FAILED: ErrorSeverity.MEDIUM,
            ErrorType.NETWORK_ERROR: ErrorSeverity.LOW,
            ErrorType.AUTHENTICATION_ERROR: ErrorSeverity.HIGH,
            ErrorType.DATA_FORMAT_ERROR: ErrorSeverity.MEDIUM,
            ErrorType.UNKNOWN_ERROR: ErrorSeverity.HIGH
        }
    
    def classify_error(self, error_message: str, error_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        分类错误并确定处理策略
        
        Args:
            error_message: 错误消息
            error_context: 错误上下文信息
            
        Returns:
            包含错误类型、严重性、建议恢复策略的字典
        """
        if not error_message:
            return self._create_error_result(ErrorType.UNKNOWN_ERROR, "空错误消息")
        
        error_context = error_context or {}
        error_message_lower = error_message.lower()
        
        # 按优先级分类错误
        error_type = self._determine_error_type(error_message, error_context)
        severity = self.severity_mapping.get(error_type, ErrorSeverity.HIGH)
        
        # 确定恢复策略
        recovery_strategy = self._determine_recovery_strategy(error_type, severity, error_context)
        
        # 提取关键错误信息
        error_details = self._extract_error_details(error_message, error_type, error_context)
        
        result = {
            "error_type": error_type.value,
            "severity": severity.value,
            "recovery_strategy": recovery_strategy,
            "error_details": error_details,
            "original_message": error_message,
            "context": error_context,
            "classification_confidence": self._calculate_confidence(error_message, error_type)
        }
        
        logger.info(f"错误分类完成: {error_type.value}, 严重性: {severity.value}, 恢复策略: {recovery_strategy}")
        return result
    
    def _determine_error_type(self, error_message: str, error_context: Dict[str, Any]) -> ErrorType:
        """确定错误类型"""
        error_message_lower = error_message.lower()
        
        # 检查参数相关错误
        if any(re.search(pattern, error_message, re.IGNORECASE) for pattern in self.parameter_error_patterns):
            return ErrorType.PARAMETER_EXTRACTION_FAILED
        
        # 检查时间解析错误
        if any(re.search(pattern, error_message, re.IGNORECASE) for pattern in self.time_error_patterns):
            return ErrorType.TIME_PARSING_FAILED
        
        # 检查位置解析错误
        if any(re.search(pattern, error_message, re.IGNORECASE) for pattern in self.location_error_patterns):
            return ErrorType.LOCATION_PARSING_FAILED
        
        # 检查API执行错误
        if any(re.search(pattern, error_message, re.IGNORECASE) for pattern in self.api_error_patterns):
            return ErrorType.API_EXECUTION_FAILED
        
        # 根据上下文判断
        if error_context:
            stage = error_context.get("stage", "")
            if stage == "parameter_extraction":
                return ErrorType.PARAMETER_EXTRACTION_FAILED
            elif stage == "tool_selection":
                return ErrorType.TOOL_SELECTION_FAILED
            elif stage == "api_execution":
                return ErrorType.API_EXECUTION_FAILED
            elif stage == "parameter_validation":
                return ErrorType.PARAMETER_VALIDATION_FAILED
        
        # 特定错误模式匹配
        if "认证" in error_message_lower or "authentication" in error_message_lower:
            return ErrorType.AUTHENTICATION_ERROR
        
        if "网络" in error_message_lower or "network" in error_message_lower:
            return ErrorType.NETWORK_ERROR
        
        if "格式" in error_message_lower or "format" in error_message_lower:
            return ErrorType.DATA_FORMAT_ERROR
        
        return ErrorType.UNKNOWN_ERROR
    
    def _determine_recovery_strategy(self, error_type: ErrorType, severity: ErrorSeverity, 
                                   error_context: Dict[str, Any]) -> str:
        """确定恢复策略"""
        strategies = {
            ErrorType.PARAMETER_EXTRACTION_FAILED: "llm_reanalysis",
            ErrorType.PARAMETER_VALIDATION_FAILED: "llm_parameter_fixing",
            ErrorType.TOOL_SELECTION_FAILED: "llm_tool_reselection",
            ErrorType.API_EXECUTION_FAILED: "retry_or_llm_alternative",
            ErrorType.TIME_PARSING_FAILED: "llm_time_clarification",
            ErrorType.LOCATION_PARSING_FAILED: "llm_location_clarification",
            ErrorType.NETWORK_ERROR: "simple_retry",
            ErrorType.AUTHENTICATION_ERROR: "sql_fallback",
            ErrorType.DATA_FORMAT_ERROR: "llm_data_interpretation",
            ErrorType.UNKNOWN_ERROR: "comprehensive_llm_analysis"
        }
        
        base_strategy = strategies.get(error_type, "comprehensive_llm_analysis")
        
        # 根据严重性调整策略
        if severity == ErrorSeverity.HIGH or severity == ErrorSeverity.CRITICAL:
            if error_context.get("retry_count", 0) > 2:
                return "sql_fallback"
        
        return base_strategy
    
    def _extract_error_details(self, error_message: str, error_type: ErrorType, 
                             error_context: Dict[str, Any]) -> Dict[str, Any]:
        """提取错误详细信息"""
        details = {
            "error_type": error_type.value,
            "failed_components": [],
            "missing_parameters": [],
            "invalid_values": [],
            "suggestions": []
        }
        
        # 提取缺失参数
        param_matches = re.findall(r"参数['\"]?(\w+)['\"]?", error_message)
        if param_matches:
            details["missing_parameters"] = param_matches
        
        # 提取失败组件
        if error_type == ErrorType.API_EXECUTION_FAILED:
            api_matches = re.findall(r"API['\"]?(\w+)['\"]?", error_message)
            if api_matches:
                details["failed_components"] = api_matches
        
        # 根据错误类型提供建议
        suggestions = self._get_error_suggestions(error_type, error_message)
        details["suggestions"] = suggestions
        
        return details
    
    def _get_error_suggestions(self, error_type: ErrorType, error_message: str) -> List[str]:
        """获取错误处理建议"""
        suggestions = []
        
        if error_type == ErrorType.PARAMETER_EXTRACTION_FAILED:
            suggestions.extend([
                "使用LLM重新分析用户问题",
                "检查问题表达是否明确",
                "考虑向用户请求澄清"
            ])
        elif error_type == ErrorType.TIME_PARSING_FAILED:
            suggestions.extend([
                "使用LLM解析复杂时间表达",
                "检查时间格式是否符合预期",
                "考虑提供时间范围示例"
            ])
        elif error_type == ErrorType.LOCATION_PARSING_FAILED:
            suggestions.extend([
                "使用LLM进行地理位置推理",
                "检查地理编码映射表",
                "考虑模糊匹配策略"
            ])
        elif error_type == ErrorType.API_EXECUTION_FAILED:
            suggestions.extend([
                "检查API服务状态",
                "验证参数格式",
                "考虑使用备用API或SQL查询"
            ])
        
        return suggestions
    
    def _calculate_confidence(self, error_message: str, error_type: ErrorType) -> float:
        """计算分类置信度"""
        confidence = 0.5  # 基础置信度
        
        # 基于模式匹配的置信度调整
        patterns_map = {
            ErrorType.PARAMETER_EXTRACTION_FAILED: self.parameter_error_patterns,
            ErrorType.TIME_PARSING_FAILED: self.time_error_patterns,
            ErrorType.LOCATION_PARSING_FAILED: self.location_error_patterns,
            ErrorType.API_EXECUTION_FAILED: self.api_error_patterns
        }
        
        patterns = patterns_map.get(error_type, [])
        matches = sum(1 for pattern in patterns if re.search(pattern, error_message, re.IGNORECASE))
        
        if matches > 0:
            confidence = min(0.9, 0.6 + (matches * 0.1))
        
        return confidence
    
    def _create_error_result(self, error_type: ErrorType, message: str) -> Dict[str, Any]:
        """创建标准错误结果"""
        severity = self.severity_mapping.get(error_type, ErrorSeverity.HIGH)
        return {
            "error_type": error_type.value,
            "severity": severity.value,
            "recovery_strategy": "comprehensive_llm_analysis",
            "error_details": {"message": message},
            "original_message": message,
            "context": {},
            "classification_confidence": 0.8
        }

# 全局错误分类器实例
_error_classifier = None

def get_error_classifier() -> ErrorClassifier:
    """获取全局错误分类器实例"""
    global _error_classifier
    if _error_classifier is None:
        _error_classifier = ErrorClassifier()
    return _error_classifier