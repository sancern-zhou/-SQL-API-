#!/usr/bin/env python3
"""
路由策略测试文件
测试开放式查询检测和智能路由功能
"""

import unittest
import sys
import os

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from uqp_router import UQPRouter
from external_api_handler import ExternalAPIHandler
from vanna_service import VannaService


class TestRoutingStrategy(unittest.TestCase):
    """路由策略测试类"""
    
    def setUp(self):
        """测试初始化"""
        # 模拟创建路由器（不依赖真实的依赖项）
        self.router = UQPRouter(None, None)
    
    def test_open_analysis_detection(self):
        """测试开放式查询检测"""
        # 应该被检测为开放式查询的样本
        open_queries = [
            "哪个站点PM2.5最高",
            "排名最后的城市",
            "超过100的站点有哪些",
            "所有超标的区域",
            "PM2.5浓度最大的监测点",
            "哪些城市空气质量最差",
            "查询实时监测数据",
            "统计各站点平均浓度",
            "计算污染物标准差",
            "分析小时级数据趋势",
            "连续三天超标的站点"
        ]
        
        for query in open_queries:
            with self.subTest(query=query):
                result = self.router._is_open_analysis_query(query)
                self.assertTrue(result, f"应该检测到开放式查询: {query}")
    
    def test_specific_queries_routing(self):
        """测试特定查询不应被检测为开放式查询"""
        api_queries = [
            "查询广州市2025年2月的空气质量",
            "对比深圳市今年与去年的数据",
            "获取广雅中学上周的监测报告",
            "查看越秀区昨天的空气质量",
            "广州市5月份综合报表"
        ]
        
        for query in api_queries:
            with self.subTest(query=query):
                result = self.router._is_open_analysis_query(query)
                self.assertFalse(result, f"不应该检测为开放式查询: {query}")
    
    def test_intent_classification_with_open_analysis(self):
        """测试意图分类中的开放式查询强制路由"""
        # 开放式查询应该强制路由到NL2SQL
        open_query = "哪个站点PM2.5浓度最高"
        intent, confidence = self.router.classify_intent(open_query)
        
        self.assertEqual(intent, "NL2SQL", "开放式查询应该路由到NL2SQL")
        self.assertEqual(confidence, 1.0, "开放式查询应该有最高置信度")
    
    def test_external_api_handler_detection(self):
        """测试外部API处理器的开放式查询检测"""
        handler = ExternalAPIHandler()
        
        # 测试检测方法
        open_query = "哪个城市空气质量最差"
        result = handler._is_open_analysis_query(open_query)
        self.assertTrue(result, "外部API处理器应该检测到开放式查询")
        
        specific_query = "查询广州市今天的空气质量"
        result = handler._is_open_analysis_query(specific_query)
        self.assertFalse(result, "外部API处理器不应该将特定查询检测为开放式查询")
    
    def test_vanna_service_detection(self):
        """测试VannaService的开放式查询检测"""
        # 创建VannaService实例（不进行完整初始化）
        service = VannaService.__new__(VannaService)
        
        # 测试检测方法
        open_query = "统计各站点平均PM2.5浓度"
        result = service._is_open_analysis_query(open_query)
        self.assertTrue(result, "VannaService应该检测到开放式查询")


class TestComplexQueries(unittest.TestCase):
    """复杂查询路由测试"""
    
    def setUp(self):
        self.router = UQPRouter(None, None)
    
    def test_time_granularity_detection(self):
        """测试时间粒度检测"""
        time_queries = [
            "查询实时PM2.5数据",
            "获取小时级监测数据",
            "当前空气质量状况",
            "实时监测站点状态"
        ]
        
        for query in time_queries:
            with self.subTest(query=query):
                result = self.router._is_open_analysis_query(query)
                self.assertTrue(result, f"时间粒度查询应该路由到SQL: {query}")
    
    def test_complex_conditions(self):
        """测试复杂条件查询"""
        complex_queries = [
            "PM2.5大于100且NO2小于50的站点",
            "复杂多条件筛选查询",
            "计算相关性分析",
            "移动平均值计算"
        ]
        
        for query in complex_queries:
            with self.subTest(query=query):
                result = self.router._is_open_analysis_query(query)
                self.assertTrue(result, f"复杂查询应该路由到SQL: {query}")


if __name__ == '__main__':
    unittest.main()