#!/usr/bin/env python3
"""
API错误分类器
API Error Classifier

负责分析和分类API调用错误，判断错误是否可通过LLM恢复
"""

import logging
from typing import Dict, Any, List

class APIErrorClassifier:
    """API错误分类器，用于判断错误是否可恢复"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def classify_api_error(self, 
                          http_status: int,
                          error_response: Dict[str, Any],
                          api_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        分类API错误类型
        
        Args:
            http_status: HTTP状态码
            error_response: 错误响应内容
            api_params: API调用参数
            
        Returns:
            {
                'category': '错误类别',
                'recoverable': bool,  # 是否可通过LLM恢复
                'suggested_action': '建议动作',
                'confidence': 0.8,
                'analysis_details': {...}
            }
        """
        self.logger.debug(f"[API_ERROR_CLASSIFIER] 开始分类API错误: HTTP {http_status}")
        
        try:
            # HTTP 500 错误处理
            if http_status == 500:
                return self._classify_500_error(error_response, api_params)
            
            # HTTP 400 错误 - 通常是参数问题
            elif http_status == 400:
                return self._classify_400_error(error_response, api_params)
            
            # HTTP 401/403 错误 - 认证问题
            elif http_status in [401, 403]:
                return self._classify_auth_error(http_status, error_response)
            
            # HTTP 404 错误 - 资源不存在
            elif http_status == 404:
                return self._classify_404_error(error_response, api_params)
            
            # HTTP 502/503/504 错误 - 服务器问题
            elif http_status in [502, 503, 504]:
                return self._classify_server_error(http_status, error_response)
            
            # 其他错误
            else:
                return self._classify_unknown_error(http_status, error_response)
                
        except Exception as e:
            self.logger.error(f"[API_ERROR_CLASSIFIER] 错误分类异常: {e}")
            return {
                'category': 'classification_error',
                'recoverable': False,
                'suggested_action': 'route_to_sql',
                'confidence': 0.5,
                'analysis_details': {'error': str(e)}
            }
    
    def _classify_500_error(self, error_response: Dict[str, Any], 
                           api_params: Dict[str, Any]) -> Dict[str, Any]:
        """分类HTTP 500错误"""
        
        # 检查是否是参数问题导致的500错误
        parameter_issues = self._analyze_parameter_issues(api_params)
        
        if parameter_issues['has_issues']:
            self.logger.info(f"[API_ERROR_CLASSIFIER] HTTP 500识别为参数问题: {parameter_issues['issues']}")
            return {
                'category': 'parameter_error_500',
                'recoverable': True,
                'suggested_action': 'llm_parameter_adjustment',
                'confidence': 0.8,
                'analysis_details': {
                    'parameter_issues': parameter_issues,
                    'error_response': error_response
                }
            }
        
        # 检查错误消息中的参数相关关键词
        error_msg = str(error_response.get('msg', '')).lower()
        parameter_keywords = [
            'parameter', 'invalid', 'missing', 'required', 
            'timepoint', 'stationcode', 'contrasttime',
            'validation', 'format', 'range'
        ]
        
        matched_keywords = [kw for kw in parameter_keywords if kw in error_msg]
        if matched_keywords:
            self.logger.info(f"[API_ERROR_CLASSIFIER] HTTP 500错误消息包含参数关键词: {matched_keywords}")
            return {
                'category': 'parameter_validation_error',
                'recoverable': True,
                'suggested_action': 'llm_parameter_correction',
                'confidence': 0.7,
                'analysis_details': {
                    'matched_keywords': matched_keywords,
                    'error_message': error_msg
                }
            }
        
        # 其他500错误，可能是服务器内部问题
        self.logger.info(f"[API_ERROR_CLASSIFIER] HTTP 500识别为服务器内部错误")
        return {
            'category': 'server_internal_error',
            'recoverable': False,
            'suggested_action': 'route_to_sql',
            'confidence': 0.9,
            'analysis_details': {
                'error_response': error_response,
                'reason': '服务器内部错误，无参数相关问题'
            }
        }
    
    def _classify_400_error(self, error_response: Dict[str, Any], 
                           api_params: Dict[str, Any]) -> Dict[str, Any]:
        """分类HTTP 400错误"""
        
        self.logger.info(f"[API_ERROR_CLASSIFIER] HTTP 400识别为请求参数错误")
        
        parameter_issues = self._analyze_parameter_issues(api_params)
        
        return {
            'category': 'bad_request',
            'recoverable': True,
            'suggested_action': 'llm_parameter_correction',
            'confidence': 0.9,
            'analysis_details': {
                'parameter_issues': parameter_issues,
                'error_response': error_response
            }
        }
    
    def _classify_auth_error(self, http_status: int, 
                            error_response: Dict[str, Any]) -> Dict[str, Any]:
        """分类认证错误"""
        
        self.logger.info(f"[API_ERROR_CLASSIFIER] HTTP {http_status}识别为认证错误")
        
        return {
            'category': 'authentication_error',
            'recoverable': False,
            'suggested_action': 'route_to_sql',
            'confidence': 1.0,
            'analysis_details': {
                'http_status': http_status,
                'error_response': error_response,
                'reason': '认证问题，需要系统级修复'
            }
        }
    
    def _classify_404_error(self, error_response: Dict[str, Any], 
                           api_params: Dict[str, Any]) -> Dict[str, Any]:
        """分类HTTP 404错误"""
        
        self.logger.info(f"[API_ERROR_CLASSIFIER] HTTP 404识别为资源不存在")
        
        return {
            'category': 'resource_not_found',
            'recoverable': True,
            'suggested_action': 'llm_parameter_adjustment',
            'confidence': 0.6,
            'analysis_details': {
                'error_response': error_response,
                'api_params': api_params,
                'reason': '可能是参数导致的资源不存在'
            }
        }
    
    def _classify_server_error(self, http_status: int, 
                              error_response: Dict[str, Any]) -> Dict[str, Any]:
        """分类服务器错误"""
        
        self.logger.info(f"[API_ERROR_CLASSIFIER] HTTP {http_status}识别为服务器错误")
        
        return {
            'category': 'server_error',
            'recoverable': False,
            'suggested_action': 'route_to_sql',
            'confidence': 0.9,
            'analysis_details': {
                'http_status': http_status,
                'error_response': error_response,
                'reason': '服务器问题，需要等待修复'
            }
        }
    
    def _classify_unknown_error(self, http_status: int, 
                               error_response: Dict[str, Any]) -> Dict[str, Any]:
        """分类未知错误"""
        
        self.logger.info(f"[API_ERROR_CLASSIFIER] HTTP {http_status}识别为未知错误")
        
        return {
            'category': 'unknown_error',
            'recoverable': False,
            'suggested_action': 'route_to_sql',
            'confidence': 0.7,
            'analysis_details': {
                'http_status': http_status,
                'error_response': error_response,
                'reason': '未知错误类型'
            }
        }
    
    def _analyze_parameter_issues(self, api_params: Dict[str, Any]) -> Dict[str, Any]:
        """分析API参数问题"""
        issues = []
        has_issues = False
        
        # 检查TimePoint是否为空
        time_point = api_params.get('TimePoint', [])
        if not time_point or (isinstance(time_point, list) and len(time_point) == 0):
            issues.append('TimePoint为空')
            has_issues = True
        elif isinstance(time_point, list):
            # 检查时间格式
            for tp in time_point:
                if not isinstance(tp, str) or not tp.strip():
                    issues.append('TimePoint包含无效时间格式')
                    has_issues = True
                    break
        
        # 检查ContrastTime是否为空（对比查询）
        contrast_time = api_params.get('ContrastTime')
        if contrast_time is not None:
            if isinstance(contrast_time, list) and len(contrast_time) == 0:
                issues.append('ContrastTime为空数组')
                has_issues = True
            elif not contrast_time:
                issues.append('ContrastTime为空')
                has_issues = True
        
        # 检查StationCode是否有效
        station_codes = api_params.get('StationCode', [])
        if not station_codes:
            issues.append('StationCode为空')
            has_issues = True
        elif isinstance(station_codes, list):
            for code in station_codes:
                if not isinstance(code, str) or not code.strip():
                    issues.append('StationCode包含无效编码')
                    has_issues = True
                    break
        
        # 检查AreaType是否有效
        area_type = api_params.get('AreaType')
        if area_type is None:
            issues.append('AreaType未指定')
            has_issues = True
        elif not isinstance(area_type, int) or area_type not in [0, 1, 2]:
            issues.append('AreaType值无效')
            has_issues = True
        
        # 检查TimeType是否有效
        time_type = api_params.get('TimeType')
        if time_type is None:
            issues.append('TimeType未指定')
            has_issues = True
        elif not isinstance(time_type, int):
            issues.append('TimeType值无效')
            has_issues = True
        elif time_type not in [3, 4, 5, 7, 8]:
            issues.append(f'TimeType值超出范围: {time_type}')
            has_issues = True
        elif time_type in [3, 4, 5, 7]:
            # 特殊报表类型可能存在兼容性问题
            issues.append(f'TimeType={time_type}可能存在兼容性问题，建议使用8（任意时间）')
            has_issues = True
        
        return {
            'has_issues': has_issues,
            'issues': issues,
            'total_issues': len(issues)
        }
    
    def is_recoverable_error(self, error_classification: Dict[str, Any]) -> bool:
        """判断错误是否可恢复"""
        return error_classification.get('recoverable', False)
    
    def get_recovery_priority(self, error_classification: Dict[str, Any]) -> int:
        """获取错误恢复优先级（数字越小优先级越高）"""
        category = error_classification.get('category', '')
        confidence = error_classification.get('confidence', 0)
        
        # 基础优先级
        base_priority = {
            'parameter_error_500': 1,
            'parameter_validation_error': 2,
            'bad_request': 3,
            'resource_not_found': 4,
            'unknown_error': 9
        }.get(category, 8)
        
        # 根据置信度调整优先级
        if confidence >= 0.8:
            priority_adjustment = 0
        elif confidence >= 0.6:
            priority_adjustment = 1
        else:
            priority_adjustment = 2
        
        return base_priority + priority_adjustment

# 全局单例
_api_error_classifier = None

def get_api_error_classifier() -> APIErrorClassifier:
    """获取API错误分类器单例"""
    global _api_error_classifier
    if _api_error_classifier is None:
        _api_error_classifier = APIErrorClassifier()
    return _api_error_classifier