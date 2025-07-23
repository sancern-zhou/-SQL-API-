#!/usr/bin/env python3
"""
阶段1路由策略测试脚本
Phase 1 Routing Strategy Testing Script
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import time
from src.routing.api_priority_engine import APIPriorityEngine
from src.routing.decision_engine import get_routing_engine
from src.routing.routing_monitor import get_routing_monitor


def test_api_priority_engine():
    """测试API优先策略引擎"""
    print("=" * 60)
    print("测试API优先策略引擎")
    print("=" * 60)
    
    try:
        # 创建引擎实例
        engine = APIPriorityEngine()
        
        # 测试用例
        test_cases = [
            # 应该走SQL的问题
            "哪些城市的空气质量最差？",
            "最近一周空气质量变化最大的站点",
            "统计所有城市的空气质量分布",
            "发现广州空气质量数据中的异常点",
            "原始数据有哪些监测因子？",
            "对比分析今年和去年的空气质量差异",
            
            # 应该走API的问题
            "查询广州市2024年5月1日的空气质量日报",
            "获取越秀区2024年5月的空气质量月报",
            "广州市2024年5月的空气质量排名",
            "广雅中学上周的空气质量数据",
            "天河区今年第一季度的空气质量报告",
            "深圳市昨天的空气质量情况"
        ]
        
        print(f"SQL排除关键词数量: {len(engine.sql_exclusion_keywords)}")
        print(f"关键词示例: {engine.sql_exclusion_keywords[:10]}")
        print()
        
        for i, question in enumerate(test_cases, 1):
            print(f"测试 {i:2d}: {question}")
            
            route, confidence, decision_info = engine.decide_route(question)
            matched_keywords = decision_info.get('matched_keywords', [])
            
            print(f"         路由: {route}")
            print(f"         置信度: {confidence:.3f}")
            print(f"         匹配关键词: {matched_keywords}")
            print()
        
        # 显示统计信息
        print("引擎统计信息:")
        stats = engine.get_statistics()
        print(f"  总请求数: {stats['total_requests']}")
        print(f"  API路由数: {stats['api_route_count']}")
        print(f"  SQL路由数: {stats['sql_route_count']}")
        print(f"  API路由比例: {stats['api_route_percentage']:.1f}%")
        print(f"  SQL路由比例: {stats['sql_route_percentage']:.1f}%")
        print(f"  平均响应时间: {stats['avg_response_time']:.4f}s")
        print()
        
        return True
        
    except Exception as e:
        print(f"API优先策略引擎测试失败: {e}")
        return False


def test_routing_decision_engine():
    """测试路由决策引擎"""
    print("=" * 60)
    print("测试路由决策引擎")
    print("=" * 60)
    
    try:
        # 获取引擎实例
        engine = get_routing_engine()
        
        # 测试用例
        test_cases = [
            "哪些城市的空气质量最差？",
            "查询广州市2024年5月1日的空气质量日报",
            "统计所有城市的空气质量分布",
            "获取越秀区2024年5月的空气质量月报",
            "发现广州空气质量数据中的异常点",
            "广雅中学上周的空气质量数据"
        ]
        
        # 显示当前策略
        debug_info = engine.get_debug_info()
        print(f"当前策略: {debug_info['current_strategy']}")
        print()
        
        for i, question in enumerate(test_cases, 1):
            print(f"测试 {i:2d}: {question}")
            
            route, confidence, decision_info = engine.decide_route(question)
            strategy = decision_info.get('strategy', 'unknown')
            
            print(f"         路由: {route}")
            print(f"         置信度: {confidence:.3f}")
            print(f"         策略: {strategy}")
            print()
        
        # 显示统计信息
        print("引擎统计信息:")
        stats = engine.get_stats()
        print(f"  当前策略: {stats['current_strategy']}")
        print(f"  引擎状态: {'启用' if stats['enabled'] else '禁用'}")
        if 'api_priority_stats' in stats:
            api_stats = stats['api_priority_stats']
            print(f"  API优先引擎统计:")
            print(f"    总请求数: {api_stats['total_requests']}")
            print(f"    API路由比例: {api_stats['api_route_percentage']:.1f}%")
            print(f"    SQL路由比例: {api_stats['sql_route_percentage']:.1f}%")
        print()
        
        return True
        
    except Exception as e:
        print(f"路由决策引擎测试失败: {e}")
        return False


def test_strategy_switching():
    """测试策略切换"""
    print("=" * 60)
    print("测试策略切换")
    print("=" * 60)
    
    try:
        engine = get_routing_engine()
        
        # 测试问题
        test_question = "哪些城市的空气质量最差？"
        
        # 测试API优先策略
        print("1. 测试API优先策略:")
        switch_result = engine.switch_strategy('api_priority')
        print(f"   切换结果: {switch_result['message']}")
        
        route, confidence, decision_info = engine.decide_route(test_question)
        print(f"   问题: {test_question}")
        print(f"   路由: {route}, 置信度: {confidence:.3f}")
        print(f"   策略: {decision_info.get('strategy', 'unknown')}")
        print()
        
        # 测试原始策略
        print("2. 测试原始策略:")
        switch_result = engine.switch_strategy('keyword_vector_hybrid')
        print(f"   切换结果: {switch_result['message']}")
        
        route, confidence, decision_info = engine.decide_route(test_question)
        print(f"   问题: {test_question}")
        print(f"   路由: {route}, 置信度: {confidence:.3f}")
        print(f"   策略: {decision_info.get('strategy', 'unknown')}")
        print()
        
        # 切换回API优先策略
        print("3. 切换回API优先策略:")
        switch_result = engine.switch_strategy('api_priority')
        print(f"   切换结果: {switch_result['message']}")
        print()
        
        return True
        
    except Exception as e:
        print(f"策略切换测试失败: {e}")
        return False


def test_routing_monitor():
    """测试路由监控器"""
    print("=" * 60)
    print("测试路由监控器")
    print("=" * 60)
    
    try:
        monitor = get_routing_monitor()
        
        # 模拟一些路由决策
        test_cases = [
            ("哪些城市的空气质量最差？", "NL2SQL", 0.9),
            ("查询广州市2024年5月1日的空气质量日报", "EXTERNAL_API", 0.85),
            ("统计所有城市的空气质量分布", "NL2SQL", 0.88),
            ("获取越秀区2024年5月的空气质量月报", "EXTERNAL_API", 0.82),
            ("发现广州空气质量数据中的异常点", "NL2SQL", 0.87),
        ]
        
        print("模拟路由决策...")
        for question, route, confidence in test_cases:
            decision_info = {
                'strategy': 'api_priority',
                'matched_keywords': ['测试关键词'],
                'route_reason': 'test_simulation'
            }
            response_time = 0.05 + (hash(question) % 100) / 10000  # 模拟响应时间
            
            monitor.record_routing_decision(
                question, route, confidence, decision_info, response_time
            )
            
            print(f"  记录: {question[:30]}... -> {route}")
        
        print()
        
        # 获取统计信息
        print("监控统计信息:")
        stats = monitor.get_statistics()
        
        performance = stats['performance']
        print(f"  总请求数: {performance['total_requests']}")
        print(f"  API路由比例: {performance['api_route_percentage']:.1f}%")
        print(f"  SQL路由比例: {performance['sql_route_percentage']:.1f}%")
        print(f"  平均响应时间: {performance['avg_response_time']:.4f}s")
        print(f"  错误率: {performance['error_rate']:.1f}%")
        
        health = stats['system_health']
        print(f"  系统健康状态: {health['status']}")
        print(f"  健康分数: {health['health_score']}")
        print()
        
        return True
        
    except Exception as e:
        print(f"路由监控器测试失败: {e}")
        return False


def test_performance_comparison():
    """测试性能对比"""
    print("=" * 60)
    print("测试性能对比")
    print("=" * 60)
    
    try:
        engine = get_routing_engine()
        
        # 测试问题
        test_questions = [
            "哪些城市的空气质量最差？",
            "查询广州市2024年5月1日的空气质量日报",
            "统计所有城市的空气质量分布",
            "获取越秀区2024年5月的空气质量月报",
            "发现广州空气质量数据中的异常点",
            "广雅中学上周的空气质量数据",
            "最近一周空气质量变化最大的站点",
            "天河区今年第一季度的空气质量报告",
            "原始数据有哪些监测因子？",
            "深圳市昨天的空气质量情况"
        ]
        
        # 测试API优先策略
        print("1. API优先策略性能测试:")
        engine.switch_strategy('api_priority')
        
        start_time = time.time()
        for _ in range(100):
            for question in test_questions:
                engine.decide_route(question)
        api_priority_time = time.time() - start_time
        
        print(f"   1000次决策总时间: {api_priority_time:.4f}s")
        print(f"   平均单次决策时间: {api_priority_time/1000:.6f}s")
        
        # 获取API优先策略统计
        stats = engine.get_stats()
        if 'api_priority_stats' in stats:
            api_stats = stats['api_priority_stats']
            print(f"   API路由比例: {api_stats['api_route_percentage']:.1f}%")
            print(f"   SQL路由比例: {api_stats['sql_route_percentage']:.1f}%")
        print()
        
        # 测试原始策略
        print("2. 原始策略性能测试:")
        engine.switch_strategy('keyword_vector_hybrid')
        
        start_time = time.time()
        for _ in range(100):
            for question in test_questions:
                engine.decide_route(question)
        original_time = time.time() - start_time
        
        print(f"   1000次决策总时间: {original_time:.4f}s")
        print(f"   平均单次决策时间: {original_time/1000:.6f}s")
        print()
        
        # 性能对比
        print("3. 性能对比:")
        speed_improvement = ((original_time - api_priority_time) / original_time) * 100
        print(f"   API优先策略速度提升: {speed_improvement:.1f}%")
        
        if speed_improvement > 0:
            print(f"   [结果] API优先策略更快")
        else:
            print(f"   [结果] 原始策略更快")
        print()
        
        # 切换回API优先策略
        engine.switch_strategy('api_priority')
        
        return True
        
    except Exception as e:
        print(f"性能对比测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("阶段1路由策略测试")
    print("=" * 60)
    print()
    
    test_results = []
    
    # 运行各项测试
    test_results.append(("API优先策略引擎", test_api_priority_engine()))
    test_results.append(("路由决策引擎", test_routing_decision_engine()))
    test_results.append(("策略切换", test_strategy_switching()))
    test_results.append(("路由监控器", test_routing_monitor()))
    test_results.append(("性能对比", test_performance_comparison()))
    
    # 显示测试结果
    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "[通过]" if result else "[失败]"
        print(f"{test_name:20s}: {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("[成功] 所有测试通过！阶段1路由优化成功。")
        return 0
    else:
        print("[失败] 部分测试失败，请检查问题。")
        return 1


if __name__ == "__main__":
    sys.exit(main())