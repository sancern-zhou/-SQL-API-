#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重构后的Vanna服务类
使用模块化架构，更易于维护和调试
"""

import os
import sys
import yaml
import json
import re
import logging
from datetime import datetime

# 导入重构后的模块
from .modules import DatabaseManager, RAGRetriever, SQLGenerator, SQLExecutor

# 导入原始的Vanna基类
from vanna.qianwen.QianwenAI_chat import QianWenAI_Chat
from vanna.chromadb import ChromaDB_VectorStore


class VannaService(QianWenAI_Chat, ChromaDB_VectorStore):
    """重构后的Vanna服务类"""
    
    def __init__(self, config_path=None):
        self.logger = logging.getLogger(__name__)
        
        # 加载配置
        self.original_config = self._load_config(config_path)
        
        # 初始化基类
        self._init_base_classes()
        
        # 初始化模块
        self._init_modules()
        
        # 版本标识
        self.version = "2.0.0"
        self.logger.info(f"VannaService 初始化完成 - 版本: {self.version}")
    
    
    
    def _load_config(self, config_path=None):
        """加载配置文件"""
        if config_path is None:
            # 修正路径，从src目录向上查找
            config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self.logger.info(f"配置文件加载成功: {config_path}")
            return config
            
        except Exception as e:
            self.logger.error(f"配置文件加载失败: {e}")
            return self._get_default_config()
    
    def _get_default_config(self):
        """获取默认配置"""
        return {
            'llm': {
                'api_key': 'your-api-key',
                'model': 'qwen-max-latest',
                'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1'
            },
            'database': {
                'primary_connection': {
                    'driver': '{ODBC Driver 18 for SQL Server}',
                    'server': 'localhost',
                    'database': 'test_db',
                    'uid': 'user',
                    'pwd': 'password'
                }
            },
            'vector_store': {
                'path': 'vanna_chroma_db'
            }
        }
    
    def _init_base_classes(self):
        """初始化基类"""
        try:
            # 新增: 为向量数据库计算绝对路径
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            vector_store_path = os.path.join(project_root, 'vanna_chroma_db')
            self.logger.info(f"动态计算的向量数据库路径: {vector_store_path}")

            # 按照原始代码的方式准备配置
            service_config = {
                "model": "qwen-plus",
                # 修改: 使用绝对路径
                "path": vector_store_path,
            }
            
            # 解包配置
            if self.original_config:
                # 解包 'llm' 部分并更新 service_config
                llm_config = self.original_config.get('llm', {})
                service_config.update(llm_config)

                # 解包其他部分
                if 'vector_store' in self.original_config:
                    service_config.update(self.original_config.get('vector_store'))
            
            # 初始化基类（使用原始方式）
            QianWenAI_Chat.__init__(self, config=service_config)
            ChromaDB_VectorStore.__init__(self, config=service_config)

            self.logger.info("基类初始化完成")
            
        except Exception as e:
            self.logger.error(f"基类初始化失败: {e}")
            raise
    
    def _init_modules(self):
        """初始化模块"""
        try:
            # 初始化数据库管理器
            db_config = self.original_config.get('database', {})
            self.logger.debug(f"VannaService配置: {self.original_config}")
            self.logger.debug(f"数据库配置: {db_config}")
            self.db_manager = DatabaseManager(db_config)
            self.db_manager.init_connection_pools()
            
            # 初始化RAG检索器
            self.rag_retriever = RAGRetriever(self)
            
            # 初始化SQL生成器
            self.sql_generator = SQLGenerator(self, self.db_manager)
            
            # 初始化SQL执行器
            self.sql_executor = SQLExecutor(self.db_manager)
            
            self.logger.info("所有模块初始化完成")
            
        except Exception as e:
            self.logger.error(f"模块初始化失败: {e}")
            raise
    
    def generate_sql(self, question, history=None, **kwargs):
        """生成SQL查询 - 重构版本"""
        self.logger.debug(f"开始生成SQL: {question}")
        
        try:
            # 步骤1: RAG检索（传递rag_settings配置）
            rag_settings = self.original_config.get('rag_settings', {})
            merged_kwargs = {**rag_settings, **kwargs}  # kwargs优先级更高
            rag_context = self.rag_retriever.retrieve_context(question, **merged_kwargs)
            
            # [核心修改] 添加详细的RAG上下文日志
            self.logger.debug("="*20 + " RAG CONTEXT RETRIEVED " + "="*20)
            self.logger.debug(f"Question: {question}")
            # 使用.get()确保安全访问，并提供默认值
            ddl_context = rag_context.get('ddl_context', 'N/A')
            doc_context = rag_context.get('doc_context', 'N/A')
            sql_context = rag_context.get('sql_context', 'N/A')
            station_info_context = rag_context.get('station_info_context', 'N/A')
            self.logger.debug(f"Retrieved DDL:\n{ddl_context}")
            self.logger.debug(f"Retrieved Docs:\n{doc_context}")
            self.logger.debug(f"Retrieved SQLs:\n{sql_context}")
            self.logger.debug(f"Retrieved Station Info:\n{station_info_context}")
            self.logger.debug("="*55)
            
            # 步骤2: 生成SQL
            sql, llm_response = self.sql_generator.generate_sql(question, rag_context, history)
            
            # 步骤3: 返回结果
            return sql, llm_response, rag_context
            
        except Exception as e:
            self.logger.error(f"生成SQL失败: {e}")
            error_msg = f'{{"error": "生成SQL失败: {str(e)}"}}'
            return error_msg, error_msg, {}
    
    def ask_and_run(self, question, history=None, **kwargs):
        """执行问答并运行SQL - 使用可靠的SQL执行"""
        self.logger.debug(f"开始ask_and_run: {question}")
        
        try:
            # 步骤1: 生成SQL
            sql, llm_response, rag_context = self.generate_sql(question, history, **kwargs)
            
            # 步骤2: 检查是否为错误响应或澄清请求
            if sql.startswith('{"error":'):
                return {
                    'status': 'error',
                    'sql': '',
                    'results': [],
                    'error': f'SQL生成失败: {sql}'
                }, None
            elif sql.startswith('{"clarification_needed":') or 'clarification_needed' in sql:
                # 处理澄清请求
                import json
                try:
                    clarification_data = json.loads(sql)
                    clarification_msg = clarification_data.get('clarification_needed', '需要更多信息')
                    return {
                        'status': 'clarification_needed', 
                        'sql': '',
                        'results': [],
                        'clarification': clarification_msg,
                        'error': f'需要澄清: {clarification_msg}'
                    }, None
                except json.JSONDecodeError:
                    return {
                        'status': 'clarification_needed',
                        'sql': '',
                        'results': [],
                        'clarification': '需要更多信息来完成查询',
                        'error': '需要澄清: 需要更多信息来完成查询'
                    }, None
            
            # 步骤3: 使用可靠的SQL执行方法
            df = self.run_sql(sql)  # 直接调用可靠的run_sql方法
            
            # 步骤4: 格式化结果
            results = df.to_dict('records') if df is not None and not df.empty else []
            
            return {
                'status': 'success',
                'sql': sql,
                'results': results,
                'row_count': len(results),
                'columns': df.columns.tolist() if df is not None else []
            }, df
            
        except Exception as e:
            self.logger.error(f"ask_and_run失败: {e}")
            return {
                'status': 'error',
                'sql': sql if 'sql' in locals() else '',
                'results': [],
                'error': f'执行失败: {str(e)}'
            }, None
    
    def get_db_connection_status(self):
        """获取数据库连接状态"""
        try:
            db_info = self.db_manager.get_database_info()
            return {
                'enabled': True,
                'type': db_info['type'],
                'primary_config': db_info['primary_config'],
                'training_pools': db_info['training_pools'],
                'mysql_available': db_info['mysql_available'],
                'pyodbc_available': db_info['pyodbc_available']
            }
        except Exception as e:
            self.logger.error(f"获取数据库状态失败: {e}")
            return {
                'enabled': False,
                'error': str(e)
            }
    
    def reset_connection_pool(self):
        """重置连接池"""
        try:
            self.db_manager.close_all_connections()
            self.db_manager.init_connection_pools()
            return {"status": "success", "message": "连接池已重置"}
        except Exception as e:
            self.logger.error(f"重置连接池失败: {e}")
            return {"status": "error", "message": str(e)}

    def close_all_connections(self):
        """关闭所有数据库连接"""
        self.db_manager.close_all_connections()

    def get_version_info(self):
        """获取版本和服务信息"""
        return {
            "service": "VannaService",
            "version": self.version,
            "timestamp": datetime.now().isoformat()
        }

    def _get_common_messages(self, **kwargs):
        """
        获取公共的消息模板，这部分保持Vanna的原始逻辑
        """
        return [{'role': 'system', 'content': self.system_message}]
    
    def get_cursor(self):
        """获取数据库游标的上下文管理器 - 从示例代码移植"""
        return self.db_manager.get_cursor()

    def run_sql(self, sql: str):
        """
        直接执行SQL查询 - 从示例代码移植的可靠版本
        只用于SQL查询路径，不影响API查询
        """
        import pandas as pd
        
        try:
            with self.get_cursor() as cursor:
                self.logger.debug(f"执行SQL: {sql}")
                cursor.execute(sql)
                
                # 获取列名
                columns = [column[0] for column in cursor.description]
                
                # 获取结果并转换为DataFrame  
                rows = cursor.fetchall()
                df = pd.DataFrame([list(row) for row in rows], columns=columns)
                
                self.logger.debug(f"SQL执行成功: {len(df)} 行结果")
                return df
                
        except Exception as e:
            self.logger.error(f"SQL执行失败: {e}")
            raise e

    def _clean_llm_response(self, response):
        """
        清理和格式化LLM的响应
        """
        self.logger.debug(f"原始LLM响应: {response}")
        # 移除代码块标记
        if response.startswith("```sql"):
            response = response[6:]
        if response.endswith("```"):
            response = response[:-3]
        
        # 移除不必要的空格和换行
        response = response.strip()
        
        self.logger.debug(f"清理后LLM响应: {response}")
        return response
    
    def call_llm_with_tools(self, messages, tools=None, tool_choice="auto"):
        """
        调用LLM的工具使用功能
        
        Args:
            messages: 消息列表，格式为 [{"role": "system", "content": "..."}, ...]
            tools: 工具定义列表
            tool_choice: 工具选择策略，默认为"auto"
        
        Returns:
            Dict: LLM响应，包含工具调用信息
        """
        try:
            # 如果没有可用的工具，直接调用普通的LLM
            if not tools:
                # 提取最后一个用户消息
                user_message = ""
                for msg in reversed(messages):
                    if msg.get('role') == 'user':
                        user_message = msg.get('content', '')
                        break
                
                # 调用现有的ask方法
                response = self.ask(user_message)
                return {
                    'content': response,
                    'tool_calls': None
                }
            
            # 这里需要实现工具调用功能
            # 由于当前的Vanna基类可能不支持工具调用，我们先实现一个简化版本
            # 提取最后一个用户消息
            user_message = ""
            for msg in reversed(messages):
                if msg.get('role') == 'user':
                    user_message = msg.get('content', '')
                    break
            
            # 简化的工具选择逻辑
            # 这里可以根据用户问题的关键词来选择合适的工具
            selected_tool = self._select_tool_by_keywords(user_message, tools)
            
            if selected_tool:
                # 构建工具调用响应
                tool_params = self._extract_tool_params(user_message, selected_tool)
                
                return {
                    'content': '',
                    'tool_calls': [{
                        'function': {
                            'name': selected_tool['function']['name'],
                            'arguments': json.dumps(tool_params, ensure_ascii=False)
                        }
                    }]
                }
            else:
                # 没有找到合适的工具，返回普通响应
                response = self.ask(user_message)
                return {
                    'content': response,
                    'tool_calls': None
                }
                
        except Exception as e:
            self.logger.error(f"调用LLM工具失败: {e}")
            return {
                'content': f"调用LLM工具失败: {str(e)}",
                'tool_calls': None
            }
    
    def _select_tool_by_keywords(self, user_message, tools):
        """
        根据关键词选择合适的工具
        """
        user_message_lower = user_message.lower()
        
        # 定义关键词映射
        keyword_mappings = {
            'get_summary_report': ['查询', '报表', '数据', '空气质量', '监测', '站点', '周报', '月报', '年报', '季报'],
            'get_comparison_report': ['比较', '对比', '同比', '环比', '相比', '对照']
        }
        
        # 为每个工具计算匹配分数
        tool_scores = {}
        for tool in tools:
            tool_name = tool['function']['name']
            if tool_name in keyword_mappings:
                score = sum(1 for keyword in keyword_mappings[tool_name] if keyword in user_message_lower)
                tool_scores[tool_name] = score
        
        # 返回得分最高的工具
        if tool_scores:
            best_tool_name = max(tool_scores.items(), key=lambda x: x[1])[0]
            for tool in tools:
                if tool['function']['name'] == best_tool_name:
                    return tool
        
        return None
    
    def _extract_tool_params(self, user_message, tool):
        """
        从用户消息中提取工具参数
        """
        import re
        
        tool_name = tool['function']['name']
        params = {}
        
        # 提取地理位置
        location_patterns = [
            r'([^，,。.！!？?\s]+(?:市|区|县|镇|街道|中学|小学|学校|站|点))',
            r'([^，,。.！!？?\s]{2,8}(?:市|区|县))',
        ]
        
        locations = []
        for pattern in location_patterns:
            matches = re.findall(pattern, user_message)
            locations.extend(matches)
        
        if locations:
            params['locations'] = list(set(locations))  # 去重
        
        # 提取时间描述 - 修复：优先匹配完整日期
        time_patterns = [
            r'(\d{4}年\d{1,2}月\d{1,2}日)',  # 优先匹配完整日期，如"2025年2月1日"
            r'(\d{4}年\d{1,2}月)',           # 然后匹配年月，如"2025年2月"
            r'(昨天|今天|明天)',
            r'(上周|本周|下周)',
            r'(上个?月|这个?月|下个?月)',
            r'(去年|今年|明年)',
            r'(\d{1,2}月\d{1,2}日)',         # 月日格式
            r'(\d{1,2}月)',
            r'(最近\d+天)',
            r'(过去\d+天)',
        ]
        
        time_descriptions = []
        for pattern in time_patterns:
            matches = re.findall(pattern, user_message)
            time_descriptions.extend(matches)
        
        if time_descriptions:
            params['time_description'] = time_descriptions[0]
        
        # 如果是对比报表，提取对比时间
        if tool_name == 'get_comparison_report':
            comparison_patterns = [
                r'(?:和|与|跟|同|相比|对比)\s*([^，,。.！!？?\s]*(?:年|月|周|天|同期|上年|去年))',
                r'(?:去年|上年|前年)\s*([^，,。.！!？?\s]*(?:同期|同月|同周))',
            ]
            
            for pattern in comparison_patterns:
                matches = re.findall(pattern, user_message)
                if matches:
                    params['comparison_time_description'] = matches[0]
                    break
        
        # 判断区域类型
        if locations:
            location_text = ' '.join(locations)
            if any(keyword in location_text for keyword in ['市', '城市']):
                params['area_type'] = '城市'
            elif any(keyword in location_text for keyword in ['区', '县', '镇']):
                params['area_type'] = '区县'
            else:
                params['area_type'] = '站点'
        
        # 默认数据源
        params['data_source'] = '审核实况'
        
        return params
    
    def _call_llm_for_analysis(self, prompt: str) -> str:
        """
        调用LLM进行智能分析
        专门用于澄清处理器的分析任务
        
        Args:
            prompt: 分析提示词
            
        Returns:
            LLM的分析结果
        """
        try:
            self.logger.debug(f"[LLM_ANALYSIS] 开始LLM分析")
            self.logger.debug(f"[LLM_ANALYSIS] 提示词长度: {len(prompt)}")
            
            # 直接调用LLM，不经过RAG检索和SQL生成流程
            response = self._call_llm_directly(prompt)
            
            self.logger.debug(f"[LLM_ANALYSIS] LLM分析完成，响应长度: {len(response)}")
            return response
            
        except Exception as e:
            self.logger.error(f"[LLM_ANALYSIS] LLM分析失败: {e}")
            raise e
    
    def _call_llm_directly(self, prompt: str) -> str:
        """
        直接调用LLM，不经过RAG检索
        
        Args:
            prompt: 提示词
            
        Returns:
            str: LLM响应
        """
        try:
            # 构建简单的消息格式
            messages = [{"role": "user", "content": prompt}]
            
            # 直接调用LLM - 使用继承的方法
            response = self.submit_prompt(messages)
            
            return response
            
        except Exception as e:
            self.logger.error(f"[LLM_DIRECT] 直接LLM调用失败: {e}")
            raise e

    def call_llm_with_tools_enhanced(self, messages, tools=None, tool_choice="auto"):
        """
        增强版工具调用，使用模块化的参数提取器
        
        Args:
            messages: 消息列表，格式为 [{"role": "system", "content": "..."}, ...]
            tools: 工具定义列表
            tool_choice: 工具选择策略，默认为"auto"
        
        Returns:
            Dict: LLM响应，包含工具调用信息
        """
        try:
            self.logger.info(f"[VANNA_TRACE] 使用增强版工具调用（模块化参数提取）")
            
            # 如果没有可用的工具，直接调用普通的LLM
            if not tools:
                # 提取最后一个用户消息
                user_message = ""
                for msg in reversed(messages):
                    if msg.get('role') == 'user':
                        user_message = msg.get('content', '')
                        break
                
                # 调用现有的ask方法
                response = self.ask(user_message)
                return {
                    'content': response,
                    'tool_calls': None
                }
            
            # 提取最后一个用户消息
            user_message = ""
            for msg in reversed(messages):
                if msg.get('role') == 'user':
                    user_message = msg.get('content', '')
                    break
            
            self.logger.info(f"[VANNA_TRACE] 提取的用户消息: {user_message}")
            
            # 简化的工具选择逻辑
            selected_tool = self._select_tool_by_keywords(user_message, tools)
            
            if selected_tool:
                # 使用模块化的参数提取器
                from .utils.param_extractor import get_param_extractor
                extractor = get_param_extractor()
                tool_params = extractor.extract_tool_params(user_message, selected_tool)
                
                self.logger.info(f"[VANNA_TRACE] 选择的工具: {selected_tool['function']['name']}")
                self.logger.info(f"[VANNA_TRACE] 提取的参数: {tool_params}")
                
                return {
                    'content': '',
                    'tool_calls': [{
                        'function': {
                            'name': selected_tool['function']['name'],
                            'arguments': json.dumps(tool_params, ensure_ascii=False)
                        }
                    }],
                    'original_question': user_message  # 添加原始问题，用于后续验证
                }
            else:
                # 没有找到合适的工具，返回普通响应
                response = self.ask(user_message)
                return {
                    'content': response,
                    'tool_calls': None
                }
                
        except Exception as e:
            self.logger.error(f"调用增强版LLM工具失败: {e}")
            return {
                'content': f"调用增强版LLM工具失败: {str(e)}",
                'tool_calls': None
            }

# 全局实例
_vanna_service_instance = None

def get_vanna_service():
    """获取VannaService全局实例"""
    from flask import current_app
    if hasattr(current_app, 'vanna_service'):
        return current_app.vanna_service
    return None

# 工厂函数，方便实例化
def create_vanna_service(config_path=None):
    """
    工厂函数，用于创建和初始化VannaService实例
    """
    try:
        logging.info("正在通过工厂函数创建VannaService...")
        service = VannaService(config_path=config_path)
        logging.info("VannaService实例创建成功")
        return service
    except Exception as e:
        logging.error(f"通过工厂函数创建VannaService失败: {e}")
        return None