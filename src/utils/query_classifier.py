#!/usr/bin/env python3
"""
查询分类器 - 智能分析用户查询意图，辅助工具选择
Query Classifier - Intelligent analysis of user query intent to assist tool selection
"""

import re
from typing import Dict, List, Tuple
from dataclasses import dataclass

@dataclass
class QueryIntent:
    """查询意图分析结果"""
    is_comparison: bool  # 是否为对比查询
    time_periods: List[str]  # 识别的时间段
    comparison_indicators: List[str]  # 对比指示词
    query_type: str  # 查询类型: "summary", "comparison", "trend"
    confidence: float  # 置信度 0-1
    reason: str  # 判断理由

class QueryClassifier:
    """查询分类器，分析用户查询意图"""
    
    def __init__(self):
        # 对比关键词（按重要性排序）
        self.comparison_keywords = {
            'strong': [  # 强对比指示词
                '对比', '比较', '相比', '比起', '相较于',
                '同比', '环比', '与.*相比', '比.*时候'
            ],
            'medium': [  # 中等对比指示词
                '变化', '改善', '增长', '减少', '提升', '下降',
                '变化了多少', '改善了吗', '增加还是减少'
            ],
            'weak': [  # 弱对比指示词
                '趋势', '走势', '发展', '情况'
            ]
        }
        
        # 时间表达式模式
        self.time_patterns = [
            r'(\d{4}年\d{1,2}月)',  # 2024年5月
            r'(去年同期)', r'(上年同期)', 
            r'(上月)', r'(本月)', r'(这月)', r'(当月)',
            r'(上周)', r'(本周)', r'(这周)', r'(当周)',
            r'(昨天)', r'(今天)', r'(明天)',
            r'(上个月)', r'(这个月)', r'(下个月)',
            r'(上一年)', r'(今年)', r'(去年)',
            r'(第.*季度)', r'(.*季度)',
            r'(.*前)', r'(.*后)'
        ]
    
    def classify(self, question: str) -> QueryIntent:
        """
        分析查询意图
        
        Args:
            question: 用户查询问题
            
        Returns:
            QueryIntent: 查询意图分析结果
        """
        question = question.lower().strip()
        
        # 1. 检测对比指示词
        comparison_indicators = self._detect_comparison_indicators(question)
        
        # 2. 检测时间段
        time_periods = self._extract_time_periods(question)
        
        # 3. 判断查询类型和置信度
        query_type, confidence, reason = self._determine_query_type(
            comparison_indicators, time_periods, question
        )
        
        return QueryIntent(
            is_comparison=(query_type == "comparison"),
            time_periods=time_periods,
            comparison_indicators=comparison_indicators,
            query_type=query_type,
            confidence=confidence,
            reason=reason
        )
    
    def _detect_comparison_indicators(self, question: str) -> List[str]:
        """检测对比指示词"""
        indicators = []
        
        for category, keywords in self.comparison_keywords.items():
            for keyword in keywords:
                if re.search(keyword, question):
                    indicators.append(f"{keyword}({category})")
        
        return indicators
    
    def _extract_time_periods(self, question: str) -> List[str]:
        """提取时间段"""
        time_periods = []
        
        for pattern in self.time_patterns:
            matches = re.findall(pattern, question)
            time_periods.extend(matches)
        
        return list(set(time_periods))  # 去重
    
    def _determine_query_type(self, comparison_indicators: List[str], 
                            time_periods: List[str], question: str) -> Tuple[str, float, str]:
        """判断查询类型和置信度"""
        
        # 强对比指示词 = 高置信度对比查询
        strong_indicators = [ind for ind in comparison_indicators if 'strong' in ind]
        if strong_indicators:
            return "comparison", 0.9, f"检测到强对比指示词: {strong_indicators}"
        
        # 两个以上时间段 = 高置信度对比查询
        if len(time_periods) >= 2:
            return "comparison", 0.85, f"检测到多个时间段: {time_periods}"
        
        # 中等对比指示词 + 一个时间段 = 中等置信度对比查询
        medium_indicators = [ind for ind in comparison_indicators if 'medium' in ind]
        if medium_indicators and len(time_periods) >= 1:
            return "comparison", 0.7, f"检测到中等对比指示词且有时间段: {medium_indicators}, {time_periods}"
        
        # 仅中等对比指示词 = 低置信度对比查询
        if medium_indicators:
            return "comparison", 0.5, f"检测到中等对比指示词: {medium_indicators}"
        
        # 弱对比指示词 = 趋势查询
        weak_indicators = [ind for ind in comparison_indicators if 'weak' in ind]
        if weak_indicators:
            return "trend", 0.4, f"检测到弱对比指示词，判断为趋势查询: {weak_indicators}"
        
        # 默认为汇总查询
        return "summary", 0.8, "无明显对比意图，判断为汇总查询"

# 全局实例
_query_classifier = None

def get_query_classifier() -> QueryClassifier:
    """获取查询分类器实例（单例模式）"""
    global _query_classifier
    if _query_classifier is None:
        _query_classifier = QueryClassifier()
    return _query_classifier