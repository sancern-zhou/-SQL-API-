#!/usr/bin/env python3
"""
API优先路由决策引擎
API Priority Routing Decision Engine

实现策略2：API优先+SQL排除关键词分流
"""

import logging
import time
from typing import Dict, Any, List, Tuple
from datetime import datetime
import yaml
import os


class APIPriorityEngine:
    """
    API优先路由决策引擎
    
    核心策略：
    1. 检查SQL排除关键词
    2. 命中则走SQL，否则走API
    3. 简单、高效、易维护
    """
    
    def __init__(self, config_path: str = None):
        """
        初始化API优先路由引擎
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认配置
        """
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path or self._get_default_config_path()
        
        # 加载配置
        self.config = self._load_config()
        
        # 修正：始终从primary_routing读取sql_exclusion_keywords
        try:
            self.sql_exclusion_keywords = self.config['primary_routing']['sql_exclusion_keywords']
        except Exception as e:
            self.logger.error(f"[API_PRIORITY] 读取sql_exclusion_keywords失败: {e}")
            self.sql_exclusion_keywords = []
        
        # 性能统计
        self.stats = {
            'total_requests': 0,
            'api_route_count': 0,
            'sql_route_count': 0,
            'avg_response_time': 0.0,
            'keyword_matches': {},  # 记录哪些关键词被匹配
            'start_time': time.time()
        }
        
        self.logger.info(f"[API_PRIORITY] 引擎初始化完成")
        self.logger.info(f"[API_PRIORITY] 配置文件: {self.config_path}")
        self.logger.info(f"[API_PRIORITY] SQL排除关键词数量: {len(self.sql_exclusion_keywords)}")
        
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        return os.path.join(
            os.path.dirname(__file__), 
            '..', '..', 'config', 'routing_config.yaml'
        )
    
    def _load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        如果配置文件不存在或加载失败，返回默认空配置（全部路由到API）
        Returns:
            配置字典
        """
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    # 修正：返回完整配置字典
                    return config
            else:
                self.logger.info(f"[API_PRIORITY] 配置文件不存在: {self.config_path}，使用默认空配置（全部路由到API）")
                return self._get_default_config()
        except Exception as e:
            self.logger.warning(f"[API_PRIORITY] 配置加载失败，使用默认空配置（全部路由到API）: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """
        获取默认配置（当配置文件不存在时使用）
        默认空关键词列表，全部路由到API
        Returns:
            默认配置字典
        """
        return {
            'primary_routing': {
                'strategy': 'api_priority',
                'sql_exclusion_keywords': [],  # 默认空列表，全部路由到API
                'debug_enabled': True,
                'performance_monitoring': True
            }
        }
    
    def decide_route(self, question: str) -> Tuple[str, float, Dict[str, Any]]:
        """
        决定路由方向
        
        Args:
            question: 用户问题
            
        Returns:
            Tuple[str, float, Dict]: (路由方向, 置信度, 决策信息)
        """
        start_time = time.time()
        
        try:
            # 更新统计
            self.stats['total_requests'] += 1
            
            # 检查SQL排除关键词
            matched_keywords = self._check_sql_keywords(question)
            
            decision_info = {
                'strategy': 'api_priority',
                'question': question,
                'matched_keywords': matched_keywords,
                'decision_time': 0.0,
                'timestamp': datetime.now().isoformat()
            }
            
            if matched_keywords:
                # 命中SQL关键词，走SQL路由
                route = "NL2SQL"
                confidence = 1.0  # 关键词匹配给予最高置信度
                self.stats['sql_route_count'] += 1
                
                # 记录关键词匹配统计
                for keyword in matched_keywords:
                    self.stats['keyword_matches'][keyword] = \
                        self.stats['keyword_matches'].get(keyword, 0) + 1
                
                decision_info.update({
                    'route_reason': 'sql_keywords_matched',
                    'confidence_reason': 'exact_keyword_match'
                })
                
                self.logger.info(f"[API_PRIORITY] SQL路由 - 问题: '{question}'")
                self.logger.info(f"[API_PRIORITY] 匹配关键词: {matched_keywords}")
                
            else:
                # 未命中关键词或无关键词配置，默认走API路由
                route = "EXTERNAL_API"
                confidence = 0.9  # API优先策略给予高置信度
                self.stats['api_route_count'] += 1
                
                if not self.sql_exclusion_keywords:
                    # 无关键词配置的情况
                    decision_info.update({
                        'route_reason': 'no_keywords_configured_route_to_api',
                        'confidence_reason': 'api_priority_strategy'
                    })
                    self.logger.info(f"[API_PRIORITY] API路由 - 问题: '{question}'")
                    self.logger.info(f"[API_PRIORITY] 原因: 无SQL关键词配置，全部路由到API")
                else:
                    # 有关键词配置但未匹配的情况
                    decision_info.update({
                        'route_reason': 'api_priority_default',
                        'confidence_reason': 'api_priority_strategy'
                    })
                    self.logger.info(f"[API_PRIORITY] API路由 - 问题: '{question}'")
                    self.logger.info(f"[API_PRIORITY] 原因: 未匹配SQL关键词，默认API路由")
            
            # 记录决策时间
            decision_time = time.time() - start_time
            decision_info['decision_time'] = decision_time
            
            # 更新平均响应时间
            self._update_avg_response_time(decision_time)
            
            # 调试日志
            debug_enabled = False
            try:
                debug_enabled = self.config['primary_routing'].get('debug_enabled', False)
            except Exception:
                debug_enabled = False
            if debug_enabled:
                self.logger.debug(f"[API_PRIORITY] 决策详情: {decision_info}")
            
            return route, confidence, decision_info
            
        except Exception as e:
            self.logger.error(f"[API_PRIORITY] 路由决策失败: {e}")
            
            # 异常情况下的默认行为
            decision_info = {
                'strategy': 'api_priority',
                'question': question,
                'error': str(e),
                'fallback_route': 'EXTERNAL_API',
                'decision_time': time.time() - start_time
            }
            
            return "EXTERNAL_API", 0.5, decision_info
    
    def _check_sql_keywords(self, question: str) -> List[str]:
        """
        检查问题中是否包含SQL排除关键词
        
        Args:
            question: 用户问题
            
        Returns:
            匹配的关键词列表
        """
        matched_keywords = []
        
        for keyword in self.sql_exclusion_keywords:
            if keyword in question:
                matched_keywords.append(keyword)
        
        return matched_keywords
    
    def _update_avg_response_time(self, decision_time: float):
        """
        更新平均响应时间
        
        Args:
            decision_time: 本次决策时间
        """
        # 使用移动平均计算
        alpha = 0.1  # 平滑因子
        if self.stats['avg_response_time'] == 0:
            self.stats['avg_response_time'] = decision_time
        else:
            self.stats['avg_response_time'] = (
                alpha * decision_time + 
                (1 - alpha) * self.stats['avg_response_time']
            )
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取引擎统计信息
        
        Returns:
            统计信息字典
        """
        current_time = time.time()
        uptime = current_time - self.stats['start_time']
        
        stats = self.stats.copy()
        stats.update({
            'uptime_seconds': uptime,
            'uptime_readable': self._format_uptime(uptime),
            'api_route_percentage': (
                (self.stats['api_route_count'] / max(self.stats['total_requests'], 1)) * 100
            ),
            'sql_route_percentage': (
                (self.stats['sql_route_count'] / max(self.stats['total_requests'], 1)) * 100
            ),
            'requests_per_second': (
                self.stats['total_requests'] / max(uptime, 1)
            )
        })
        
        return stats
    
    def _format_uptime(self, seconds: float) -> str:
        """
        格式化运行时间
        
        Args:
            seconds: 运行秒数
            
        Returns:
            格式化的时间字符串
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        
        return f"{hours}h {minutes}m {seconds}s"
    
    def update_sql_keywords(self, new_keywords: List[str]):
        """
        运行时更新SQL排除关键词
        
        Args:
            new_keywords: 新的关键词列表
        """
        old_count = len(self.sql_exclusion_keywords)
        self.sql_exclusion_keywords = new_keywords
        new_count = len(new_keywords)
        
        self.logger.info(f"[API_PRIORITY] 关键词更新: {old_count} -> {new_count}")
        self.logger.info(f"[API_PRIORITY] 新关键词: {new_keywords}")
        
        # 重置关键词匹配统计
        self.stats['keyword_matches'] = {}
    
    def reload_config(self):
        """
        重新加载配置文件
        """
        self.logger.info(f"[API_PRIORITY] 重新加载配置文件")
        
        old_config = self.config.copy()
        self.config = self._load_config()
        
        # 更新关键词
        old_keywords = self.sql_exclusion_keywords
        self.sql_exclusion_keywords = self.config.get('sql_exclusion_keywords', [])
        
        if old_keywords != self.sql_exclusion_keywords:
            self.logger.info(f"[API_PRIORITY] 关键词已更新")
            self.stats['keyword_matches'] = {}  # 重置统计
        
        return {
            'config_reloaded': True,
            'keywords_changed': old_keywords != self.sql_exclusion_keywords,
            'old_keyword_count': len(old_keywords),
            'new_keyword_count': len(self.sql_exclusion_keywords)
        }
    
    def get_debug_info(self) -> Dict[str, Any]:
        """
        获取调试信息
        
        Returns:
            调试信息字典
        """
        return {
            'engine_type': 'APIPriorityEngine',
            'config_path': self.config_path,
            'config_loaded': bool(self.config),
            'sql_keywords_count': len(self.sql_exclusion_keywords),
            'sql_keywords_preview': self.sql_exclusion_keywords[:10],
            'statistics': self.get_statistics(),
            'recent_keyword_matches': dict(
                sorted(self.stats['keyword_matches'].items(), 
                      key=lambda x: x[1], reverse=True)[:10]
            )
        }