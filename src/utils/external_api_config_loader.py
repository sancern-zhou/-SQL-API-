#!/usr/bin/env python3
"""
外部API配置加载器
External API Configuration Loader
"""
import os
import yaml
import json
import logging
from typing import Dict, Any


class ExternalAPIConfigLoader:
    """外部API配置加载器"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or self._get_default_config_path()
        self.logger = logging.getLogger(__name__)
        self._config = None
        self._mock_data = None
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        return os.path.join(
            os.path.dirname(__file__), 
            '..', '..', 'config', 'external_api_config.yaml'
        )
    
    def load_config(self) -> Dict[str, Any]:
        """
        加载外部API配置
        
        Returns:
            外部API配置字典
        """
        if self._config is None:
            try:
                if os.path.exists(self.config_path):
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                    self._config = config.get('external_api', {})
                    
                    # 支持环境变量覆盖
                    self._apply_env_overrides()
                    
                    self.logger.info(f"外部API配置加载成功: {self.config_path}")
                else:
                    self.logger.warning(f"配置文件不存在: {self.config_path}，使用默认配置")
                    self._config = self._get_default_config()
            except Exception as e:
                self.logger.error(f"外部API配置加载失败: {e}，使用默认配置")
                self._config = self._get_default_config()
        
        return self._config
    
    def _apply_env_overrides(self):
        """应用环境变量覆盖"""
        env_mappings = {
            'EXTERNAL_API_USERNAME': ['username'],
            'EXTERNAL_API_PASSWORD': ['password'],
            'EXTERNAL_API_BASE_URL': ['base_url'],
            'EXTERNAL_API_TEST_MODE': ['test_mode']
        }
        
        for env_var, config_path in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                if env_var == 'EXTERNAL_API_TEST_MODE':
                    # 布尔值处理
                    env_value = env_value.lower() in ('true', '1', 'yes', 'on')
                
                # 设置配置值
                current = self._config
                for key in config_path[:-1]:
                    current = current.setdefault(key, {})
                current[config_path[-1]] = env_value
                
                self.logger.info(f"使用环境变量 {env_var} 覆盖配置")
    
    def load_mock_data(self) -> Dict[str, Any]:
        """
        加载模拟数据
        
        Returns:
            模拟数据字典
        """
        if self._mock_data is None:
            config = self.load_config()
            mock_file = config.get('mock_data_file', 'external_api_mock_data.json')
            
            # 构建模拟数据文件路径
            config_dir = os.path.dirname(self.config_path)
            mock_path = os.path.join(config_dir, mock_file)
            
            try:
                if os.path.exists(mock_path):
                    with open(mock_path, 'r', encoding='utf-8') as f:
                        self._mock_data = json.load(f)
                    self.logger.info(f"模拟数据加载成功: {mock_path}")
                else:
                    self.logger.warning(f"模拟数据文件不存在: {mock_path}，使用默认数据")
                    self._mock_data = self._get_default_mock_data()
            except Exception as e:
                self.logger.error(f"模拟数据加载失败: {e}，使用默认数据")
                self._mock_data = self._get_default_mock_data()
        
        return self._mock_data
    
    def _get_default_config(self) -> Dict[str, Any]:
        """
        获取默认配置
        
        Returns:
            默认配置字典
        """
        return {
            "base_url": "http://10.10.10.131:28001",
            "sys_code": "SunAirProvince",
            "username": "ScGuanLy",
            "password": "Suncere$0717",
            "endpoints": {
                "token": "/api/airprovinceproduct/AirCityBaseCommon/GetExternalApiToken",
                "summary_report": "/api/airprovinceproduct/dataanalysis/ReportDataQuery/GetReportForRangePagedListAsync",
                "comparison_report": "/api/airprovinceproduct/dataanalysis/ReportDataQuery/GetReportForRangeCompareListAsync"
            },
            "timeout": 30,
            "token_cache_time": 1800,
            "test_mode": False,
            "mock_data_file": "external_api_mock_data.json"
        }
    
    def _get_default_mock_data(self) -> Dict[str, Any]:
        """
        获取默认模拟数据
        
        Returns:
            默认模拟数据字典
        """
        return {
            "stations": [],
            "detection_items": [],
            "instruments": []
        }
    
    def get_endpoint_url(self, endpoint_name: str) -> str:
        """
        获取完整的端点URL
        
        Args:
            endpoint_name: 端点名称
            
        Returns:
            完整的URL
        """
        config = self.load_config()
        base_url = config.get('base_url', '')
        endpoints = config.get('endpoints', {})
        endpoint = endpoints.get(endpoint_name, '')
        
        return f"{base_url.rstrip('/')}{endpoint}"
    
    def is_test_mode(self) -> bool:
        """
        检查是否为测试模式
        
        Returns:
            是否为测试模式
        """
        config = self.load_config()
        return config.get('test_mode', False)
    
    def reload_config(self):
        """重新加载配置"""
        self._config = None
        self._mock_data = None
        self.logger.info("配置已重置，下次访问时将重新加载")


# 单例模式
_config_loader = None

def get_external_api_config_loader() -> ExternalAPIConfigLoader:
    """获取外部API配置加载器单例"""
    global _config_loader
    if _config_loader is None:
        _config_loader = ExternalAPIConfigLoader()
    return _config_loader

def get_external_api_config() -> Dict[str, Any]:
    """获取外部API配置"""
    loader = get_external_api_config_loader()
    return loader.load_config()

def get_external_api_mock_data() -> Dict[str, Any]:
    """获取外部API模拟数据"""
    loader = get_external_api_config_loader()
    return loader.load_mock_data()

def is_test_mode() -> bool:
    """检查是否为测试模式"""
    loader = get_external_api_config_loader()
    return loader.is_test_mode()

def get_endpoint_url(endpoint_name: str) -> str:
    """获取完整的端点URL"""
    loader = get_external_api_config_loader()
    return loader.get_endpoint_url(endpoint_name)

def reload_external_api_config():
    """重新加载外部API配置"""
    loader = get_external_api_config_loader()
    loader.reload_config()