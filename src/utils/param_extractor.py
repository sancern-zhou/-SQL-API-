#!/usr/bin/env python3
"""
参数提取器模块
Parameter Extractor Module

负责从自然语言文本中提取结构化参数，支持：
- 地理位置提取
- 时间描述提取  
- 区域类型判断
- 数据源识别
- 配置文件管理
"""

import re
import logging
import yaml
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime


class ParameterExtractor:
    """参数提取器类，支持配置文件"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
        
        # 从配置文件加载模式和关键词
        self._load_patterns_from_config()
        
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        return os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'routing_config.yaml')
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    self.logger.info(f"[PARAM_EXTRACTOR] 配置加载成功: {self.config_path}")
                    return config
            else:
                self.logger.warning(f"[PARAM_EXTRACTOR] 配置文件不存在: {self.config_path}，使用默认配置")
                return self._get_default_config()
        except Exception as e:
            self.logger.error(f"[PARAM_EXTRACTOR] 配置加载失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'parameter_extraction': {
                'location_patterns': [
                    {'pattern': r'([^，,。.！!？?\s]+(?:市|区|县|镇|街道|中学|小学|学校|站|点))', 'description': '标准地理位置模式', 'enabled': True},
                    {'pattern': r'([^，,。.！!？?\s]{2,8}(?:市|区|县))', 'description': '简化地理位置模式', 'enabled': True},
                    {'pattern': r'([^，,。.！!？?\s]+(?:省|自治区))', 'description': '省份模式', 'enabled': True}
                ],
                'time_patterns': [
                    {'pattern': r'(\d{4}年\d{1,2}月\d{1,2}日)', 'description': '完整日期', 'priority': 1, 'enabled': True},
                    {'pattern': r'(\d{4}年\d{1,2}月)', 'description': '年月', 'priority': 2, 'enabled': True},
                    {'pattern': r'(上周|上个月|昨天|今天|本周|本月|今年|去年)', 'description': '相对时间', 'priority': 3, 'enabled': True}
                ],
                'comparison_time_patterns': [
                    {'pattern': r'(?:和|与|跟|同|相比|对比)\s*([^，,。.！!？?\s]*(?:年|月|周|天|同期|上年|去年))', 'description': '对比时间提取模式', 'enabled': True}
                ],
                'area_type_keywords': {
                    '城市': ['市', '城市'],
                    '区县': ['区', '县', '镇'],
                    '站点': ['中学', '小学', '学校', '站', '点', '监测站']
                },
                'data_source_keywords': {
                    '原始实况': ['原始实况', '原始数据'],
                    '审核实况': ['审核实况', '审核数据', '实况']
                },
                'exclude_prefixes': [
                    '比较', '查询', '获取', '对比', '分析', '监测', '检测', '统计', '计算', '研究', '调查'
                ]
            }
        }
    
    def _load_patterns_from_config(self):
        """从配置文件加载所有模式和关键词"""
        try:
            param_config = self.config.get('parameter_extraction', {})
            
            # 加载地理位置模式
            self.location_patterns = []
            location_patterns = param_config.get('location_patterns', [])
            for pattern_config in location_patterns:
                if pattern_config.get('enabled', True):
                    self.location_patterns.append(pattern_config['pattern'])
            
            # 加载时间模式（按优先级排序）
            self.time_patterns = []
            time_patterns = param_config.get('time_patterns', [])
            sorted_patterns = sorted(time_patterns, key=lambda x: x.get('priority', 999))
            for pattern_config in sorted_patterns:
                if pattern_config.get('enabled', True):
                    self.time_patterns.append((pattern_config['pattern'], pattern_config.get('description', '')))
            
            # 加载对比时间模式
            self.comparison_patterns = []
            comparison_patterns = param_config.get('comparison_time_patterns', [])
            for pattern_config in comparison_patterns:
                if pattern_config.get('enabled', True):
                    self.comparison_patterns.append(pattern_config['pattern'])
            
            # 加载区域类型关键词
            self.area_type_keywords = param_config.get('area_type_keywords', {})
            
            # 加载数据源关键词
            self.data_source_keywords = param_config.get('data_source_keywords', {})
            
            # 加载排除前缀
            self.exclude_prefixes = param_config.get('exclude_prefixes', [])
            
            self.logger.info(f"[PARAM_EXTRACTOR] 配置加载完成:")
            self.logger.info(f"[PARAM_EXTRACTOR]   - 地理位置模式: {len(self.location_patterns)}个")
            self.logger.info(f"[PARAM_EXTRACTOR]   - 时间模式: {len(self.time_patterns)}个")
            self.logger.info(f"[PARAM_EXTRACTOR]   - 对比时间模式: {len(self.comparison_patterns)}个")
            self.logger.info(f"[PARAM_EXTRACTOR]   - 排除前缀: {len(self.exclude_prefixes)}个")
            
        except Exception as e:
            self.logger.error(f"[PARAM_EXTRACTOR] 从配置加载模式失败: {e}，使用默认配置")
            default_config = self._get_default_config()
            self._load_patterns_from_config_dict(default_config['parameter_extraction'])
    
    def _load_patterns_from_config_dict(self, param_config: Dict[str, Any]):
        """从配置字典加载模式（内部方法）"""
        # 简化版加载（用于默认配置）
        self.location_patterns = [p['pattern'] for p in param_config.get('location_patterns', [])]
        self.time_patterns = [(p['pattern'], p.get('description', '')) for p in param_config.get('time_patterns', [])]
        self.comparison_patterns = [p['pattern'] for p in param_config.get('comparison_time_patterns', [])]
        self.area_type_keywords = param_config.get('area_type_keywords', {})
        self.data_source_keywords = param_config.get('data_source_keywords', {})
        self.exclude_prefixes = param_config.get('exclude_prefixes', [])
    
    def reload_config(self) -> Dict[str, Any]:
        """重新加载配置文件"""
        try:
            old_patterns_count = {
                'location': len(self.location_patterns),
                'time': len(self.time_patterns),
                'comparison': len(self.comparison_patterns),
                'exclude_prefixes': len(self.exclude_prefixes)
            }
            
            # 重新加载配置
            self.config = self._load_config()
            self._load_patterns_from_config()
            
            new_patterns_count = {
                'location': len(self.location_patterns),
                'time': len(self.time_patterns),
                'comparison': len(self.comparison_patterns),
                'exclude_prefixes': len(self.exclude_prefixes)
            }
            
            self.logger.info(f"[PARAM_EXTRACTOR] 配置重新加载完成")
            
            return {
                'config_reloaded': True,
                'patterns_changed': True,
                'old_patterns_count': old_patterns_count,
                'new_patterns_count': new_patterns_count,
                'config_path': self.config_path
            }
            
        except Exception as e:
            self.logger.error(f"[PARAM_EXTRACTOR] 配置重新加载失败: {e}")
            return {
                'config_reloaded': False,
                'error': str(e),
                'config_path': self.config_path
            }
    
    def extract_locations(self, text: str) -> List[str]:
        """
        提取地理位置名称 - 使用智能地理位置提取器
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 提取到的地理位置列表
        """
        self.logger.debug(f"[EXTRACTOR] 开始提取地理位置: {text}")
        
        # 使用智能地理位置提取器
        try:
            from .smart_geo_extractor import get_smart_geo_extractor
            smart_extractor = get_smart_geo_extractor()
            geo_results = smart_extractor.extract_locations(text)
            
            if geo_results:
                # 提取地理位置名称列表（适配新的多结果格式）
                location_names = [geo_result['name'] for geo_result in geo_results]
                self.logger.debug(f"[EXTRACTOR] 智能提取到的位置: {geo_results}")
                self.logger.debug(f"[EXTRACTOR] 转换后的位置名称: {location_names}")
                return location_names
            else:
                self.logger.debug(f"[EXTRACTOR] 智能提取无结果，使用传统方法")
        except Exception as e:
            self.logger.error(f"[EXTRACTOR] 智能提取失败: {e}，使用传统方法")
        
        # 传统方法作为后备
        locations = []
        for pattern in self.location_patterns:
            matches = re.findall(pattern, text)
            locations.extend(matches)
        
        # 智能过滤：如果位置包含动词前缀，尝试提取其中的地理位置部分
        filtered_locations = []
        for loc in locations:
            processed_loc = loc
            
            # 检查是否以动词开头，如果是，尝试提取地理位置部分
            for prefix in self.exclude_prefixes:
                if loc.startswith(prefix):
                    # 尝试提取动词后面的地理位置
                    remaining = loc[len(prefix):]
                    # 如果剩余部分仍然是有效的地理位置，使用它
                    if remaining and any(suffix in remaining for suffix in ['市', '区', '县', '镇', '街道', '中学', '小学', '学校', '站', '点', '省', '自治区']):
                        processed_loc = remaining
                        self.logger.debug(f"[EXTRACTOR] 提取动词后的地理位置: {loc} -> {processed_loc}")
                        break
                    else:
                        # 如果剩余部分不是有效位置，排除整个匹配
                        self.logger.debug(f"[EXTRACTOR] 排除动词前缀位置: {loc} (前缀: {prefix})")
                        processed_loc = None
                        break
            
            if processed_loc:
                filtered_locations.append(processed_loc)
        
        # 去重并保持顺序
        unique_locations = []
        for loc in filtered_locations:
            if loc not in unique_locations:
                unique_locations.append(loc)
        
        self.logger.debug(f"[EXTRACTOR] 提取到的位置: {unique_locations}")
        return unique_locations
    
    def extract_time_description(self, text: str) -> Optional[str]:
        """
        提取时间描述（按优先级）
        
        Args:
            text: 输入文本
            
        Returns:
            Optional[str]: 提取到的时间描述
        """
        self.logger.debug(f"[EXTRACTOR] 开始提取时间描述: {text}")
        
        for pattern, description in self.time_patterns:
            matches = re.findall(pattern, text)
            if matches:
                time_desc = matches[0]
                self.logger.debug(f"[EXTRACTOR] 提取到时间 ({description}): {time_desc}")
                return time_desc
        
        self.logger.debug(f"[EXTRACTOR] 未提取到时间描述")
        return None
    
    def extract_comparison_time(self, text: str) -> Optional[str]:
        """
        提取对比时间描述
        
        Args:
            text: 输入文本
            
        Returns:
            Optional[str]: 提取到的对比时间描述
        """
        self.logger.debug(f"[EXTRACTOR] 开始提取对比时间: {text}")
        
        for pattern in self.comparison_patterns:
            matches = re.findall(pattern, text)
            if matches:
                comparison_time = matches[0]
                self.logger.debug(f"[EXTRACTOR] 提取到对比时间: {comparison_time}")
                return comparison_time
        
        self.logger.debug(f"[EXTRACTOR] 未提取到对比时间")
        return None
    
    def _smart_infer_comparison_time(self, text: str, main_time: str) -> Optional[str]:
        """
        智能推断对比时间
        
        Args:
            text: 用户查询文本
            main_time: 主要时间描述
            
        Returns:
            Optional[str]: 推断的对比时间描述
        """
        if not main_time:
            return None
            
        text_lower = text.lower()
        self.logger.debug(f"[EXTRACTOR] 开始智能推断对比时间，主时间: {main_time}")
        
        # 同比关键词：默认为去年同期
        if any(keyword in text_lower for keyword in ['同比', '同期', '去年', '上年']):
            inferred_time = self._infer_year_over_year_time(main_time)
            if inferred_time:
                self.logger.info(f"[EXTRACTOR] 同比推断: {main_time} → {inferred_time}")
                return inferred_time
        
        # 环比关键词：根据主时间推断
        elif any(keyword in text_lower for keyword in ['环比', '较上']):
            inferred_time = self._infer_period_over_period_time(main_time)
            if inferred_time:
                self.logger.info(f"[EXTRACTOR] 环比推断: {main_time} → {inferred_time}")
                return inferred_time
        
        # 变化/对比查询：默认为同比
        elif any(keyword in text_lower for keyword in ['变化', '对比', '比较', '差异']):
            inferred_time = self._infer_year_over_year_time(main_time)
            if inferred_time:
                self.logger.info(f"[EXTRACTOR] 变化查询推断为同比: {main_time} → {inferred_time}")
                return inferred_time
        
        self.logger.debug(f"[EXTRACTOR] 无法智能推断对比时间")
        return None
    
    def _infer_year_over_year_time(self, main_time: str) -> Optional[str]:
        """推断同比时间（去年同期）"""
        if not main_time:
            return None
            
        main_time_lower = main_time.lower()
        
        # 相对时间同比推断
        if main_time_lower in ['上月', '上个月']:
            return '去年同期'
        elif main_time_lower in ['本月', '这个月']:
            return '去年同月'
        elif main_time_lower in ['上周', '上个周']:
            return '去年同期'
        elif main_time_lower in ['本周', '这周']:
            return '去年同期'
        elif main_time_lower in ['昨天']:
            return '去年同日'
        elif main_time_lower in ['今天']:
            return '去年同日'
        
        # 绝对时间同比推断
        elif '月' in main_time and '年' in main_time:
            # 如"2025年6月" → "2024年6月"
            import re
            match = re.search(r'(\d{4})年(\d{1,2})月', main_time)
            if match:
                year = int(match.group(1))
                month = match.group(2)
                return f"{year-1}年{month}月"
        
        return None
    
    def _infer_period_over_period_time(self, main_time: str) -> Optional[str]:
        """推断环比时间（上一个周期）- 增强版，支持绝对时间格式"""
        if not main_time:
            return None
            
        main_time_lower = main_time.lower()
        
        # 新增：绝对时间格式的环比推断
        # 处理 "YYYY年MM月" → "YYYY年(MM-1)月" 或 "(YYYY-1)年12月"
        year_month_match = re.search(r'(\d{4})年(\d{1,2})月', main_time)
        if year_month_match:
            year = int(year_month_match.group(1))
            month = int(year_month_match.group(2))
            
            if month == 1:
                # 1月的环比是去年12月
                contrast_time = f"{year-1}年12月"
                self.logger.debug(f"[EXTRACTOR] 绝对时间环比推断(跨年): {main_time} → {contrast_time}")
                return contrast_time
            else:
                # 其他月份减1
                contrast_time = f"{year}年{month-1}月"
                self.logger.debug(f"[EXTRACTOR] 绝对时间环比推断: {main_time} → {contrast_time}")
                return contrast_time
        
        # 处理 "YYYY年MM月DD日" → 上一个月的同一天
        year_month_day_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', main_time)
        if year_month_day_match:
            year = int(year_month_day_match.group(1))
            month = int(year_month_day_match.group(2))
            day = int(year_month_day_match.group(3))
            
            if month == 1:
                # 1月的环比是去年12月
                contrast_time = f"{year-1}年12月{day}日"
                self.logger.debug(f"[EXTRACTOR] 绝对日期环比推断(跨年): {main_time} → {contrast_time}")
                return contrast_time
            else:
                # 其他月份减1
                contrast_time = f"{year}年{month-1}月{day}日"
                self.logger.debug(f"[EXTRACTOR] 绝对日期环比推断: {main_time} → {contrast_time}")
                return contrast_time
        
        # 处理 "YYYY年" → "(YYYY-1)年"
        year_only_match = re.search(r'(\d{4})年$', main_time)
        if year_only_match:
            year = int(year_only_match.group(1))
            contrast_time = f"{year-1}年"
            self.logger.debug(f"[EXTRACTOR] 绝对年份环比推断: {main_time} → {contrast_time}")
            return contrast_time
        
        # 现有相对时间推断规则
        if main_time_lower in ['本月', '这个月']:
            return '上月'
        elif main_time_lower in ['上月', '上个月']:
            return '前月'  # 两个月前
        elif main_time_lower in ['本周', '这周']:
            return '上周'
        elif main_time_lower in ['上周', '上个周']:
            return '前周'  # 两周前
        elif main_time_lower in ['今天']:
            return '昨天'
        elif main_time_lower in ['昨天']:
            return '前天'
        
        self.logger.debug(f"[EXTRACTOR] 无法推断环比时间: {main_time}")
        return None
    
    def _infer_intelligent_contrast_time(self, question: str, main_time: str) -> Optional[str]:
        """
        智能推断对比时间（统一方法）
        
        Args:
            question: 原始问题
            main_time: 主时间描述
            
        Returns:
            Optional[str]: 推断的对比时间
        """
        if not question or not main_time:
            return None
        
        # 检测对比类型
        question_lower = question.lower()
        
        # 环比处理
        if any(keyword in question_lower for keyword in ['环比', '较上期', '上月', '上期', '上周']):
            return self._infer_period_over_period_time(main_time)
        
        # 同比处理
        elif any(keyword in question_lower for keyword in ['同比', '较去年', '去年同期', '上年同期']):
            return self._infer_year_over_year_time(main_time)
        
        # 通用对比处理
        elif any(keyword in question_lower for keyword in ['对比', '比较', '变化', '相比']):
            # 根据上下文判断是同比还是环比
            if any(keyword in question_lower for keyword in ['去年', '上年']):
                return self._infer_year_over_year_time(main_time)
            else:
                return self._infer_period_over_period_time(main_time)  # 默认环比
        
        return None
    
    
    def extract_data_source(self, text: str) -> str:
        """
        提取数据源类型
        
        Args:
            text: 输入文本
            
        Returns:
            str: 数据源类型
        """
        text_lower = text.lower()
        
        for data_source, keywords in self.data_source_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                self.logger.debug(f"[EXTRACTOR] 提取到数据源: {data_source}")
                return data_source
        
        # 默认为审核实况
        default_source = "审核实况"
        self.logger.debug(f"[EXTRACTOR] 使用默认数据源: {default_source}")
        return default_source
    
    def extract_tool_params(self, text: str, tool_def: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取工具参数（主入口方法）
        
        Args:
            text: 用户输入文本
            tool_def: 工具定义
            
        Returns:
            Dict[str, Any]: 提取到的参数字典
        """
        self.logger.info(f"[EXTRACTOR] 开始提取工具参数")
        self.logger.info(f"[EXTRACTOR] 输入文本: {text}")
        self.logger.info(f"[EXTRACTOR] 目标工具: {tool_def.get('function', {}).get('name', 'unknown')}")
        
        tool_name = tool_def.get('function', {}).get('name', '')
        params = {}
        
        # 提取地理位置
        locations = self.extract_locations(text)
        if locations:
            params['locations'] = locations
        
        # 提取时间描述
        time_description = self.extract_time_description(text)
        if time_description:
            params['time_description'] = time_description
        
        # 提取对比时间（仅对比较工具）
        if tool_name == 'get_comparison_report':
            comparison_time = self.extract_comparison_time(text)
            if not comparison_time:
                # 智能补全对比时间
                comparison_time = self._smart_infer_comparison_time(text, params.get('time_description'))
            if comparison_time:
                params['comparison_time_description'] = comparison_time
        
        # 注意：区域类型判断已移除，改由多层级处理机制处理
        
        # 提取数据源
        data_source = self.extract_data_source(text)
        params['data_source'] = data_source
        
        self.logger.info(f"[EXTRACTOR] 提取完成，参数: {params}")
        return params
    
    def add_location_pattern(self, pattern: str, description: str = ""):
        """动态添加地理位置提取模式"""
        self.location_patterns.append(pattern)
        self.logger.info(f"[EXTRACTOR] 添加位置模式: {pattern} ({description})")
    
    def add_time_pattern(self, pattern: str, description: str = "", priority: int = -1):
        """动态添加时间提取模式"""
        if priority == -1:
            self.time_patterns.append((pattern, description))
        else:
            self.time_patterns.insert(priority, (pattern, description))
        self.logger.info(f"[EXTRACTOR] 添加时间模式: {pattern} ({description})")
    
    def set_area_type_keywords(self, area_type: str, keywords: List[str]):
        """设置区域类型关键词（已弃用，保留以保持兼容性）"""
        self.area_type_keywords[area_type] = keywords
        self.logger.info(f"[EXTRACTOR] 设置区域类型关键词 {area_type}: {keywords}")
    
    def extract_time_params_only(self, text: str) -> Dict[str, Any]:
        """
        仅提取时间相关参数（新的统一机制专用）
        
        这个方法专门为新的多层级处理机制设计，只提取时间相关参数，
        不处理地理位置和区域类型（这些由其他组件处理）。
        
        Args:
            text: 用户输入文本
            
        Returns:
            Dict[str, Any]: 只包含时间参数的字典
        """
        self.logger.info(f"[TIME_ONLY] 开始提取时间参数")
        
        params = {}
        
        # 提取主时间描述
        time_description = self.extract_time_description(text)
        if time_description:
            params['time_description'] = time_description
            self.logger.debug(f"[TIME_ONLY] 主时间: {time_description}")
        
        # 提取对比时间
        comparison_time = self.extract_comparison_time(text)
        if comparison_time:
            params['comparison_time_description'] = comparison_time
            self.logger.debug(f"[TIME_ONLY] 对比时间: {comparison_time}")
        else:
            # 尝试智能推断对比时间
            if time_description:
                inferred_comparison = self._smart_infer_comparison_time(text, time_description)
                if inferred_comparison:
                    params['comparison_time_description'] = inferred_comparison
                    self.logger.debug(f"[TIME_ONLY] 智能推断对比时间: {inferred_comparison}")
        
        # 提取数据源
        data_source = self.extract_data_source(text)
        params['data_source'] = data_source
        self.logger.debug(f"[TIME_ONLY] 数据源: {data_source}")
        
        self.logger.info(f"[TIME_ONLY] 时间参数提取完成: {params}")
        return params


# 全局实例
_param_extractor = None

def get_param_extractor() -> ParameterExtractor:
    """获取参数提取器单例"""
    global _param_extractor
    if _param_extractor is None:
        _param_extractor = ParameterExtractor()
    return _param_extractor