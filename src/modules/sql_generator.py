#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL生成模块
负责将自然语言转换为SQL查询
"""

import os
import logging
from datetime import datetime
import yaml
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.prompt_loader import get_prompt


class SQLGenerator:
    """SQL生成器"""
    
    def __init__(self, vanna_instance, database_manager):
        self.vanna = vanna_instance
        self.db_manager = database_manager
        self.logger = logging.getLogger(__name__)
        
    def generate_sql(self, question, rag_context, history=None, open_analysis_query=False, enhancement_callback=None):
        """生成SQL查询"""
        self.logger.debug(f"开始生成SQL: {question}")
        
        try:
            # 步骤1: 加载提示词模板
            template = self._load_prompt_template()
            
            # 步骤2: 安全地格式化提示词
            formatted_prompt = self._format_prompt_safely(template, question, rag_context, history)
            
            # 步骤2.5: 如果是开放式查询，进行提示词增强
            if open_analysis_query and enhancement_callback:
                self.logger.debug("应用开放式查询提示词增强")
                formatted_prompt = enhancement_callback(question, formatted_prompt)
            
            # 步骤3: 调用大语言模型
            # 修正: 将完整提示词作为system_prompt，原始问题作为user_question分别传入
            llm_response = self._call_llm(system_prompt=formatted_prompt, user_question=question)
            
            # 步骤4: 清理响应
            cleaned_sql = self._clean_response(llm_response)
            
            self.logger.debug(f"SQL生成完成: {len(cleaned_sql)} 字符")
            return cleaned_sql, llm_response
            
        except Exception as e:
            self.logger.error(f"SQL生成失败: {e}")
            error_response = f'{{"error": "SQL生成失败: {str(e)}"}}'
            return error_response, error_response
    
    def _load_prompt_template(self):
        """加载提示词模板"""
        try:
            # 修正路径：从src/modules返回两级到项目根目录，再进入config
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            template_path = os.path.join(project_root, 'config', 'sql_prompts.yaml')
            with open(template_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                template = config['main_prompt']
            
            self.logger.debug(f"提示词模板加载成功: {len(template)} 字符")
            return template
            
        except FileNotFoundError:
            self.logger.error("提示词模板文件未找到")
            return self._get_default_template()
        except Exception as e:
            self.logger.error(f"加载提示词模板失败: {e}")
            return self._get_default_template()
    
    def _get_default_template(self):
        """获取默认提示词模板"""
        try:
            # 尝试从配置文件加载提示词
            return get_prompt(
                'sql_generator',
                'main_prompt',
                rag_context='{rag_context}',
                history='{history}',
                question='{question}'
            )
        except Exception as e:
            self.logger.error(f"加载SQL生成器提示词失败: {e}")
            # 返回原始的后备提示词
            return """
你是一个专业的SQL查询生成助手。根据用户的问题和提供的上下文信息，生成准确的SQL查询。

数据库信息：
- 数据库名称: {primary_database_name}
- 数据库类型: {db_type}

相关表结构：
{ddl_context}

相关业务知识：
{doc_context}

相关站点信息：
{station_info_context}

相似SQL示例：
{sql_context}

历史对话：
{history_context}

用户问题: {question}

请生成相应的SQL查询。
"""
    
    def _format_prompt_safely(self, template, question, rag_context, history=None):
        """安全地格式化提示词"""
        try:
            # 获取数据库配置
            db_config = self.db_manager.get_primary_config()
            
            # 创建安全的模板参数
            template_params = {
                "primary_database_name": db_config.get('database', 'gd_suncere_product_data_air'),
                "db_type": self.db_manager.db_type or "SQL Server",
                "station_info_context": self._safe_get(rag_context, "station_info_context", "无相关站点信息"),
                "ddl_context": self._safe_get(rag_context, "ddl_context", "无相关表结构信息"),
                "doc_context": self._safe_get(rag_context, "doc_context", "无相关业务知识"),
                "sql_context": self._safe_get(rag_context, "sql_context", "无相关SQL范例"),
                "history_context": self._format_history(history),
                "question": question or "无问题"
            }
            
            # 验证所有参数都不为None
            for key, value in template_params.items():
                if value is None:
                    self.logger.warning(f"参数 {key} 为None，使用默认值")
                    template_params[key] = f"默认_{key}"
            
            # 格式化模板
            formatted_prompt = template.format(**template_params)
            
            self.logger.debug(f"提示词格式化成功: {len(formatted_prompt)} 字符")
            return formatted_prompt
            
        except Exception as e:
            self.logger.error(f"格式化提示词失败: {e}")
            # 返回最基本的安全提示词
            return f"请为以下问题生成SQL查询: {question}"
    
    def _safe_get(self, obj, key, default=""):
        """安全地获取字典值"""
        if obj is None:
            return default
        
        if not isinstance(obj, dict):
            return default
        
        value = obj.get(key)
        if value is None or value == "":
            return default
        
        return str(value)
    
    def _format_history(self, history):
        """格式化历史记录"""
        if not history:
            return "无历史对话"
        
        try:
            if isinstance(history, list) and len(history) > 0:
                history_items = []
                for item in history[-3:]:  # 只取最近3条
                    if isinstance(item, dict):
                        role = item.get('role', '用户')
                        content = item.get('content', '')
                        history_items.append(f"{role}: {content}")
                    else:
                        history_items.append(str(item))
                
                return "\n".join(history_items)
            else:
                return "无历史对话"
                
        except Exception as e:
            self.logger.error(f"格式化历史记录失败: {e}")
            return "历史记录处理错误"
    
    def _call_llm(self, system_prompt: str, user_question: str):
        """
        调用大语言模型 - 修正版
        - system_prompt: 包含所有上下文和指令的完整提示
        - user_question: 用户的原始问题
        """
        try:
            # 修正: 不再调用有问题的_get_common_messages，而是自己构建消息列表
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question}
            ]
            
            # 提交请求
            response = self.vanna.submit_prompt(messages)
            
            return response
            
        except Exception as e:
            self.logger.error(f"调用LLM失败: {e}", exc_info=True)
            return f'{{"error": "LLM调用失败: {str(e)}"}}'
    
    def _clean_response(self, response):
        """清理LLM响应"""
        try:
            if hasattr(self.vanna, '_clean_llm_response'):
                cleaned = self.vanna._clean_llm_response(response)
            else:
                # 默认清理方法
                cleaned = response.strip()
                if cleaned.startswith('```sql'):
                    cleaned = cleaned[6:]
                elif cleaned.startswith('```'):
                    cleaned = cleaned[3:]
                if cleaned.endswith('```'):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            
            self.logger.debug(f"响应清理成功: {len(cleaned)} 字符")
            return cleaned
        except Exception as e:
            self.logger.error(f"响应清理失败: {e}")
            return response


class SQLExecutor:
    """SQL执行器"""
    
    def __init__(self, database_manager):
        self.db_manager = database_manager
        self.logger = logging.getLogger(__name__)
    
    def execute_sql(self, sql, pool_name='primary'):
        """执行SQL查询"""
        self.logger.debug(f"执行SQL: {sql[:100]}...")
        
        try:
            with self.db_manager.get_connection(pool_name) as conn:
                cursor = conn.cursor()
                cursor.execute(sql)
                
                # 获取结果
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    
                    # 转换为字典列表
                    results = []
                    for row in rows:
                        results.append(dict(zip(columns, row)))
                    
                    self.logger.debug(f"SQL执行成功: {len(results)} 行结果")
                    return {
                        'status': 'success',
                        'results': results,
                        'row_count': len(results),
                        'columns': columns
                    }
                else:
                    self.logger.debug("SQL执行成功: 无返回结果")
                    return {
                        'status': 'success',
                        'results': [],
                        'row_count': 0,
                        'columns': []
                    }
                    
        except Exception as e:
            self.logger.error(f"SQL执行失败: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'results': [],
                'row_count': 0,
                'columns': []
            }
    
    def validate_sql(self, sql):
        """验证SQL语法"""
        try:
            # 基本的SQL验证
            sql_upper = sql.upper().strip()
            
            # 检查是否包含危险操作
            dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE']
            for keyword in dangerous_keywords:
                if keyword in sql_upper:
                    return False, f"SQL包含危险关键词: {keyword}"
            
            # 检查是否为SELECT语句
            if not sql_upper.startswith('SELECT'):
                return False, "只允许SELECT查询"
            
            return True, "SQL验证通过"
            
        except Exception as e:
            return False, f"SQL验证失败: {e}"


if __name__ == "__main__":
    # 测试代码
    print("SQL生成模块已加载")