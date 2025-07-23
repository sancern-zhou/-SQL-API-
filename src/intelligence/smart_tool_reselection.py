"""
智能工具重选择器 - 第四阶段智能错误恢复
在工具选择或执行失败时，基于失败原因和上下文智能重新选择合适的工具
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
import re

logger = logging.getLogger(__name__)

class SmartToolReselection:
    """智能工具重选择器"""
    
    def __init__(self):
        # 工具适用性规则
        self.tool_rules = {
            "air_quality_comparison": {
                "keywords": ["对比", "比较", "差异", "变化", "趋势"],
                "time_requirements": "range",  # 需要时间范围
                "location_requirements": "multiple_or_specific",  # 支持多个位置或特定位置
                "data_types": ["historical"],
                "limitations": ["不支持实时数据", "需要明确的时间范围"]
            },
            "air_quality_comprehensive": {
                "keywords": ["报表", "综合", "统计", "汇总", "分析"],
                "time_requirements": "flexible",  # 时间要求灵活
                "location_requirements": "any",  # 支持任何位置
                "data_types": ["historical", "aggregated"],
                "limitations": ["数据更新可能有延迟"]
            },
            "air_quality_real_time": {
                "keywords": ["实时", "当前", "现在", "最新"],
                "time_requirements": "current",  # 当前时间
                "location_requirements": "specific",  # 需要特定位置
                "data_types": ["real_time"],
                "limitations": ["只支持当前数据", "不支持历史查询"]
            }
        }
        
        # 失败模式分析
        self.failure_patterns = {
            "parameter_mismatch": r"参数.*不匹配|参数.*错误|invalid parameter",
            "time_constraint": r"时间.*不支持|时间.*范围.*错误|time.*not.*supported",
            "location_constraint": r"位置.*不支持|地点.*无效|location.*not.*found",
            "data_availability": r"数据.*不可用|没有.*数据|no.*data.*available",
            "api_limit": r"API.*限制|请求.*频繁|rate.*limit",
            "service_unavailable": r"服务.*不可用|连接.*失败|service.*unavailable"
        }
    
    def reselect_tool(self, original_tool: str, failure_reason: str, 
                     question: str, parameters: Dict[str, Any], 
                     context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        重新选择工具
        
        Args:
            original_tool: 原始选择的工具
            failure_reason: 失败原因
            question: 用户问题
            parameters: 提取的参数
            context: 额外上下文
            
        Returns:
            重选结果
        """
        context = context or {}
        
        logger.info(f"开始智能工具重选择: 原工具={original_tool}, 失败原因={failure_reason}")
        
        # 分析失败原因
        failure_analysis = self._analyze_failure(failure_reason, original_tool)
        
        # 分析用户意图和需求
        intent_analysis = self._analyze_user_intent(question, parameters)
        
        # 获取可用工具
        available_tools = self._get_available_tools(exclude=[original_tool])
        
        # 基于失败原因和意图选择新工具
        reselection_result = self._select_best_tool(
            available_tools, 
            failure_analysis, 
            intent_analysis, 
            parameters,
            context
        )
        
        # 参数适配
        if reselection_result.get("recommended_tool"):
            adapted_params = self._adapt_parameters(
                reselection_result["recommended_tool"],
                parameters,
                failure_analysis
            )
            reselection_result["adapted_parameters"] = adapted_params
        
        logger.info(f"工具重选择完成: {reselection_result.get('recommended_tool', '无合适工具')}")
        return reselection_result
    
    def _analyze_failure(self, failure_reason: str, original_tool: str) -> Dict[str, Any]:
        """分析失败原因"""
        analysis = {
            "failure_type": "unknown",
            "constraint_violated": None,
            "severity": "medium",
            "recoverable": True
        }
        
        # 匹配失败模式
        for pattern_name, pattern in self.failure_patterns.items():
            if re.search(pattern, failure_reason, re.IGNORECASE):
                analysis["failure_type"] = pattern_name
                break
        
        # 基于失败类型确定约束冲突
        if analysis["failure_type"] == "parameter_mismatch":
            analysis["constraint_violated"] = "parameter_format"
            analysis["severity"] = "low"
        elif analysis["failure_type"] == "time_constraint":
            analysis["constraint_violated"] = "time_requirements"
            analysis["severity"] = "medium"
        elif analysis["failure_type"] == "location_constraint":
            analysis["constraint_violated"] = "location_requirements"
            analysis["severity"] = "medium"
        elif analysis["failure_type"] == "data_availability":
            analysis["constraint_violated"] = "data_types"
            analysis["severity"] = "high"
        elif analysis["failure_type"] in ["api_limit", "service_unavailable"]:
            analysis["severity"] = "high"
            analysis["recoverable"] = False
        
        # 分析原工具的限制
        original_tool_info = self.tool_rules.get(original_tool, {})
        analysis["original_tool_limitations"] = original_tool_info.get("limitations", [])
        
        return analysis
    
    def _analyze_user_intent(self, question: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """分析用户意图"""
        intent = {
            "query_type": "unknown",
            "time_nature": "unknown",
            "location_nature": "unknown",
            "data_preference": "any",
            "keywords_found": []
        }
        
        question_lower = question.lower()
        
        # 分析查询类型
        for tool_name, tool_info in self.tool_rules.items():
            keywords_found = [kw for kw in tool_info["keywords"] if kw in question_lower]
            if keywords_found:
                intent["keywords_found"].extend(keywords_found)
                if intent["query_type"] == "unknown":
                    intent["query_type"] = tool_name
        
        # 分析时间性质
        if "实时" in question_lower or "当前" in question_lower or "现在" in question_lower:
            intent["time_nature"] = "current"
        elif "对比" in question_lower or "比较" in question_lower:
            intent["time_nature"] = "range"
        elif parameters.get("start_time") and parameters.get("end_time"):
            intent["time_nature"] = "range"
        elif parameters.get("start_time") or parameters.get("end_time"):
            intent["time_nature"] = "specific"
        else:
            intent["time_nature"] = "flexible"
        
        # 分析位置性质
        location_name = parameters.get("location_name", "")
        if isinstance(location_name, list) and len(location_name) > 1:
            intent["location_nature"] = "multiple"
        elif location_name:
            intent["location_nature"] = "specific"
        else:
            intent["location_nature"] = "any"
        
        # 数据偏好
        if "历史" in question_lower:
            intent["data_preference"] = "historical"
        elif "实时" in question_lower:
            intent["data_preference"] = "real_time"
        elif "统计" in question_lower or "汇总" in question_lower:
            intent["data_preference"] = "aggregated"
        
        return intent
    
    def _get_available_tools(self, exclude: List[str] = None) -> List[str]:
        """获取可用工具列表"""
        exclude = exclude or []
        all_tools = list(self.tool_rules.keys())
        return [tool for tool in all_tools if tool not in exclude]
    
    def _select_best_tool(self, available_tools: List[str], failure_analysis: Dict[str, Any],
                         intent_analysis: Dict[str, Any], parameters: Dict[str, Any],
                         context: Dict[str, Any]) -> Dict[str, Any]:
        """选择最佳工具"""
        if not available_tools:
            return {
                "success": False,
                "error": "没有可用的备选工具",
                "recommended_tool": None
            }
        
        tool_scores = {}
        
        for tool in available_tools:
            score = self._calculate_tool_score(
                tool, failure_analysis, intent_analysis, parameters, context
            )
            tool_scores[tool] = score
        
        # 选择得分最高的工具
        best_tool = max(tool_scores, key=tool_scores.get)
        best_score = tool_scores[best_tool]
        
        if best_score < 0.3:  # 最低可接受分数
            return {
                "success": False,
                "error": "没有找到合适的备选工具",
                "recommended_tool": None,
                "tool_scores": tool_scores
            }
        
        return {
            "success": True,
            "recommended_tool": best_tool,
            "confidence": best_score,
            "selection_reason": self._generate_selection_reason(
                best_tool, failure_analysis, intent_analysis
            ),
            "tool_scores": tool_scores,
            "alternatives": self._get_alternatives(tool_scores, best_tool)
        }
    
    def _calculate_tool_score(self, tool: str, failure_analysis: Dict[str, Any],
                             intent_analysis: Dict[str, Any], parameters: Dict[str, Any],
                             context: Dict[str, Any]) -> float:
        """计算工具适用性分数"""
        tool_info = self.tool_rules.get(tool, {})
        score = 0.0
        
        # 基础分数
        score += 0.2
        
        # 关键词匹配分数 (40%)
        tool_keywords = tool_info.get("keywords", [])
        intent_keywords = intent_analysis.get("keywords_found", [])
        keyword_matches = len(set(tool_keywords) & set(intent_keywords))
        if tool_keywords:
            score += 0.4 * (keyword_matches / len(tool_keywords))
        
        # 时间需求匹配分数 (25%)
        time_req = tool_info.get("time_requirements", "flexible")
        intent_time = intent_analysis.get("time_nature", "unknown")
        if self._time_requirements_match(time_req, intent_time):
            score += 0.25
        
        # 位置需求匹配分数 (20%)
        location_req = tool_info.get("location_requirements", "any")
        intent_location = intent_analysis.get("location_nature", "unknown")
        if self._location_requirements_match(location_req, intent_location):
            score += 0.20
        
        # 数据类型匹配分数 (15%)
        data_types = tool_info.get("data_types", [])
        intent_data = intent_analysis.get("data_preference", "any")
        if intent_data in data_types or intent_data == "any":
            score += 0.15
        
        # 失败原因避免分数 (扣分机制)
        constraint_violated = failure_analysis.get("constraint_violated")
        if constraint_violated:
            if constraint_violated == "time_requirements" and time_req == "current" and intent_time == "range":
                score -= 0.3
            elif constraint_violated == "location_requirements" and location_req == "specific" and intent_location == "any":
                score -= 0.2
            elif constraint_violated == "data_types" and intent_data not in data_types:
                score -= 0.25
        
        return max(0.0, min(1.0, score))
    
    def _time_requirements_match(self, tool_req: str, intent_time: str) -> bool:
        """检查时间需求匹配"""
        if tool_req == "flexible":
            return True
        elif tool_req == "current" and intent_time == "current":
            return True
        elif tool_req == "range" and intent_time in ["range", "specific"]:
            return True
        return False
    
    def _location_requirements_match(self, tool_req: str, intent_location: str) -> bool:
        """检查位置需求匹配"""
        if tool_req == "any":
            return True
        elif tool_req == "specific" and intent_location in ["specific", "multiple"]:
            return True
        elif tool_req == "multiple_or_specific" and intent_location in ["specific", "multiple"]:
            return True
        return False
    
    def _generate_selection_reason(self, tool: str, failure_analysis: Dict[str, Any],
                                  intent_analysis: Dict[str, Any]) -> str:
        """生成选择理由"""
        tool_info = self.tool_rules.get(tool, {})
        reasons = []
        
        # 基于关键词匹配
        intent_keywords = intent_analysis.get("keywords_found", [])
        tool_keywords = tool_info.get("keywords", [])
        matched_keywords = set(intent_keywords) & set(tool_keywords)
        if matched_keywords:
            reasons.append(f"匹配关键词: {', '.join(matched_keywords)}")
        
        # 基于时间需求
        time_req = tool_info.get("time_requirements", "flexible")
        intent_time = intent_analysis.get("time_nature", "unknown")
        if self._time_requirements_match(time_req, intent_time):
            reasons.append(f"支持{intent_time}时间查询")
        
        # 基于失败原因避免
        failure_type = failure_analysis.get("failure_type", "unknown")
        if failure_type != "unknown":
            reasons.append(f"避免了{failure_type}类型的错误")
        
        return "; ".join(reasons) if reasons else "基于综合评估选择"
    
    def _get_alternatives(self, tool_scores: Dict[str, float], best_tool: str) -> List[Dict[str, Any]]:
        """获取备选工具"""
        alternatives = []
        sorted_tools = sorted(tool_scores.items(), key=lambda x: x[1], reverse=True)
        
        for tool, score in sorted_tools:
            if tool != best_tool and score > 0.2:
                alternatives.append({
                    "tool": tool,
                    "score": score,
                    "description": self.tool_rules.get(tool, {}).get("keywords", [])
                })
        
        return alternatives[:2]  # 返回最多2个备选项
    
    def _adapt_parameters(self, new_tool: str, original_params: Dict[str, Any],
                         failure_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """适配参数到新工具"""
        adapted_params = original_params.copy()
        tool_info = self.tool_rules.get(new_tool, {})
        
        # 基于新工具的要求调整参数
        time_req = tool_info.get("time_requirements", "flexible")
        location_req = tool_info.get("location_requirements", "any")
        
        # 时间参数适配
        if time_req == "current":
            # 实时查询，移除时间范围参数
            adapted_params.pop("start_time", None)
            adapted_params.pop("end_time", None)
            adapted_params["query_type"] = "real_time"
        elif time_req == "range":
            # 确保有时间范围
            if not adapted_params.get("start_time") or not adapted_params.get("end_time"):
                # 提供默认时间范围（最近一周）
                from datetime import datetime, timedelta
                end_date = datetime.now()
                start_date = end_date - timedelta(days=7)
                adapted_params["start_time"] = start_date.strftime("%Y-%m-%d")
                adapted_params["end_time"] = end_date.strftime("%Y-%m-%d")
        
        # 位置参数适配
        if location_req == "specific":
            location_name = adapted_params.get("location_name")
            if isinstance(location_name, list):
                # 选择第一个位置
                adapted_params["location_name"] = location_name[0] if location_name else None
        
        # 基于失败原因调整参数
        constraint_violated = failure_analysis.get("constraint_violated")
        if constraint_violated == "parameter_format":
            # 清理可能有问题的参数格式
            adapted_params = self._clean_parameter_format(adapted_params)
        
        return adapted_params
    
    def _clean_parameter_format(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """清理参数格式"""
        cleaned = {}
        
        for key, value in params.items():
            if value is not None:
                if isinstance(value, str):
                    # 清理字符串参数
                    cleaned[key] = value.strip()
                elif isinstance(value, list):
                    # 清理列表参数
                    cleaned[key] = [str(item).strip() for item in value if item is not None]
                else:
                    cleaned[key] = value
        
        return cleaned

# 全局智能工具重选择器实例
_smart_tool_reselection = None

def get_smart_tool_reselection() -> SmartToolReselection:
    """获取全局智能工具重选择器实例"""
    global _smart_tool_reselection
    if _smart_tool_reselection is None:
        _smart_tool_reselection = SmartToolReselection()
    return _smart_tool_reselection