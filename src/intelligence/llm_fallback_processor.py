#!/usr/bin/env python3
"""
LLM托底专用处理模块
LLM Fallback Processor

专门处理所有LLM托底场景，与传统流程完全隔离：
- LLM参数解析和验证
- 地理位置编码转换
- API参数组装
- 接口调用和结果处理
- 失败时直接转SQL
"""

import logging
import os
from typing import Dict, Any, List, Optional, Tuple
import json
import re

class LLMFallbackProcessor:
    """LLM托底专用处理器 - 完全独立的处理流程"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("[LLM_FALLBACK_PROCESSOR] 初始化LLM托底处理器")
    
    def _determine_time_type_from_query(self, question: str) -> int:
        """根据用户查询智能选择TimeType
        
        Args:
            question (str): 用户查询问题
            
        Returns:
            int: TimeType值 (3=周报, 4=月报, 5=季报, 7=年报, 8=任意时间)
        """
        if not question:
            return 8  # 默认任意时间
        
        # 检查是否包含报表类型关键词
        if re.search(r'周报|每周报|周[度期]报', question, re.IGNORECASE):
            self.logger.info(f"[LLM_FALLBACK] 检测到周报需求，设置TimeType=3")
            return 3  # 周报
        elif re.search(r'月报|每月报|月[度期]报', question, re.IGNORECASE):
            self.logger.info(f"[LLM_FALLBACK] 检测到月报需求，设置TimeType=4")
            return 4  # 月报
        elif re.search(r'季报|每季报|季[度期]报', question, re.IGNORECASE):
            self.logger.info(f"[LLM_FALLBACK] 检测到季报需求，设置TimeType=5")
            return 5  # 季报
        elif re.search(r'年报|每年报|年[度期]报', question, re.IGNORECASE):
            self.logger.info(f"[LLM_FALLBACK] 检测到年报需求，设置TimeType=7")
            return 7  # 年报
        else:
            # 默认任意时间，适用于大多数查询
            return 8
        
    def process_llm_fallback_result(self, llm_params: Dict[str, Any], question: str, tool_name: str) -> Dict[str, Any]:
        """
        处理LLM托底结果的完整流程
        
        Args:
            llm_params: LLM生成的参数
            question: 用户原始问题  
            tool_name: 工具名称
            
        Returns:
            Dict: 处理结果 (成功返回API结果，失败返回转SQL指令)
        """
        try:
            self.logger.info(f"[LLM_FALLBACK] 开始处理LLM托底结果: {tool_name}")
            self.logger.debug(f"[LLM_FALLBACK] LLM参数: {llm_params}")
            
            # 1. 参数验证和预处理
            validated_params = self._validate_and_preprocess_params(llm_params, tool_name, question)
            if not validated_params['valid']:
                return self._route_to_sql(question, f"LLM参数验证失败: {validated_params['errors']}")
            
            # 2. 地理位置编码转换
            geo_result = self._convert_locations_to_codes(validated_params['locations'], validated_params['area_type'])
            if not geo_result['success']:
                return self._route_to_sql(question, f"地理位置编码转换失败: {geo_result['error']}")
            
            # 3. 组装API参数
            api_params = self._assemble_api_params(validated_params, geo_result)
            
            # 4. 执行API调用
            api_result = self._execute_api_call(api_params, tool_name)
            if api_result['success']:
                self.logger.info("[LLM_FALLBACK] API调用成功，返回结果")
                return {
                    "status": "success",
                    "response_type": "data", 
                    "payload": {
                        "format": "json",
                        "value": api_result['data']
                    },
                    "debug_info": {
                        "execution_path": "LLM_FALLBACK_PROCESSOR",
                        "tool_name": tool_name,
                        "processing_method": "llm_fallback_dedicated",
                        "api_params": api_params
                    }
                }
            else:
                self.logger.warning(f"[LLM_FALLBACK] API调用失败: {api_result['error']}")
                return self._route_to_sql(question, f"LLM托底API调用失败: {api_result['error']}")
                
        except Exception as e:
            self.logger.error(f"[LLM_FALLBACK] 处理异常: {e}")
            return self._route_to_sql(question, f"LLM托底处理异常: {str(e)}")
    
    def _validate_and_preprocess_params(self, llm_params: Dict[str, Any], tool_name: str, question: str = "") -> Dict[str, Any]:
        """验证和预处理LLM参数"""
        try:
            self.logger.info("[LLM_FALLBACK] 开始参数验证和预处理")
            
            errors = []
            result = {
                'valid': True,
                'errors': [],
                'time_point': None,
                'contrast_time': None,
                'locations': [],
                'area_type': '',
                'time_type': 8,
                'data_source': 1
            }
            
            # 验证时间参数
            if 'TimePoint' in llm_params:
                time_point = llm_params['TimePoint']
                if isinstance(time_point, list) and len(time_point) == 2:
                    result['time_point'] = time_point
                else:
                    errors.append("TimePoint格式错误，需要2元素时间数组")
            else:
                errors.append("缺少TimePoint时间参数")
            
            # 对比查询验证对比时间
            if tool_name == 'get_comparison_report':
                if 'ContrastTime' in llm_params:
                    contrast_time = llm_params['ContrastTime']
                    if isinstance(contrast_time, list) and len(contrast_time) == 2:
                        result['contrast_time'] = contrast_time
                    else:
                        errors.append("ContrastTime格式错误，需要2元素时间数组")
                else:
                    errors.append("对比查询缺少ContrastTime参数")
            
            # 验证地理位置
            if 'locations' in llm_params:
                locations = llm_params['locations']
                if isinstance(locations, list) and locations:
                    result['locations'] = locations
                else:
                    errors.append("locations格式错误或为空")
            else:
                errors.append("缺少locations地理位置参数")
            
            # 验证区域类型
            if 'area_type' in llm_params:
                area_type = llm_params['area_type']
                if area_type in ['站点', '区县', '城市']:
                    result['area_type'] = area_type
                else:
                    errors.append(f"area_type值错误: {area_type}")
            else:
                errors.append("缺少area_type区域类型参数")
            
            # 智能选择TimeType：优先使用LLM指定值，否则根据查询内容智能判断
            time_type = llm_params.get('TimeType')
            if time_type is None:
                time_type = self._determine_time_type_from_query(question)
                self.logger.info(f"[LLM_FALLBACK] LLM未指定TimeType，根据查询智能选择: {time_type}")
            else:
                self.logger.info(f"[LLM_FALLBACK] 使用LLM指定的TimeType: {time_type}")
            
            # 设置可选参数
            result['time_type'] = time_type
            result['data_source'] = llm_params.get('DataSource', 1)
            
            if errors:
                result['valid'] = False
                result['errors'] = errors
                self.logger.error(f"[LLM_FALLBACK] 参数验证失败: {errors}")
            else:
                self.logger.info("[LLM_FALLBACK] 参数验证成功")
                
            return result
            
        except Exception as e:
            self.logger.error(f"[LLM_FALLBACK] 参数验证异常: {e}")
            return {'valid': False, 'errors': [f'参数验证异常: {str(e)}']}
    
    def _convert_locations_to_codes(self, locations: List[str], area_type: str) -> Dict[str, Any]:
        """地理位置编码转换"""
        try:
            self.logger.info(f"[LLM_FALLBACK] 开始地理位置编码转换: {locations}, 类型: {area_type}")
            
            # 使用现有的参数转换器
            from ..utils.param_converter import get_param_converter
            param_converter = get_param_converter()
            
            # 调用现有的地理位置编码转换方法
            converted_codes, failed_locations = param_converter.convert_locations_to_codes(locations, area_type)
            
            if not converted_codes:
                return {
                    'success': False,
                    'error': f'所有地理位置都无法转换为编码: {locations}, 失败列表: {failed_locations}',
                    'codes': [],
                    'area_type_code': None
                }
            
            # 转换区域类型为编码
            area_type_code = self._get_area_type_code(area_type)
            
            # 记录转换结果
            self.logger.info(f"[LLM_FALLBACK] 地理位置编码转换成功: {len(converted_codes)}/{len(locations)}")
            if failed_locations:
                self.logger.warning(f"[LLM_FALLBACK] 部分位置转换失败: {failed_locations}")
            
            return {
                'success': True,
                'codes': converted_codes,
                'area_type_code': area_type_code,
                'error': None
            }
            
        except Exception as e:
            self.logger.error(f"[LLM_FALLBACK] 地理位置编码转换异常: {e}")
            return {
                'success': False,
                'error': f'地理位置编码转换异常: {str(e)}',
                'codes': [],
                'area_type_code': None
            }
    
    def _get_area_type_code(self, area_type: str) -> int:
        """获取区域类型编码"""
        area_type_map = {
            '站点': 0,
            '区县': 1, 
            '城市': 2
        }
        return area_type_map.get(area_type, 1)  # 默认区县
    
    def _assemble_api_params(self, validated_params: Dict[str, Any], geo_result: Dict[str, Any]) -> Dict[str, Any]:
        """组装API参数"""
        api_params = {
            'TimePoint': validated_params['time_point'],
            'StationCode': geo_result['codes'],
            'AreaType': geo_result['area_type_code'],
            'TimeType': validated_params['time_type'],
            'DataSource': validated_params['data_source']
        }
        
        # 对比查询添加对比时间
        if validated_params['contrast_time']:
            api_params['ContrastTime'] = validated_params['contrast_time']
        
        self.logger.info(f"[LLM_FALLBACK] API参数组装完成: {api_params}")
        return api_params
    
    def _execute_api_call(self, api_params: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        """执行API调用"""
        try:
            self.logger.info(f"[LLM_FALLBACK] 开始API调用: {tool_name}")
            
            # 获取API端点配置
            endpoint = self._get_api_endpoint(tool_name)
            if not endpoint:
                return {
                    'success': False,
                    'error': f'未找到工具{tool_name}的API端点配置',
                    'data': None
                }
            
            # 调用外部API处理器的API调用方法
            from ..external_api_handler import ExternalAPIHandler
            api_handler = ExternalAPIHandler()
            
            # 直接调用API
            response = api_handler._call_api_directly(endpoint, api_params)
            
            if response.get('success'):
                return {
                    'success': True,
                    'data': response['data'],
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'error': response.get('error', '未知API错误'),
                    'data': None
                }
                
        except Exception as e:
            self.logger.error(f"[LLM_FALLBACK] API调用异常: {e}")
            return {
                'success': False,
                'error': f'API调用异常: {str(e)}',
                'data': None
            }
    
    def _get_api_endpoint(self, tool_name: str) -> Optional[str]:
        """获取API端点"""
        try:
            from ..utils.external_api_config_loader import get_external_api_config
            config = get_external_api_config()
            
            endpoint_map = {
                'get_summary_report': config['endpoints']['summary_report'],
                'get_comparison_report': config['endpoints']['comparison_report']
            }
            
            return endpoint_map.get(tool_name)
            
        except Exception as e:
            self.logger.error(f"[LLM_FALLBACK] 获取API端点失败: {e}")
            return None
    
    def _route_to_sql(self, question: str, reason: str) -> Dict[str, Any]:
        """转向SQL查询"""
        self.logger.info(f"[LLM_FALLBACK] 转向SQL查询: {reason}")
        return {
            'status': 'route_to_sql',
            'question': question,
            'reason': reason,
            'execution_path': 'LLM_FALLBACK_TO_SQL'
        }


def get_llm_fallback_processor():
    """获取LLM托底处理器实例"""
    if not hasattr(get_llm_fallback_processor, '_instance'):
        get_llm_fallback_processor._instance = LLMFallbackProcessor()
    return get_llm_fallback_processor._instance