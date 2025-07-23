#!/usr/bin/env python3
"""
路由监控器
Routing Monitor - 监控路由决策的性能和准确性
"""

import logging
import time
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque
import json
import os


class RoutingMonitor:
    """
    路由监控器
    
    负责监控路由决策的性能指标、准确性和系统健康状况
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化路由监控器
        
        Args:
            config: 监控配置
        """
        self.logger = logging.getLogger(__name__)
        self.config = config or {}
        
        # 性能统计
        self.performance_stats = {
            'total_requests': 0,
            'api_route_count': 0,
            'sql_route_count': 0,
            'clarification_count': 0,
            'avg_response_time': 0.0,
            'max_response_time': 0.0,
            'min_response_time': float('inf'),
            'error_count': 0,
            'start_time': time.time()
        }
        
        # 策略使用统计
        self.strategy_stats = defaultdict(int)
        
        # 关键词匹配统计
        self.keyword_matches = defaultdict(int)
        
        # 响应时间历史（最近1000条记录）
        self.response_time_history = deque(maxlen=1000)
        
        # 错误历史
        self.error_history = deque(maxlen=100)
        
        # 路由决策历史
        self.decision_history = deque(maxlen=500)
        
        # 线程锁
        self.lock = threading.Lock()
        
        # 启动监控线程
        self.monitoring_enabled = self.config.get('enabled', True)
        if self.monitoring_enabled:
            self._start_monitoring_thread()
        
        self.logger.info("路由监控器初始化完成")
    
    def record_routing_decision(self, 
                              question: str, 
                              route: str, 
                              confidence: float, 
                              decision_info: Dict[str, Any],
                              response_time: float):
        """
        记录路由决策
        
        Args:
            question: 用户问题
            route: 路由结果
            confidence: 置信度
            decision_info: 决策信息
            response_time: 响应时间
        """
        with self.lock:
            # 更新基本统计
            self.performance_stats['total_requests'] += 1
            
            # 更新路由统计
            if route == 'EXTERNAL_API':
                self.performance_stats['api_route_count'] += 1
            elif route == 'NL2SQL':
                self.performance_stats['sql_route_count'] += 1
            elif route == 'CLARIFICATION_NEEDED':
                self.performance_stats['clarification_count'] += 1
            
            # 更新响应时间统计
            self._update_response_time_stats(response_time)
            
            # 更新策略统计
            strategy = decision_info.get('strategy', 'unknown')
            self.strategy_stats[strategy] += 1
            
            # 更新关键词匹配统计
            matched_keywords = decision_info.get('matched_keywords', [])
            for keyword in matched_keywords:
                self.keyword_matches[keyword] += 1
            
            # 记录决策历史
            decision_record = {
                'timestamp': datetime.now().isoformat(),
                'question': question[:100],  # 限制长度
                'route': route,
                'confidence': confidence,
                'strategy': strategy,
                'response_time': response_time,
                'matched_keywords': matched_keywords
            }
            self.decision_history.append(decision_record)
            
            # 调试日志
            if self.config.get('debug_enabled', False):
                self.logger.debug(f"[MONITOR] 决策记录: {decision_record}")
    
    def record_error(self, error: Exception, context: Dict[str, Any] = None):
        """
        记录错误
        
        Args:
            error: 异常对象
            context: 错误上下文
        """
        with self.lock:
            self.performance_stats['error_count'] += 1
            
            error_record = {
                'timestamp': datetime.now().isoformat(),
                'error_type': type(error).__name__,
                'error_message': str(error),
                'context': context or {}
            }
            self.error_history.append(error_record)
            
            self.logger.error(f"[MONITOR] 错误记录: {error_record}")
    
    def _update_response_time_stats(self, response_time: float):
        """
        更新响应时间统计
        
        Args:
            response_time: 响应时间
        """
        # 更新最大最小值
        self.performance_stats['max_response_time'] = max(
            self.performance_stats['max_response_time'], 
            response_time
        )
        self.performance_stats['min_response_time'] = min(
            self.performance_stats['min_response_time'], 
            response_time
        )
        
        # 更新平均响应时间（移动平均）
        alpha = 0.1  # 平滑因子
        if self.performance_stats['avg_response_time'] == 0:
            self.performance_stats['avg_response_time'] = response_time
        else:
            self.performance_stats['avg_response_time'] = (
                alpha * response_time + 
                (1 - alpha) * self.performance_stats['avg_response_time']
            )
        
        # 记录响应时间历史
        self.response_time_history.append({
            'timestamp': time.time(),
            'response_time': response_time
        })
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        with self.lock:
            current_time = time.time()
            uptime = current_time - self.performance_stats['start_time']
            
            total_requests = self.performance_stats['total_requests']
            
            stats = {
                'performance': {
                    'total_requests': total_requests,
                    'api_route_count': self.performance_stats['api_route_count'],
                    'sql_route_count': self.performance_stats['sql_route_count'],
                    'clarification_count': self.performance_stats['clarification_count'],
                    'api_route_percentage': (
                        (self.performance_stats['api_route_count'] / max(total_requests, 1)) * 100
                    ),
                    'sql_route_percentage': (
                        (self.performance_stats['sql_route_count'] / max(total_requests, 1)) * 100
                    ),
                    'clarification_percentage': (
                        (self.performance_stats['clarification_count'] / max(total_requests, 1)) * 100
                    ),
                    'avg_response_time': self.performance_stats['avg_response_time'],
                    'max_response_time': self.performance_stats['max_response_time'],
                    'min_response_time': (
                        self.performance_stats['min_response_time'] 
                        if self.performance_stats['min_response_time'] != float('inf') 
                        else 0.0
                    ),
                    'error_count': self.performance_stats['error_count'],
                    'error_rate': (
                        (self.performance_stats['error_count'] / max(total_requests, 1)) * 100
                    ),
                    'requests_per_second': total_requests / max(uptime, 1),
                    'uptime_seconds': uptime,
                    'uptime_readable': self._format_uptime(uptime)
                },
                'strategy_usage': dict(self.strategy_stats),
                'keyword_matches': dict(sorted(
                    self.keyword_matches.items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )[:20]),  # 只显示前20个
                'recent_errors': list(self.error_history)[-10:],  # 最近10个错误
                'system_health': self._get_system_health()
            }
            
            return stats
    
    def _get_system_health(self) -> Dict[str, Any]:
        """
        获取系统健康状况
        
        Returns:
            Dict[str, Any]: 系统健康状况
        """
        total_requests = self.performance_stats['total_requests']
        error_rate = (self.performance_stats['error_count'] / max(total_requests, 1)) * 100
        
        # 计算健康分数
        health_score = 100
        
        # 错误率影响
        if error_rate > 10:
            health_score -= 40
        elif error_rate > 5:
            health_score -= 20
        elif error_rate > 1:
            health_score -= 10
        
        # 响应时间影响
        avg_response_time = self.performance_stats['avg_response_time']
        if avg_response_time > 2.0:
            health_score -= 30
        elif avg_response_time > 1.0:
            health_score -= 15
        elif avg_response_time > 0.5:
            health_score -= 5
        
        # 澄清率影响
        clarification_rate = (self.performance_stats['clarification_count'] / max(total_requests, 1)) * 100
        if clarification_rate > 30:
            health_score -= 20
        elif clarification_rate > 20:
            health_score -= 10
        elif clarification_rate > 10:
            health_score -= 5
        
        # 确定健康状态
        if health_score >= 90:
            status = 'excellent'
        elif health_score >= 80:
            status = 'good'
        elif health_score >= 70:
            status = 'fair'
        elif health_score >= 60:
            status = 'poor'
        else:
            status = 'critical'
        
        return {
            'status': status,
            'health_score': max(0, health_score),
            'error_rate': error_rate,
            'avg_response_time': avg_response_time,
            'clarification_rate': clarification_rate,
            'last_updated': datetime.now().isoformat()
        }
    
    def _format_uptime(self, seconds: float) -> str:
        """
        格式化运行时间
        
        Args:
            seconds: 运行秒数
            
        Returns:
            str: 格式化的时间字符串
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        
        return f"{hours}h {minutes}m {seconds}s"
    
    def get_recent_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取最近的决策记录
        
        Args:
            limit: 返回记录数量限制
            
        Returns:
            List[Dict[str, Any]]: 最近的决策记录
        """
        with self.lock:
            return list(self.decision_history)[-limit:]
    
    def get_performance_trend(self, hours: int = 24) -> Dict[str, Any]:
        """
        获取性能趋势
        
        Args:
            hours: 时间范围（小时）
            
        Returns:
            Dict[str, Any]: 性能趋势数据
        """
        with self.lock:
            current_time = time.time()
            cutoff_time = current_time - (hours * 3600)
            
            # 过滤响应时间历史
            recent_response_times = [
                record for record in self.response_time_history
                if record['timestamp'] >= cutoff_time
            ]
            
            if not recent_response_times:
                return {
                    'time_range_hours': hours,
                    'data_points': 0,
                    'trend': 'no_data'
                }
            
            # 计算趋势
            response_times = [record['response_time'] for record in recent_response_times]
            avg_response_time = sum(response_times) / len(response_times)
            
            # 简单的趋势分析（比较前半段和后半段）
            mid_point = len(response_times) // 2
            if mid_point > 0:
                first_half_avg = sum(response_times[:mid_point]) / mid_point
                second_half_avg = sum(response_times[mid_point:]) / (len(response_times) - mid_point)
                
                if second_half_avg > first_half_avg * 1.1:
                    trend = 'degrading'
                elif second_half_avg < first_half_avg * 0.9:
                    trend = 'improving'
                else:
                    trend = 'stable'
            else:
                trend = 'stable'
            
            return {
                'time_range_hours': hours,
                'data_points': len(response_times),
                'avg_response_time': avg_response_time,
                'min_response_time': min(response_times),
                'max_response_time': max(response_times),
                'trend': trend
            }
    
    def _start_monitoring_thread(self):
        """
        启动监控线程
        """
        def monitoring_loop():
            while self.monitoring_enabled:
                try:
                    # 定期导出统计报告
                    if self.config.get('export_enabled', False):
                        self._export_statistics()
                    
                    # 检查系统健康状况
                    health = self._get_system_health()
                    if health['status'] in ['poor', 'critical']:
                        self.logger.warning(f"[MONITOR] 系统健康状况: {health['status']}, 分数: {health['health_score']}")
                    
                    # 等待下一次检查
                    time.sleep(self.config.get('monitoring_interval', 60))
                    
                except Exception as e:
                    self.logger.error(f"[MONITOR] 监控线程异常: {e}")
                    time.sleep(5)
        
        monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitor_thread.start()
        self.logger.info("监控线程已启动")
    
    def _export_statistics(self):
        """
        导出统计数据
        """
        try:
            export_path = self.config.get('export_path', 'logs/routing_stats.json')
            os.makedirs(os.path.dirname(export_path), exist_ok=True)
            
            stats = self.get_statistics()
            stats['export_timestamp'] = datetime.now().isoformat()
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(stats, f, indent=2, ensure_ascii=False)
            
            self.logger.debug(f"[MONITOR] 统计数据已导出到: {export_path}")
            
        except Exception as e:
            self.logger.error(f"[MONITOR] 导出统计数据失败: {e}")
    
    def stop_monitoring(self):
        """
        停止监控
        """
        self.monitoring_enabled = False
        self.logger.info("监控器已停止")
    
    def reset_statistics(self):
        """
        重置统计数据
        """
        with self.lock:
            self.performance_stats = {
                'total_requests': 0,
                'api_route_count': 0,
                'sql_route_count': 0,
                'clarification_count': 0,
                'avg_response_time': 0.0,
                'max_response_time': 0.0,
                'min_response_time': float('inf'),
                'error_count': 0,
                'start_time': time.time()
            }
            
            self.strategy_stats.clear()
            self.keyword_matches.clear()
            self.response_time_history.clear()
            self.error_history.clear()
            self.decision_history.clear()
            
            self.logger.info("统计数据已重置")


# 全局监控器实例
_monitor_instance = None


def get_routing_monitor(config: Dict[str, Any] = None) -> RoutingMonitor:
    """
    获取路由监控器单例
    
    Args:
        config: 监控配置
        
    Returns:
        RoutingMonitor: 监控器实例
    """
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = RoutingMonitor(config)
    return _monitor_instance


def monitor_routing_decision(question: str, 
                           route: str, 
                           confidence: float, 
                           decision_info: Dict[str, Any],
                           response_time: float):
    """
    便捷函数：记录路由决策
    
    Args:
        question: 用户问题
        route: 路由结果
        confidence: 置信度
        decision_info: 决策信息
        response_time: 响应时间
    """
    monitor = get_routing_monitor()
    monitor.record_routing_decision(question, route, confidence, decision_info, response_time)