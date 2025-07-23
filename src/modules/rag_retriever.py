#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG检索模块
负责从向量数据库中检索相关上下文
"""

import os
import json
import logging
import re
import difflib


class RAGRetriever:
    """RAG检索器"""
    
    def __init__(self, vanna_instance):
        self.vanna = vanna_instance
        self.logger = logging.getLogger(__name__)
        self.station_info = self._load_station_info()
        
    def _load_station_info(self):
        """加载站点信息"""
        try:
            station_file = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'knowledge', 'station_info.json')
            if os.path.exists(station_file):
                with open(station_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 核心修正：从返回的字典中提取 "results" 列表
                    if isinstance(data, dict) and 'results' in data:
                        self.logger.info("从JSON字典中成功提取 'results' 列表。")
                        return data.get('results', [])
                    # 如果JSON本身就是列表，直接返回
                    elif isinstance(data, list):
                        self.logger.info("JSON文件本身就是一个列表，直接使用。")
                        return data
                    else:
                        self.logger.warning(f"station_info.json 格式未知或不包含 'results' 键。返回空列表。数据类型: {type(data)}")
                        return []
            else:
                self.logger.warning("站点信息文件不存在")
                return []
        except Exception as e:
            self.logger.error(f"加载站点信息失败: {e}")
            return []
    
    def retrieve_context(self, question, **kwargs):
        """检索RAG上下文"""
        self.logger.debug(f"开始RAG检索: {question}")
        
        try:
            # 步骤1: 提取实体
            entities = self._extract_entities(question)
            
            # 步骤2: 检索站点信息
            station_context = self._get_station_context(entities)
            
            # 步骤3: 并行检索其他上下文
            ddl_context = self._get_ddl_context(question, **kwargs)
            doc_context = self._get_doc_context(question, **kwargs)
            sql_context = self._get_sql_context(question, **kwargs)
            
            # 步骤4: 组合上下文
            context = {
                "station_info_context": station_context,
                "ddl_context": ddl_context,
                "doc_context": doc_context,
                "sql_context": sql_context
            }
            
            self.logger.debug(f"RAG检索完成: {[k for k, v in context.items() if v]}")
            return context
            
        except Exception as e:
            self.logger.error(f"RAG检索失败: {e}")
            return self._get_default_context()
    
    def _extract_entities(self, question):
        """提取实体"""
        entities = {
            'locations': [],
            'dates': [],
            'metrics': [],
            'other_terms': []
        }
        
        # 提取地名
        location_patterns = [
            r'([^市县区]+市)',
            r'([^市县区]+县)',
            r'([^市县区]+区)',
            r'(广州|深圳|珠海|佛山|韶关|河源|梅州|惠州|汕尾|东莞|中山|江门|阳江|湛江|茂名|肇庆|清远|潮州|揭阳|云浮|汕头)',
            r'(guangzhou|shenzhen|beijing|shanghai)',
        ]
        
        for pattern in location_patterns:
            matches = re.findall(pattern, question, re.IGNORECASE)
            entities['locations'].extend(matches)
        
        # 提取日期
        date_patterns = [
            r'(\d{4}年\d{1,2}月\d{1,2}日)',
            r'(\d{4}-\d{1,2}-\d{1,2})',
            r'(\d{1,2}月\d{1,2}日)',
            r'(今天|昨天|明天|最近|latest|today|yesterday)'
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, question, re.IGNORECASE)
            entities['dates'].extend(matches)
        
        # 提取指标
        metric_patterns = [
            r'(pm2\.5|pm10|so2|no2|co|o3|aqi)',
            r'(空气质量|air quality|污染|质量指数)'
        ]
        
        for pattern in metric_patterns:
            matches = re.findall(pattern, question, re.IGNORECASE)
            entities['metrics'].extend(matches)
        
        # 清理重复项
        for key in entities:
            entities[key] = list(set(entities[key]))
        
        self.logger.debug(f"提取的实体: {entities}")
        return entities
    
    def _get_station_context(self, entities):
        """获取站点上下文"""
        if not entities['locations']:
            return "无相关站点信息"
        
        station_info_list = []
        similarity_threshold = 80
        
        for location in entities['locations']:
            # 模糊匹配站点
            matched_stations = []
            for station in self.station_info:
                # 核心修正：使用JSON文件中实际的中文键名
                city_name = station.get('城市名称', '')
                station_name = station.get('站点名称', '')
                
                # 计算相似度 (使用标准库替代rapidfuzz)
                city_similarity = difflib.SequenceMatcher(None, location.lower(), city_name.lower()).ratio() * 100
                station_similarity = difflib.SequenceMatcher(None, location.lower(), station_name.lower()).ratio() * 100
                
                if city_similarity >= similarity_threshold or station_similarity >= similarity_threshold:
                    matched_stations.append(station)
            
            # 格式化匹配的站点信息
            for station in matched_stations:  # 移除数量限制
                station_info_str = self._format_station_info(station)
                station_info_list.append(station_info_str)
        
        if station_info_list:
            # 修正：确保返回的是字符串，而不是列表
            return "\n---\n".join(station_info_list)
        else:
            return f"未能根据关键词 '{', '.join(entities['locations'])}' 找到匹配的站点信息"
    
    def _format_station_info(self, station):
        """格式化站点信息"""
        # 核心修正：使用JSON文件中实际的中文键名
        station_name = station.get('站点名称', '未知')
        station_code = station.get('唯一编码', '未知')
        longitude = station.get('经度', '未知')
        latitude = station.get('纬度', '未知')
        city_name = station.get('城市名称', '未知')
        station_type_id = station.get('站点类型ID', '未知')
        
        return f"关于站点'{station_name}'的信息：其唯一编码是'{station_code}'，地理坐标为经度{longitude}、纬度{latitude}，所属城市为'{city_name}'，站点类型ID为{station_type_id}。"
    
    def _get_ddl_context(self, question, **kwargs):
        """获取DDL上下文"""
        try:
            n_results = kwargs.get('n_ddl', 4)
            # 修正：如果vanna返回None，则视为空列表
            ddl_results = self.vanna.get_related_ddl(question=question, n_results=n_results) or []
            
            if ddl_results:
                # 修正：确保处理的是列表
                return "\n---\n".join(list(dict.fromkeys(ddl_results)))
            else:
                return "无相关表结构信息"
        except Exception as e:
            self.logger.error(f"获取DDL上下文失败: {e}")
            return "无相关表结构信息"
    
    def _get_doc_context(self, question, **kwargs):
        """获取文档上下文"""
        try:
            n_results = kwargs.get('n_docs', 20)
            # 修正：如果vanna返回None，则视为空列表
            doc_results = self.vanna.get_related_documentation(question=question, n_results=n_results) or []
            
            if doc_results:
                # 修正：确保处理的是列表
                return "\n---\n".join(list(dict.fromkeys(doc_results)))
            else:
                return "无相关业务知识"
        except Exception as e:
            self.logger.error(f"获取文档上下文失败: {e}")
            return "无相关业务知识"
    
    def _get_sql_context(self, question, **kwargs):
        """获取SQL上下文"""
        try:
            n_results = kwargs.get('n_sql', 10)
            # 修正：如果vanna返回None，则视为空列表
            sql_results = self.vanna.get_similar_question_sql(question=question, n_results=n_results) or []
            
            if sql_results:
                # 调试：记录实际返回的格式
                self.logger.debug(f"SQL检索原始结果类型: {type(sql_results)}")
                if sql_results:
                    self.logger.debug(f"第一个元素类型: {type(sql_results[0])}")
                    self.logger.debug(f"第一个元素内容: {sql_results[0]}")
                
                # 处理不同的返回格式
                formatted_sqls = []
                for item in sql_results:
                    if isinstance(item, dict):
                        # 如果是字典格式 {"question": "...", "sql": "..."}
                        sql_text = item.get('sql', str(item))
                        formatted_sqls.append(sql_text)
                    elif isinstance(item, str):
                        # 如果是字符串格式
                        formatted_sqls.append(item)
                    else:
                        # 其他格式，转换为字符串
                        formatted_sqls.append(str(item))
                
                # 去重并返回
                unique_sqls = list(dict.fromkeys(formatted_sqls))
                return "\n---\n".join(unique_sqls)
            else:
                return "无相关SQL范例"
        except Exception as e:
            self.logger.error(f"获取SQL上下文失败: {e}")
            return "无相关SQL范例"
    
    def _get_default_context(self):
        """获取默认上下文"""
        return {
            "station_info_context": "无相关站点信息",
            "ddl_context": "无相关表结构信息",
            "doc_context": "无相关业务知识",
            "sql_context": "无相关SQL范例"
        }
    
    def format_context_for_debug(self, context):
        """格式化上下文用于调试"""
        debug_output = []
        
        for key, value in context.items():
            title = {
                'station_info_context': '相关站点信息 (Station Info)',
                'ddl_context': '相关表结构 (DDL)',
                'doc_context': '相关业务知识 (Documentation)',
                'sql_context': '相似SQL查询 (SQL Examples)'
            }.get(key, key)
            
            debug_output.append(f"--- {title} ---")
            debug_output.append(value or "无相关信息")
        
        return "\n".join(debug_output)


if __name__ == "__main__":
    # 测试代码
    print("RAG检索模块已加载")