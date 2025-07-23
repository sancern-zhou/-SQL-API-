# -*- coding: utf-8 -*-
"""
地理位置层级分组器
Geographic Level Grouper

将SmartGeoExtractor提取的多层级地理位置按类型分组，
支持统一的单层级和多层级处理机制。
"""

import logging
from typing import Dict, List, Any, Optional
from collections import defaultdict


class GeoLevelGrouper:
    """
    地理位置层级分组器
    
    负责将SmartGeoExtractor提取的地理位置结果按层级（城市、区县、站点）分组，
    为后续的多层级API调用提供数据准备。
    """
    
    def __init__(self, min_confidence: int = 70, max_levels: int = 5):
        """
        初始化地理位置分组器
        
        Args:
            min_confidence: 最低置信度阈值，低于此值的位置将被过滤
            max_levels: 单次查询支持的最大层级数
        """
        self.logger = logging.getLogger(__name__)
        self.min_confidence = min_confidence
        self.max_levels = max_levels
        
        # 层级优先级映射（用于排序和优化）
        self.level_priority = {
            '站点': 1,
            '区县': 2, 
            '城市': 3
        }
        
        self.logger.info(f"[GEO_GROUPER] 初始化完成 - 最低置信度: {min_confidence}, 最大层级数: {max_levels}")
    
    def group_by_levels(self, extracted_locations: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        将提取的地理位置按层级分组
        
        这是核心方法，处理SmartGeoExtractor的输出，按type字段进行分组。
        无论输入是单层级还是多层级，都通过此统一方法处理。
        
        Args:
            extracted_locations: SmartGeoExtractor.extract_locations()的输出
                格式: [
                    {'name': '广州市', 'type': '城市', 'confidence': 100},
                    {'name': '广州塔', 'type': '站点', 'confidence': 80}
                ]
        
        Returns:
            Dict[str, List[str]]: 按层级分组的位置字典
                格式: {
                    '城市': ['广州市'],
                    '站点': ['广州塔']
                }
        """
        if not extracted_locations:
            self.logger.warning("[GEO_GROUPER] 输入的地理位置列表为空")
            return {}
        
        self.logger.info(f"[GEO_GROUPER] 开始分组处理，输入位置数: {len(extracted_locations)}")
        
        # 使用defaultdict简化分组逻辑
        grouped = defaultdict(list)
        filtered_count = 0
        
        for location in extracted_locations:
            name = location.get('name', '')
            level = location.get('type', '')
            confidence = location.get('confidence', 0)
            
            self.logger.debug(f"[GEO_GROUPER] 处理位置: '{name}', 类型: '{level}', 置信度: {confidence}")
            
            # 置信度过滤
            if confidence < self.min_confidence:
                self.logger.debug(f"[GEO_GROUPER] 位置 '{name}' 置信度过低({confidence}%), 已过滤")
                filtered_count += 1
                continue
            
            # 验证数据完整性
            if not name or not level:
                self.logger.warning(f"[GEO_GROUPER] 位置数据不完整: name='{name}', type='{level}', 已跳过")
                continue
            
            # 按层级分组
            grouped[level].append(name)
            self.logger.debug(f"[GEO_GROUPER] 位置 '{name}' 已分组到 '{level}'")
        
        # 转换为普通字典
        result = dict(grouped)
        
        # 层级数量检查
        if len(result) > self.max_levels:
            self.logger.warning(f"[GEO_GROUPER] 层级数({len(result)})超过最大限制({self.max_levels})")
            result = self._limit_levels(result)
        
        # 去重处理
        result = self._deduplicate_locations(result)
        
        # 统计信息
        total_locations = sum(len(locations) for locations in result.values())
        self.logger.info(f"[GEO_GROUPER] 分组完成 - 层级数: {len(result)}, 总位置数: {total_locations}, 过滤数: {filtered_count}")
        
        for level, locations in result.items():
            self.logger.info(f"[GEO_GROUPER] {level}: {locations}")
        
        return result
    
    def _limit_levels(self, grouped: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """
        限制层级数量，按优先级保留最重要的层级
        
        Args:
            grouped: 原始分组结果
            
        Returns:
            Dict[str, List[str]]: 限制后的分组结果
        """
        # 按优先级排序层级
        sorted_levels = sorted(
            grouped.keys(), 
            key=lambda x: self.level_priority.get(x, 999)
        )
        
        # 保留前max_levels个层级
        kept_levels = sorted_levels[:self.max_levels]
        limited_result = {level: grouped[level] for level in kept_levels}
        
        removed_levels = set(grouped.keys()) - set(kept_levels)
        if removed_levels:
            self.logger.warning(f"[GEO_GROUPER] 已移除层级: {list(removed_levels)}")
        
        return limited_result
    
    def _deduplicate_locations(self, grouped: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """
        去重处理：移除重复的地理位置名称
        
        Args:
            grouped: 原始分组结果
            
        Returns:
            Dict[str, List[str]]: 去重后的分组结果
        """
        deduplicated = {}
        
        for level, locations in grouped.items():
            # 保持顺序的去重
            unique_locations = []
            seen = set()
            
            for location in locations:
                if location not in seen:
                    unique_locations.append(location)
                    seen.add(location)
                else:
                    self.logger.debug(f"[GEO_GROUPER] 移除重复位置: '{location}' in {level}")
            
            if unique_locations:
                deduplicated[level] = unique_locations
        
        return deduplicated
    
    def get_total_locations(self, grouped: Dict[str, List[str]]) -> int:
        """
        获取分组后的总位置数量
        
        Args:
            grouped: 分组结果
            
        Returns:
            int: 总位置数量
        """
        return sum(len(locations) for locations in grouped.values())
    
    def get_levels_info(self, grouped: Dict[str, List[str]]) -> Dict[str, Dict[str, Any]]:
        """
        获取层级详细信息
        
        Args:
            grouped: 分组结果
            
        Returns:
            Dict[str, Dict[str, Any]]: 层级信息字典
        """
        levels_info = {}
        
        for level, locations in grouped.items():
            levels_info[level] = {
                'count': len(locations),
                'locations': locations,
                'priority': self.level_priority.get(level, 999)
            }
        
        return levels_info
    
    def validate_grouping_result(self, grouped: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        验证分组结果的有效性
        
        Args:
            grouped: 分组结果
            
        Returns:
            Dict[str, Any]: 验证结果
        """
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'stats': {}
        }
        
        # 检查是否为空
        if not grouped:
            validation_result['is_valid'] = False
            validation_result['errors'].append("分组结果为空")
            return validation_result
        
        # 检查每个层级
        total_locations = 0
        for level, locations in grouped.items():
            if not locations:
                validation_result['warnings'].append(f"层级 '{level}' 无有效位置")
            
            total_locations += len(locations)
        
        # 统计信息
        validation_result['stats'] = {
            'total_levels': len(grouped),
            'total_locations': total_locations,
            'levels': list(grouped.keys())
        }
        
        self.logger.debug(f"[GEO_GROUPER] 验证完成: {validation_result}")
        return validation_result


def get_geo_level_grouper(min_confidence: int = 70, max_levels: int = 5) -> GeoLevelGrouper:
    """
    获取地理位置分组器实例（工厂方法）
    
    Args:
        min_confidence: 最低置信度阈值
        max_levels: 最大层级数
        
    Returns:
        GeoLevelGrouper: 分组器实例
    """
    return GeoLevelGrouper(min_confidence=min_confidence, max_levels=max_levels)


# 测试函数
def test_geo_level_grouper():
    """测试地理位置分组器功能"""
    grouper = GeoLevelGrouper()
    
    # 测试数据
    test_data = [
        {'name': '广州市', 'type': '城市', 'confidence': 100},
        {'name': '广州', 'type': '城市', 'confidence': 95},
        {'name': '广州塔', 'type': '站点', 'confidence': 80},
        {'name': '越秀区', 'type': '区县', 'confidence': 85},
        {'name': '天河奥体', 'type': '站点', 'confidence': 75},
        {'name': '低置信度位置', 'type': '站点', 'confidence': 50}  # 应被过滤
    ]
    
    result = grouper.group_by_levels(test_data)
    print("分组结果:")
    for level, locations in result.items():
        print(f"  {level}: {locations}")
    
    # 验证结果
    validation = grouper.validate_grouping_result(result)
    print(f"\n验证结果: {validation}")


if __name__ == "__main__":
    test_geo_level_grouper()