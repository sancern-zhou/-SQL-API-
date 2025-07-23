#!/usr/bin/env python3
"""
参数转换与润色模块
Parameter Converter Module

负责将LLM提取的自然语言实体转换为API要求的精确格式，
并处理各种不确定性和模糊匹配情况。
"""

import re
import json
import logging
import yaml
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union
from thefuzz import fuzz
import os


class ParamConverter:
    """参数转换器类，支持配置文件"""
    
    def __init__(self, config_or_path: Optional[Union[str, Dict[str, Any]]] = None):
        self.logger = logging.getLogger(__name__)
        
        # 支持传入配置字典或配置文件路径
        if isinstance(config_or_path, dict):
            # 直接使用传入的配置字典
            self.config = config_or_path
            self.config_path = None
            self.logger.info("[PARAM_CONVERTER] 使用传入的配置字典")
        elif isinstance(config_or_path, str):
            # 使用指定的配置文件路径
            self.config_path = config_or_path
            self.config = self._load_config()
        else:
            # 使用默认配置文件路径
            self.config_path = self._get_default_config_path()
            self.config = self._load_config()
        
        # 从配置文件加载设置
        self._load_settings_from_config()
        
        # 加载地理编码映射数据
        self._load_geo_mappings()
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        return os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'routing_config.yaml')
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    self.logger.info(f"[PARAM_CONVERTER] 配置加载成功: {self.config_path}")
                    return config
            else:
                self.logger.warning(f"[PARAM_CONVERTER] 配置文件不存在: {self.config_path}，使用默认配置")
                return self._get_default_config()
        except Exception as e:
            self.logger.error(f"[PARAM_CONVERTER] 配置加载失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'geo_location_extended': {
                'fuzzy_matching': {
                    'fuzzy_matching_threshold': 0.85
                }
            },
            'time_parsing_extended': {
                'format_patterns': {
                    'absolute_date': r'\d{4}年\d{1,2}月\d{1,2}日',
                    'absolute_month': r'\d{4}年\d{1,2}月',
                    'absolute_year': r'\d{4}年',
                    'api_date': r'\d{4}-\d{1,2}-\d{1,2}',
                    'api_month': r'\d{4}-\d{1,2}',
                    'recent_days': r'最近\d+天',
                    'past_days': r'过去\d+天',
                    'month_day': r'\d{1,2}月\d{1,2}日',
                    'month_only': r'\d{1,2}月'
                },
                'relative_time_mappings': {
                    '昨天': 'yesterday',
                    '今天': 'today',
                    '上周': 'last_week',
                    '上个月': 'last_month',
                    '去年': 'last_year',
                    '本周': 'this_week',
                    '本月': 'this_month',
                    '今年': 'this_year'
                }
            }
        }
    
    def _load_settings_from_config(self):
        """从配置文件加载设置"""
        try:
            # 加载模糊匹配阈值
            fuzzy_config = (self.config.get('geo_location_extended', {})
                           .get('fuzzy_matching', {}))
            self.fuzzy_match_threshold = fuzzy_config.get('fuzzy_matching_threshold', 0.85) * 100
            
            # 加载完整的时间解析配置
            time_config = self.config.get('time_parsing_extended', {})
            
            # 加载各类时间表达式
            self.current_time_expressions = time_config.get('current_time_expressions', {})
            self.historical_time_expressions = time_config.get('historical_time_expressions', {})
            self.range_time_expressions = time_config.get('range_time_expressions', {})
            self.month_expressions = time_config.get('month_expressions', {})
            self.quarter_expressions = time_config.get('quarter_expressions', {})
            self.absolute_time_expressions = time_config.get('absolute_time_expressions', {})
            self.api_format_expressions = time_config.get('api_format_expressions', {})
            self.comparison_time_expressions = time_config.get('comparison_time_expressions', {})
            self.future_time_expressions = time_config.get('future_time_expressions', {})
            
            # 加载解析规则
            parsing_rules = time_config.get('parsing_rules', {})
            self.priority_order = parsing_rules.get('priority_order', {})
            self.calculation_rules = parsing_rules.get('calculation_rules', {})
            self.output_format = parsing_rules.get('output_format', {})
            self.error_handling = parsing_rules.get('error_handling', {})
            
            # 加载调试设置
            debug_settings = time_config.get('debug_settings', {})
            self.debug_enabled = debug_settings.get('enable_trace_logging', True)
            self.log_prefix = debug_settings.get('log_prefix', '[TIME_PARSE]')
            
            # 兼容性：保留原有的配置
            self.format_patterns = time_config.get('format_patterns', {})
            self.relative_time_mappings = time_config.get('legacy_mappings', {})
            
            # 数据源映射（保持不变）
            self.data_source_mapping = {
                "原始实况": 0,
                "审核实况": 1,
                "原始标况": 2,
                "审核标况": 3
            }
            
            # 区域类型映射（保持不变）
            self.area_type_mapping = {
                "站点": 0,
                "区县": 1,
                "城市": 2
            }
            
            self.logger.info(f"[PARAM_CONVERTER] 配置加载完成:")
            self.logger.info(f"[PARAM_CONVERTER]   - 模糊匹配阈值: {self.fuzzy_match_threshold}")
            self.logger.info(f"[PARAM_CONVERTER]   - 时间格式模式: {len(self.format_patterns)}个")
            self.logger.info(f"[PARAM_CONVERTER]   - 相对时间映射: {len(self.relative_time_mappings)}个")
            self.logger.info(f"[PARAM_CONVERTER]   - 新配置优先级顺序: {len(self.priority_order)}个")
            self.logger.info(f"[PARAM_CONVERTER]   - 绝对时间表达式: {len(self.absolute_time_expressions)}个")
            self.logger.info(f"[PARAM_CONVERTER]   - 当前时间表达式: {len(self.current_time_expressions)}个")
            
        except Exception as e:
            self.logger.error(f"[PARAM_CONVERTER] 从配置加载设置失败: {e}，使用默认设置")
            # 使用默认设置
            self.fuzzy_match_threshold = 85
            self.format_patterns = {}
            self.relative_time_mappings = {}
    
    def reload_config(self) -> Dict[str, Any]:
        """重新加载配置文件"""
        try:
            old_threshold = self.fuzzy_match_threshold
            old_patterns_count = len(self.format_patterns)
            old_mappings_count = len(self.relative_time_mappings)
            
            # 重新加载配置
            self.config = self._load_config()
            self._load_settings_from_config()
            
            self.logger.info(f"[PARAM_CONVERTER] 配置重新加载完成")
            
            return {
                'config_reloaded': True,
                'settings_changed': True,
                'old_threshold': old_threshold,
                'new_threshold': self.fuzzy_match_threshold,
                'old_patterns_count': old_patterns_count,
                'new_patterns_count': len(self.format_patterns),
                'old_mappings_count': old_mappings_count,
                'new_mappings_count': len(self.relative_time_mappings),
                'config_path': self.config_path
            }
            
        except Exception as e:
            self.logger.error(f"[PARAM_CONVERTER] 配置重新加载失败: {e}")
            return {
                'config_reloaded': False,
                'error': str(e),
                'config_path': self.config_path
            }
    
    def _match_time_pattern(self, time_desc: str, pattern_name: str) -> Optional[re.Match]:
        """使用配置中的正则模式匹配时间"""
        if pattern_name in self.format_patterns:
            pattern = self.format_patterns[pattern_name]
            return re.match(pattern, time_desc)
        return None
    
    def _load_geo_mappings(self):
        """加载地理编码映射数据"""
        try:
            # 从配置文件加载地理编码映射
            config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'geo_mappings.json')
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    mappings = json.load(f)
                
                self.station_mappings = mappings.get('stations', {})
                self.district_mappings = mappings.get('districts', {})
                self.city_mappings = mappings.get('cities', {})
                
                self.logger.info(f"从配置文件加载地理编码映射数据: {config_path}")
                self.logger.info(f"加载站点数量: {len(self.station_mappings)}")
                self.logger.info(f"加载区县数量: {len(self.district_mappings)}")
                self.logger.info(f"加载城市数量: {len(self.city_mappings)}")
            else:
                # 配置文件不存在，使用默认映射
                self.logger.warning(f"地理编码配置文件不存在: {config_path}")
                self._load_default_mappings()
            
        except Exception as e:
            self.logger.error(f"加载地理编码映射数据失败: {e}")
            # 使用默认映射作为后备
            self._load_default_mappings()
    
    def _load_default_mappings(self):
        """加载默认的映射数据（后备方案）"""
        self.station_mappings = {
            "广雅中学": "1001A",
            "广雅": "1001A",
            "市一中": "1002A",
            "第一中学": "1002A"
        }
        
        self.district_mappings = {
            "越秀区": "440103",
            "越秀": "440103",
            "天河区": "440106",
            "天河": "440106"
        }
        
        self.city_mappings = {
            "广州市": "440100",
            "广州": "440100",
            "深圳市": "440300",
            "深圳": "440300"
        }
        
        self.logger.info("使用默认地理编码映射数据")
    
    def convert_locations_to_codes(self, locations: List[str], area_type: str) -> Tuple[List[str], List[str]]:
        """
        将地理位置名称转换为编码
        
        Args:
            locations: 地理位置名称列表
            area_type: 区域类型 ("站点", "区县", "城市")
        
        Returns:
            Tuple[List[str], List[str]]: (成功转换的编码列表, 需要澄清的位置列表)
        """
        try:
            self.logger.info(f"[PARAM_TRACE] 开始地理位置编码转换")
            self.logger.info(f"[PARAM_TRACE] 输入位置列表: {locations}")
            self.logger.info(f"[PARAM_TRACE] 区域类型: {area_type}")
            
            # 选择合适的映射表
            if area_type == "站点":
                mapping_dict = self.station_mappings
                self.logger.info(f"[PARAM_TRACE] 使用站点映射表，包含 {len(mapping_dict)} 个映射")
            elif area_type == "区县":
                mapping_dict = self.district_mappings
                self.logger.info(f"[PARAM_TRACE] 使用区县映射表，包含 {len(mapping_dict)} 个映射")
            elif area_type == "城市":
                mapping_dict = self.city_mappings
                self.logger.info(f"[PARAM_TRACE] 使用城市映射表，包含 {len(mapping_dict)} 个映射")
            else:
                self.logger.warning(f"[PARAM_TRACE] 未知的区域类型: {area_type}")
                return [], locations
            
            converted_codes = []
            needs_clarification = []
            
            for location in locations:
                self.logger.info(f"[PARAM_TRACE] 处理位置: '{location}'")
                
                # 尝试精确匹配
                if location in mapping_dict:
                    code = mapping_dict[location]
                    converted_codes.append(code)
                    self.logger.info(f"[PARAM_TRACE] 精确匹配成功: '{location}' -> '{code}'")
                    continue
                
                # 尝试模糊匹配
                self.logger.info(f"[PARAM_TRACE] 精确匹配失败，尝试模糊匹配")
                best_match, confidence = self._fuzzy_match_location(location, mapping_dict)
                
                if confidence >= self.fuzzy_match_threshold:
                    code = mapping_dict[best_match]
                    converted_codes.append(code)
                    self.logger.info(f"[PARAM_TRACE] 模糊匹配成功: '{location}' -> '{best_match}' -> '{code}' (置信度: {confidence}%)")
                else:
                    needs_clarification.append(location)
                    self.logger.warning(f"[PARAM_TRACE] 位置匹配失败: '{location}' (最佳匹配: '{best_match}', 置信度: {confidence}%)")
            
            self.logger.info(f"[PARAM_TRACE] 地理位置转换完成")
            self.logger.info(f"[PARAM_TRACE] 成功转换: {converted_codes}")
            self.logger.info(f"[PARAM_TRACE] 需要澄清: {needs_clarification}")
            
            return converted_codes, needs_clarification
            
        except Exception as e:
            self.logger.error(f"地理位置转换失败: {e}")
            return [], locations
    
    def _fuzzy_match_location(self, target: str, mapping_dict: Dict[str, str]) -> Tuple[str, int]:
        """
        模糊匹配地理位置
        
        Returns:
            Tuple[str, int]: (最佳匹配名称, 置信度分数)
        """
        best_match = ""
        best_score = 0
        
        for name in mapping_dict.keys():
            # 使用多种模糊匹配策略
            score1 = fuzz.ratio(target, name)
            score2 = fuzz.partial_ratio(target, name)
            score3 = fuzz.token_sort_ratio(target, name)
            
            # 取最高分
            score = max(score1, score2, score3)
            
            if score > best_score:
                best_score = score
                best_match = name
        
        return best_match, best_score
    
    def parse_time_description(self, time_desc: str) -> Tuple[Optional[List[str]], str]:
        """
        配置驱动的时间描述解析器
        
        Args:
            time_desc: 时间描述文本
        
        Returns:
            Tuple[Optional[List[str]], str]: (时间范围数组, 错误信息)
        """
        try:
            if self.debug_enabled:
                self.logger.info(f"{self.log_prefix} 开始配置驱动时间解析")
                self.logger.info(f"{self.log_prefix} 输入时间描述: '{time_desc}'")
            
            if not time_desc:
                error_msg = self.error_handling.get('unknown_expression_message', "时间描述为空").format(time_desc=time_desc)
                self.logger.warning(f"{self.log_prefix} {error_msg}")
                return None, error_msg
            
            # 检查是否为LLM输出的API格式数组
            if isinstance(time_desc, list) and len(time_desc) == 2:
                try:
                    # 验证API格式时间的有效性
                    datetime_format = self.output_format.get('datetime_format', '%Y-%m-%d %H:%M:%S')
                    start_time = datetime.strptime(time_desc[0], datetime_format)
                    end_time = datetime.strptime(time_desc[1], datetime_format)
                    if self.debug_enabled:
                        self.logger.info(f"{self.log_prefix} 检测到API格式时间，直接使用: {time_desc}")
                    return time_desc, ""  # 直接返回原始数组格式
                except Exception as e:
                    error_msg = self.error_handling.get('parsing_error_message', "API格式时间解析失败: {error}").format(error=str(e))
                    self.logger.error(f"{self.log_prefix} {error_msg}")
                    return None, error_msg
            
            time_desc = time_desc.strip().lower()
            now = datetime.now()
            if self.debug_enabled:
                self.logger.info(f"{self.log_prefix} 标准化时间描述: '{time_desc}'")
                self.logger.info(f"{self.log_prefix} 当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 检查未来时间表达式（明确不支持）
            unsupported_keywords = self.future_time_expressions.get('unsupported_keywords', [])
            if time_desc in unsupported_keywords:
                error_msg = self.future_time_expressions.get('error_message', "未来时间表达式不支持: '{time_desc}'").format(time_desc=time_desc)
                self.logger.warning(f"{self.log_prefix} {error_msg}")
                return None, error_msg
            
            # 按优先级顺序处理时间表达式
            if self.debug_enabled:
                self.logger.info(f"{self.log_prefix} 开始遍历优先级顺序，共{len(self.priority_order)}个表达式类型")
                
            for priority, expression_type in self.priority_order.items():
                if self.debug_enabled:
                    self.logger.info(f"{self.log_prefix} 尝试解析类型: {expression_type}（优先级{priority}）")
                result, error = self._parse_by_expression_type(expression_type, time_desc, now)
                if result is not None:
                    if self.debug_enabled:
                        self.logger.info(f"{self.log_prefix} 成功匹配 {expression_type}（优先级{priority}）: {result}")
                    return result, error
                elif error and "无法解析" not in error:
                    # 如果有具体错误（不是简单的无法解析），直接返回
                    self.logger.warning(f"{self.log_prefix} {expression_type} 解析出错: {error}")
                    return None, error
                else:
                    if self.debug_enabled:
                        self.logger.debug(f"{self.log_prefix} {expression_type} 未匹配")
            
            # 所有表达式类型都无法匹配
            error_msg = self.error_handling.get('unknown_expression_message', "无法解析的时间描述: '{time_desc}'").format(time_desc=time_desc)
            self.logger.warning(f"{self.log_prefix} {error_msg}")
            return None, error_msg
        except Exception as e:
            error_msg = self.error_handling.get('parsing_error_message', "时间解析出错: {error}").format(error=str(e))
            self.logger.error(f"{self.log_prefix} {error_msg}")
            return None, error_msg
    
    def _extract_time_keywords(self, user_query: str) -> Optional[str]:
        """
        从用户查询中提取纯时间关键词
        这是时间处理的第一阶段：时间提取阶段
        只提取时间相关的关键词，不处理整句话
        """
        if not user_query:
            return None
            
        self.logger.info(f"[TIME_EXTRACT] 开始从用户查询中提取时间关键词: '{user_query}'")
        
        # 从配置中获取时间提取模式
        parameter_extraction = self.config.get('parameter_extraction', {})
        time_patterns = parameter_extraction.get('time_patterns', [])
        
        if not time_patterns:
            # 使用默认的时间提取模式
            time_patterns = [
                {'pattern': r'(\d{4}年\d{1,2}月\d{1,2}日)', 'name': 'full_date'},
                {'pattern': r'(\d{4}年\d{1,2}月)', 'name': 'year_month'},
                {'pattern': r'(\d{1,2}月\d{1,2}日)', 'name': 'month_day'},
                {'pattern': r'(\d{1,2}月)', 'name': 'month_only'},
                {'pattern': r'(昨天|今天|明天)', 'name': 'relative_day'},
                {'pattern': r'(上周|本周|下周)', 'name': 'relative_week'},
                {'pattern': r'(上个?月|本月|下个?月)', 'name': 'relative_month'},
                {'pattern': r'(去年|今年|明年)', 'name': 'relative_year'},
                {'pattern': r'(\d{4}-\d{1,2}-\d{1,2})', 'name': 'api_date'},
                {'pattern': r'(\d{4}-\d{1,2})', 'name': 'api_month'}
            ]
        
        # 按照配置的优先级顺序尝试提取
        for pattern_config in time_patterns:
            pattern = pattern_config['pattern']
            pattern_name = pattern_config.get('name', 'unknown')
            
            # 使用re.search支持从复杂文本中提取
            match = re.search(pattern, user_query)
            if match:
                # 提取匹配的时间关键词
                time_keyword = match.group(1) if match.groups() else match.group(0)
                self.logger.info(f"[TIME_EXTRACT] 成功提取时间关键词: '{time_keyword}' (模式: {pattern_name})")
                return time_keyword
        
        self.logger.info(f"[TIME_EXTRACT] 未能提取到时间关键词")
        return None
    
    def parse_time_with_unified_fallback(self, user_query: str, 
                                        question: str = "") -> Tuple[Optional[List[str]], Optional[str]]:
        """
        统一的时间解析方法，实现正确的两阶段处理
        第一阶段：时间提取 - 从用户查询中提取时间关键词
        第二阶段：时间解析 - 将时间关键词解析为API格式
        """
        if not user_query:
            return None, "用户查询为空"
        
        self.logger.info(f"[UNIFIED_TIME_PARSE] 开始两阶段时间处理")
        self.logger.info(f"[UNIFIED_TIME_PARSE] 用户查询: '{user_query}'")
        
        # 第一阶段：时间提取 - 从复杂查询中提取时间关键词
        time_keyword = self._extract_time_keywords(user_query)
        if not time_keyword:
            # 如果无法提取时间关键词，直接使用用户查询作为时间描述
            time_keyword = user_query.strip()
            self.logger.info(f"[UNIFIED_TIME_PARSE] 未提取到关键词，使用原查询: '{time_keyword}'")
        
        # 第二阶段：时间解析 - 将时间关键词解析为API格式
        self.logger.info(f"[UNIFIED_TIME_PARSE] 开始解析时间关键词: '{time_keyword}'")
        
        # 第一层：传统配置解析
        time_range, error = self._parse_time_with_config(time_keyword)
        if time_range:
            self.logger.info(f"[UNIFIED_TIME_PARSE] 传统解析成功: {time_range}")
            return time_range, None
        
        # 第二层：智能年份补全
        completed_time = self._smart_complete_year(time_keyword)
        if completed_time:
            self.logger.info(f"[UNIFIED_TIME_PARSE] 尝试年份补全: {time_keyword} → {completed_time}")
            time_range, error = self._parse_time_with_config(completed_time)
            if time_range:
                self.logger.info(f"[UNIFIED_TIME_PARSE] 年份补全解析成功: {time_range}")
                return time_range, None
        
        # 第三层：统一LLM兜底
        self.logger.info(f"[UNIFIED_TIME_PARSE] 启动LLM时间解析兜底")
        try:
            from ..intelligence.unified_llm_fallback_manager import get_unified_llm_fallback_manager
            
            fallback_manager = get_unified_llm_fallback_manager()
            fallback_result = fallback_manager.handle_fallback(
                fallback_type='time_parsing',
                question=question,
                context={
                    'failed_time_desc': time_keyword,
                    'completed_time': completed_time,
                    'parsing_attempts': [
                        {'method': 'traditional', 'result': 'failed', 'error': error},
                        {'method': 'year_completion', 'result': 'failed' if not completed_time else 'partial'}
                    ]
                },
                error_info=f"传统解析失败: {error}, 年份补全: {'成功但仍无法解析' if completed_time else '无效格式'}"
            )
            
            if fallback_result['status'] == 'success' and fallback_result.get('action') == 'continue':
                llm_data = fallback_result['result_data']
                self.logger.info(f"[UNIFIED_TIME_PARSE] LLM兜底成功: {llm_data}")
                
                # 检查LLM返回的数据格式
                if isinstance(llm_data, list) and len(llm_data) == 2:
                    # LLM返回时间数组格式，直接使用
                    return llm_data, None
                elif isinstance(llm_data, dict) and 'TimePoint' in llm_data:
                    # LLM返回完整API参数格式，提取时间部分
                    time_point = llm_data.get('TimePoint')
                    if isinstance(time_point, list) and len(time_point) == 2:
                        self.logger.info(f"[UNIFIED_TIME_PARSE] 从LLM API参数中提取时间: {time_point}")
                        return time_point, None
                    else:
                        error_msg = f"LLM返回的API参数中时间格式错误: {time_point}"
                        self.logger.error(f"[UNIFIED_TIME_PARSE] {error_msg}")
                        return None, error_msg
                else:
                    # LLM返回未知格式，尝试直接使用
                    self.logger.warning(f"[UNIFIED_TIME_PARSE] LLM返回未知格式，尝试直接使用: {llm_data}")
                    return llm_data, None
            else:
                # LLM托底失败，建议转SQL
                final_error = f"LLM时间解析失败，建议转SQL: {fallback_result.get('reason', '未知原因')}"
                self.logger.warning(f"[UNIFIED_TIME_PARSE] {final_error}")
                return None, final_error
                
        except Exception as e:
            self.logger.error(f"[UNIFIED_TIME_PARSE] LLM兜底异常: {e}")
            final_error = f"无法解析时间描述 '{time_keyword}'。传统解析失败: {error}, 年份补全: {'成功但仍无法解析' if completed_time else '无效格式'}, LLM兜底异常: {str(e)}"
            return None, final_error
    
    def _smart_complete_year(self, time_desc: str) -> Optional[str]:
        """智能年份补全"""
        from datetime import datetime
        current_year = datetime.now().year
        
        # 处理 "MM月DD日" → "YYYY年MM月DD日"
        month_day_match = re.search(r'^(\d{1,2})月(\d{1,2})日$', time_desc.strip())
        if month_day_match:
            month = month_day_match.group(1)
            day = month_day_match.group(2)
            completed = f"{current_year}年{month}月{day}日"
            self.logger.info(f"[YEAR_COMPLETE] 月日补全: {time_desc} → {completed}")
            return completed
        
        # 处理 "MM月" → "YYYY年MM月"  
        month_only_match = re.search(r'^(\d{1,2})月$', time_desc.strip())
        if month_only_match:
            month = month_only_match.group(1)
            completed = f"{current_year}年{month}月"
            self.logger.info(f"[YEAR_COMPLETE] 月份补全: {time_desc} → {completed}")
            return completed
        
        return None
    
    def _format_time_range(self, start_date: datetime, end_date: datetime) -> List[str]:
        """使用配置格式化时间范围为API格式"""
        datetime_format = self.output_format.get('datetime_format', '%Y-%m-%d %H:%M:%S')
        start_suffix = self.output_format.get('start_time_suffix', ' 00:00:00')
        end_suffix = self.output_format.get('end_time_suffix', ' 23:59:59')
        
        start_str = start_date.strftime('%Y-%m-%d') + start_suffix
        end_str = end_date.strftime('%Y-%m-%d') + end_suffix
        
        return [start_str, end_str]
    
    def _parse_by_expression_type(self, expression_type: str, time_desc: str, now: datetime) -> Tuple[Optional[List[str]], str]:
        """根据表达式类型解析时间"""
        try:
            if expression_type == "current_time_expressions":
                return self._parse_current_time(time_desc, now)
            elif expression_type == "historical_time_expressions":
                return self._parse_historical_time(time_desc, now)
            elif expression_type == "range_time_expressions":
                return self._parse_range_time(time_desc, now)
            elif expression_type == "quarter_expressions":
                return self._parse_quarter_time(time_desc, now)
            elif expression_type == "absolute_time_expressions":
                return self._parse_absolute_time(time_desc, now)
            elif expression_type == "api_format_expressions":
                return self._parse_api_format_time(time_desc, now)
            elif expression_type == "month_expressions":
                return self._parse_month_time(time_desc, now)
            else:
                return None, f"未知的表达式类型: {expression_type}"
        except Exception as e:
            return None, f"解析{expression_type}失败: {str(e)}"
    
    def _parse_current_time(self, time_desc: str, now: datetime) -> Tuple[Optional[List[str]], str]:
        """解析当前时间表达式"""
        expressions = getattr(self, 'current_time_expressions', {})
        
        for time_type, keywords in expressions.items():
            if time_desc in [kw.lower() for kw in keywords]:
                if time_type == 'today':
                    return self._format_time_range(now, now), ""
                elif time_type == 'this_week':
                    days_since_monday = now.weekday()
                    this_monday = now - timedelta(days=days_since_monday)
                    this_sunday = this_monday + timedelta(days=6)
                    return self._format_time_range(this_monday, this_sunday), ""
                elif time_type == 'this_month':
                    first_day = datetime(now.year, now.month, 1)
                    return self._format_time_range(first_day, now), ""
                elif time_type == 'this_year':
                    start_date = datetime(now.year, 1, 1)
                    return self._format_time_range(start_date, now), ""
        
        return None, ""
    
    def _parse_historical_time(self, time_desc: str, now: datetime) -> Tuple[Optional[List[str]], str]:
        """解析历史时间表达式"""
        expressions = getattr(self, 'historical_time_expressions', {})
        calculation_rules = getattr(self, 'calculation_rules', {})
        
        for time_type, keywords in expressions.items():
            if time_desc in [kw.lower() for kw in keywords]:
                if time_type == 'yesterday':
                    start_date = now - timedelta(days=1)
                    return self._format_time_range(start_date, start_date), ""
                elif time_type == 'last_week':
                    days_since_monday = now.weekday()
                    last_monday = now - timedelta(days=days_since_monday + 7)
                    last_sunday = last_monday + timedelta(days=6)
                    return self._format_time_range(last_monday, last_sunday), ""
                elif time_type == 'last_month':
                    if now.month == 1:
                        last_month = datetime(now.year - 1, 12, 1)
                        next_month = datetime(now.year, 1, 1)
                    else:
                        last_month = datetime(now.year, now.month - 1, 1)
                        next_month = datetime(now.year, now.month, 1)
                    last_day = next_month - timedelta(days=1)
                    return self._format_time_range(last_month, last_day), ""
                elif time_type == 'last_year':
                    start_date = datetime(now.year - 1, 1, 1)
                    end_date = datetime(now.year - 1, 12, 31)
                    return self._format_time_range(start_date, end_date), ""
        
        # 处理"前天"、"大前天"等
        days_ago_keywords = expressions.get('days_ago', [])
        if time_desc in [kw.lower() for kw in days_ago_keywords]:
            days_ago_mapping = calculation_rules.get('days_ago_mapping', {})
            days = days_ago_mapping.get(time_desc, 2)
            start_date = now - timedelta(days=days)
            return self._format_time_range(start_date, start_date), ""
        
        return None, ""
    
    def _parse_range_time(self, time_desc: str, now: datetime) -> Tuple[Optional[List[str]], str]:
        """解析范围时间表达式"""
        expressions = getattr(self, 'range_time_expressions', {})
        
        # 处理"最近N天"
        recent_days_pattern = expressions.get('recent_days', '')
        if recent_days_pattern:
            match = re.match(recent_days_pattern, time_desc)
            if match:
                days = int(match.group(1))
                start_date = now - timedelta(days=days - 1)  # 包含今天
                return self._format_time_range(start_date, now), ""
        
        # 处理"过去N天"
        past_days_pattern = expressions.get('past_days', '')
        if past_days_pattern:
            match = re.match(past_days_pattern, time_desc)
            if match:
                days = int(match.group(1))
                end_date = now - timedelta(days=1)  # 不包含今天
                start_date = end_date - timedelta(days=days - 1)
                return self._format_time_range(start_date, end_date), ""
        
        return None, ""
    
    def _parse_quarter_time(self, time_desc: str, now: datetime) -> Tuple[Optional[List[str]], str]:
        """解析季度时间表达式"""
        expressions = getattr(self, 'quarter_expressions', {})
        
        # 本季度
        this_quarter_keywords = expressions.get('this_quarter', [])
        if time_desc in [kw.lower() for kw in this_quarter_keywords]:
            current_quarter = (now.month - 1) // 3 + 1
            quarter_start_month = (current_quarter - 1) * 3 + 1
            start_date = datetime(now.year, quarter_start_month, 1)
            return self._format_time_range(start_date, now), ""
        
        # 上季度
        last_quarter_keywords = expressions.get('last_quarter', [])
        if time_desc in [kw.lower() for kw in last_quarter_keywords]:
            current_quarter = (now.month - 1) // 3 + 1
            if current_quarter == 1:
                # 去年第四季度
                start_date = datetime(now.year - 1, 10, 1)
                end_date = datetime(now.year - 1, 12, 31)
            else:
                # 今年前一季度
                last_quarter_start_month = (current_quarter - 2) * 3 + 1
                start_date = datetime(now.year, last_quarter_start_month, 1)
                current_quarter_start_month = (current_quarter - 1) * 3 + 1
                end_date = datetime(now.year, current_quarter_start_month, 1) - timedelta(days=1)
            return self._format_time_range(start_date, end_date), ""
        
        return None, ""
    
    def _parse_absolute_time(self, time_desc: str, now: datetime) -> Tuple[Optional[List[str]], str]:
        """解析绝对时间表达式"""
        expressions = getattr(self, 'absolute_time_expressions', {})
        
        # YYYY年MM月DD日 - 改为search支持复杂文本
        full_date_pattern = expressions.get('full_date', '')
        if full_date_pattern:
            match = re.search(full_date_pattern, time_desc)
            if match:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                try:
                    target_date = datetime(year, month, day)
                    return self._format_time_range(target_date, target_date), ""
                except ValueError:
                    return None, self._get_error_message('invalid_date_message', '无效的日期').format(date_desc=f"{year}年{month}月{day}日")
        
        # YYYY年MM月 - 改为search支持复杂文本
        year_month_pattern = expressions.get('year_month', '')
        if year_month_pattern:
            match = re.search(year_month_pattern, time_desc)
            if match:
                year, month = int(match.group(1)), int(match.group(2))
                try:
                    start_date = datetime(year, month, 1)
                    if month == 12:
                        next_month = datetime(year + 1, 1, 1)
                    else:
                        next_month = datetime(year, month + 1, 1)
                    end_date = next_month - timedelta(days=1)
                    return self._format_time_range(start_date, end_date), ""
                except ValueError:
                    return None, self._get_error_message('invalid_month_message', '无效的年月').format(month=f"{year}-{month}")
        
        # YYYY年 - 改为search支持复杂文本
        year_only_pattern = expressions.get('year_only', '')
        if year_only_pattern:
            match = re.match(year_only_pattern, time_desc)
            if match:
                year = int(match.group(1))
                try:
                    start_date = datetime(year, 1, 1)
                    end_date = datetime(year, 12, 31)
                    return self._format_time_range(start_date, end_date), ""
                except ValueError:
                    return None, self._get_error_message('invalid_year_message', '无效的年份').format(year=year)
        
        return None, ""
    
    def _parse_api_format_time(self, time_desc: str, now: datetime) -> Tuple[Optional[List[str]], str]:
        """解析API格式时间表达式"""
        expressions = getattr(self, 'api_format_expressions', {})
        
        # YYYY-MM-DD
        api_date_pattern = expressions.get('api_date', '')
        if api_date_pattern:
            match = re.match(api_date_pattern, time_desc)
            if match:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                try:
                    target_date = datetime(year, month, day)
                    return self._format_time_range(target_date, target_date), ""
                except ValueError:
                    return None, f"无效的API格式日期: {year}-{month}-{day}"
        
        # YYYY-MM
        api_month_pattern = expressions.get('api_month', '')
        if api_month_pattern:
            match = re.match(api_month_pattern, time_desc)
            if match:
                year, month = int(match.group(1)), int(match.group(2))
                try:
                    start_date = datetime(year, month, 1)
                    if month == 12:
                        next_month = datetime(year + 1, 1, 1)
                    else:
                        next_month = datetime(year, month + 1, 1)
                    end_date = next_month - timedelta(days=1)
                    return self._format_time_range(start_date, end_date), ""
                except ValueError:
                    return None, f"无效的API格式年月: {year}-{month}"
        
        return None, ""
    
    def _parse_month_time(self, time_desc: str, now: datetime) -> Tuple[Optional[List[str]], str]:
        """解析月份表达式"""
        expressions = getattr(self, 'month_expressions', {})
        
        # N月
        month_only_pattern = expressions.get('month_only', '')
        if month_only_pattern:
            match = re.match(month_only_pattern, time_desc)
            if match:
                month = int(match.group(1))
                if 1 <= month <= 12:
                    start_date = datetime(now.year, month, 1)
                    if month == 12:
                        next_month = datetime(now.year + 1, 1, 1)
                    else:
                        next_month = datetime(now.year, month + 1, 1)
                    end_date = next_month - timedelta(days=1)
                    return self._format_time_range(start_date, end_date), ""
                else:
                    return None, self._get_error_message('invalid_month_message', '无效的月份').format(month=month)
        
        return None, ""
    
    def _calculate_unified_comparison_time(self, main_start: datetime, main_end: datetime, comparison_type: str) -> List[str]:
        """
        统一的对比时间计算逻辑
        
        Args:
            main_start: 主时间开始
            main_end: 主时间结束
            comparison_type: "period" (环比) | "year" (同比)
            
        Returns:
            List[str]: 对比时间范围
        """
        try:
            if comparison_type == "period":
                # 环比：向前推一个相同的时间跨度
                time_span = main_end - main_start
                comp_end = main_start - timedelta(days=1)
                comp_start = comp_end - time_span
                
            elif comparison_type == "year":
                # 同比：向前推一年，保持相同跨度
                try:
                    comp_start = main_start.replace(year=main_start.year - 1)
                    comp_end = main_end.replace(year=main_end.year - 1)
                except ValueError:
                    # 处理2月29日等特殊情况
                    comp_start = datetime(main_start.year - 1, main_start.month, 28)
                    comp_end = datetime(main_end.year - 1, main_end.month, 28)
            else:
                raise ValueError(f"不支持的对比类型: {comparison_type}")
                
            return self._format_time_range(comp_start, comp_end)
            
        except Exception as e:
            self.logger.error(f"[统一对比] 计算失败: {e}")
            raise
    
    def _detect_comparison_type(self, comparison_desc: str) -> Optional[str]:
        """
        检测对比时间类型
        
        Args:
            comparison_desc: 对比时间描述
            
        Returns:
            str: "period" | "year" | None
        """
        try:
            comparison_config = getattr(self, 'comparison_time_expressions', {})
            
            # 检查环比关键词
            period_keywords = comparison_config.get('period_comparison', {}).get('keywords', [])
            if comparison_desc in period_keywords:
                return "period"
                
            # 检查同比关键词
            year_keywords = comparison_config.get('year_comparison', {}).get('keywords', [])
            if comparison_desc in year_keywords:
                return "year"
                
            return None
            
        except Exception as e:
            self.logger.error(f"[对比类型检测] 失败: {e}")
            return None
    
    def parse_comparison_time_based_on_main_time(self, comparison_desc: str, main_time_point: List[str]) -> Tuple[Optional[List[str]], str]:
        """
        基于主时间范围解析对比时间描述
        
        Args:
            comparison_desc: 对比时间描述（如"去年同期"、"2024年1月"）
            main_time_point: 主时间范围 ["2025-01-01 00:00:00", "2025-01-31 23:59:59"]
            
        Returns:
            Tuple[Optional[List[str]], str]: (对比时间范围数组, 错误信息)
        """
        try:
            self.logger.info(f"[PARAM_TRACE] 基于主时间解析对比时间")
            self.logger.info(f"[PARAM_TRACE] 对比时间描述: '{comparison_desc}'")
            self.logger.info(f"[PARAM_TRACE] 主时间范围: {main_time_point}")
            
            # 解析主时间范围
            main_start = datetime.strptime(main_time_point[0], "%Y-%m-%d %H:%M:%S")
            main_end = datetime.strptime(main_time_point[1], "%Y-%m-%d %H:%M:%S")
            
            # 检测对比类型
            comparison_type = self._detect_comparison_type(comparison_desc)
            
            if comparison_type:
                # 使用统一的计算逻辑
                result = self._calculate_unified_comparison_time(main_start, main_end, comparison_type)
                self.logger.info(f"[PARAM_TRACE] 统一对比计算成功: {comparison_desc} -> {comparison_type} -> {result}")
                return result, ""
            
            else:
                # 尝试直接解析（可能是具体的时间描述）
                self.logger.warning(f"[PARAM_TRACE] 未识别的对比时间类型: {comparison_desc}，尝试直接解析")
                return self.parse_time_description(comparison_desc)
                
        except Exception as e:
            self.logger.error(f"[PARAM_TRACE] 基于主时间解析对比时间失败: {e}")
            return None, f"基于主时间解析对比时间失败: {str(e)}"
    
    def determine_time_type(self, time_desc: str) -> int:
        """
        根据时间描述确定时间类型，统一使用任意时间类型，让API根据时间范围自动处理
        
        Returns:
            int: 时间类型 (3: 周报, 4: 月报, 5: 季报, 7: 年报, 8: 任意时间)
        """
        return 8  # 任意时间
    
    def convert_data_source(self, data_source_desc: str) -> int:
        """转换数据源描述为对应的数值"""
        return self.data_source_mapping.get(data_source_desc, 1)  # 默认为审核实况
    
    def convert_area_type(self, area_type_desc: str) -> int:
        """转换区域类型描述为对应的数值"""
        return self.area_type_mapping.get(area_type_desc, 0)  # 默认为站点
    
    def validate_and_convert_params(self, tool_params: Dict[str, Any], 
                                   enable_llm_completion: bool = True) -> Dict[str, Any]:
        """
        验证和转换工具参数 - 支持LLM智能补充
        
        Args:
            tool_params: LLM提取的工具参数
            enable_llm_completion: 是否启用LLM智能补充
        
        Returns:
            Dict: 包含转换结果、错误信息和澄清问题的字典
        """
        self.logger.info(f"[PARAM_TRACE] 开始参数验证和转换")
        self.logger.info(f"[PARAM_TRACE] 输入工具参数: {tool_params}")
        self.logger.info(f"[PARAM_TRACE] LLM智能补充: {enable_llm_completion}")
        
        result = {
            "status": "success",
            "converted_params": {},
            "errors": [],
            "clarifications": []
        }
        
        try:
            # 验证必需参数
            locations = tool_params.get('locations', [])
            time_description = tool_params.get('time_description', '')
            area_type = tool_params.get('area_type', '站点')
            data_source = tool_params.get('data_source', '审核实况')
            
            self.logger.info(f"[PARAM_TRACE] 提取的参数:")
            self.logger.info(f"[PARAM_TRACE]   - 位置列表: {locations}")
            self.logger.info(f"[PARAM_TRACE]   - 时间描述: '{time_description}'")
            self.logger.info(f"[PARAM_TRACE]   - 区域类型: '{area_type}'")
            self.logger.info(f"[PARAM_TRACE]   - 数据源: '{data_source}'")
            
            # 检查必需参数
            missing_params = []
            if not locations:
                missing_params.append("位置")
                result["errors"].append("未指定查询位置")
                result["clarifications"].append("请指定要查询的地理位置（如站点、区县或城市）")
            
            if not time_description:
                missing_params.append("时间")
                result["errors"].append("未指定时间范围")
                result["clarifications"].append("请指定要查询的时间范围（如上周、本月等）")
            
            # 如果有必需参数缺失且启用了LLM补充，尝试LLM智能分析
            if result["errors"] and enable_llm_completion:
                self.logger.info(f"[PARAM_TRACE] 检测到缺失参数: {missing_params}，尝试LLM智能补充")
                
                # 返回特殊状态，交给LLM处理器处理
                result["status"] = "llm_completion_needed"
                result["missing_params"] = missing_params
                return result
            
            # 如果有必需参数缺失且未启用LLM补充，直接返回澄清
            if result["errors"]:
                result["status"] = "clarification_needed"
                return result
            
            # 转换地理位置
            self.logger.info(f"[PARAM_TRACE] 开始地理位置转换")
            station_codes, unclear_locations = self.convert_locations_to_codes(locations, area_type)
            
            if unclear_locations:
                result["clarifications"].extend([
                    f"无法确定位置 '{loc}' 的具体含义，请提供更准确的名称" 
                    for loc in unclear_locations
                ])
            
            if not station_codes:
                result["errors"].append("所有位置都无法识别")
                result["status"] = "clarification_needed"
                return result
            
            # 转换时间
            self.logger.info(f"[PARAM_TRACE] 开始时间转换")
            time_point, time_error = self.parse_time_description(time_description)
            
            if time_error:
                result["errors"].append(time_error)
                result["clarifications"].append("请提供更具体的时间范围（如2024年5月、上周等）")
                result["status"] = "clarification_needed"
                return result
            
            # 构建转换后的参数
            converted_area_type = self.convert_area_type(area_type)
            converted_time_type = self.determine_time_type(time_description)
            converted_data_source = self.convert_data_source(data_source)
            
            result["converted_params"] = {
                "area_type": converted_area_type,
                "time_type": converted_time_type,
                "time_point": time_point,
                "station_codes": station_codes,
                "data_source": converted_data_source
            }
            
            self.logger.info(f"[PARAM_TRACE] 参数转换完成:")
            self.logger.info(f"[PARAM_TRACE]   - 区域类型: {area_type} -> {converted_area_type}")
            self.logger.info(f"[PARAM_TRACE]   - 时间类型: {time_description} -> {converted_time_type}")
            self.logger.info(f"[PARAM_TRACE]   - 数据源: {data_source} -> {converted_data_source}")
            self.logger.info(f"[PARAM_TRACE]   - 站点编码: {station_codes}")
            self.logger.info(f"[PARAM_TRACE]   - 时间范围: {time_point}")
            
            # 处理对比时间（如果存在）
            comparison_time = tool_params.get('comparison_time_description')
            if comparison_time:
                self.logger.info(f"[PARAM_TRACE] 发现对比时间描述: '{comparison_time}'")
                
                # 尝试基于主时间的智能解析
                if time_point:
                    comparison_time_point, comparison_error = self.parse_comparison_time_based_on_main_time(comparison_time, time_point)
                else:
                    # 如果没有主时间，使用普通解析
                    comparison_time_point, comparison_error = self.parse_time_description(comparison_time)
                
                if comparison_error:
                    self.logger.error(f"[PARAM_TRACE] 对比时间解析失败: {comparison_error}")
                    result["errors"].append(f"对比时间解析失败: {comparison_error}")
                    result["clarifications"].append("请提供更具体的对比时间范围")
                    result["status"] = "clarification_needed"
                    return result
                
                result["converted_params"]["contrast_time"] = comparison_time_point
                self.logger.info(f"[PARAM_TRACE] 对比时间转换成功: {comparison_time_point}")
            
            # 如果有澄清问题但仍能继续，状态设为warning
            if result["clarifications"]:
                result["status"] = "warning"
                self.logger.warning(f"[PARAM_TRACE] 参数转换完成但有警告: {result['clarifications']}")
            else:
                self.logger.info(f"[PARAM_TRACE] 参数转换完全成功")
            
            return result
            
        except Exception as e:
            self.logger.error(f"[PARAM_TRACE] 参数验证和转换异常: {e}")
            result["status"] = "error"
            result["errors"].append(f"参数转换错误: {str(e)}")
            return result
    
    def convert_multi_level_params(self, grouped_locations: Dict[str, List[str]], 
                                  time_params: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        """
        统一的多层级参数转换方法
        
        处理所有层级的地理位置和时间参数转换，支持单层级和多层级统一处理。
        
        Args:
            grouped_locations: 按层级分组的地理位置
                格式: {'城市': ['广州市'], '站点': ['广州塔']}
            time_params: 时间参数字典
                包含: time_description, comparison_time_description, data_source等
            tool_name: API工具名称
        
        Returns:
            Dict[str, Any]: 完整的多层级转换结果
                格式: {
                    'levels': {
                        '城市': {
                            'area_type_code': 2,
                            'station_codes': ['440100'],
                            'location_names': ['广州市'],
                            'success': True,
                            'failed_locations': []
                        }
                    },
                    'time_params': {...},
                    'tool_name': 'get_comparison_report'
                }
        """
        try:
            self.logger.info(f"[MULTI_LEVEL] 开始多层级参数转换")
            self.logger.info(f"[MULTI_LEVEL] 输入层级: {list(grouped_locations.keys())}")
            self.logger.info(f"[MULTI_LEVEL] 工具名称: {tool_name}")
            
            result = {
                'levels': {},
                'time_params': {},
                'tool_name': tool_name,
                'status': 'success',
                'errors': [],
                'warnings': []
            }
            
            # 1. 处理每个层级的地理位置转换
            levels_data = {}
            total_successful_levels = 0
            
            for level, locations in grouped_locations.items():
                self.logger.info(f"[MULTI_LEVEL] 处理层级: {level}, 位置: {locations}")
                
                # 获取层级对应的区域类型编码
                area_type_code = self._get_area_type_code(level)
                if area_type_code is None:
                    self.logger.error(f"[MULTI_LEVEL] 未知的区域层级: {level}")
                    result['warnings'].append(f"跳过未知层级: {level}")
                    continue
                
                # 获取对应的映射字典
                mapping_dict = self._get_mapping_dict(level)
                if not mapping_dict:
                    self.logger.warning(f"[MULTI_LEVEL] 层级 {level} 的映射表为空")
                    result['warnings'].append(f"层级 {level} 无可用映射数据")
                    continue
                
                # 转换地理位置为编码
                codes, failed_locations = self._convert_locations_to_codes_internal(locations, mapping_dict)
                
                # 构建层级数据
                level_data = {
                    'area_type_code': area_type_code,
                    'station_codes': codes,
                    'location_names': locations,
                    'success': len(codes) > 0,
                    'failed_locations': failed_locations,
                    'total_requested': len(locations),
                    'total_converted': len(codes)
                }
                
                levels_data[level] = level_data
                
                if level_data['success']:
                    total_successful_levels += 1
                    self.logger.info(f"[MULTI_LEVEL] 层级 {level} 转换成功: {len(codes)}/{len(locations)}")
                else:
                    self.logger.warning(f"[MULTI_LEVEL] 层级 {level} 转换失败: 所有位置都无法匹配")
                    result['warnings'].append(f"层级 {level} 中所有位置都无法匹配到编码")
            
            result['levels'] = levels_data
            
            # 检查是否有成功的层级
            if total_successful_levels == 0:
                result['status'] = 'error'
                result['errors'].append("所有层级的地理位置转换都失败")
                self.logger.error("[MULTI_LEVEL] 所有层级转换失败")
                return result
            
            # 2. 处理时间参数（使用统一兜底机制）
            processed_time_params = self._process_time_params_with_fallback(time_params, tool_name)
            
            # 检查时间处理结果
            if processed_time_params.get('status') == 'error':
                result['status'] = 'error'
                result['action'] = 'route_to_sql'
                result['errors'].extend(processed_time_params.get('errors', []))
                result['reason'] = f"时间参数处理失败: {'; '.join(processed_time_params.get('errors', []))}"
                self.logger.error(f"[MULTI_LEVEL] 时间参数处理失败，建议转SQL")
                return result
            
            result['time_params'] = processed_time_params
            
            # 3. 设置最终状态
            if result['warnings'] and not result['errors']:
                result['status'] = 'warning'
            
            self.logger.info(f"[MULTI_LEVEL] 多层级转换完成 - 成功层级: {total_successful_levels}/{len(grouped_locations)}")
            return result
            
        except Exception as e:
            self.logger.error(f"[MULTI_LEVEL] 多层级参数转换异常: {e}")
            return {
                'levels': {},
                'time_params': {},
                'tool_name': tool_name,
                'status': 'error',
                'errors': [f"多层级转换异常: {str(e)}"],
                'warnings': []
            }
    
    def _process_time_params_with_fallback(self, time_params: Dict[str, Any], 
                                          tool_name: str) -> Dict[str, Any]:
        """
        处理时间参数，集成统一兜底机制
        
        Args:
            time_params: 时间参数字典
            tool_name: 工具名称
            
        Returns:
            Dict: 处理结果
        """
        try:
            result = {}
            errors = []
            
            # 双格式兼容处理：同时支持中间格式和API格式
            adapted_time_params = dict(time_params)  # 创建副本避免修改原始数据
            
            # 格式适配：确保始终使用中间格式进行处理
            # API格式 -> 中间格式的转换
            if 'TimePoint' in adapted_time_params and 'time_description' not in adapted_time_params:
                adapted_time_params['time_description'] = adapted_time_params['TimePoint']
                self.logger.info(f"[DUAL_FORMAT] 兼容API格式: TimePoint -> time_description")
            
            if 'ContrastTime' in adapted_time_params and 'comparison_time_description' not in adapted_time_params:
                adapted_time_params['comparison_time_description'] = adapted_time_params['ContrastTime']
                self.logger.info(f"[DUAL_FORMAT] 兼容API格式: ContrastTime -> comparison_time_description")
            
            # 反向兼容：中间格式 -> API格式的标记（用于最终输出）
            has_api_format = 'TimePoint' in time_params or 'ContrastTime' in time_params
            
            # 使用适配后的参数继续处理
            time_params = adapted_time_params
            
            # 处理主时间参数
            main_time_desc = time_params.get('time_description', '')
            if main_time_desc:
                # 检查是否已经是API格式的时间数组
                if isinstance(main_time_desc, list) and len(main_time_desc) == 2:
                    # 已经是API格式，直接使用
                    result['main_time_range'] = main_time_desc
                    self.logger.info(f"[TIME_FALLBACK] 检测到API格式时间，直接使用: {main_time_desc}")
                else:
                    # 需要解析的字符串，调用解析方法
                    time_range, error = self.parse_time_with_unified_fallback(
                        main_time_desc, 
                        question=getattr(self, '_current_question', '')
                    )
                    
                    if time_range:
                        result['main_time_range'] = time_range
                        self.logger.info(f"[TIME_FALLBACK] 主时间解析成功: {time_range}")
                    else:
                        errors.append(f"主时间解析失败: {error}")
                        self.logger.error(f"[TIME_FALLBACK] 主时间解析失败: {error}")
            else:
                errors.append("缺少主时间描述")
            
            # 处理对比时间参数（如果是对比查询）
            if tool_name == 'get_comparison_report':
                contrast_time_desc = time_params.get('comparison_time_description', '')
                if contrast_time_desc:
                    # 检查是否已经是API格式的时间数组
                    if isinstance(contrast_time_desc, list) and len(contrast_time_desc) == 2:
                        # 已经是API格式，直接使用
                        result['contrast_time_range'] = contrast_time_desc
                        self.logger.info(f"[TIME_FALLBACK] 检测到API格式对比时间，直接使用: {contrast_time_desc}")
                    else:
                        # 需要解析的字符串，调用解析方法
                        contrast_time_range, contrast_error = self.parse_time_with_unified_fallback(
                            contrast_time_desc,
                            question=getattr(self, '_current_question', '')
                        )
                        
                        if contrast_time_range:
                            result['contrast_time_range'] = contrast_time_range
                            self.logger.info(f"[TIME_FALLBACK] 对比时间解析成功: {contrast_time_range}")
                        else:
                            errors.append(f"对比时间解析失败: {contrast_error}")
                            self.logger.error(f"[TIME_FALLBACK] 对比时间解析失败: {contrast_error}")
                else:
                    errors.append("对比查询缺少comparison_time_description字段")
            
            # 复制其他时间参数
            result['data_source'] = time_params.get('data_source', '审核实况')
            
            # 确定最终状态
            if errors:
                return {
                    'status': 'error',
                    'errors': errors,
                    **result
                }
            else:
                return {
                    'status': 'success',
                    **result
                }
                
        except Exception as e:
            self.logger.error(f"[TIME_FALLBACK] 时间参数处理异常: {e}")
            return {
                'status': 'error',
                'errors': [f'时间参数处理异常: {str(e)}']
            }
    
    def set_current_question(self, question: str):
        """设置当前查询问题（用于LLM兜底）"""
        self._current_question = question
    
    def _get_area_type_code(self, level: str) -> Optional[int]:
        """
        获取区域层级对应的API编码
        
        Args:
            level: 区域层级名称 ('站点', '区县', '城市')
            
        Returns:
            Optional[int]: API编码，None表示未知层级
        """
        mapping = {
            '站点': 0,
            '区县': 1, 
            '城市': 2
        }
        return mapping.get(level)
    
    def _get_mapping_dict(self, level: str) -> Dict[str, str]:
        """
        获取指定层级的地理位置映射字典
        
        Args:
            level: 区域层级名称
            
        Returns:
            Dict[str, str]: 地理位置到编码的映射字典
        """
        if level == '站点':
            return self.station_mappings
        elif level == '区县':
            return self.district_mappings
        elif level == '城市':
            return self.city_mappings
        else:
            self.logger.warning(f"[MAPPING] 未知的层级类型: {level}")
            return {}
    
    def _convert_locations_to_codes_internal(self, locations: List[str], 
                                           mapping_dict: Dict[str, str]) -> Tuple[List[str], List[str]]:
        """
        内部地理位置编码转换方法
        
        Args:
            locations: 地理位置名称列表
            mapping_dict: 映射字典
            
        Returns:
            Tuple[List[str], List[str]]: (成功转换的编码列表, 失败的位置列表)
        """
        converted_codes = []
        failed_locations = []
        
        for location in locations:
            self.logger.debug(f"[CONVERT] 转换位置: '{location}'")
            
            # 尝试精确匹配
            if location in mapping_dict:
                code = mapping_dict[location]
                converted_codes.append(code)
                self.logger.debug(f"[CONVERT] 精确匹配: '{location}' -> '{code}'")
                continue
            
            # 尝试模糊匹配
            best_match, confidence = self._fuzzy_match_location(location, mapping_dict)
            
            if confidence >= self.fuzzy_match_threshold:
                code = mapping_dict[best_match]
                converted_codes.append(code)
                self.logger.debug(f"[CONVERT] 模糊匹配: '{location}' -> '{best_match}' -> '{code}' (置信度: {confidence}%)")
            else:
                failed_locations.append(location)
                self.logger.warning(f"[CONVERT] 匹配失败: '{location}' (最佳匹配: '{best_match}', 置信度: {confidence}%)")
        
        return converted_codes, failed_locations
    
    def _process_time_params(self, time_params: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        """
        处理时间参数
        
        Args:
            time_params: 原始时间参数
            tool_name: API工具名称
            
        Returns:
            Dict[str, Any]: 处理后的时间参数
        """
        processed = {}
        
        # 处理主时间范围
        time_description = time_params.get('time_description')
        if time_description:
            time_point, time_type = self._parse_time_description(time_description)
            processed['time_description'] = time_point
            processed['time_type'] = time_type
        
        # 处理对比时间范围（仅对比查询需要）
        if tool_name == 'get_comparison_report':
            comparison_time = time_params.get('comparison_time_description')
            if comparison_time:
                comparison_time_point, _ = self._parse_time_description(comparison_time)
                processed['comparison_time_description'] = comparison_time_point
        
        # 处理数据源
        data_source = time_params.get('data_source', '审核实况')
        processed['data_source'] = self._convert_data_source(data_source)
        
        return processed
    
    def _parse_time_description(self, time_description: str) -> Tuple[List[str], int]:
        """
        解析时间描述为API格式
        
        Args:
            time_description: 时间描述字符串
            
        Returns:
            Tuple[List[str], int]: (时间点数组, 时间类型编码)
        """
        try:
            # 使用现有的时间解析方法
            time_point, time_type_str = self.parse_time_description(time_description)
            time_type = 8  # 默认为任意时间类型
            
            if time_point:
                return time_point, time_type
            else:
                return [], time_type
            
        except Exception as e:
            self.logger.error(f"[PARSE_TIME] 时间解析异常: {e}")
            # 返回默认值
            return [], 8
    
    def _convert_data_source(self, data_source: str) -> int:
        """
        转换数据源为API编码
        
        Args:
            data_source: 数据源名称
            
        Returns:
            int: API数据源编码
        """
        mapping = {
            '原始实况': 0,
            '审核实况': 1,
            '原始标况': 2,
            '审核标况': 3
        }
        
        return mapping.get(data_source, 1)  # 默认为审核实况
    
    def _extract_time_keywords(self, user_query: str) -> Optional[str]:
        """
        时间提取阶段：从用户查询中提取纯时间关键词（单个时间，向后兼容）
        
        Args:
            user_query: 完整的用户查询文本
            
        Returns:
            Optional[str]: 提取出的纯时间关键词，如果没有提取到则返回None
        """
        # 使用新的多时间参数提取方法，取第一个结果保持向后兼容
        all_time_params = self.extract_all_time_parameters(user_query)
        
        if all_time_params:
            self.logger.info(f"[TIME_EXTRACT] 提取成功: '{user_query}' → '{all_time_params[0]}' (共{len(all_time_params)}个时间参数)")
            return all_time_params[0]
        else:
            self.logger.warning(f"[TIME_EXTRACT] 未能从查询中提取时间关键词: '{user_query}'")
            return None

    def extract_all_time_parameters(self, user_query: str) -> List[str]:
        """
        多时间参数提取：支持复杂性检测的完整时间参数提取
        
        Args:
            user_query: 完整的用户查询文本
            
        Returns:
            List[str]: 去重后的时间参数列表
        """
        try:
            all_matches = []
            
            # 使用配置中的time_patterns进行提取
            time_patterns = self.config.get('parameter_extraction', {}).get('time_patterns', [])
            
            # 调试：检查配置加载
            self.logger.debug(f"[TIME_EXTRACT] 从配置加载了{len(time_patterns)}个时间模式")
            if not time_patterns:
                self.logger.warning(f"[TIME_EXTRACT] 时间模式为空，检查配置文件")
                return []
            
            # 按优先级排序
            sorted_patterns = sorted(
                time_patterns, 
                key=lambda x: x.get('priority', 999)
            )
            
            # 收集所有匹配项及其位置信息
            for pattern_config in sorted_patterns:
                if not pattern_config.get('enabled', True):
                    continue
                    
                pattern = pattern_config.get('pattern', '')
                priority = pattern_config.get('priority', 999)
                description = pattern_config.get('description', '')
                
                if not pattern:
                    continue
                
                try:
                    matches_found = 0
                    for match in re.finditer(pattern, user_query):
                        match_text = match.group(1) if match.groups() else match.group(0)
                        all_matches.append({
                            'text': match_text,
                            'start': match.start(),
                            'end': match.end(),
                            'priority': priority,
                            'description': description
                        })
                        matches_found += 1
                        
                        self.logger.debug(f"[TIME_EXTRACT] 找到匹配: '{match_text}' "
                                        f"(位置{match.start()}-{match.end()}, "
                                        f"优先级{priority}, {description})")
                    
                    if matches_found == 0:
                        self.logger.debug(f"[TIME_EXTRACT] 模式未匹配: '{pattern}' ({description})")
                                        
                except re.error as e:
                    self.logger.warning(f"[TIME_EXTRACT] 正则模式错误: {pattern}, 错误: {e}")
                    continue
            
            # 去除重叠项，保留最佳匹配
            final_matches = self._remove_overlapping_time_matches(all_matches)
            
            # 进一步去重（处理完全相同的文本）
            unique_matches = self._deduplicate_exact_time_matches(final_matches)
            
            self.logger.info(f"[TIME_EXTRACT] 最终提取结果: {unique_matches} ({len(unique_matches)}个参数)")
            
            return unique_matches
            
        except Exception as e:
            self.logger.error(f"[TIME_EXTRACT] 多时间参数提取失败: {e}")
            return []

    def _remove_overlapping_time_matches(self, matches: List[Dict]) -> List[str]:
        """
        移除重叠的时间匹配项
        
        策略：
        1. 按优先级排序（高优先级优先）
        2. 相同优先级时，按长度排序（长文本优先）
        3. 检查位置重叠，保留最佳匹配
        """
        if not matches:
            return []
        
        # 按优先级和长度排序
        matches.sort(key=lambda x: (x['priority'], -len(x['text'])))
        
        final_matches = []
        used_positions = set()
        
        for match in matches:
            # 检查是否与已选择的匹配项重叠
            match_positions = set(range(match['start'], match['end']))
            
            if not match_positions.intersection(used_positions):
                # 无重叠，保留此匹配
                final_matches.append(match['text'])
                used_positions.update(match_positions)
                
                self.logger.debug(f"[TIME_EXTRACT] 保留匹配: '{match['text']}' "
                                f"(优先级{match['priority']}, "
                                f"位置{match['start']}-{match['end']})")
            else:
                # 有重叠，跳过此匹配
                self.logger.debug(f"[TIME_EXTRACT] 跳过重叠: '{match['text']}' "
                                f"(优先级{match['priority']}, "
                                f"位置{match['start']}-{match['end']})")
        
        return final_matches

    def _deduplicate_exact_time_matches(self, matches: List[str]) -> List[str]:
        """
        去除完全相同的匹配项，保持顺序
        """
        seen = set()
        unique_matches = []
        
        for match in matches:
            if match not in seen:
                unique_matches.append(match)
                seen.add(match)
            else:
                self.logger.debug(f"[TIME_EXTRACT] 去除重复: '{match}'")
        
        return unique_matches

    def detect_query_complexity(self, user_query: str) -> Dict[str, Any]:
        """
        检测查询复杂性（基于时间参数数量）
        
        Args:
            user_query: 用户查询文本
            
        Returns:
            Dict: {
                'is_complex': bool,
                'time_param_count': int,  
                'time_parameters': List[str],
                'complexity_reason': str
            }
        """
        try:
            # 提取时间参数
            time_parameters = self.extract_all_time_parameters(user_query)
            param_count = len(time_parameters)
            
            # 复杂性阈值（从配置读取，默认2）
            complexity_config = self.config.get('complexity_detection', {})
            time_complexity = complexity_config.get('time_complexity', {})
            threshold = time_complexity.get('threshold', 2)
            
            # 判断复杂性
            is_complex = param_count >= threshold
            
            if is_complex:
                complexity_reason = f"检测到{param_count}个时间参数（≥{threshold}），判定为复杂查询"
            else:
                complexity_reason = f"检测到{param_count}个时间参数（<{threshold}），判定为简单查询"
            
            result = {
                'is_complex': is_complex,
                'time_param_count': param_count,
                'time_parameters': time_parameters,
                'complexity_reason': complexity_reason
            }
            
            self.logger.info(f"[COMPLEXITY_DETECT] {complexity_reason}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"[COMPLEXITY_DETECT] 复杂性检测失败: {e}")
            return {
                'is_complex': False,
                'time_param_count': 0,
                'time_parameters': [],
                'complexity_reason': f'检测失败: {e}'
            }

    def parse_time_with_unified_fallback(self, user_query: str, question: str = "") -> Tuple[Optional[List[str]], Optional[str]]:
        """
        使用统一兜底机制的时间处理（包含时间提取和解析两个阶段）
        
        处理流程：
        1. 时间提取阶段：从用户查询中提取纯时间关键词
        2. 时间解析阶段：三层解析方法（传统解析、年份补全、LLM兜底）
        
        Args:
            user_query: 完整的用户查询文本
            question: 原始问题（用于LLM上下文）
            
        Returns:
            Tuple[Optional[List[str]], Optional[str]]: (时间范围, 错误信息)
        """
        try:
            self.logger.info(f"[UNIFIED_TIME_PARSE] 开始统一时间处理: {user_query}")
            
            # 第一步：时间提取阶段
            time_keyword = self._extract_time_keywords(user_query)
            if not time_keyword:
                # 没有提取到时间关键词，但可能是纯时间描述，尝试直接解析
                time_keyword = user_query.strip()
                self.logger.info(f"[UNIFIED_TIME_PARSE] 未提取到时间关键词，尝试直接解析: {time_keyword}")
            
            # 第二步：时间解析阶段 - Layer 1 传统解析
            time_range, error_msg = self.parse_time_description(time_keyword)
            if time_range:
                self.logger.info(f"[UNIFIED_TIME_PARSE] 传统解析成功: {time_keyword} -> {time_range}")
                return time_range, None
            
            # Layer 2：智能年份补全
            self.logger.info(f"[UNIFIED_TIME_PARSE] 传统解析失败，尝试年份补全")
            completed_time = self._smart_complete_year(time_keyword)
            if completed_time:
                time_range, error_msg = self.parse_time_description(completed_time)
                if time_range:
                    self.logger.info(f"[UNIFIED_TIME_PARSE] 年份补全成功: {time_keyword} -> {completed_time} -> {time_range}")
                    return time_range, None
            
            # Layer 3失败，返回错误信息给LLM兜底处理
            error_info = f"传统解析失败: {error_msg}, 年份补全失败: {completed_time or '无法补全'}"
            self.logger.warning(f"[UNIFIED_TIME_PARSE] 前两层解析都失败: {error_info}")
            return None, error_info
            
        except Exception as e:
            error_info = f"统一时间处理异常: {str(e)}"
            self.logger.error(f"[UNIFIED_TIME_PARSE] {error_info}")
            return None, error_info
    
    def _smart_complete_year(self, time_desc: str) -> Optional[str]:
        """
        智能年份补全
        
        处理格式如：
        - "2月1日" -> "2025年2月1日"
        - "3月" -> "2025年3月"
        
        Args:
            time_desc: 原始时间描述
            
        Returns:
            Optional[str]: 补全年份后的时间描述
        """
        try:
            current_year = datetime.now().year
            
            # 匹配"月日"格式 (如"2月1日") - 改为搜索而非匹配，支持复杂文本
            month_day_pattern = r'(\d{1,2})月(\d{1,2})日'
            match = re.search(month_day_pattern, time_desc)
            if match:
                month, day = match.groups()
                # 替换原文中的月日为完整年月日
                completed = time_desc.replace(match.group(0), f"{current_year}年{month}月{day}日")
                self.logger.info(f"[YEAR_COMPLETE] 月日格式补全: {time_desc} -> {completed}")
                return completed
            
            # 匹配"月"格式 (如"3月") - 改为搜索，但要避免与月日格式冲突
            month_pattern = r'(\d{1,2})月(?!\d)'  # 负前瞻断言，确保月后面不是数字
            match = re.search(month_pattern, time_desc)
            if match:
                month = match.group(1)
                # 替换原文中的月为完整年月
                completed = time_desc.replace(match.group(0), f"{current_year}年{month}月")
                self.logger.info(f"[YEAR_COMPLETE] 月份格式补全: {time_desc} -> {completed}")
                return completed
            
            # 其他格式暂不处理
            return None
            
        except Exception as e:
            self.logger.error(f"[YEAR_COMPLETE] 年份补全异常: {e}")
            return None


# 全局实例
_param_converter = None

def get_param_converter() -> ParamConverter:
    """获取参数转换器单例"""
    global _param_converter
    if _param_converter is None:
        _param_converter = ParamConverter()
    return _param_converter