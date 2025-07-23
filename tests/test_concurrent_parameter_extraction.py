#!/usr/bin/env python3
"""
参数提取并发测试脚本
Concurrent Parameter Extraction Test Script

支持Windows系统，最大并发数20
"""

import asyncio
import time
import json
import logging
import sys
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Tuple
import threading
from dataclasses import dataclass, asdict

# 添加项目路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    from src.utils.smart_geo_extractor import get_smart_geo_extractor
    from src.utils.param_converter import get_param_converter
    from src.utils.parameter_deduplicator import get_parameter_deduplicator
except ImportError as e:
    print(f"导入模块失败: {e}")
    print("请确保在项目根目录下运行此脚本")
    sys.exit(1)

@dataclass
class TestCase:
    """测试用例数据类"""
    id: str
    category: str
    input_text: str
    expected_location: str
    expected_location_code: str
    expected_time: str
    description: str
    priority: str

@dataclass
class TestResult:
    """测试结果数据类"""
    test_id: str
    category: str
    input_text: str
    success: bool
    extracted_location: str
    extracted_time: str
    response_time_ms: float
    error_message: str
    thread_id: str
    timestamp: str

class ConcurrentParameterTester:
    """并发参数提取测试器"""
    
    def __init__(self, max_workers: int = 20):
        self.max_workers = min(max_workers, 20)  # 限制最大并发数为20
        self.geo_extractor = None
        self.param_converter = None
        self.param_deduplicator = None
        self.results: List[TestResult] = []
        self.lock = threading.Lock()
        self.logger = self._setup_logger()
        
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger('concurrent_test')
        logger.setLevel(logging.INFO)
        
        # 创建文件处理器
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        fh = logging.FileHandler('logs/concurrent_test.log', encoding='utf-8')
        fh.setLevel(logging.INFO)
        
        # 创建控制台处理器
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        # 创建格式器
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        # 添加处理器
        logger.addHandler(fh)
        logger.addHandler(ch)
        
        return logger
    
    def _initialize_components(self):
        """初始化组件（线程安全）"""
        try:
            if not self.geo_extractor:
                self.geo_extractor = get_smart_geo_extractor()
            if not self.param_converter:
                self.param_converter = get_param_converter()
            if not self.param_deduplicator:
                self.param_deduplicator = get_parameter_deduplicator()
            return True
        except Exception as e:
            self.logger.error(f"组件初始化失败: {e}")
            return False
    
    def create_test_cases(self) -> List[TestCase]:
        """创建测试用例"""
        test_cases = []
        
        # 地理位置精确匹配测试用例
        geo_exact_cases = [
            ("geo_001", "广州市今天空气质量", "广州市", "440100", "今天"),
            ("geo_002", "深圳华侨城PM2.5浓度", "华侨城", "1019A", ""),
            ("geo_003", "珠海前山空气质量数据", "前山", "1029A", ""),
            ("geo_004", "天河五山监测数据", "天河五山", "1427A", ""),
            ("geo_005", "广雅中学空气质量", "广雅中学", "1001A", ""),
            ("geo_006", "市监测站数据", "市监测站", "1008A", ""),
            ("geo_007", "番禺大学城空气质量", "番禺大学城", "1421A", ""),
            ("geo_008", "南沙大稳PM2.5", "南沙大稳", "1111A", ""),
            ("geo_009", "白云嘉禾数据", "白云嘉禾", "1333A", ""),
            ("geo_010", "增城荔城空气质量", "增城荔城", "1429A", ""),
        ]
        
        for case_id, input_text, expected_location, expected_code, expected_time in geo_exact_cases:
            test_cases.append(TestCase(
                id=case_id,
                category="地理位置精确匹配",
                input_text=input_text,
                expected_location=expected_location,
                expected_location_code=expected_code,
                expected_time=expected_time,
                description=f"测试精确匹配: {expected_location}",
                priority="high"
            ))
        
        # 地理位置模糊匹配测试用例
        geo_fuzzy_cases = [
            ("geo_f01", "广雅的空气质量", "广雅中学", "1001A", ""),
            ("geo_f02", "五山的PM2.5", "天河五山", "1427A", ""),
            ("geo_f03", "大学城空气质量", "番禺大学城", "1421A", ""),
            ("geo_f04", "华侨城的数据", "华侨城", "1019A", ""),
            ("geo_f05", "天河的空气质量", "天河区", "440100009", ""),
            ("geo_f06", "越秀空气数据", "越秀区", "440100011", ""),
            ("geo_f07", "南山PM2.5浓度", "南山区", "440300008", ""),
            ("geo_f08", "广州市区空气质量", "广州市", "440100", ""),
            ("geo_f09", "深圳市中心PM2.5", "深圳市", "440300", ""),
            ("geo_f10", "珠海市区环境", "珠海市", "440400", ""),
        ]
        
        for case_id, input_text, expected_location, expected_code, expected_time in geo_fuzzy_cases:
            test_cases.append(TestCase(
                id=case_id,
                category="地理位置模糊匹配",
                input_text=input_text,
                expected_location=expected_location,
                expected_location_code=expected_code,
                expected_time=expected_time,
                description=f"测试模糊匹配: {expected_location}",
                priority="high"
            ))
        
        # 时间解析测试用例
        time_cases = [
            ("time_001", "2024年5月15日空气质量", "", "", "2024年5月15日"),
            ("time_002", "昨天广州空气质量", "广州市", "440100", "昨天"),
            ("time_003", "上周深圳PM2.5", "深圳市", "440300", "上周"),
            ("time_004", "本月珠海数据", "珠海市", "440400", "本月"),
            ("time_005", "去年同期空气质量", "", "", "去年同期"),
            ("time_006", "2024年5月空气质量", "", "", "2024年5月"),
            ("time_007", "今年PM2.5数据", "", "", "今年"),
            ("time_008", "上个月环境数据", "", "", "上个月"),
            ("time_009", "本季度空气质量", "", "", "本季度"),
            ("time_010", "最近7天PM2.5", "", "", "最近7天"),
        ]
        
        for case_id, input_text, expected_location, expected_code, expected_time in time_cases:
            test_cases.append(TestCase(
                id=case_id,
                category="时间解析",
                input_text=input_text,
                expected_location=expected_location,
                expected_location_code=expected_code,
                expected_time=expected_time,
                description=f"测试时间解析: {expected_time}",
                priority="high"
            ))
        
        # 组合测试用例
        combo_cases = [
            ("combo_001", "广州市昨天的空气质量", "广州市", "440100", "昨天"),
            ("combo_002", "深圳华侨城上周PM2.5", "华侨城", "1019A", "上周"),
            ("combo_003", "珠海前山2024年5月数据", "前山", "1029A", "2024年5月"),
            ("combo_004", "天河五山本月空气质量", "天河五山", "1427A", "本月"),
            ("combo_005", "广雅中学去年同期PM2.5", "广雅中学", "1001A", "去年同期"),
            ("combo_006", "昨天广州广雅中学的环境数据", "广雅中学", "1001A", "昨天"),
            ("combo_007", "上周珠海香洲区前山监测站", "前山", "1029A", "上周"),
            ("combo_008", "广州天河区上个月空气质量", "天河区", "440100009", "上个月"),
            ("combo_009", "深圳市2024年第二季度PM2.5", "深圳市", "440300", "2024年第二季度"),
            ("combo_010", "番禺大学城最近30天数据", "番禺大学城", "1421A", "最近30天"),
        ]
        
        for case_id, input_text, expected_location, expected_code, expected_time in combo_cases:
            test_cases.append(TestCase(
                id=case_id,
                category="组合测试",
                input_text=input_text,
                expected_location=expected_location,
                expected_location_code=expected_code,
                expected_time=expected_time,
                description=f"测试组合提取: {expected_location} + {expected_time}",
                priority="high"
            ))
        
        return test_cases
    
    def execute_single_test(self, test_case: TestCase) -> TestResult:
        """执行单个测试用例"""
        start_time = time.time()
        thread_id = threading.current_thread().name
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        try:
            # 初始化组件
            if not self._initialize_components():
                return TestResult(
                    test_id=test_case.id,
                    category=test_case.category,
                    input_text=test_case.input_text,
                    success=False,
                    extracted_location="",
                    extracted_time="",
                    response_time_ms=0,
                    error_message="组件初始化失败",
                    thread_id=thread_id,
                    timestamp=timestamp
                )
            
            # 提取地理位置
            extracted_locations = []
            extracted_time = ""
            
            if test_case.category.startswith("地理位置") or test_case.category == "组合测试":
                locations = self.geo_extractor.extract_locations(test_case.input_text)
                extracted_locations = locations
            
            # 解析时间
            if test_case.category == "时间解析" or test_case.category == "组合测试":
                if test_case.expected_time:
                    time_result, time_error = self.param_converter.parse_time_description(test_case.expected_time)
                    if time_result:
                        extracted_time = f"{time_result[0]} 到 {time_result[1]}"
                    else:
                        extracted_time = f"解析失败: {time_error}"
            
            # 计算响应时间
            response_time = (time.time() - start_time) * 1000
            
            # 判断成功条件
            success = True
            error_message = ""
            
            # 验证地理位置提取
            if test_case.expected_location:
                if not extracted_locations or test_case.expected_location not in extracted_locations:
                    success = False
                    error_message += f"地理位置提取失败: 期望 {test_case.expected_location}, 实际 {extracted_locations}; "
            
            # 验证时间解析
            if test_case.expected_time and test_case.category != "组合测试":
                if "解析失败" in extracted_time:
                    success = False
                    error_message += f"时间解析失败: {extracted_time}; "
            
            return TestResult(
                test_id=test_case.id,
                category=test_case.category,
                input_text=test_case.input_text,
                success=success,
                extracted_location=str(extracted_locations),
                extracted_time=extracted_time,
                response_time_ms=round(response_time, 2),
                error_message=error_message.strip(),
                thread_id=thread_id,
                timestamp=timestamp
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return TestResult(
                test_id=test_case.id,
                category=test_case.category,
                input_text=test_case.input_text,
                success=False,
                extracted_location="",
                extracted_time="",
                response_time_ms=round(response_time, 2),
                error_message=f"执行异常: {str(e)}",
                thread_id=thread_id,
                timestamp=timestamp
            )
    
    def run_concurrent_tests(self, test_cases: List[TestCase]) -> List[TestResult]:
        """运行并发测试"""
        self.logger.info(f"开始并发测试，测试用例数: {len(test_cases)}, 最大并发数: {self.max_workers}")
        
        results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_test = {
                executor.submit(self.execute_single_test, test_case): test_case 
                for test_case in test_cases
            }
            
            # 收集结果
            completed_count = 0
            for future in as_completed(future_to_test):
                test_case = future_to_test[future]
                try:
                    result = future.result()
                    results.append(result)
                    completed_count += 1
                    
                    if completed_count % 10 == 0:
                        self.logger.info(f"已完成 {completed_count}/{len(test_cases)} 个测试")
                    
                except Exception as e:
                    self.logger.error(f"测试用例 {test_case.id} 执行失败: {e}")
                    results.append(TestResult(
                        test_id=test_case.id,
                        category=test_case.category,
                        input_text=test_case.input_text,
                        success=False,
                        extracted_location="",
                        extracted_time="",
                        response_time_ms=0,
                        error_message=f"Future异常: {str(e)}",
                        thread_id="unknown",
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    ))
        
        total_time = time.time() - start_time
        self.logger.info(f"并发测试完成，总耗时: {total_time:.2f}秒")
        
        return results
    
    def generate_report(self, results: List[TestResult]) -> Dict[str, Any]:
        """生成测试报告"""
        if not results:
            return {"error": "没有测试结果"}
        
        # 基础统计
        total_tests = len(results)
        successful_tests = sum(1 for r in results if r.success)
        failed_tests = total_tests - successful_tests
        success_rate = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
        
        # 响应时间统计
        response_times = [r.response_time_ms for r in results if r.response_time_ms > 0]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0
        min_response_time = min(response_times) if response_times else 0
        
        # 按类别统计
        category_stats = {}
        for result in results:
            category = result.category
            if category not in category_stats:
                category_stats[category] = {"total": 0, "success": 0, "failed": 0}
            category_stats[category]["total"] += 1
            if result.success:
                category_stats[category]["success"] += 1
            else:
                category_stats[category]["failed"] += 1
        
        # 计算各类别成功率
        for category, stats in category_stats.items():
            stats["success_rate"] = (stats["success"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        
        # 性能分析
        thread_stats = {}
        for result in results:
            thread_id = result.thread_id
            if thread_id not in thread_stats:
                thread_stats[thread_id] = {"count": 0, "total_time": 0}
            thread_stats[thread_id]["count"] += 1
            thread_stats[thread_id]["total_time"] += result.response_time_ms
        
        # 计算平均并发数
        avg_thread_usage = len(thread_stats)
        
        report = {
            "测试概要": {
                "总测试数": total_tests,
                "成功数": successful_tests,
                "失败数": failed_tests,
                "成功率": f"{success_rate:.2f}%",
                "最大并发数": self.max_workers,
                "实际使用线程数": avg_thread_usage
            },
            "性能指标": {
                "平均响应时间(ms)": f"{avg_response_time:.2f}",
                "最大响应时间(ms)": f"{max_response_time:.2f}",
                "最小响应时间(ms)": f"{min_response_time:.2f}",
                "总测试时间": f"{sum(response_times):.2f}ms"
            },
            "分类统计": category_stats,
            "线程使用情况": {
                thread_id: {
                    "测试数量": stats["count"],
                    "平均响应时间": f"{stats['total_time']/stats['count']:.2f}ms"
                }
                for thread_id, stats in thread_stats.items()
            },
            "失败案例": [
                {
                    "测试ID": r.test_id,
                    "输入": r.input_text,
                    "错误": r.error_message
                }
                for r in results if not r.success
            ][:10]  # 只显示前10个失败案例
        }
        
        return report
    
    def save_detailed_results(self, results: List[TestResult], filename: str = None):
        """保存详细测试结果"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"logs/concurrent_test_results_{timestamp}.json"
        
        # 确保目录存在
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # 转换为可序列化的格式
        results_data = [asdict(result) for result in results]
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results_data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"详细测试结果已保存到: {filename}")
        return filename


def main():
    """主函数"""
    print("=" * 60)
    print("参数提取并发测试工具")
    print("=" * 60)
    
    # 获取并发数
    try:
        max_workers = int(input("请输入并发数 (1-20, 默认10): ") or "10")
        max_workers = max(1, min(max_workers, 20))
    except ValueError:
        max_workers = 10
    
    print(f"使用并发数: {max_workers}")
    
    # 创建测试器
    tester = ConcurrentParameterTester(max_workers=max_workers)
    
    # 创建测试用例
    print("正在创建测试用例...")
    test_cases = tester.create_test_cases()
    print(f"创建了 {len(test_cases)} 个测试用例")
    
    # 执行测试
    print("开始执行并发测试...")
    results = tester.run_concurrent_tests(test_cases)
    
    # 生成报告
    print("正在生成测试报告...")
    report = tester.generate_report(results)
    
    # 保存详细结果
    results_file = tester.save_detailed_results(results)
    
    # 显示报告
    print("\n" + "=" * 60)
    print("测试报告")
    print("=" * 60)
    
    print(json.dumps(report, ensure_ascii=False, indent=2))
    
    # 保存报告
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = f"logs/concurrent_test_report_{timestamp}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n报告已保存到: {report_file}")
    print(f"详细结果已保存到: {results_file}")
    
    return report, results


if __name__ == "__main__":
    main()