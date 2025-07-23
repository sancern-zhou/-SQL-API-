#!/usr/bin/env python3
"""
参数去重处理器 - 阶段2优化
解决HTTP 500错误的参数去重和单位置约束问题
"""

import logging
import yaml
import os
from typing import Dict, Any, List, Optional, Tuple
import re
# 暂时使用内置的相似度计算，避免外部依赖
# from thefuzz import fuzz

logger = logging.getLogger(__name__)

class ParameterDeduplicator:
    """参数去重处理器，支持配置文件"""
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化参数去重处理器"""
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
        
        # 从配置文件加载设置
        self._load_settings_from_config()
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        return os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'routing_config.yaml')
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    self.logger.info(f"[PARAM_DEDUP] 配置加载成功: {self.config_path}")
                    return config
            else:
                self.logger.warning(f"[PARAM_DEDUP] 配置文件不存在: {self.config_path}，使用默认配置")
                return self._get_default_config()
        except Exception as e:
            self.logger.error(f"[PARAM_DEDUP] 配置加载失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'parameter_deduplication': {
                'time_precision_scores': {
                    'absolute_date': 100,
                    'absolute_month': 80,
                    'relative_recent': 60,
                    'relative_general': 40,
                    'vague': 20
                },
                'time_precision_patterns': {
                    'absolute_date': r'\d{4}年\d{1,2}月\d{1,2}日',
                    'absolute_month': r'\d{4}年\d{1,2}月',
                    'relative_recent': r'上周|上个月|上季度|去年',
                    'relative_general': r'今天|昨天|本周|本月'
                },
                'location_deduplication': {
                    'enabled': True,
                    'case_sensitive': False,
                    'remove_duplicates': True
                }
            }
        }
    
    def _load_settings_from_config(self):
        """从配置文件加载设置"""
        try:
            dedup_config = self.config.get('parameter_deduplication', {})
            
            # 加载时间精度配置
            self.time_precision_scores = dedup_config.get('time_precision_scores', {})
            self.time_precision_patterns = dedup_config.get('time_precision_patterns', {})
            
            # 加载位置去重配置
            location_config = dedup_config.get('location_deduplication', {})
            self.location_dedup_enabled = location_config.get('enabled', True)
            self.case_sensitive = location_config.get('case_sensitive', False)
            self.remove_duplicates = location_config.get('remove_duplicates', True)
            
            # 相似度阈值
            self.similarity_threshold = 0.85
            
            self.logger.info(f"[PARAM_DEDUP] 配置加载完成:")
            self.logger.info(f"[PARAM_DEDUP]   - 时间精度模式: {len(self.time_precision_patterns)}个")
            self.logger.info(f"[PARAM_DEDUP]   - 位置去重: {'启用' if self.location_dedup_enabled else '禁用'}")
            
        except Exception as e:
            self.logger.error(f"[PARAM_DEDUP] 从配置加载设置失败: {e}，使用默认设置")
            # 使用默认设置
            self.similarity_threshold = 0.85
            self.time_precision_scores = {}
            self.time_precision_patterns = {}
            self.location_dedup_enabled = True
            self.case_sensitive = False
            self.remove_duplicates = True
        
    def deduplicate_and_validate(self, raw_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        参数去重和验证的完整流程
        
        Args:
            raw_params: 原始参数字典
            
        Returns:
            Dict: 去重和验证结果
        """
        result = {
            'status': 'processing',
            'deduplication_applied': False,
            'issues_found': []
        }
        
        try:
            self.logger.info(f"[DEDUP] 开始参数去重处理")
            self.logger.info(f"[DEDUP] 原始参数: {raw_params}")
            
            # 1. 简化的地理位置处理（智能提取器已完成层级选择）
            if 'locations' in raw_params:
                locations = raw_params['locations']
                if not locations:
                    result['status'] = 'error'
                    result['issues_found'].append('缺少地理位置信息')
                    return result
                
                # 简单去重，保持顺序
                unique_locations = list(dict.fromkeys(locations))
                raw_params['locations'] = unique_locations
                
                if len(unique_locations) != len(locations):
                    result['deduplication_applied'] = True
                    result['issues_found'].append(f'地理位置去重: 从{len(locations)}个去重到{len(unique_locations)}个')
            
            # 2. 时间描述去重（保留最精确的）
            if 'time_descriptions' in raw_params:
                best_time = self._select_best_time_description(raw_params['time_descriptions'])
                raw_params['time_description'] = best_time
                result['deduplication_applied'] = True
                result['issues_found'].append(f"时间描述去重: 从{len(raw_params['time_descriptions'])}个选择最佳")
            
            # 3. 数据源去重（保留最匹配的）
            if 'data_sources' in raw_params:
                best_source = self._select_best_data_source(raw_params['data_sources'])
                raw_params['data_source'] = best_source
                result['deduplication_applied'] = True
                result['issues_found'].append(f"数据源去重: 从{len(raw_params['data_sources'])}个选择最佳")
            
            result['status'] = 'success'
            result['params'] = raw_params
            
            self.logger.info(f"[DEDUP] 参数去重完成")
            self.logger.info(f"[DEDUP] 去重后参数: {raw_params}")
            self.logger.info(f"[DEDUP] 去重应用: {result['deduplication_applied']}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"[DEDUP] 参数去重处理失败: {e}")
            return {
                'status': 'error',
                'message': f'参数去重处理失败: {str(e)}',
                'original_params': raw_params
            }
    
    
    
    
    def _select_best_time_description(self, time_descriptions: List[str]) -> str:
        """选择最佳时间描述（最精确的）"""
        if not time_descriptions:
            return None
        
        # 按精确度排序
        precision_scores = {
            'absolute_date': 100,    # 2024年5月1日
            'absolute_month': 80,    # 2024年5月
            'relative_specific': 60, # 上周、上个月
            'relative_vague': 40,    # 最近、前段时间
            'current': 20            # 现在、当前
        }
        
        def get_precision_score(time_desc):
            if re.match(r'\\d{4}年\\d{1,2}月\\d{1,2}日', time_desc):
                return precision_scores['absolute_date']
            elif re.match(r'\\d{4}年\\d{1,2}月', time_desc):
                return precision_scores['absolute_month']
            elif any(kw in time_desc for kw in ['上周', '上个月', '上季度', '去年']):
                return precision_scores['relative_specific']
            elif any(kw in time_desc for kw in ['最近', '前段时间', '近期']):
                return precision_scores['relative_vague']
            else:
                return precision_scores['current']
        
        # 返回精确度最高的时间描述
        best_time = max(time_descriptions, key=get_precision_score)
        
        self.logger.info(f"[DEDUP] 选择最佳时间描述: {best_time} (从{len(time_descriptions)}个中选择)")
        return best_time
    
    def _select_best_data_source(self, data_sources: List[str]) -> str:
        """选择最佳数据源"""
        # 优先级：审核实况 > 原始实况 > 审核标况 > 原始标况
        priority_order = ['审核实况', '原始实况', '审核标况', '原始标况']
        
        for preferred in priority_order:
            if preferred in data_sources:
                self.logger.info(f"[DEDUP] 选择最佳数据源: {preferred} (从{len(data_sources)}个中选择)")
                return preferred
        
        # 如果都不匹配，返回第一个
        best_source = data_sources[0] if data_sources else '审核实况'
        self.logger.info(f"[DEDUP] 选择默认数据源: {best_source}")
        return best_source
    
    def deduplicate_converted_params(self, converted_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        去重已转换的参数（针对station_codes等API参数）
        这是解决HTTP 500错误的关键步骤
        """
        result = {
            'status': 'success',
            'params': converted_params.copy(),
            'deduplication_applied': False,
            'fixes_applied': []
        }
        
        try:
            self.logger.info(f"[DEDUP] 开始转换参数去重")
            self.logger.info(f"[DEDUP] 原始转换参数: {converted_params}")
            
            # 1. 站点编码去重（解决HTTP 500错误的核心）
            if 'station_codes' in converted_params and isinstance(converted_params['station_codes'], list):
                original_codes = converted_params['station_codes']
                unique_codes = list(dict.fromkeys(original_codes))  # 保持顺序的去重
                
                if len(unique_codes) != len(original_codes):
                    result['params']['station_codes'] = unique_codes
                    result['deduplication_applied'] = True
                    fix_info = f"站点编码去重: {len(original_codes)} -> {len(unique_codes)}"
                    result['fixes_applied'].append(fix_info)
                    self.logger.info(f"[DEDUP] {fix_info}")
                    self.logger.info(f"[DEDUP] 原始编码: {original_codes}")
                    self.logger.info(f"[DEDUP] 去重后编码: {unique_codes}")
            
            # 2. 其他列表类型参数去重
            list_params = ['time_point', 'contrast_time']
            for param_name in list_params:
                if param_name in converted_params and isinstance(converted_params[param_name], list):
                    original_list = converted_params[param_name]
                    unique_list = list(dict.fromkeys(original_list))
                    
                    if len(unique_list) != len(original_list):
                        result['params'][param_name] = unique_list
                        result['deduplication_applied'] = True
                        fix_info = f"{param_name}去重: {len(original_list)} -> {len(unique_list)}"
                        result['fixes_applied'].append(fix_info)
                        self.logger.info(f"[DEDUP] {fix_info}")
            
            self.logger.info(f"[DEDUP] 转换参数去重完成")
            self.logger.info(f"[DEDUP] 去重应用: {result['deduplication_applied']}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"[DEDUP] 转换参数去重失败: {e}")
            return {
                'status': 'error',
                'message': f'转换参数去重失败: {str(e)}',
                'original_params': converted_params
            }


# 全局参数去重处理器实例
_parameter_deduplicator_instance = None

def get_parameter_deduplicator() -> ParameterDeduplicator:
    """获取参数去重处理器单例"""
    global _parameter_deduplicator_instance
    if _parameter_deduplicator_instance is None:
        _parameter_deduplicator_instance = ParameterDeduplicator()
    return _parameter_deduplicator_instance

def initialize_parameter_deduplicator():
    """初始化参数去重处理器"""
    global _parameter_deduplicator_instance
    if _parameter_deduplicator_instance is None:
        _parameter_deduplicator_instance = ParameterDeduplicator()
        logger.info("ParameterDeduplicator initialized successfully")