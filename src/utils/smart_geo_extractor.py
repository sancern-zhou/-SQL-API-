#!/usr/bin/env python3
"""
智能地理位置提取器 (简化版)
Smart Geographic Location Extractor (Simplified)

基于纯模糊匹配的地理位置提取，支持：
- 直接从用户问题进行模糊匹配
- 动态阈值策略
- 层级优先逻辑
- 高精度地理位置识别
"""

import re
import logging
import yaml
from typing import Dict, Any, List, Optional, Tuple
from thefuzz import fuzz
import json
import os

class SmartGeoExtractor:
    """智能地理位置提取器，支持配置文件"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
        
        # 加载多结果配置
        self._load_multi_result_config()
        
        self._load_geo_mappings()
        
        # 构建搜索候选集
        self._build_search_candidates()
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        return os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'routing_config.yaml')
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    return config
            else:
                return self._get_default_config()
        except Exception as e:
            self.logger.error(f"[SMART_GEO] 配置加载失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'geo_location_extended': {
                'fuzzy_matching': {
                    'multi_result_config': {
                        'max_results': 100,
                        'min_confidence_threshold': 60,
                        'enable_type_annotation': True,
                        'enable_confidence_info': True
                    }
                }
            }
        }
    
    def _load_multi_result_config(self):
        """从配置文件加载多结果配置"""
        try:
            geo_config = self.config.get('geo_location_extended', {})
            fuzzy_config = geo_config.get('fuzzy_matching', {})
            multi_config = fuzzy_config.get('multi_result_config', {})
            
            self.max_results = multi_config.get('max_results', 100)
            self.min_confidence_threshold = multi_config.get('min_confidence_threshold', 60)
            self.enable_type_annotation = multi_config.get('enable_type_annotation', True)
            self.enable_confidence_info = multi_config.get('enable_confidence_info', True)
            
            self.logger.info(f"[SMART_GEO] 多结果配置加载完成:")
            self.logger.info(f"[SMART_GEO]   - 最大结果数: {self.max_results}")
            self.logger.info(f"[SMART_GEO]   - 最小置信度: {self.min_confidence_threshold}")
            self.logger.info(f"[SMART_GEO]   - 类型标注: {self.enable_type_annotation}")
            self.logger.info(f"[SMART_GEO]   - 置信度信息: {self.enable_confidence_info}")
            
        except Exception as e:
            self.logger.error(f"[SMART_GEO] 多结果配置加载失败: {e}，使用默认配置")
            self.max_results = 100
            self.min_confidence_threshold = 60
            self.enable_type_annotation = True
            self.enable_confidence_info = True
    
    def _load_geo_mappings(self):
        """加载地理映射数据"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'geo_mappings.json')
            with open(config_path, 'r', encoding='utf-8') as f:
                self.geo_mappings = json.load(f)
            self.logger.info(f"加载地理映射数据成功")
        except Exception as e:
            self.logger.error(f"加载地理映射数据失败: {e}")
            self.geo_mappings = {"stations": {}, "districts": {}, "cities": {}}
    
    def _build_search_candidates(self):
        """构建搜索候选集（包含所有地理位置）"""
        self.search_candidates = []
        
        # 添加所有地理位置到候选集
        for geo_type, mappings in self.geo_mappings.items():
            for name, code in mappings.items():
                self.search_candidates.append({
                    'name': name,
                    'code': code,
                    'type': geo_type
                })
        
        self.logger.info(f"构建搜索候选集完成，共 {len(self.search_candidates)} 个地理位置")
    
    
    def extract_locations(self, text: str) -> List[Dict[str, Any]]:
        """智能地理位置提取 - 返回多结果格式"""
        self.logger.debug(f"[SMART_GEO] 开始智能地理位置提取: {text}")
        
        # 直接进行全文模糊匹配
        fuzzy_matches = self._fuzzy_match_from_text(text)
        self.logger.debug(f"[SMART_GEO] 模糊匹配结果: {len(fuzzy_matches)}个")
        
        # 过滤和格式化结果
        final_results = self._format_multi_results(fuzzy_matches)
        
        self.logger.info(f"[SMART_GEO] 最终提取结果: {len(final_results)}个地理位置")
        return final_results
    
    
    
    def _fuzzy_match_from_text(self, text: str) -> List[Dict]:
        """直接从原文进行模糊匹配（核心创新）"""
        matches = []
        
        # 对每个地理位置候选项进行模糊匹配
        for candidate in self.search_candidates:
            name = candidate['name']
            
            # 跳过过短的名称（避免误匹配）
            if len(name) < 2:
                continue
            
            # 计算多种模糊匹配分数
            scores = {
                'ratio': fuzz.ratio(name, text),
                'partial_ratio': fuzz.partial_ratio(name, text),
                'token_sort_ratio': fuzz.token_sort_ratio(name, text),
                'token_set_ratio': fuzz.token_set_ratio(name, text)
            }
            
            # 取最高分作为置信度
            confidence = max(scores.values())
            
            # 设置不同的阈值策略
            threshold = self._get_threshold(candidate['type'], name)
            
            if confidence >= threshold:
                matches.append({
                    'name': name,
                    'code': candidate['code'],
                    'type': candidate['type'],
                    'source': 'fuzzy_match',
                    'confidence': confidence,
                    'scores': scores
                })
        
        # 按置信度排序
        matches.sort(key=lambda x: x['confidence'], reverse=True)
        
        return matches
    
    def _get_threshold(self, geo_type: str, name: str) -> int:
        """动态阈值策略"""
        base_threshold = 60
        
        # 根据地理位置类型调整阈值
        if geo_type == 'cities':
            base_threshold = 70  # 城市名称要求更高精度
        elif geo_type == 'districts':
            base_threshold = 65  # 区县适中
        elif geo_type == 'stations':
            base_threshold = 60  # 站点名称可以宽松一些
        
        # 根据名称长度调整阈值
        if len(name) <= 3:
            base_threshold += 10  # 短名称要求更高精度
        elif len(name) >= 8:
            base_threshold -= 5   # 长名称可以宽松一些
        
        return base_threshold
    
    
    
    def _format_multi_results(self, matches: List[Dict]) -> List[Dict[str, Any]]:
        """格式化多结果返回"""
        if not matches:
            return []
        
        # 过滤低置信度结果
        filtered_matches = [m for m in matches if m['confidence'] >= self.min_confidence_threshold]
        
        # 如果没有高置信度结果，返回空
        if not filtered_matches:
            self.logger.debug(f"[SMART_GEO] 没有达到置信度阈值({self.min_confidence_threshold})的结果")
            return []
        
        # 限制结果数量
        limited_matches = filtered_matches[:self.max_results]
        
        # 格式化结果
        results = []
        for match in limited_matches:
            result = {'name': match['name']}
            
            # 添加类型标注（如果启用）
            if self.enable_type_annotation:
                result['type'] = self._get_type_label(match['type'])
            
            # 添加置信度信息（如果启用）
            if self.enable_confidence_info:
                result['confidence'] = match['confidence']
            
            results.append(result)
        
        self.logger.debug(f"[SMART_GEO] 格式化完成，返回{len(results)}个结果")
        return results
    
    def _get_type_label(self, geo_type: str) -> str:
        """获取地理位置类型标签"""
        type_mapping = {
            'stations': '站点',
            'districts': '区县', 
            'cities': '城市'
        }
        return type_mapping.get(geo_type, '未知')
    
    def _find_location_info(self, location: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        查找地理位置的详细信息
        
        这个方法修复了日志中报告的缺失方法问题。它接收extract_locations()返回的
        位置字典，并尝试查找更详细的信息，如编码等。
        
        Args:
            location: 地理位置字典，格式如 {'name': '广州市', 'type': '城市', 'confidence': 100}
            
        Returns:
            Optional[Dict[str, Any]]: 详细信息字典，包含 name, type, code 等字段
        """
        try:
            if not isinstance(location, dict):
                self.logger.warning(f"[FIND_INFO] 输入参数不是字典类型: {type(location)}")
                return None
            
            location_name = location.get('name', '')
            location_type = location.get('type', '')
            
            if not location_name:
                self.logger.warning("[FIND_INFO] 位置名称为空")
                return None
            
            self.logger.debug(f"[FIND_INFO] 查找位置详细信息: {location_name} ({location_type})")
            
            # 构建返回信息
            location_info = {
                'name': location_name,
                'type': location_type,
                'confidence': location.get('confidence', 0),
                'source': 'smart_geo_extractor'
            }
            
            # 尝试从映射数据中查找编码
            code = self._lookup_location_code(location_name, location_type)
            if code:
                location_info['code'] = code
                self.logger.debug(f"[FIND_INFO] 找到编码: {location_name} -> {code}")
            else:
                location_info['code'] = ''
                self.logger.debug(f"[FIND_INFO] 未找到编码: {location_name}")
            
            return location_info
            
        except Exception as e:
            self.logger.error(f"[FIND_INFO] 查找位置信息异常: {e}")
            return None
    
    def _lookup_location_code(self, location_name: str, location_type: str) -> Optional[str]:
        """
        从地理映射数据中查找位置编码
        
        Args:
            location_name: 位置名称
            location_type: 位置类型 ('城市', '区县', '站点')
            
        Returns:
            Optional[str]: 位置编码，如果未找到返回None
        """
        try:
            # 根据类型选择对应的映射表
            if location_type == '站点':
                mapping_key = 'stations'
            elif location_type == '区县':
                mapping_key = 'districts'
            elif location_type == '城市':
                mapping_key = 'cities'
            else:
                self.logger.warning(f"[LOOKUP_CODE] 未知的位置类型: {location_type}")
                return None
            
            # 获取映射表
            mapping_dict = self.geo_mappings.get(mapping_key, {})
            if not mapping_dict:
                self.logger.debug(f"[LOOKUP_CODE] 映射表 {mapping_key} 为空")
                return None
            
            # 精确匹配
            if location_name in mapping_dict:
                code = mapping_dict[location_name]
                self.logger.debug(f"[LOOKUP_CODE] 精确匹配: {location_name} -> {code}")
                return code
            
            # 模糊匹配
            from difflib import SequenceMatcher
            best_match = ''
            best_ratio = 0
            threshold = 0.8  # 模糊匹配阈值
            
            for mapped_name in mapping_dict.keys():
                ratio = SequenceMatcher(None, location_name, mapped_name).ratio()
                if ratio > best_ratio and ratio >= threshold:
                    best_ratio = ratio
                    best_match = mapped_name
            
            if best_match:
                code = mapping_dict[best_match]
                self.logger.debug(f"[LOOKUP_CODE] 模糊匹配: {location_name} -> {best_match} -> {code} (相似度: {best_ratio:.2f})")
                return code
            
            self.logger.debug(f"[LOOKUP_CODE] 未找到匹配: {location_name}")
            return None
            
        except Exception as e:
            self.logger.error(f"[LOOKUP_CODE] 编码查找异常: {e}")
            return None

# 测试函数
def test_smart_geo_extractor():
    """测试简化版智能地理位置提取器"""
    extractor = SmartGeoExtractor()
    
    test_cases = [
        "昨天广州市O3-8h是多少？",      # 应该识别出"广州市"
        "查询广雅中学上周的空气质量",    # 应该识别出"广雅中学"
        "五山的PM2.5浓度",             # 应该识别出相关站点
        "广雅的数据",                  # 应该识别出"广雅中学"
        "深圳华侨城空气质量",          # 应该识别出"华侨城"
        "分析广州的空气质量数据",       # 应该识别出"广州市"
        "珠海前山空气质量",            # 应该识别出"前山"
        "上月广东省各城市常规六参的月均值",  # 应该识别出"广东省"
    ]
    
    for test_text in test_cases:
        print(f"\n测试: {test_text}")
        results = extractor.extract_locations(test_text)
        print(f"结果: {results}")

# 全局实例
_smart_geo_extractor = None

def get_smart_geo_extractor() -> SmartGeoExtractor:
    """获取智能地理位置提取器单例"""
    global _smart_geo_extractor
    if _smart_geo_extractor is None:
        _smart_geo_extractor = SmartGeoExtractor()
    return _smart_geo_extractor

if __name__ == "__main__":
    test_smart_geo_extractor()