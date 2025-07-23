#!/usr/bin/env python3
"""
简化工具选择器 - 阶段2优化
基于关键词匹配的工具选择策略
"""

import logging
import time
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import yaml
import os

logger = logging.getLogger(__name__)

class SimplifiedToolSelector:
    """简化的工具选择器 - 基于关键词匹配，支持配置文件"""
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化工具选择器"""
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
        
        # 从配置文件加载对比关键词
        self.comparison_keywords = self._load_comparison_keywords()
        
        self.stats = {
            'total_selections': 0,
            'comparison_tool_selected': 0,
            'summary_tool_selected': 0,
            'selection_time_total': 0.0
        }
        
        logger.info(f"SimplifiedToolSelector 初始化完成")
        logger.info(f"配置文件: {self.config_path}")
        logger.info(f"对比关键词数量: {len(self.comparison_keywords)}")
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        return os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'routing_config.yaml')
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    logger.info(f"[TOOL_SELECTOR] 配置加载成功: {self.config_path}")
                    return config
            else:
                logger.warning(f"[TOOL_SELECTOR] 配置文件不存在: {self.config_path}，使用默认配置")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"[TOOL_SELECTOR] 配置加载失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'secondary_routing': {
                'keyword_matching': {
                    'comparison_keywords': [
                        # 默认对比关键词
                        '环比', '同比', '同期', '对比', '比较', '相比',
                        '变化', '增长', '下降', '升降', '差异', '差别',
                        '去年同期', '上年同期', '同期相比', '上期相比',
                        '增加', '减少', '上升', '下滑', '波动',
                        '幅度', '涨跌', '变动', '趋势对比',
                        '与', '和', '跟', '较', '比起',
                        '相对于', '对照', '对应'
                    ]
                }
            }
        }
    
    def _load_comparison_keywords(self) -> List[str]:
        """从配置文件加载对比关键词"""
        try:
            # 尝试从新的配置节加载
            keywords = (self.config.get('secondary_routing', {})
                       .get('keyword_matching', {})
                       .get('comparison_keywords', []))
            
            if keywords:
                logger.info(f"[TOOL_SELECTOR] 从配置文件加载对比关键词: {len(keywords)}个")
                return keywords
            else:
                logger.warning(f"[TOOL_SELECTOR] 配置文件中未找到对比关键词，使用默认配置")
                return self._get_default_config()['secondary_routing']['keyword_matching']['comparison_keywords']
                
        except Exception as e:
            logger.error(f"[TOOL_SELECTOR] 加载对比关键词失败: {e}，使用默认配置")
            return self._get_default_config()['secondary_routing']['keyword_matching']['comparison_keywords']
    
    def select_tool(self, question: str) -> Dict[str, Any]:
        """
        基于关键词选择工具
        
        Args:
            question: 用户查询问题
            
        Returns:
            Dict: 工具选择结果
        """
        start_time = time.time()
        
        try:
            # 工具选择逻辑
            selected_tool = self._select_tool_by_keywords(question)
            
            # 更新统计
            self.stats['total_selections'] += 1
            if selected_tool == 'get_comparison_report':
                self.stats['comparison_tool_selected'] += 1
            else:
                self.stats['summary_tool_selected'] += 1
            
            selection_time = time.time() - start_time
            self.stats['selection_time_total'] += selection_time
            
            # 记录选择日志
            matched_keywords = self._get_matched_keywords(question)
            logger.info(f"[TOOL_SELECT] 工具选择: {selected_tool}")
            logger.info(f"[TOOL_SELECT] 匹配关键词: {matched_keywords}")
            logger.info(f"[TOOL_SELECT] 选择耗时: {selection_time:.4f}s")
            
            return {
                'status': 'success',
                'selected_tool': selected_tool,
                'selection_method': 'keyword_matching',
                'matched_keywords': matched_keywords,
                'selection_time': selection_time,
                'confidence': 1.0 if matched_keywords else 0.9  # 匹配到关键词置信度更高
            }
            
        except Exception as e:
            logger.error(f"[TOOL_SELECT] 工具选择失败: {e}")
            return {
                'status': 'error',
                'error_type': 'tool_selection_failed',
                'message': f'工具选择失败: {str(e)}',
                'fallback_tool': 'get_summary_report'  # 默认降级到综合报表
            }
    
    def _select_tool_by_keywords(self, question: str) -> str:
        """
        基于关键词选择工具
        策略：检测到对比关键词 -> 对比报表，否则 -> 综合报表
        """
        # 检查是否包含对比关键词
        for keyword in self.comparison_keywords:
            if keyword in question:
                logger.debug(f"[TOOL_SELECT] 检测到对比关键词: {keyword}")
                return 'get_comparison_report'
        
        # 没有对比关键词，使用综合报表
        logger.debug(f"[TOOL_SELECT] 未检测到对比关键词，选择综合报表")
        return 'get_summary_report'
    
    def _get_matched_keywords(self, question: str) -> List[str]:
        """获取匹配到的关键词列表"""
        matched = []
        for keyword in self.comparison_keywords:
            if keyword in question:
                matched.append(keyword)
        return matched
    
    def get_tool_info(self, tool_name: str) -> Dict[str, Any]:
        """获取工具信息"""
        tool_info = {
            'get_summary_report': {
                'name': '综合报表查询',
                'description': '获取指定地点和时间的空气质量综合报表数据',
                'api_endpoint': 'GetReportForRangePagedListAsync',
                'required_params': ['locations', 'time_description'],
                'optional_params': ['area_type', 'data_source']
            },
            'get_comparison_report': {
                'name': '对比报表查询', 
                'description': '获取两个时间段的空气质量对比数据',
                'api_endpoint': 'GetReportForRangeCompareListAsync',
                'required_params': ['locations', 'time_description', 'comparison_time'],
                'optional_params': ['area_type', 'data_source']
            }
        }
        
        return tool_info.get(tool_name, {})
    
    def generate_comparison_time(self, current_time: List[str]) -> Optional[List[str]]:
        """
        生成默认的对比时间（去年同期）
        
        Args:
            current_time: 当前查询的时间范围 [start_time, end_time]
            
        Returns:
            List[str]: 对比时间范围，格式同current_time
        """
        if not current_time or len(current_time) != 2:
            logger.warning("[TOOL_SELECT] 当前时间格式不正确，无法生成对比时间")
            return None
        
        try:
            # 解析当前时间
            start_time_str, end_time_str = current_time
            start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
            end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S')
            
            # 计算去年同期
            comparison_start = start_time.replace(year=start_time.year - 1)
            comparison_end = end_time.replace(year=end_time.year - 1)
            
            comparison_time = [
                comparison_start.strftime('%Y-%m-%d %H:%M:%S'),
                comparison_end.strftime('%Y-%m-%d %H:%M:%S')
            ]
            
            logger.info(f"[TOOL_SELECT] 生成对比时间: {comparison_time}")
            return comparison_time
            
        except Exception as e:
            logger.error(f"[TOOL_SELECT] 生成对比时间失败: {e}")
            return None
    
    def get_selection_stats(self) -> Dict[str, Any]:
        """获取工具选择统计信息"""
        if self.stats['total_selections'] > 0:
            avg_selection_time = self.stats['selection_time_total'] / self.stats['total_selections']
            comparison_rate = (self.stats['comparison_tool_selected'] / self.stats['total_selections']) * 100
            summary_rate = (self.stats['summary_tool_selected'] / self.stats['total_selections']) * 100
        else:
            avg_selection_time = 0.0
            comparison_rate = 0.0
            summary_rate = 0.0
        
        return {
            'total_selections': self.stats['total_selections'],
            'comparison_tool_rate': f"{comparison_rate:.1f}%",
            'summary_tool_rate': f"{summary_rate:.1f}%",
            'avg_selection_time': f"{avg_selection_time:.4f}s",
            'comparison_keywords_count': len(self.comparison_keywords)
        }
    
    def add_comparison_keywords(self, keywords: List[str]):
        """添加新的对比关键词"""
        for keyword in keywords:
            if keyword not in self.comparison_keywords:
                self.comparison_keywords.append(keyword)
                logger.info(f"[TOOL_SELECT] 添加对比关键词: {keyword}")
    
    def remove_comparison_keywords(self, keywords: List[str]):
        """移除对比关键词"""
        for keyword in keywords:
            if keyword in self.comparison_keywords:
                self.comparison_keywords.remove(keyword)
                logger.info(f"[TOOL_SELECT] 移除对比关键词: {keyword}")
    
    def reload_config(self) -> Dict[str, Any]:
        """重新加载配置文件"""
        try:
            old_keywords_count = len(self.comparison_keywords)
            
            # 重新加载配置
            self.config = self._load_config()
            self.comparison_keywords = self._load_comparison_keywords()
            
            new_keywords_count = len(self.comparison_keywords)
            
            logger.info(f"[TOOL_SELECTOR] 配置重新加载完成")
            logger.info(f"[TOOL_SELECTOR] 对比关键词数量: {old_keywords_count} -> {new_keywords_count}")
            
            return {
                'config_reloaded': True,
                'keywords_changed': True,
                'old_keywords_count': old_keywords_count,
                'new_keywords_count': new_keywords_count,
                'config_path': self.config_path
            }
            
        except Exception as e:
            logger.error(f"[TOOL_SELECTOR] 配置重新加载失败: {e}")
            return {
                'config_reloaded': False,
                'error': str(e),
                'config_path': self.config_path
            }


# 全局工具选择器实例
_tool_selector_instance = None

def get_tool_selector() -> SimplifiedToolSelector:
    """获取工具选择器单例"""
    global _tool_selector_instance
    if _tool_selector_instance is None:
        _tool_selector_instance = SimplifiedToolSelector()
    return _tool_selector_instance

def initialize_tool_selector():
    """初始化工具选择器"""
    global _tool_selector_instance
    if _tool_selector_instance is None:
        _tool_selector_instance = SimplifiedToolSelector()
        logger.info("SimplifiedToolSelector initialized successfully")