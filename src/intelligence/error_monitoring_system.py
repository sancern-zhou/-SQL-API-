"""
错误监控系统 - 第四阶段智能错误恢复
提供完整的错误监控、统计分析和性能指标
"""

import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque
import threading
import json

logger = logging.getLogger(__name__)

class ErrorMonitoringSystem:
    """错误监控系统"""
    
    def __init__(self, max_history_size: int = 1000):
        self.max_history_size = max_history_size
        self.lock = threading.Lock()
        
        # 错误记录历史
        self.error_history = deque(maxlen=max_history_size)
        
        # 错误统计
        self.error_stats = {
            "total_errors": 0,
            "error_types": defaultdict(int),
            "error_severity": defaultdict(int),
            "recovery_success": defaultdict(int),
            "recovery_failure": defaultdict(int),
            "sql_fallback_count": 0,
            "api_types": defaultdict(int),
            "hourly_stats": defaultdict(lambda: defaultdict(int)),
            "daily_stats": defaultdict(lambda: defaultdict(int))
        }
        
        # 性能指标
        self.performance_metrics = {
            "recovery_time": deque(maxlen=100),  # 最近100次恢复时间
            "classification_time": deque(maxlen=100),  # 最近100次分类时间
            "total_processing_time": deque(maxlen=100)  # 最近100次总处理时间
        }
        
        # 恢复策略成功率
        self.recovery_strategy_stats = defaultdict(lambda: {
            "total_attempts": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "average_recovery_time": 0.0
        })
        
        # 系统健康度指标
        self.health_metrics = {
            "last_update": time.time(),
            "system_availability": 1.0,
            "error_rate": 0.0,
            "recovery_rate": 0.0,
            "average_response_time": 0.0
        }
        
        # 报警阈值
        self.alert_thresholds = {
            "error_rate_threshold": 0.1,  # 10%错误率报警
            "recovery_failure_threshold": 0.3,  # 30%恢复失败率报警
            "response_time_threshold": 10.0,  # 10秒响应时间报警
            "sql_fallback_rate_threshold": 0.5  # 50%SQL回退率报警
        }
    
    def record_error(self, error_info: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """
        记录错误信息
        
        Args:
            error_info: 错误分类信息
            context: 错误上下文
            
        Returns:
            错误记录ID
        """
        with self.lock:
            error_id = f"error_{int(time.time() * 1000)}_{len(self.error_history)}"
            timestamp = datetime.now()
            
            error_record = {
                "id": error_id,
                "timestamp": timestamp,
                "error_type": error_info.get("error_type", "unknown"),
                "severity": error_info.get("severity", "medium"),
                "recovery_strategy": error_info.get("recovery_strategy", "unknown"),
                "original_message": error_info.get("original_message", ""),
                "context": context or {},
                "recovery_status": "pending",
                "recovery_result": None,
                "processing_times": {},
                "sql_fallback": False
            }
            
            # 添加到历史记录
            self.error_history.append(error_record)
            
            # 更新统计
            self._update_error_stats(error_record)
            
            logger.info(f"[ERROR_MONITOR] 记录错误: {error_id}, 类型: {error_record['error_type']}")
            return error_id
    
    def record_recovery_attempt(self, error_id: str, recovery_type: str, 
                              recovery_result: Dict[str, Any], 
                              processing_times: Dict[str, float] = None) -> None:
        """
        记录恢复尝试结果
        
        Args:
            error_id: 错误记录ID
            recovery_type: 恢复类型
            recovery_result: 恢复结果
            processing_times: 处理时间统计
        """
        with self.lock:
            # 查找对应的错误记录
            error_record = self._find_error_record(error_id)
            if not error_record:
                logger.warning(f"[ERROR_MONITOR] 未找到错误记录: {error_id}")
                return
            
            # 更新错误记录
            error_record["recovery_status"] = "completed"
            error_record["recovery_result"] = recovery_result
            error_record["recovery_type"] = recovery_type
            error_record["processing_times"] = processing_times or {}
            
            # 判断是否为SQL回退
            if recovery_result.get("status") == "sql_fallback":
                error_record["sql_fallback"] = True
                self.error_stats["sql_fallback_count"] += 1
            
            # 更新恢复统计
            self._update_recovery_stats(error_record, recovery_result)
            
            # 更新性能指标
            self._update_performance_metrics(processing_times or {})
            
            logger.info(f"[ERROR_MONITOR] 记录恢复结果: {error_id}, 类型: {recovery_type}, 成功: {recovery_result.get('success', False)}")
    
    def record_classification_time(self, classification_time: float) -> None:
        """记录分类时间"""
        with self.lock:
            self.performance_metrics["classification_time"].append(classification_time)
    
    def record_recovery_time(self, recovery_time: float) -> None:
        """记录恢复时间"""
        with self.lock:
            self.performance_metrics["recovery_time"].append(recovery_time)
    
    def record_total_processing_time(self, total_time: float) -> None:
        """记录总处理时间"""
        with self.lock:
            self.performance_metrics["total_processing_time"].append(total_time)
    
    def get_error_statistics(self, time_range: str = "24h") -> Dict[str, Any]:
        """
        获取错误统计信息
        
        Args:
            time_range: 时间范围 ("1h", "24h", "7d", "30d", "all")
            
        Returns:
            统计信息
        """
        with self.lock:
            now = datetime.now()
            
            # 计算时间范围
            if time_range == "1h":
                start_time = now - timedelta(hours=1)
            elif time_range == "24h":
                start_time = now - timedelta(hours=24)
            elif time_range == "7d":
                start_time = now - timedelta(days=7)
            elif time_range == "30d":
                start_time = now - timedelta(days=30)
            else:  # "all"
                start_time = datetime.min
            
            # 过滤时间范围内的错误
            filtered_errors = [
                error for error in self.error_history
                if error["timestamp"] >= start_time
            ]
            
            # 计算统计信息
            stats = self._calculate_statistics(filtered_errors)
            stats["time_range"] = time_range
            stats["total_records"] = len(filtered_errors)
            stats["query_time"] = now.isoformat()
            
            return stats
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        with self.lock:
            metrics = {}
            
            # 计算平均时间
            for metric_name, times in self.performance_metrics.items():
                if times:
                    metrics[f"avg_{metric_name}"] = sum(times) / len(times)
                    metrics[f"max_{metric_name}"] = max(times)
                    metrics[f"min_{metric_name}"] = min(times)
                    metrics[f"recent_{metric_name}"] = list(times)[-10:]  # 最近10次
                else:
                    metrics[f"avg_{metric_name}"] = 0.0
                    metrics[f"max_{metric_name}"] = 0.0
                    metrics[f"min_{metric_name}"] = 0.0
                    metrics[f"recent_{metric_name}"] = []
            
            return metrics
    
    def get_recovery_strategy_analysis(self) -> Dict[str, Any]:
        """获取恢复策略分析"""
        with self.lock:
            strategy_analysis = {}
            
            for strategy, stats in self.recovery_strategy_stats.items():
                total = stats["total_attempts"]
                if total > 0:
                    success_rate = stats["successful_recoveries"] / total
                    strategy_analysis[strategy] = {
                        "total_attempts": total,
                        "success_rate": success_rate,
                        "failure_rate": 1 - success_rate,
                        "average_recovery_time": stats["average_recovery_time"],
                        "recommendation": self._get_strategy_recommendation(strategy, success_rate)
                    }
            
            return strategy_analysis
    
    def get_system_health(self) -> Dict[str, Any]:
        """获取系统健康度"""
        with self.lock:
            # 更新健康度指标
            self._update_health_metrics()
            
            # 检查报警条件
            alerts = self._check_alerts()
            
            return {
                "health_metrics": self.health_metrics.copy(),
                "alerts": alerts,
                "last_updated": datetime.now().isoformat(),
                "monitoring_status": "active"
            }
    
    def get_hourly_trend(self, hours: int = 24) -> Dict[str, Any]:
        """获取小时级趋势"""
        with self.lock:
            now = datetime.now()
            trend_data = {}
            
            for i in range(hours):
                hour_start = now - timedelta(hours=i+1)
                hour_key = hour_start.strftime("%Y-%m-%d %H:00")
                
                hour_errors = [
                    error for error in self.error_history
                    if hour_start <= error["timestamp"] < hour_start + timedelta(hours=1)
                ]
                
                trend_data[hour_key] = {
                    "total_errors": len(hour_errors),
                    "error_types": self._count_by_field(hour_errors, "error_type"),
                    "recovery_success": len([e for e in hour_errors if e.get("recovery_result", {}).get("success", False)]),
                    "sql_fallbacks": len([e for e in hour_errors if e.get("sql_fallback", False)])
                }
            
            return trend_data
    
    def export_statistics(self, format_type: str = "json") -> str:
        """
        导出统计信息
        
        Args:
            format_type: 导出格式 ("json", "csv")
            
        Returns:
            导出的数据字符串
        """
        with self.lock:
            all_stats = {
                "error_statistics": self.get_error_statistics("all"),
                "performance_metrics": self.get_performance_metrics(),
                "recovery_strategy_analysis": self.get_recovery_strategy_analysis(),
                "system_health": self.get_system_health(),
                "hourly_trend": self.get_hourly_trend(24),
                "export_time": datetime.now().isoformat()
            }
            
            if format_type == "json":
                return json.dumps(all_stats, ensure_ascii=False, indent=2)
            elif format_type == "csv":
                # 简化的CSV导出（仅包含基础统计）
                csv_lines = ["timestamp,error_type,severity,recovery_success,sql_fallback"]
                for error in self.error_history:
                    csv_lines.append(f"{error['timestamp']},{error['error_type']},{error['severity']},{error.get('recovery_result', {}).get('success', False)},{error.get('sql_fallback', False)}")
                return "\n".join(csv_lines)
            else:
                raise ValueError(f"不支持的导出格式: {format_type}")
    
    def _find_error_record(self, error_id: str) -> Optional[Dict[str, Any]]:
        """查找错误记录"""
        for error in reversed(self.error_history):
            if error["id"] == error_id:
                return error
        return None
    
    def _update_error_stats(self, error_record: Dict[str, Any]) -> None:
        """更新错误统计"""
        self.error_stats["total_errors"] += 1
        self.error_stats["error_types"][error_record["error_type"]] += 1
        self.error_stats["error_severity"][error_record["severity"]] += 1
        
        # 按时间统计
        timestamp = error_record["timestamp"]
        hour_key = timestamp.strftime("%Y-%m-%d %H")
        day_key = timestamp.strftime("%Y-%m-%d")
        
        self.error_stats["hourly_stats"][hour_key]["total"] += 1
        self.error_stats["hourly_stats"][hour_key][error_record["error_type"]] += 1
        
        self.error_stats["daily_stats"][day_key]["total"] += 1
        self.error_stats["daily_stats"][day_key][error_record["error_type"]] += 1
    
    def _update_recovery_stats(self, error_record: Dict[str, Any], recovery_result: Dict[str, Any]) -> None:
        """更新恢复统计"""
        recovery_type = error_record.get("recovery_type", "unknown")
        recovery_success = recovery_result.get("success", False)
        
        # 更新策略统计
        strategy_stats = self.recovery_strategy_stats[recovery_type]
        strategy_stats["total_attempts"] += 1
        
        if recovery_success:
            strategy_stats["successful_recoveries"] += 1
            self.error_stats["recovery_success"][recovery_type] += 1
        else:
            strategy_stats["failed_recoveries"] += 1
            self.error_stats["recovery_failure"][recovery_type] += 1
        
        # 更新平均恢复时间
        recovery_time = error_record.get("processing_times", {}).get("recovery_time", 0.0)
        if recovery_time > 0:
            current_avg = strategy_stats["average_recovery_time"]
            total_attempts = strategy_stats["total_attempts"]
            strategy_stats["average_recovery_time"] = (current_avg * (total_attempts - 1) + recovery_time) / total_attempts
    
    def _update_performance_metrics(self, processing_times: Dict[str, float]) -> None:
        """更新性能指标"""
        for metric_name, metric_time in processing_times.items():
            if metric_name in self.performance_metrics:
                self.performance_metrics[metric_name].append(metric_time)
    
    def _calculate_statistics(self, filtered_errors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算统计信息"""
        if not filtered_errors:
            return {
                "total_errors": 0,
                "error_types": {},
                "error_severity": {},
                "recovery_success_rate": 0.0,
                "sql_fallback_rate": 0.0
            }
        
        total = len(filtered_errors)
        error_types = self._count_by_field(filtered_errors, "error_type")
        error_severity = self._count_by_field(filtered_errors, "severity")
        
        # 计算恢复成功率
        successful_recoveries = len([
            e for e in filtered_errors 
            if e.get("recovery_result", {}).get("success", False)
        ])
        recovery_success_rate = successful_recoveries / total if total > 0 else 0.0
        
        # 计算SQL回退率
        sql_fallbacks = len([e for e in filtered_errors if e.get("sql_fallback", False)])
        sql_fallback_rate = sql_fallbacks / total if total > 0 else 0.0
        
        return {
            "total_errors": total,
            "error_types": dict(error_types),
            "error_severity": dict(error_severity),
            "recovery_success_rate": recovery_success_rate,
            "sql_fallback_rate": sql_fallback_rate,
            "successful_recoveries": successful_recoveries,
            "sql_fallbacks": sql_fallbacks
        }
    
    def _count_by_field(self, errors: List[Dict[str, Any]], field: str) -> defaultdict:
        """按字段统计"""
        counts = defaultdict(int)
        for error in errors:
            counts[error.get(field, "unknown")] += 1
        return counts
    
    def _update_health_metrics(self) -> None:
        """更新系统健康度指标"""
        now = time.time()
        
        # 计算最近24小时的错误率
        last_24h = datetime.now() - timedelta(hours=24)
        recent_errors = [
            error for error in self.error_history
            if error["timestamp"] >= last_24h
        ]
        
        total_recent = len(recent_errors)
        if total_recent > 0:
            # 假设总请求数是错误数的10倍（这里需要根据实际情况调整）
            estimated_total_requests = total_recent * 10
            self.health_metrics["error_rate"] = total_recent / estimated_total_requests
            
            # 计算恢复率
            successful_recoveries = len([
                e for e in recent_errors 
                if e.get("recovery_result", {}).get("success", False)
            ])
            self.health_metrics["recovery_rate"] = successful_recoveries / total_recent
        else:
            self.health_metrics["error_rate"] = 0.0
            self.health_metrics["recovery_rate"] = 1.0
        
        # 计算平均响应时间
        recent_times = list(self.performance_metrics["total_processing_time"])
        if recent_times:
            self.health_metrics["average_response_time"] = sum(recent_times) / len(recent_times)
        else:
            self.health_metrics["average_response_time"] = 0.0
        
        # 计算系统可用性
        availability = 1.0 - self.health_metrics["error_rate"]
        self.health_metrics["system_availability"] = max(0.0, min(1.0, availability))
        
        self.health_metrics["last_update"] = now
    
    def _check_alerts(self) -> List[Dict[str, Any]]:
        """检查报警条件"""
        alerts = []
        
        # 错误率报警
        if self.health_metrics["error_rate"] > self.alert_thresholds["error_rate_threshold"]:
            alerts.append({
                "type": "high_error_rate",
                "severity": "warning",
                "message": f"错误率过高: {self.health_metrics['error_rate']:.2%}",
                "threshold": self.alert_thresholds["error_rate_threshold"],
                "current_value": self.health_metrics["error_rate"]
            })
        
        # 恢复失败率报警
        recovery_failure_rate = 1.0 - self.health_metrics["recovery_rate"]
        if recovery_failure_rate > self.alert_thresholds["recovery_failure_threshold"]:
            alerts.append({
                "type": "high_recovery_failure_rate",
                "severity": "warning",
                "message": f"恢复失败率过高: {recovery_failure_rate:.2%}",
                "threshold": self.alert_thresholds["recovery_failure_threshold"],
                "current_value": recovery_failure_rate
            })
        
        # 响应时间报警
        if self.health_metrics["average_response_time"] > self.alert_thresholds["response_time_threshold"]:
            alerts.append({
                "type": "slow_response_time",
                "severity": "warning",
                "message": f"响应时间过长: {self.health_metrics['average_response_time']:.2f}秒",
                "threshold": self.alert_thresholds["response_time_threshold"],
                "current_value": self.health_metrics["average_response_time"]
            })
        
        return alerts
    
    def _get_strategy_recommendation(self, strategy: str, success_rate: float) -> str:
        """获取策略建议"""
        if success_rate >= 0.8:
            return "excellent"
        elif success_rate >= 0.6:
            return "good"
        elif success_rate >= 0.4:
            return "needs_improvement"
        else:
            return "poor_performance"

# 全局错误监控系统实例
_error_monitoring_system = None

def get_error_monitoring_system() -> ErrorMonitoringSystem:
    """获取全局错误监控系统实例"""
    global _error_monitoring_system
    if _error_monitoring_system is None:
        _error_monitoring_system = ErrorMonitoringSystem()
    return _error_monitoring_system