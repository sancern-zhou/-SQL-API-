"""
增强参数重提取器 - 第四阶段智能错误恢复
基于错误分析和上下文进行智能参数重提取，支持多种提取策略
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class EnhancedParamExtractor:
    """增强参数重提取器"""
    
    def __init__(self):
        self.vanna_service = None
        
        # 参数提取模板
        self.extraction_prompts = {
            "basic_reextraction": """
你是一个专业的参数提取专家。请从用户问题中提取查询参数。

用户问题："{question}"

之前提取失败的原因：{error_reason}

请提取以下参数：
1. location_name: 地点名称（城市、区县、站点等）
2. start_time: 开始时间 (YYYY-MM-DD格式)
3. end_time: 结束时间 (YYYY-MM-DD格式)
4. query_type: 查询类型（comparison/comprehensive/real_time）

注意事项：
- 时间可以是相对表达（如"上周"、"本月"），请转换为具体日期
- 当前时间：2025年7月18日
- 如果没有明确时间，请根据查询类型推断合理的时间范围
- 地点可能是简称或别名，请保持原始表达

请返回JSON格式：
{
  "location_name": "提取的地点",
  "start_time": "YYYY-MM-DD",
  "end_time": "YYYY-MM-DD", 
  "query_type": "查询类型",
  "confidence": 0.8,
  "extraction_notes": "提取说明"
}
""",
            
            "context_aware_extraction": """
你是一个上下文感知的参数提取专家。请基于用户问题和对话历史提取参数。

当前问题："{question}"
对话历史：{conversation_history}
上下文信息：{context}

之前提取失败的原因：{error_reason}

请综合分析：
1. 用户的真实意图
2. 对话历史中的相关信息
3. 上下文中的隐含信息

提取参数：
- location_name: 地点名称
- start_time: 开始时间
- end_time: 结束时间
- query_type: 查询类型
- additional_filters: 其他筛选条件

请返回JSON格式：
{
  "location_name": "地点",
  "start_time": "YYYY-MM-DD",
  "end_time": "YYYY-MM-DD",
  "query_type": "类型", 
  "additional_filters": {},
  "confidence": 0.9,
  "reasoning": "推理过程说明"
}
""",
            
            "error_specific_extraction": """
你是一个错误恢复专家。基于特定的错误类型重新提取参数。

用户问题："{question}"
错误类型：{error_type}
错误详情：{error_details}
原始参数：{original_params}

针对错误类型 {error_type}，请重新提取和修正参数：

{error_specific_instructions}

请返回JSON格式：
{
  "corrected_params": {
    "location_name": "修正后的地点",
    "start_time": "修正后的开始时间",
    "end_time": "修正后的结束时间",
    "query_type": "修正后的查询类型"
  },
  "corrections_made": ["修正说明1", "修正说明2"],
  "confidence": 0.85
}
"""
        }
        
        # 错误特定的指导说明
        self.error_specific_instructions = {
            "time_parsing_failed": """
时间解析失败。请特别注意：
1. 将相对时间转换为绝对时间（如"上周" → "2025-07-11 到 2025-07-17"）
2. 补充缺失的时间范围（单个日期 → 时间段）
3. 修正不合理的时间格式
4. 当前时间：2025年7月18日星期五
""",
            "location_parsing_failed": """
地点解析失败。请特别注意：
1. 识别地点的别名或简称（如"广雅" → "广雅中学"）
2. 补充完整的行政区划信息
3. 处理多个地点的情况
4. 识别模糊地点表达
""",
            "parameter_validation_failed": """
参数验证失败。请特别注意：
1. 检查参数格式的正确性
2. 确保必需参数不为空
3. 验证参数值的合理性
4. 修正参数类型错误
""",
            "parameter_extraction_failed": """
参数提取失败。请特别注意：
1. 重新分析用户的真实意图
2. 从问题中提取所有可能的参数信息
3. 对缺失信息进行合理推断
4. 确保提取的参数完整性
"""
        }
        
        # 时间解析规则
        self.time_patterns = {
            r"今天|当天": self._get_today_range,
            r"昨天": self._get_yesterday_range,
            r"上周|上星期": self._get_last_week_range,
            r"本周|这周|这星期": self._get_this_week_range,
            r"上个?月": self._get_last_month_range,
            r"本月|这个?月": self._get_this_month_range,
            r"去年": self._get_last_year_range,
            r"今年": self._get_this_year_range,
            r"最近(\d+)天": self._get_recent_days_range,
            r"(\d{4})年(\d{1,2})月": self._get_year_month_range,
            r"(\d{1,2})月(\d{1,2})日": self._get_month_day_range
        }
    
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
    
    def reextract_parameters(self, question: str, error_info: Dict[str, Any], 
                           context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        重新提取参数
        
        Args:
            question: 用户问题
            error_info: 错误信息
            context: 上下文信息
            
        Returns:
            重提取结果
        """
        context = context or {}
        error_type = error_info.get("error_type", "unknown")
        
        logger.info(f"开始参数重提取：错误类型={error_type}")
        
        try:
            # 根据错误类型选择提取策略
            if error_type in ["time_parsing_failed", "location_parsing_failed", "parameter_validation_failed"]:
                return self._error_specific_reextraction(question, error_info, context)
            elif context.get("conversation_history"):
                return self._context_aware_reextraction(question, error_info, context)
            else:
                return self._basic_reextraction(question, error_info, context)
                
        except Exception as e:
            logger.error(f"参数重提取过程中出现异常: {e}")
            return {
                "success": False,
                "error": f"重提取失败: {str(e)}",
                "fallback_required": True
            }
    
    def _basic_reextraction(self, question: str, error_info: Dict[str, Any], 
                           context: Dict[str, Any]) -> Dict[str, Any]:
        """基础重提取"""
        vanna_service = self._get_vanna_service()
        if not vanna_service:
            return {"success": False, "error": "Vanna服务不可用", "fallback_required": True}
        
        prompt = self.extraction_prompts["basic_reextraction"].format(
            question=question,
            error_reason=error_info.get("original_message", "")
        )
        
        try:
            llm_response = vanna_service._call_llm_for_analysis(prompt)
            result = self._parse_json_response(llm_response)
            
            if result and result.get("location_name"):
                # 后处理：时间智能补充
                result = self._enhance_time_parameters(result, question)
                
                return {
                    "success": True,
                    "extraction_type": "basic_reextraction",
                    "extracted_params": result,
                    "confidence": result.get("confidence", 0.7)
                }
            else:
                return {
                    "success": False,
                    "error": "基础重提取未能获取有效参数",
                    "partial_result": result
                }
                
        except Exception as e:
            logger.error(f"基础重提取失败: {e}")
            return {"success": False, "error": str(e), "fallback_required": True}
    
    def _context_aware_reextraction(self, question: str, error_info: Dict[str, Any], 
                                   context: Dict[str, Any]) -> Dict[str, Any]:
        """上下文感知重提取"""
        vanna_service = self._get_vanna_service()
        if not vanna_service:
            return {"success": False, "error": "Vanna服务不可用", "fallback_required": True}
        
        conversation_history = context.get("conversation_history", [])
        context_info = {k: v for k, v in context.items() if k != "conversation_history"}
        
        prompt = self.extraction_prompts["context_aware_extraction"].format(
            question=question,
            conversation_history=json.dumps(conversation_history, ensure_ascii=False),
            context=json.dumps(context_info, ensure_ascii=False),
            error_reason=error_info.get("original_message", "")
        )
        
        try:
            llm_response = vanna_service._call_llm_for_analysis(prompt)
            result = self._parse_json_response(llm_response)
            
            if result and result.get("location_name"):
                return {
                    "success": True,
                    "extraction_type": "context_aware_reextraction",
                    "extracted_params": result,
                    "confidence": result.get("confidence", 0.8),
                    "reasoning": result.get("reasoning", "")
                }
            else:
                return {
                    "success": False,
                    "error": "上下文感知重提取未能获取有效参数",
                    "partial_result": result
                }
                
        except Exception as e:
            logger.error(f"上下文感知重提取失败: {e}")
            return {"success": False, "error": str(e), "fallback_required": True}
    
    def _error_specific_reextraction(self, question: str, error_info: Dict[str, Any], 
                                    context: Dict[str, Any]) -> Dict[str, Any]:
        """基于错误类型的重提取"""
        vanna_service = self._get_vanna_service()
        if not vanna_service:
            return {"success": False, "error": "Vanna服务不可用", "fallback_required": True}
        
        error_type = error_info.get("error_type", "unknown")
        error_instructions = self.error_specific_instructions.get(
            error_type, 
            "请重新分析并提取正确的参数"
        )
        
        prompt = self.extraction_prompts["error_specific_extraction"].format(
            question=question,
            error_type=error_type,
            error_details=json.dumps(error_info.get("error_details", {}), ensure_ascii=False),
            original_params=json.dumps(context.get("original_params", {}), ensure_ascii=False),
            error_specific_instructions=error_instructions
        )
        
        try:
            llm_response = vanna_service._call_llm_for_analysis(prompt)
            result = self._parse_json_response(llm_response)
            
            if result and result.get("corrected_params"):
                corrected_params = result["corrected_params"]
                
                # 特定错误类型的后处理
                if error_type == "time_parsing_failed":
                    corrected_params = self._post_process_time_params(corrected_params, question)
                elif error_type == "location_parsing_failed":
                    corrected_params = self._post_process_location_params(corrected_params, question)
                
                return {
                    "success": True,
                    "extraction_type": "error_specific_reextraction",
                    "extracted_params": corrected_params,
                    "corrections_made": result.get("corrections_made", []),
                    "confidence": result.get("confidence", 0.8)
                }
            else:
                return {
                    "success": False,
                    "error": f"针对{error_type}的重提取失败",
                    "partial_result": result
                }
                
        except Exception as e:
            logger.error(f"错误特定重提取失败: {e}")
            return {"success": False, "error": str(e), "fallback_required": True}
    
    def _enhance_time_parameters(self, params: Dict[str, Any], question: str) -> Dict[str, Any]:
        """增强时间参数"""
        enhanced_params = params.copy()
        
        # 如果缺少时间参数，尝试从问题中解析
        if not enhanced_params.get("start_time") or not enhanced_params.get("end_time"):
            time_info = self._parse_time_expressions(question)
            if time_info:
                enhanced_params.update(time_info)
        
        # 验证和修正时间范围
        start_time = enhanced_params.get("start_time")
        end_time = enhanced_params.get("end_time")
        
        if start_time and end_time:
            try:
                start_dt = datetime.strptime(start_time, "%Y-%m-%d")
                end_dt = datetime.strptime(end_time, "%Y-%m-%d")
                
                # 确保开始时间早于结束时间
                if start_dt > end_dt:
                    enhanced_params["start_time"] = end_time
                    enhanced_params["end_time"] = start_time
                    
            except ValueError:
                # 时间格式错误，使用默认范围
                logger.warning(f"时间格式错误: {start_time}, {end_time}")
                enhanced_params.update(self._get_default_time_range())
        
        elif not start_time and not end_time:
            # 完全缺少时间信息，根据查询类型提供默认值
            query_type = enhanced_params.get("query_type", "comprehensive")
            if query_type == "real_time":
                enhanced_params.update(self._get_today_range())
            else:
                enhanced_params.update(self._get_default_time_range())
        
        return enhanced_params
    
    def _parse_time_expressions(self, text: str) -> Optional[Dict[str, str]]:
        """解析时间表达式"""
        for pattern, handler in self.time_patterns.items():
            match = re.search(pattern, text)
            if match:
                return handler(match)
        return None
    
    def _post_process_time_params(self, params: Dict[str, Any], question: str) -> Dict[str, Any]:
        """后处理时间参数"""
        processed_params = params.copy()
        
        # 补充缺失的时间参数
        if not processed_params.get("start_time") or not processed_params.get("end_time"):
            time_info = self._parse_time_expressions(question)
            if time_info:
                processed_params.update(time_info)
            else:
                processed_params.update(self._get_default_time_range())
        
        return processed_params
    
    def _post_process_location_params(self, params: Dict[str, Any], question: str) -> Dict[str, Any]:
        """后处理地点参数"""
        processed_params = params.copy()
        
        location_name = processed_params.get("location_name", "")
        if location_name:
            # 尝试标准化地点名称
            standardized_location = self._standardize_location_name(location_name)
            if standardized_location != location_name:
                processed_params["location_name"] = standardized_location
                processed_params["location_standardized"] = True
        
        return processed_params
    
    def _standardize_location_name(self, location: str) -> str:
        """标准化地点名称"""
        # 常见地点别名映射
        location_aliases = {
            "广雅": "广雅中学",
            "珠海市": "珠海",
            "深圳市": "深圳",
            "广州市": "广州"
        }
        
        return location_aliases.get(location, location)
    
    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """解析JSON响应"""
        if not response:
            return None
        
        try:
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
            
            logger.warning(f"无法解析JSON响应: {response}")
            return None
    
    # 时间范围计算方法
    def _get_today_range(self, match=None) -> Dict[str, str]:
        """获取今天的时间范围"""
        today = datetime.now().strftime("%Y-%m-%d")
        return {"start_time": today, "end_time": today}
    
    def _get_yesterday_range(self, match=None) -> Dict[str, str]:
        """获取昨天的时间范围"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        return {"start_time": yesterday, "end_time": yesterday}
    
    def _get_last_week_range(self, match=None) -> Dict[str, str]:
        """获取上周的时间范围"""
        today = datetime.now()
        last_week_end = today - timedelta(days=today.weekday() + 1)
        last_week_start = last_week_end - timedelta(days=6)
        return {
            "start_time": last_week_start.strftime("%Y-%m-%d"),
            "end_time": last_week_end.strftime("%Y-%m-%d")
        }
    
    def _get_this_week_range(self, match=None) -> Dict[str, str]:
        """获取本周的时间范围"""
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        return {
            "start_time": week_start.strftime("%Y-%m-%d"),
            "end_time": today.strftime("%Y-%m-%d")
        }
    
    def _get_last_month_range(self, match=None) -> Dict[str, str]:
        """获取上个月的时间范围"""
        today = datetime.now()
        if today.month == 1:
            last_month = today.replace(year=today.year-1, month=12, day=1)
        else:
            last_month = today.replace(month=today.month-1, day=1)
        
        # 计算上个月的最后一天
        if last_month.month == 12:
            next_month = last_month.replace(year=last_month.year+1, month=1, day=1)
        else:
            next_month = last_month.replace(month=last_month.month+1, day=1)
        last_day = next_month - timedelta(days=1)
        
        return {
            "start_time": last_month.strftime("%Y-%m-%d"),
            "end_time": last_day.strftime("%Y-%m-%d")
        }
    
    def _get_this_month_range(self, match=None) -> Dict[str, str]:
        """获取本月的时间范围"""
        today = datetime.now()
        month_start = today.replace(day=1)
        return {
            "start_time": month_start.strftime("%Y-%m-%d"),
            "end_time": today.strftime("%Y-%m-%d")
        }
    
    def _get_last_year_range(self, match=None) -> Dict[str, str]:
        """获取去年的时间范围"""
        today = datetime.now()
        last_year = today.year - 1
        return {
            "start_time": f"{last_year}-01-01",
            "end_time": f"{last_year}-12-31"
        }
    
    def _get_this_year_range(self, match=None) -> Dict[str, str]:
        """获取今年的时间范围"""
        today = datetime.now()
        return {
            "start_time": f"{today.year}-01-01",
            "end_time": today.strftime("%Y-%m-%d")
        }
    
    def _get_recent_days_range(self, match) -> Dict[str, str]:
        """获取最近N天的时间范围"""
        days = int(match.group(1))
        today = datetime.now()
        start_date = today - timedelta(days=days-1)
        return {
            "start_time": start_date.strftime("%Y-%m-%d"),
            "end_time": today.strftime("%Y-%m-%d")
        }
    
    def _get_year_month_range(self, match) -> Dict[str, str]:
        """获取指定年月的时间范围"""
        year = int(match.group(1))
        month = int(match.group(2))
        
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        
        return {
            "start_time": start_date.strftime("%Y-%m-%d"),
            "end_time": end_date.strftime("%Y-%m-%d")
        }
    
    def _get_month_day_range(self, match) -> Dict[str, str]:
        """获取指定月日的时间范围（当年）"""
        month = int(match.group(1))
        day = int(match.group(2))
        year = datetime.now().year
        
        target_date = datetime(year, month, day).strftime("%Y-%m-%d")
        return {
            "start_time": target_date,
            "end_time": target_date
        }
    
    def _get_default_time_range(self) -> Dict[str, str]:
        """获取默认时间范围（最近一周）"""
        today = datetime.now()
        week_ago = today - timedelta(days=7)
        return {
            "start_time": week_ago.strftime("%Y-%m-%d"),
            "end_time": today.strftime("%Y-%m-%d")
        }

# 全局增强参数提取器实例
_enhanced_param_extractor = None

def get_enhanced_param_extractor() -> EnhancedParamExtractor:
    """获取全局增强参数提取器实例"""
    global _enhanced_param_extractor
    if _enhanced_param_extractor is None:
        _enhanced_param_extractor = EnhancedParamExtractor()
    return _enhanced_param_extractor