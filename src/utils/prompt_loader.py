#!/usr/bin/env python3
"""
LLM提示词加载器
用于统一管理和加载系统中的所有LLM提示词模板
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class PromptLoader:
    """LLM提示词加载器"""
    
    def __init__(self):
        self.prompts = {}
        self.config_dir = None
        self._load_prompts()
    
    def _load_prompts(self):
        """从配置文件夹加载所有提示词配置文件"""
        try:
            # 构建配置文件夹路径
            current_dir = os.path.dirname(__file__)
            self.config_dir = os.path.join(current_dir, '..', '..', 'config')
            
            # 配置文件映射
            config_files = {
                'external_api_handler': 'external_api_prompts.yaml',
                'sql_generator': 'sql_prompts.yaml'
            }
            
            loaded_count = 0
            for module_name, config_file in config_files.items():
                config_path = os.path.join(self.config_dir, config_file)
                
                if os.path.exists(config_path):
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            module_prompts = yaml.safe_load(f)
                        
                        self.prompts[module_name] = module_prompts
                        loaded_count += 1
                        logger.debug(f"成功加载模块 {module_name} 的提示词配置: {config_file}")
                    
                    except Exception as e:
                        logger.error(f"加载模块 {module_name} 配置文件失败 {config_file}: {e}")
                        self.prompts[module_name] = {}
                else:
                    logger.warning(f"配置文件不存在: {config_path}")
                    self.prompts[module_name] = {}
            
            logger.info(f"LLM提示词配置加载完成，成功加载 {loaded_count}/{len(config_files)} 个模块")
        
        except Exception as e:
            logger.error(f"加载LLM提示词配置失败: {e}")
            self.prompts = {}
    
    def get_prompt(self, module: str, prompt_name: str, **kwargs) -> str:
        """
        获取指定的提示词模板并进行变量替换
        
        Args:
            module: 模块名称 (如 'external_api_handler', 'llm_error_recovery')
            prompt_name: 提示词名称 (如 'parameter_conversion_failure', 'time_clarification')
            **kwargs: 模板变量的值
        
        Returns:
            str: 格式化后的提示词
        """
        try:
            # 获取提示词模板
            if module not in self.prompts:
                logger.error(f"未找到模块 '{module}' 的提示词配置")
                return self._get_fallback_prompt(module, prompt_name)
            
            module_prompts = self.prompts[module]
            if prompt_name not in module_prompts:
                logger.error(f"未找到模块 '{module}' 中的提示词 '{prompt_name}'")
                return self._get_fallback_prompt(module, prompt_name)
            
            prompt_template = module_prompts[prompt_name]
            
            # 进行变量替换
            if kwargs:
                try:
                    formatted_prompt = prompt_template.format(**kwargs)
                    logger.debug(f"成功格式化提示词: {module}.{prompt_name}")
                    return formatted_prompt
                except KeyError as e:
                    logger.warning(f"提示词模板变量缺失: {e}, 模块: {module}, 提示词: {prompt_name}")
                    # 返回原始模板，让调用方处理
                    return prompt_template
            else:
                return prompt_template
                
        except Exception as e:
            logger.error(f"获取提示词失败: {e}, 模块: {module}, 提示词: {prompt_name}")
            return self._get_fallback_prompt(module, prompt_name)
    
    def _get_fallback_prompt(self, module: str, prompt_name: str) -> str:
        """获取后备提示词"""
        fallback_prompts = {
            'external_api_handler': {
                'parameter_conversion_failure': "你是一个智能参数修复助手。请分析并修复参数转换失败的问题。",
                'time_parameter_supplement': "你是一个智能时间参数补充助手。请分析用户查询并补充缺失的时间参数。",
                'tool_reselection': "你是一个智能工具选择助手。请分析是否需要重新选择工具。",
                'parameter_supplement': "你是一个智能参数补充助手。请分析用户查询并补充缺失的参数。",
                'fallback_prompt': "你是一个专业的空气质量数据查询助手。",
                'system_default': "你是一个专业的空气质量数据查询助手。"
            },
            'llm_error_recovery': {
                'parameter_reextraction': "你是一个智能参数提取专家。请重新分析用户问题，提取正确的参数。",
                'tool_reselection': "你是一个智能工具选择专家。请重新分析用户问题，选择更合适的工具。",
                'time_clarification': "你是一个时间解析专家。请提供标准化的时间描述。",
                'location_clarification': "你是一个地理位置解析专家。请提供标准化的地理位置名称。",
                'comprehensive_analysis': "你是一个全面的问题分析专家。请进行全面分析，提供解决方案。"
            },
            'enhanced_param_extractor': {
                'basic_reextraction': "你是一个专业的参数提取专家。请从用户问题中提取查询参数。",
                'context_aware_extraction': "你是一个上下文感知的参数提取专家。请基于用户问题和对话历史提取参数。",
                'error_specific_extraction': "你是一个错误恢复专家。基于特定的错误类型重新提取参数。"
            },
            'llm_clarification_handler': {
                'extraction_failure': "你是一个智能参数提取助手。请分析并尝试智能补充缺失的参数。",
                'api_failure': "你是一个智能API错误分析助手。请分析API失败原因并提供解决方案。",
                'clarification_integration': "你是一个智能查询整合助手。请整合用户的原始问题和澄清信息。"
            },
            'sql_generator': {
                'main_prompt': "你是一个专业的SQL查询生成助手。根据用户的问题生成准确的SQL查询。"
            }
        }
        
        if module in fallback_prompts and prompt_name in fallback_prompts[module]:
            logger.info(f"使用后备提示词: {module}.{prompt_name}")
            return fallback_prompts[module][prompt_name]
        else:
            logger.warning(f"未找到后备提示词: {module}.{prompt_name}")
            return "你是一个专业的数据查询助手。请根据用户需求提供帮助。"
    
    def reload_prompts(self):
        """重新加载提示词配置"""
        logger.info("重新加载LLM提示词配置")
        self._load_prompts()
    
    def get_all_prompts(self) -> Dict[str, Any]:
        """获取所有提示词配置"""
        return self.prompts.copy()
    
    def get_module_prompts(self, module: str) -> Dict[str, str]:
        """获取指定模块的所有提示词"""
        return self.prompts.get(module, {}).copy()


# 全局提示词加载器实例
_prompt_loader_instance = None

def get_prompt_loader() -> PromptLoader:
    """获取提示词加载器单例"""
    global _prompt_loader_instance
    if _prompt_loader_instance is None:
        _prompt_loader_instance = PromptLoader()
    return _prompt_loader_instance

def get_prompt(module: str, prompt_name: str, **kwargs) -> str:
    """
    便捷函数：获取格式化的提示词
    
    Args:
        module: 模块名称
        prompt_name: 提示词名称
        **kwargs: 模板变量
    
    Returns:
        str: 格式化后的提示词
    """
    loader = get_prompt_loader()
    return loader.get_prompt(module, prompt_name, **kwargs)

def reload_prompts():
    """便捷函数：重新加载提示词配置"""
    loader = get_prompt_loader()
    loader.reload_prompts()