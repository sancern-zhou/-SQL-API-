#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路由决策引擎
基于API优先策略的智能路由决策
"""

import logging
from typing import Dict, Any, Tuple
import os
import yaml

from .api_priority_engine import APIPriorityEngine


class RoutingDecisionEngine:
    """
    路由决策引擎
    使用API优先策略进行智能路由决策
    """
    
    def __init__(self, config_path: str = None):
        self.logger = logging.getLogger(__name__)
        
        # 保存配置文件路径
        self.config_path = config_path
        
        # 加载配置
        self.config = self._load_config(config_path)
        
        # 初始化API优先引擎
        self.api_priority_engine = None
        self._init_api_priority_engine()
        
        self.logger.info("路由决策引擎初始化完成，使用API优先策略")
    
    def _load_config(self, config_path: str = None) -> Dict[str, Any]:
        """加载配置文件"""
        if config_path is None:
            # 优先尝试加载新的路由配置文件
            routing_config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'routing_config.yaml')
            if os.path.exists(routing_config_path):
                try:
                    with open(routing_config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                    return config.get('primary_routing', {})
                except Exception as e:
                    self.logger.warning(f"新路由配置文件加载失败: {e}")
            
            # 回退到原配置文件
            config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'config.yaml')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config.get('routing_decision', {})
        except Exception as e:
            self.logger.warning(f"配置文件加载失败，使用默认配置: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'strategy': 'api_priority',
            'enabled': True,
            'confidence_threshold': 0.6,
            'sql_exclusion_keywords': [],  # 默认空列表，全部路由到API
            'debug_enabled': True
        }
    
    def _init_api_priority_engine(self):
        """初始化API优先引擎"""
        try:
            # 传递正确的配置文件路径
            engine_config_path = None
            if self.config_path:
                engine_config_path = self.config_path
            else:
                # 使用默认路径
                import os
                engine_config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'routing_config.yaml')
            
            self.logger.info(f"初始化API优先引擎，配置文件: {engine_config_path}")
            self.api_priority_engine = APIPriorityEngine(engine_config_path)
            
            if self.api_priority_engine:
                self.logger.info("API优先策略引擎初始化成功")
            else:
                self.logger.error("API优先策略引擎初始化返回空值")
                
        except Exception as e:
            self.logger.error(f"API优先策略引擎初始化异常: {e}")
            import traceback
            self.logger.error(f"异常堆栈: {traceback.format_exc()}")
            self.api_priority_engine = None
    
    def decide_route(self, question: str) -> Tuple[str, float, Dict[str, Any]]:
        """
        决策查询路由
        
        Args:
            question: 用户问题
            
        Returns:
            Tuple[str, float, Dict[str, Any]]: (路由决策, 置信度, 决策信息)
        """
        if not self.config.get('enabled', True):
            return 'NL2SQL', 0.5, {'reason': 'routing_disabled', 'strategy': 'disabled'}
        
        # 使用API优先策略进行路由决策
        if self.api_priority_engine:
            return self._decide_route_api_priority(question)
        else:
            # 如果API优先引擎不可用，默认路由到NL2SQL
            return 'NL2SQL', 0.5, {'reason': 'api_priority_engine_unavailable', 'strategy': 'fallback'}
    
    def _decide_route_api_priority(self, question: str) -> Tuple[str, float, Dict[str, Any]]:
        """
        使用API优先策略进行路由决策
        """
        try:
            # 调用API优先引擎进行决策
            route, confidence, decision_info = self.api_priority_engine.decide_route(question)
            
            # 添加策略标识
            decision_info['strategy'] = 'api_priority'
            
            return route, confidence, decision_info
            
        except Exception as e:
            self.logger.error(f"API优先策略决策失败: {e}")
            # 降级到默认路由
            return 'NL2SQL', 0.5, {'reason': 'api_priority_engine_error', 'strategy': 'fallback', 'error': str(e)}
    
    def get_debug_info(self, question: str) -> Dict[str, Any]:
        """获取调试信息"""
        debug_info = {
            'config_enabled': self.config.get('enabled', True),
            'strategy': 'api_priority',
            'api_priority_engine_available': self.api_priority_engine is not None
        }
        
        # 如果使用API优先策略，添加其调试信息
        if self.api_priority_engine:
            try:
                debug_info.update(self.api_priority_engine.get_debug_info(question))
            except Exception as e:
                debug_info['api_priority_debug_error'] = str(e)
        
        return debug_info
    
    def get_stats(self) -> Dict[str, Any]:
        """获取路由引擎统计信息"""
        stats = {
            'engine_type': 'RoutingDecisionEngine',
            'strategy': 'api_priority',
            'config_enabled': self.config.get('enabled', True),
            'api_priority_engine_available': self.api_priority_engine is not None
        }
        
        # 如果使用API优先策略，添加其统计信息
        if self.api_priority_engine:
            try:
                stats.update(self.api_priority_engine.get_stats())
            except Exception as e:
                stats['api_priority_stats_error'] = str(e)
        
        return stats


# 全局实例
_routing_engine_instance = None

def get_routing_engine(config_path: str = None) -> RoutingDecisionEngine:
    """获取路由决策引擎单例"""
    global _routing_engine_instance
    if _routing_engine_instance is None:
        _routing_engine_instance = RoutingDecisionEngine(config_path)
    return _routing_engine_instance

def initialize_routing_engine(config_path: str = None):
    """初始化路由决策引擎"""
    global _routing_engine_instance
    if _routing_engine_instance is None:
        _routing_engine_instance = RoutingDecisionEngine(config_path)
        logging.getLogger(__name__).info("RoutingDecisionEngine initialized successfully")

def decide_route(question: str) -> Tuple[str, float, Dict[str, Any]]:
    """
    便捷函数：决策查询路由
    
    Args:
        question: 用户问题
        
    Returns:
        Tuple[str, float, Dict[str, Any]]: (路由决策, 置信度, 决策信息)
    """
    engine = get_routing_engine()
    return engine.decide_route(question)

def get_route_explanation(question: str) -> Dict[str, Any]:
    """
    便捷函数：获取路由决策的详细解释
    
    Args:
        question: 用户问题
        
    Returns:
        Dict[str, Any]: 路由决策的详细解释信息
    """
    engine = get_routing_engine()
    route, confidence, decision_info = engine.decide_route(question)
    
    return {
        'question': question,
        'route': route,
        'confidence': confidence,
        'decision_info': decision_info,
        'debug_info': engine.get_debug_info(question)
    }