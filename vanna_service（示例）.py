import os
import yaml
import pandas as pd
from vanna.qianwen.QianwenAI_chat import QianWenAI_Chat
from vanna.chromadb import ChromaDB_VectorStore
import json
import time
from contextlib import contextmanager
from threading import Thread
from rapidfuzz import fuzz
import re
from pandasql import sqldf

# 根据配置动态导入数据库驱动
try:
    import mysql.connector
    from mysql.connector.pooling import MySQLConnectionPool
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False

try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False

# 简单的SQL Server连接池实现
class SimpleConnectionPool:
    def __init__(self, max_connections, connection_creator):
        self.max_connections = max_connections
        self.connection_creator = connection_creator
        self.connections = []
        self.in_use = set()
    
    def get_connection(self):
        # 首先清理无效引用
        self.in_use = {conn for conn in self.in_use if conn in self.connections}
        
        # 尝试从现有连接中找到未使用的
        for i in range(len(self.connections) - 1, -1, -1):  # 反向遍历以安全移除
            conn = self.connections[i]
            if conn not in self.in_use:
                try:
                    # pyodbc连接需要执行查询来检查是否有效
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.close()
                    self.in_use.add(conn)
                    return conn
                except Exception as e:
                    print(f"连接池中的连接已失效，移除: {e}")
                    # 连接失效，移除
                    try:
                        self.connections.pop(i)
                    except:
                        pass
        
        # 创建新连接
        if len(self.connections) < self.max_connections:
            try:
                conn = self.connection_creator()
                self.connections.append(conn)
                self.in_use.add(conn)
                return conn
            except Exception as e:
                print(f"创建新连接失败: {e}")
                raise
        
        # 连接池已满，打印当前状态
        print(f"连接池已满: 总连接数={len(self.connections)}, 使用中={len(self.in_use)}")
        raise Exception("连接池已满，无法获取新连接")
    
    def release(self, connection):
        if connection in self.in_use:
            self.in_use.remove(connection)
            print(f"连接已释放回连接池，当前使用中连接: {len(self.in_use)}/{len(self.connections)}")
    
    def close_all(self):
        for conn in self.connections:
            try:
                conn.close()
            except Exception as e:
                print(f"关闭连接时出错: {e}")
        self.connections = []
        self.in_use = set()
        print("所有数据库连接已关闭")

# Load configuration from YAML file
def load_config():
    with open('config.yaml', 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)

class MyVanna(QianWenAI_Chat, ChromaDB_VectorStore):
    def _get_common_messages(self, **kwargs) -> list:
        """
        [新增] 实现基类中缺失的通用消息方法，提供一个默认的系统指令。
        这修复了在 generate_sql 和 correct_sql 中发生的 'AttributeError'。
        """
        return [{"role": "system", "content": "You are a professional SQL assistant. Given the user's question and context, generate a single, executable SQL query for the specified database dialect. Do not add any explanations or markdown."}]

    def _format_rag_context_for_prompt(self, rag_context_obj: dict) -> str:
        """
        [新增] 将RAG上下文对象格式化为单个字符串，用于注入到提示中。
        此辅助方法确保了调试输出和提示构建的一致性。
        """
        context_parts = []
        if rag_context_obj.get("station_info_context"):
            context_parts.append(f"--- 相关站点信息 (Station Info) ---\n{rag_context_obj['station_info_context']}")
        if rag_context_obj.get("ddl_context"):
            context_parts.append(f"--- 相关表结构 (DDL) ---\n{rag_context_obj['ddl_context']}")
        if rag_context_obj.get("doc_context"):
            context_parts.append(f"--- 相关业务知识 (General Documentation) ---\n{rag_context_obj['doc_context']}")
        if rag_context_obj.get("sql_context"):
            context_parts.append(f"--- 类似的查询范例 (Similar SQL Queries) ---\n{rag_context_obj['sql_context']}")
        
        return "\n\n".join(context_parts) if context_parts else "无相关上下文信息。"

    def _clean_llm_response(self, response: str) -> str:
        """
        A robust function to clean various forms of cruft from LLM-generated SQL.
        Handles markdown, language identifiers, and leading/trailing whitespace.
        """
        # 1. Strip leading/trailing whitespace
        cleaned_str = response.strip()

        # 2. Handle markdown blocks (e.g., ```sql ... ```)
        if cleaned_str.startswith("```") and cleaned_str.endswith("```"):
            # Find the first newline
            first_newline = cleaned_str.find('\n')
            if first_newline != -1:
                # Take everything after the first line (which contains ```sql)
                cleaned_str = cleaned_str[first_newline + 1:]
            # Remove the trailing ```
            cleaned_str = cleaned_str.rsplit('```', 1)[0].strip()
        
        # 3. Handle cases where the response starts with 'sql' or 'json' identifier
        if cleaned_str.lower().startswith('sql'):
            cleaned_str = cleaned_str[3:].lstrip() # Remove 'sql' and any following whitespace/newline

        return cleaned_str

    def stringify_history(self, history: list) -> str:
        """
        [新增] 将对话历史列表转换为格式化的字符串。
        """
        if not history:
            return "无历史对话"
            
        history_str_parts = []
        for turn in history:
            role = "用户" if turn.get("role") == "user" else "AI助手"
            content = turn.get("content", "")
            
            # 尝试解析内容，看它是否是模型返回的JSON对象
            try:
                content_json = json.loads(content)
                if isinstance(content_json, dict):
                    # 如果是澄清问题，就提取问题文本
                    if 'clarification_needed' in content_json:
                        content = f"请求澄清: {content_json['clarification_needed']}"
                    # 如果是SQL，就格式化展示
                    elif 'sql' in content_json:
                        content = f"生成了SQL:\n```sql\n{content_json['sql']}\n```"
            except (json.JSONDecodeError, TypeError):
                # 内容不是JSON，直接使用原始文本
                pass
                
            history_str_parts.append(f"{role}: {content}")
            
        return "\n".join(history_str_parts)

    def _extract_entities_for_rag(self, question: str) -> dict:
        """
        [重构] 使用LLM从问题中提取关键实体，并返回一个结构化的字典。
        上下文信息现在从 self.table_metadata 和 self.field_mappings 动态构建。
        输出被重构成一个JSON对象，以分类实体。
        """
        print("正在提取问题中的关键实体...")

        # --- 1. 动态构建上下文 ---
        try:
            # 构建关键表信息字符串
            table_info_parts = []
            for name, meta in self.table_metadata.items():
                part = f"- **{name} ({meta.get('business_name', 'N/A')})**: {meta.get('description', 'N/A')}"
                table_info_parts.append(part)
            key_table_info_str = "\n".join(table_info_parts)

            # 构建关键字段信息字符串 (选择性地展示部分，避免过长)
            field_info_parts = []
            # 简单地取前 N 个或根据某种逻辑选择
            for field, desc in list(self.field_mappings.items())[:30]: # 取前30个作为示例
                field_info_parts.append(f"- **{field}**: {desc}")
            key_field_info_str = "\n".join(field_info_parts)
        except Exception as e:
            print(f"[警告] 动态构建实体提取上下文时出错: {e}. 将使用基础提示。")
            key_table_info_str = "无"
            key_field_info_str = "无"

        # --- 2. 构建动态 Prompt ---
        prompt = f"""你是一个数据库元数据分析器。你的任务是从用户的自然语言问题中，提取出所有可能与数据库查询相关的关键词。

请参考以下动态生成的数据库关键表信息和字段释义，以提高你提取的准确性。

### 关键表信息:
{key_table_info_str}

### 部分关键字段释义:
{key_field_info_str}

用户问题: "{question}"

请分析以上问题，并**只返回一个JSON对象字符串**，用于分类提取出的实体。
JSON对象应包含以下键： "locations", "tables", "columns", "time_expressions", "other_terms"。
- "locations": 地点或站点名称 (例如 '凤凰山', '广州'，'天河区')。
- "tables": 数据库表名或其业务同义词 (例如 '站点日均值表', 'dat_station_day')。
- "columns": 数据库列名或其业务同义词 (例如 'AQI', '首要污染物')。
- "time_expressions": 时间相关的词 (例如 '昨天', '2025年3月1日')。
- "other_terms": 其他无法归入以上分类的业务术语 (例如 '空气质量', '严重污染')。

如果某个类别没有识别到实体，请返回一个空数组 `[]` 作为其值。
**返回格式示例**: {{"locations": ["凤凰山"], "tables": ["dat_station_day"], "columns": ["aqi"], "time_expressions": ["2025年3月1日"], "other_terms": ["空气质量数据"]}}
"""
        try:
            # 注意：此处直接调用了父类的 submit_prompt
            response_str = self.submit_prompt([{"role": "user", "content": prompt}])
            
            # 清理并解析JSON
            start = response_str.find('{')
            end = response_str.rfind('}')
            if start != -1 and end != -1:
                json_str = response_str[start:end+1]
                entities = json.loads(json_str)

                # 确保返回的是字典，且包含预期的键
                if isinstance(entities, dict):
                    print(f"成功提取并分类实体: {entities}")
                    # 验证并补充缺失的键
                    for key in ["locations", "tables", "columns", "time_expressions", "other_terms"]:
                        if key not in entities:
                            entities[key] = []
                    return entities
                else:
                    print(f"警告: LLM返回的不是一个有效的JSON对象，而是一个: {type(entities)}")
                    return {}
            else:
                print("警告: 未能从LLM响应中解析出实体JSON。")
                return {}
        except Exception as e:
            print(f"错误: 提取实体时出错 - {e}")
            return {}

    def __init__(self, config=None):
        """
        Initializes the MyVanna service by correctly unpacking the nested configuration
        and initializing the parent classes in the correct order.
        """
        # --- Final and Correct Initialization Logic ---

        # 1. Start with a base config and define defaults
        service_config = {
            "model": "qwen-plus",
            "path": "./vanna_chroma_db",
        }

        # 2. Unpack the nested config from the YAML file into a flat dictionary
        if config:
            # Unpack the 'llm' section and update the service_config
            llm_config = config.get('llm', {})
            service_config.update(llm_config)

            # Unpack other sections if they exist
            if 'vector_store' in config:
                service_config.update(config.get('vector_store'))
            
            # This ensures the final config passed to initializers is flat
            # and contains the api_key at the top level where the initializer expects it.

        # 3. Initialize the parent classes in the correct order,
        #    passing the prepared, flat configuration.
        QianWenAI_Chat.__init__(self, config=service_config)
        ChromaDB_VectorStore.__init__(self, config=service_config)

        # 4. Initialize local database connection attributes
        if config:
            # [修改] 增强数据库配置的读取逻辑
            db_config = config.get('database', {})
            # 优先使用新的嵌套结构，如果不存在，则假定为旧的扁平结构
            self.db_primary_connection_config = db_config.get('primary_connection')
            if self.db_primary_connection_config is None and db_config:
                print("未找到 'primary_connection'，将使用根 'database' 对象作为主连接配置。")
                self.db_primary_connection_config = db_config
            
            self.db_training_connections = db_config.get('training_connections', [])
            self.execution_mode = config.get('execution_mode', 'direct')
            
            # 检测主连接的数据库类型
            self.db_type = self._detect_db_type(self.db_primary_connection_config)
        else:
            self.db_primary_connection_config = None
            self.db_training_connections = []
            self.execution_mode = 'direct'
            self.db_type = None
        
        # 5. 连接池和连接管理相关属性 (基于主连接)
        self.use_connection_pool = config.get('use_connection_pool', True) if config else True
        self.max_connections = config.get('max_connections', 10) if config else 10  # 增加默认连接数
        self.connection_pool = None
        self.connection_retry_attempts = config.get('connection_retry_attempts', 3) if config else 3

        # 6. [新增] 调试模式
        self.debug_mode = config.get('debug', False) if config else False
        if self.debug_mode:
            print("🚀 DEBUG MODE IS ENABLED. RAG context will be printed to the console.")
    
        # 7. [核心修改] 集中管理业务元数据，使其在整个实例中可用
        self.table_metadata = {
            "bsd_station": {"business_name": "站点信息表", "description": "存储各个监测站点的基础信息，如名称、编码、经纬度、地址、状态等。", "relations": "通过 `areacode` 与 `bsd_region` 表关联。"},
            "bsd_region": {"business_name": "区域信息表", "description": "存储行政区域的层级关系，如省、市、区。", "relations": "可通过 `parentid` 进行自关联，实现层级查询。"},
            "dat_station_day": {"business_name": "站点日均值表", "description": "存储每个站点每天的各类污染物浓度日均值和AQI相关数据。", "relations": "通过 `code` 与 `bsd_station.stationcode` 或 `bsd_station.uniquecode` 关联。"},
            "dat_city_day": {"business_name": "城市日均值表", "description": "存储每个城市每天的污染物平均浓度和AQI。", "relations": "通过 `code` 与 `bsd_region.areacode` 关联。"},
            "dat_station_hour": {"business_name": "站点小时表", "description": "存储每个站点每小时的各类污染物浓度、气象数据以及AQI。", "relations": "通过 `code` 与 `bsd_station.stationcode` 或 `bsd_station.uniquecode` 关联。表名通常按年份切分，例如 `dat_station_hour_2024`。"},
            "dat_city_hour": {"business_name": "城市小时表", "description": "存储每个城市每小时的污染物浓度。", "relations": "通过 `code` 与 `bsd_region.areacode` 关联。"}
        }
        self.field_mappings = {
            # --- 通用字段 ---
            'id': '自增主键',
            'name': '名称（如站点/区县/城市名称）',
            'code': '编码（如站点/区县/城市编码）',
            'areacode': '区域编码',
            'areaname': '区域名称',
            'longitude': '经度',
            'latitude': '纬度',
            'timepoint': '时间点',
            'datatype': '数据类型（0=原始实况, 1=审核实况, 2=原始标况, 3=审核标况）',
            'orderid': '排序ID',
            'createtime': '创建时间',
            'createuser': '创建用户',
            'updatetime': '更新时间',
            'updateuser': '更新用户',
            # --- bsd_station (站点信息表) ---
            'positionname': '站点名称',
            'uniquecode': '唯一编码',
            'stationcode': '站点编码',
            'stationpic': '站点图片路径',
            'address': '站点地址',
            'pollutantcodes': '污染物编码列表',
            'stationtypeid': '站点类型ID',
            'status': '状态（如站点启用/禁用）',
            'builddate': '建站日期',
            'phone': '联系电话',
            'manager': '管理人员',
            'description': '描述',
            'iscontrast': '是否为对比站点',
            'ismonitor': '是否正在监测',
            'ispublish': '是否发布数据',
            'stoptime': '停止监测时间',
            'mn': '监测点编号',
            'parkcode': '园区编码',
            'towncode': '乡镇编码',
            'stationmultitypeid': '站点多类型ID',
            # --- bsd_region (区域信息表) ---
            'parentid': '父级区域ID',
            'areajc': '区域简称',
            'level': '区域级别',
            'weathercode': '气象编码',
            # --- 数据表 (dat_*) ---
            'so2': '二氧化硫浓度',
            'no2': '二氧化氮浓度',
            'pm10': 'PM10浓度',
            'co': '一氧化碳浓度',
            'o3': '臭氧浓度',
            'pm2_5': 'PM2.5浓度',
            'no': '一氧化氮浓度',
            'nox': '氮氧化物浓度',
            'o3_8h': '臭氧8小时滑动平均值',
            'windspeed': '风速',
            'winddirect': '风向',
            'pressure': '气压',
            'temperature': '温度',
            'humidity': '湿度',
            'rainfall': '降雨量',
            'visibility': '能见度',
            'precipitation': '降水量',
            'pm1': 'PM1浓度',
            'co2': '二氧化碳浓度',
            'ch4': '甲烷浓度',
            'thc': '总烃浓度',
            'nmhc': '非甲烷烃浓度',
            'so2_mark': '二氧化硫数据标记',
            'no2_mark': '二氧化氮数据标记',
            'pm10_mark': 'PM10数据标记',
            'co_mark': '一氧化碳数据标记',
            'o3_mark': '臭氧数据标记',
            'o3_8h_mark': '臭氧8小时数据标记',
            'pm2_5_mark': 'PM2.5数据标记',
            'no_mark': '一氧化氮数据标记',
            'nox_mark': '氮氧化物数据标记',
            'windspeed_mark': '风速数据标记',
            'winddirect_mark': '风向数据标记',
            'pressure_mark': '气压数据标记',
            'temperature_mark': '温度数据标记',
            'humidity_mark': '湿度数据标记',
            'rainfall_mark': '降雨量数据标记',
            'visibility_mark': '能见度数据标记',
            'precipitation_mark': '降水量数据标记',
            'pm1_mark': 'PM1数据标记',
            'co2_mark': '二氧化碳数据标记',
            'ch4_mark': '甲烷数据标记',
            'thc_mark': '总烃数据标记',
            'nmhc_mark': '非甲烷烃数据标记',
            'so2_iaqi': '二氧化硫IAQI值',
            'no2_iaqi': '二氧化氮IAQI值',
            'pm10_iaqi': 'PM10 IAQI值',
            'co_iaqi': '一氧化碳IAQI值',
            'o3_iaqi': '臭氧IAQI值',
            'pm2_5_iaqi': 'PM2.5 IAQI值',
            'aqi': '空气质量指数（AQI）',
            'qualitytype': '空气质量类型（优、良、轻度污染等）',
            'primarypollutant': '首要污染物'
        }

        # [新增] 从配置中加载RAG相关参数，作为 self.kwargs
        self.kwargs = config.get('rag_settings', {}) if config else {}

        # [新增] 模糊匹配阈值
        self.similarity_threshold = config.get('fuzzy_matching', {}).get('similarity_threshold', 80)

        # [新增] 通用字段业务含义映射
        if config and 'field_mappings' in config:
            self.field_mappings.update(config['field_mappings'])

        # [新增] 将站点信息加载到内存
        self.station_info_data = []
        self._load_station_info()

    def _load_station_info(self, file_path='station_info.json'):
        """[新增] 将站点信息从JSON文件加载到内存中。"""
        print(f"--- 正在从 '{file_path}' 加载站点信息到内存 ---")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data_obj = json.load(f)
            
            if isinstance(data_obj, dict) and 'results' in data_obj:
                self.station_info_data = data_obj['results']
                print(f"✅ 成功加载 {len(self.station_info_data)} 条站点记录。")
            elif isinstance(data_obj, list):
                 self.station_info_data = data_obj
                 print(f"✅ 成功加载 {len(self.station_info_data)} 条站点记录。")
            else:
                print(f"⚠️ 警告: 无法在 '{file_path}' 中找到站点列表。期望的格式是一个列表，或是一个包含 'results' 键的字典。")
        except FileNotFoundError:
            print(f"⚠️ 警告: 站点信息文件 '{file_path}' 未找到。程序将继续运行，但无法提供站点上下文。")
        except json.JSONDecodeError as e:
            print(f"❌ 错误: 解析站点信息文件 '{file_path}' 失败: {e}")
        except Exception as e:
            print(f"❌ 读取站点信息文件时发生未知错误: {e}")

    def _format_station_info_for_prompt(self, station: dict) -> str:
        """[新增] 将单个站点字典格式化为用于提示词上下文的可读字符串。"""
        name = station.get('站点名称')
        if not name: return ""
        
        parts = [f"关于站点'{name}'的信息："]
        details = []
        uniquecode = station.get('唯一编码')
        longitude = station.get('经度')
        latitude = station.get('纬度')
        city = station.get('城市名称', '未知')
        station_type_id = station.get('站点类型ID')

        if uniquecode: details.append(f"其唯一编码是'{uniquecode}'")
        if longitude and latitude: details.append(f"地理坐标为经度{longitude}、纬度{latitude}")
        if city: details.append(f"所属城市为'{city}'")
        if station_type_id is not None: details.append(f"站点类型ID为{station_type_id}")
        
        if not details: return ""
        return " ".join(parts) + "，".join(details) + "。"

    def _get_station_info_context_programmatically(self, entities: dict) -> str:
        """
        [重构] 通过模糊匹配从内存数据中筛选站点信息。
        使用 rapidfuzz 计算相似度，并根据配置的阈值进行筛选。
        """
        if not self.station_info_data:
            return "无站点信息可供查询。"

        # 从实体中提取用于搜索的关键词
        raw_keywords = entities.get('locations', []) + entities.get('other_terms', [])
        if not raw_keywords:
            return "未在问题中识别出需要查询的站点或城市。"
        
        # 使用原始关键词进行日志记录，不进行规范化
        print(f"正在基于关键词 {raw_keywords} 进行模糊匹配...")
        
        matched_stations = []
        added_station_codes = set()

        for station in self.station_info_data:
            station_name = station.get('站点名称', '')
            city_name = station.get('城市名称', '')
            station_code = station.get('唯一编码')

            if not station_code or station_code in added_station_codes:
                continue
            
            # 如果没有城市和站点名，则跳过
            if not station_name and not city_name:
                continue

            # [核心修改] 计算每个关键词与城市名和站点名的最高相似度
            # 使用 ratio 匹配城市名，适合匹配完整的词
            best_city_score = max((fuzz.ratio(kw, city_name) for kw in raw_keywords if kw and city_name), default=0)
            
            # 使用 partial_ratio 匹配站点名，适合查找部分匹配
            best_station_score = max((fuzz.partial_ratio(kw, station_name) for kw in raw_keywords if kw and station_name), default=0)

            # 如果任一分数达到阈值，则认为匹配
            if best_city_score >= self.similarity_threshold or best_station_score >= self.similarity_threshold:
                matched_stations.append(station)
                added_station_codes.add(station_code)

        if not matched_stations:
            return f"未能根据关键词 '{', '.join(raw_keywords)}' 和相似度阈值 '{self.similarity_threshold}' 找到匹配的站点信息。"
        
        print(f"✅ 模糊匹配成功，找到 {len(matched_stations)} 个相关站点。")
        
        # 格式化找到的站点信息
        context_parts = [self._format_station_info_for_prompt(s) for s in matched_stations]
        # 限制最终上下文的长度，防止超出限制
        return "\n---\n".join(filter(None, context_parts[:20])) # 最多返回20条

    def _detect_db_type(self, db_config):
        """
        根据配置检测数据库类型
        """
        if not db_config:
            return None
        
        # 检查是否有 SQL Server 特有的配置项
        if 'driver' in db_config or 'server' in db_config or 'host' in db_config:
            if not PYODBC_AVAILABLE:
                raise ImportError("要连接到 SQL Server，请安装 pyodbc 包: pip install pyodbc")
            return "sqlserver"
        
        # 默认为 MySQL
        if not MYSQL_AVAILABLE:
            raise ImportError("要连接到 MySQL，请安装 mysql-connector-python 包: pip install mysql-connector-python")
        return "mysql"

    def init_connection_pool(self):
        """初始化连接池"""
        if not self.use_connection_pool or not self.db_primary_connection_config:
            print("未启用连接池或缺少主数据库配置")
            return
            
        if self.connection_pool:
            # 已存在连接池
            print(f"连接池已存在，跳过初始化，当前连接池: {type(self.connection_pool).__name__}")
            return
            
        try:
            if self.db_type == "mysql":
                if not MYSQL_AVAILABLE:
                    raise ImportError("要使用MySQL连接池，请安装mysql-connector-python")
                pool_config = self.db_primary_connection_config.copy()
                pool_config['pool_name'] = 'vanna_pool'
                pool_config['pool_size'] = self.max_connections
                self.connection_pool = MySQLConnectionPool(**pool_config)
                print(f"MySQL连接池初始化成功，最大连接数: {self.max_connections}")
            elif self.db_type == "sqlserver":
                if not PYODBC_AVAILABLE:
                    raise ImportError("要使用SQL Server连接池，请安装pyodbc")
                    
                # 创建连接字符串和连接创建器
                def create_connection():
                    # [修改] 使用正确的配置键并处理遗留键
                    conn_str_parts = []
                    if 'driver' in self.db_primary_connection_config: conn_str_parts.append(f"DRIVER={self.db_primary_connection_config['driver']}")
                    if 'host' in self.db_primary_connection_config or 'server' in self.db_primary_connection_config: conn_str_parts.append(f"SERVER={self.db_primary_connection_config.get('host') or self.db_primary_connection_config.get('server')}")
                    if 'dbname' in self.db_primary_connection_config or 'database' in self.db_primary_connection_config: conn_str_parts.append(f"DATABASE={self.db_primary_connection_config.get('dbname') or self.db_primary_connection_config.get('database')}")
                    if 'user' in self.db_primary_connection_config or 'uid' in self.db_primary_connection_config: conn_str_parts.append(f"UID={self.db_primary_connection_config.get('user') or self.db_primary_connection_config.get('uid')}")
                    if 'password' in self.db_primary_connection_config or 'pwd' in self.db_primary_connection_config: conn_str_parts.append(f"PWD={self.db_primary_connection_config.get('password') or self.db_primary_connection_config.get('pwd')}")
                    
                    # [最终修改] 强制启用加密并信任证书，以激活 odbcinst.ini 中的 MinTLS 设置
                    conn_str_parts.append("TrustServerCertificate=yes")
                    conn_str_parts.append("Encrypt=yes")
                    conn_str = ";".join(conn_str_parts)
                    print(f"sql server链接字符串: {conn_str}") # [新增] 调试输出

                    # 增加重试逻辑
                    for attempt in range(1, self.connection_retry_attempts + 1):
                        try:
                            # 尝试连接，增加超时
                            print(f"正在尝试创建新连接 (第 {attempt}/{self.connection_retry_attempts} 次)...")
                            return pyodbc.connect(conn_str, timeout=5)
                        except pyodbc.Error as e:
                            print(f"创建新连接尝试 {attempt}/{self.connection_retry_attempts} 失败: {e}")
                            if attempt >= self.connection_retry_attempts:
                                raise  # 最后一次尝试失败，重新引发异常
                            time.sleep(1) # 等待1秒再重试
                    
                self.connection_pool = SimpleConnectionPool(self.max_connections, create_connection)
                print(f"SQL Server连接池初始化成功，最大连接数: {self.max_connections}")
        except Exception as e:
            print(f"连接池初始化失败: {e}")
            self.connection_pool = None
            
    @contextmanager
    def get_db_connection(self):
        """获取数据库连接的上下文管理器"""
        connection = None
        retry_count = 0
        
        while retry_count < self.connection_retry_attempts:
            try:
                if self.use_connection_pool and self.connection_pool:
                    # 使用连接池获取连接
                    if self.db_type == "mysql":
                        connection = self.connection_pool.get_connection()
                    else:  # sqlserver
                        connection = self.connection_pool.get_connection()
                else:
                    # 不使用连接池，直接创建连接
                    if self.db_type == "mysql":
                        connection = mysql.connector.connect(**self.db_primary_connection_config)
                    elif self.db_type == "sqlserver":
                        # [修改] 使用正确的配置键并处理遗留键
                        conn_str_parts = []
                        if 'driver' in self.db_primary_connection_config: conn_str_parts.append(f"DRIVER={self.db_primary_connection_config['driver']}")
                        if 'host' in self.db_primary_connection_config or 'server' in self.db_primary_connection_config: conn_str_parts.append(f"SERVER={self.db_primary_connection_config.get('host') or self.db_primary_connection_config.get('server')}")
                        if 'dbname' in self.db_primary_connection_config or 'database' in self.db_primary_connection_config: conn_str_parts.append(f"DATABASE={self.db_primary_connection_config.get('dbname') or self.db_primary_connection_config.get('database')}")
                        if 'user' in self.db_primary_connection_config or 'uid' in self.db_primary_connection_config: conn_str_parts.append(f"UID={self.db_primary_connection_config.get('user') or self.db_primary_connection_config.get('uid')}")
                        if 'password' in self.db_primary_connection_config or 'pwd' in self.db_primary_connection_config: conn_str_parts.append(f"PWD={self.db_primary_connection_config.get('password') or self.db_primary_connection_config.get('pwd')}")
                        
                        # [最终修改] 强制启用加密并信任证书，以激活 odbcinst.ini 中的 MinTLS 设置
                        conn_str_parts.append("TrustServerCertificate=yes")
                        conn_str_parts.append("Encrypt=yes")
                        conn_str = ";".join(conn_str_parts)
                        print(f"sql server链接字符串: {conn_str}") # [新增] 调试输出
                        connection = pyodbc.connect(conn_str, timeout=5)
                
                # 验证连接是否有效
                if self.db_type == "mysql" and not connection.is_connected():
                    raise Exception("MySQL连接无效")
                elif self.db_type == "sqlserver":
                    # 使用查询来验证SQL Server连接
                    try:
                        cursor = connection.cursor()
                        cursor.execute("SELECT 1")
                        cursor.close()
                    except Exception as e:
                        raise Exception(f"SQL Server连接无效: {e}")
                    
                break  # 连接成功，退出重试循环
            except Exception as e:
                retry_count += 1
                print(f"数据库连接尝试 {retry_count}/{self.connection_retry_attempts} 失败: {e}")
                if retry_count >= self.connection_retry_attempts:
                    raise Exception(f"数据库连接失败，已重试 {self.connection_retry_attempts} 次: {e}")
                time.sleep(1)  # 重试前等待1秒
        
        try:
            yield connection
        finally:
            try:
                if self.use_connection_pool and self.connection_pool:
                    # 归还连接到连接池
                    if self.db_type == "mysql":
                        pass  # MySQL连接池会自动管理
                    else:  # sqlserver
                        self.connection_pool.release(connection)
                else:
                    # 不使用连接池，关闭连接
                    connection.close()
            except Exception as e:
                print(f"关闭数据库连接出错: {e}")

    @contextmanager
    def get_cursor(self):
        """获取数据库游标的上下文管理器"""
        with self.get_db_connection() as connection:
            cursor = None
            try:
                cursor = connection.cursor()
                yield cursor
                connection.commit()  # 提交事务
            except Exception as e:
                try:
                    connection.rollback()  # 回滚事务
                except:
                    pass
                raise e
            finally:
                if cursor:
                    try:
                        cursor.close()
                    except:
                        pass

    def connect_to_db(self):
        """此方法已不再使用，保留仅为兼容"""
        # 初始化连接池
        self.init_connection_pool()

    def train_on_database(self):
        """
        [重构] 遍历 `training_connections` 列表，为每个数据库建立独立连接进行训练，
        以确保元数据获取的准确性和隔离性。
        """
        print("--- 开始数据库训练流程 ---")

        # [修改] 元数据已移动到 __init__ 中作为实例属性，此处不再定义

        # --- [新增] 训练所有字段的通用业务知识 ---
        print("\n--- 正在训练通用的字段业务知识 ---")
        try:
            field_doc_str = "以下是数据库中一些常见字段的业务含义解释：\n"
            field_doc_str += "\n".join([f"- 字段 `{field}` 代表 '{desc}'" for field, desc in self.field_mappings.items()])
            super().train(documentation=field_doc_str)
            print("✅ 通用字段业务知识训练完成。")
        except Exception as e:
            print(f"[错误] 训练通用字段业务知识时失败: {e}")

        # [修改] 不再遍历 training_connections，只使用主连接训练 DDL
        if not self.db_primary_connection_config:
            print("[警告] `database` 或 `database.primary_connection` 未配置，跳过 DDL 训练。")
            print("\n--- 数据库训练流程已完成 ---")
            return

        conn_config = self.db_primary_connection_config
        db_name = conn_config.get('database') or conn_config.get('dbname') # 兼容不同键名
        db_type = self._detect_db_type(conn_config)
        print(f"\n--- 正在为主要业务数据库 '{db_name}' ({db_type}) 进行 DDL 训练 ---")

        try:
            # [核心修改] 为当前数据库建立一个临时的、独立的连接
            with self._get_temp_connection(conn_config) as temp_conn:
                cursor = temp_conn.cursor()
                
                # 1. 获取当前库的所有表
                all_tables_in_db = self._get_tables_for_db(cursor, db_type, db_name)
                print(f"在数据库 '{db_name}' 中找到 {len(all_tables_in_db)} 个表: {all_tables_in_db}")

                # 2. 遍历并训练每个表的 DDL
                for schema, table in all_tables_in_db:
                    # 准备业务元数据注释
                    metadata_key = self._get_metadata_key(table)
                    metadata = self.table_metadata.get(metadata_key)
                    ddl_header = self._build_ddl_header(metadata)

                    # 获取并丰富DDL
                    ddl = self._get_ddl_for_table(cursor, db_type, db_name, schema, table, self.field_mappings)
                    if ddl:
                        enriched_ddl = f"{ddl_header}{ddl}"
                        print(f"训练DDL: {enriched_ddl.strip()}")
                        super().train(ddl=enriched_ddl)
                        
                        # --- [核心修改] 为每个表额外训练一条清晰的、可检索的业务知识 ---
                        if metadata:
                            table_doc = f"表 '{table}' (业务名: {metadata.get('business_name', 'N/A')}) 用于: {metadata.get('description', 'N/A')}. 与其他表的关联关系: {metadata.get('relations', 'N/A')}"
                            print(f"训练业务知识: {table_doc}")
                            super().train(documentation=table_doc)
                        # --- [核心修改结束] ---
                    else:
                        print(f"警告: 未能获取表 {db_name}.{schema}.{table} 的DDL")
                
                cursor.close()
        except Exception as e:
            print(f"[错误] 训练数据库 '{db_name}' 时失败: {e}")
        
        print("\n--- 数据库训练流程已完成 ---")

    # --- [新增] 以下为 train_on_database 的辅助方法 ---

    @contextmanager
    def _get_temp_connection(self, conn_config: dict):
        """根据给定的配置创建一个临时的数据库连接。"""
        conn = None
        db_type = self._detect_db_type(conn_config)
        try:
            if db_type == "mysql":
                conn = mysql.connector.connect(**conn_config)
            elif db_type == "sqlserver":
                conn_str_parts = []
                if 'driver' in conn_config: conn_str_parts.append(f"DRIVER={conn_config['driver']}")
                if 'server' in conn_config: conn_str_parts.append(f"SERVER={conn_config['server']}")
                if 'database' in conn_config: conn_str_parts.append(f"DATABASE={conn_config['database']}")
                if 'uid' in conn_config: conn_str_parts.append(f"UID={conn_config['uid']}")
                if 'pwd' in conn_config: conn_str_parts.append(f"PWD={conn_config['pwd']}")
                conn_str_parts.append("TrustServerCertificate=yes")
                conn_str_parts.append("Encrypt=yes")
                conn_str = ";".join(conn_str_parts)
                conn = pyodbc.connect(conn_str, timeout=5)
            
            yield conn
        finally:
            if conn:
                conn.close()

    def _get_tables_for_db(self, cursor, db_type: str, db_name: str) -> list:
        """获取指定数据库中的所有表。返回 [(schema, table_name), ...]"""
        if db_type == "mysql":
            cursor.execute("SHOW TABLES")
            return [(None, table[0]) for table in cursor.fetchall()]
        elif db_type == "sqlserver":
            # 对于SQL Server，因为连接已经指向特定DB，所以不需要db_name前缀
            query = "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
            cursor.execute(query)
            return cursor.fetchall()
        return []

    def _get_metadata_key(self, table_name: str) -> str:
        """处理分表情况，返回用于元数据字典的键。"""
        if table_name.startswith("dat_station_hour"):
            return "dat_station_hour"
        if table_name.startswith("dat_city_hour"):
            return "dat_city_hour"
        return table_name

    def _build_ddl_header(self, metadata: dict) -> str:
        """构建DDL的注释头。"""
        if not metadata:
            return ""
        return f"-- 业务名称: {metadata.get('business_name', 'N/A')}\n-- 功能描述: {metadata.get('description', 'N/A')}\n-- 关联关系: {metadata.get('relations', 'N/A')}\n"

    def _get_ddl_for_table(self, cursor, db_type: str, db_name: str, schema: str, table: str, field_mappings: dict) -> str:
        """为单个表生成DDL字符串，并附带字段注释。"""
        try:
            if db_type == "mysql":
                cursor.execute(f"SHOW CREATE TABLE `{table}`")
                return cursor.fetchone()[1]
            elif db_type == "sqlserver":
                # 对于SQL Server，DDL需要包含数据库和schema名以确保全局唯一
                full_table_name = f"[{db_name}].[{schema}].[{table}]"
                col_sql = f"SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE FROM [{db_name}].INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{table}' AND TABLE_SCHEMA = '{schema}' ORDER BY ORDINAL_POSITION"
                cursor.execute(col_sql)
                columns_info = cursor.fetchall()

                ddl_parts = []
                for col in columns_info:
                    col_name, data_type, char_max_len, is_nullable = col
                    col_def = f"  [{col_name}] {data_type}"
                    if char_max_len is not None: col_def += f"({char_max_len})"
                    if is_nullable == 'NO': col_def += " NOT NULL"
                    
                    # [新增] 添加字段的中文注释
                    comment = field_mappings.get(col_name.lower())
                    if comment:
                        col_def += f" -- {comment}"

                    ddl_parts.append(col_def)

                pk_sql = f"SELECT KCU.COLUMN_NAME FROM [{db_name}].INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS TC JOIN [{db_name}].INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS KCU ON TC.CONSTRAINT_NAME = KCU.CONSTRAINT_NAME WHERE TC.TABLE_NAME = '{table}' AND TC.TABLE_SCHEMA = '{schema}' AND TC.CONSTRAINT_TYPE = 'PRIMARY KEY' ORDER BY KCU.ORDINAL_POSITION"
                cursor.execute(pk_sql)
                pk_columns = [col[0] for col in cursor.fetchall()]
                if pk_columns:
                    ddl_parts.append(f"  PRIMARY KEY ({', '.join([f'[{col}]' for col in pk_columns])})")

                ddl_content = ',\n'.join(ddl_parts)
                return f"CREATE TABLE {full_table_name} (\n{ddl_content}\n);"
        except Exception as e:
            print(f"为表 {db_name}.{schema}.{table} 生成DDL时出错: {e}")
            return None

    def add_sql_example(self, question: str, sql: str):
        super().train(question=question, sql=sql)

    def get_sample_data(self):
        """
        从每个表中抽取1个样本数据（最多10行）
        返回格式：{
            "table_name": [
                {"column1": value1, "column2": value2, ...},
                ...
            ],
            ...
        }
        """
        sample_data = {}
        
        try:
            with self.get_cursor() as cursor:
                # [修改] 从所有配置的数据库中获取表名
                all_tables = []
                if self.db_type == "mysql":
                    for db_name in self.db_training_connections:
                        try:
                            cursor.execute(f"USE `{db_name}`")
                            cursor.execute("SHOW TABLES")
                            # 存储 (数据库名, schema名, 表名)
                            tables_in_db = [(db_name, None, table[0]) for table in cursor.fetchall()]
                            all_tables.extend(tables_in_db)
                        except Exception as e:
                            print(f"无法访问MySQL数据库 '{db_name}': {e}")
                elif self.db_type == "sqlserver":
                    for db_name in self.db_training_connections:
                        try:
                            query = f"SELECT TABLE_SCHEMA, TABLE_NAME FROM [{db_name}].INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
                            cursor.execute(query)
                            tables_in_db = [(db_name, schema, table) for schema, table in cursor.fetchall()]
                            all_tables.extend(tables_in_db)
                        except Exception as e:
                            print(f"无法从SQL Server数据库 '{db_name}' 获取表: {e}")
                else:
                    raise ValueError(f"不支持的数据库类型: {self.db_type}")
                    
                # 处理每个表
                for db_name, schema, table in all_tables:
                    try:
                        # [修改] 使用完全限定名来唯一标识表
                        full_table_name_key = f"{db_name}.{schema}.{table}" if schema else f"{db_name}.{table}"
                        
                        # 根据数据库类型构建查询
                        if self.db_type == "mysql":
                            sample_query = f"SELECT * FROM `{db_name}`.`{table}` LIMIT 10"
                        elif self.db_type == "sqlserver":
                            sample_query = f"SELECT TOP 10 * FROM [{db_name}].[{schema}].[{table}]"
                        
                        # 执行查询
                        cursor.execute(sample_query)
                        
                        # 获取列名
                        columns = [column[0] for column in cursor.description]
                        
                        # 获取结果并转换为字典列表
                        rows = cursor.fetchall()
                        table_results = []
                        for row in rows:
                            table_results.append(dict(zip(columns, row)))
                        
                        if table_results:  # 只有当表有数据时才添加
                            sample_data[full_table_name_key] = table_results
                    except Exception as err:
                        print(f"从表 {full_table_name_key} 获取样本数据时出错: {err}")
                        continue
                
        except Exception as err:
            print(f"获取样本数据时出错: {err}")
            
        return sample_data

    def _perform_rag_retrieval(self, question: str, **kwargs) -> dict:
        """
        [重构] 采用确定性程序化匹配站点信息，并结合RAG检索其他知识的策略。
        """
        print("--- 开始使用新的混合检索策略（程序化匹配 + RAG） ---")

        # 步骤 1：问题意图分析与结构化实体提取
        structured_entities = self._extract_entities_for_rag(question)
        
        # 步骤 2: [核心修改] 通过程序化方式获取站点信息上下文
        station_info_context_str = self._get_station_info_context_programmatically(structured_entities)

        # 步骤 3: 并行执行剩余的RAG检索（DDL, 通用文档, SQL）
        all_entities = [item for sublist in structured_entities.values() for item in sublist]
        general_entities_query = ' '.join(all_entities) if all_entities else question
        print(f"实体用于DDL和SQL检索: {general_entities_query}")

        # 构建专门用于通用文档(业务知识)检索的查询
        general_query_terms = structured_entities.get('other_terms', []) + structured_entities.get('columns', [])
        doc_query = ' '.join(general_query_terms) if general_query_terms else question
        print(f"实体用于通用文档检索: {doc_query}")

        # 从 self.kwargs (config.yaml) 中获取召回数量，并提供默认值
        n_ddl = self.kwargs.get('n_ddl', 4)
        n_docs = self.kwargs.get('n_docs', 10)
        n_sql = self.kwargs.get('n_sql', 4)
        print(f"RAG召回数量配置: DDL={n_ddl}, Docs={n_docs}, SQL={n_sql}")

        # 定义并行检索任务
        ddl_results = []
        doc_results = []
        sql_results = []

        def retrieve_ddl():
            all_ddls = self.get_related_ddl(question=general_entities_query, n_results=n_ddl)
            if all_ddls:
                ddl_results.extend(all_ddls)

        def retrieve_docs():
            # 此函数现在只检索通用的业务知识，因为站点信息已通过程序化方式处理
            all_docs = self.get_related_documentation(question=doc_query, n_results=n_docs)
            if all_docs:
                doc_results.extend(all_docs)

        def retrieve_sql():
            sql_list = self.get_similar_question_sql(question=general_entities_query, n_results=n_sql)
            if sql_list:
                # 格式化
                formatted_sqls = [f"Q: {item['question']}\nA: {item['sql']}" for item in sql_list]
                sql_results.extend(formatted_sqls)

        threads = [
            Thread(target=retrieve_ddl),
            Thread(target=retrieve_docs),
            Thread(target=retrieve_sql),
        ]

        # 启动并等待所有线程完成
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 步骤 4：组合并过滤RAG上下文
        print(f"✅ 已成功检索到 {len(ddl_results)} 条DDL信息。")
        print(f"✅ 已成功检索到 {len(doc_results)} 条通用业务知识。")
        print(f"✅ 已成功检索到 {len(sql_results)} 条相似SQL查询。")
        
        ddl_context_str = "\n---\n".join(list(dict.fromkeys(ddl_results)))
        doc_context_str = "\n---\n".join(list(dict.fromkeys(doc_results)))
        sql_context_str = "\n---\n".join(list(dict.fromkeys(sql_results)))

        rag_context_obj = {
            "station_info_context": station_info_context_str,
            "ddl_context": ddl_context_str,
            "doc_context": doc_context_str,
            "sql_context": sql_context_str,
        }

        if self.debug_mode:
            debug_context_str = self._format_rag_context_for_prompt(rag_context_obj)
            print("\n" + "="*50)
            print("🕵️  DEBUGGER: RAG CONTEXT TO BE SENT TO LLM 🕵️")
            print("="*50)
            print(debug_context_str)
            print("\n" + "="*50 + "\n")
        
        return rag_context_obj

    def generate_sql(self, question: str, history: list = None, **kwargs) -> tuple[str, str, dict]:
        """
        [重构] 采用多路并行、各司其职的混合检索策略生成SQL。
        该方法现在主要负责编排，核心RAG逻辑已移至 _perform_rag_retrieval。
        """
        # --- 步骤 1: 加载外部的提示词模板 ---
        try:
            with open('prompt_template.txt', 'r', encoding='utf-8') as f:
                prompt_template = f.read()
        except FileNotFoundError:
            print("[错误] prompt_template.txt 文件未找到。无法继续生成SQL。")
            return '{"error": "Configuration file prompt_template.txt not found."}', '{"error": "Configuration file prompt_template.txt not found."}', {}

        # --- 步骤 2: 执行RAG检索 ---
        rag_context_obj = self._perform_rag_retrieval(question, **kwargs)

        # --- 步骤 3：将动态上下文注入到模板中 ---
        try:
            # [新增] 获取当前主连接的数据库名
            primary_db_name = self.db_primary_connection_config.get('database') or self.db_primary_connection_config.get('dbname', 'default_db')

            final_prompt = prompt_template.format(
                primary_database_name=primary_db_name,  # 注入主数据库名
                db_type=self.db_type or '数据库',
                station_info_context=rag_context_obj["station_info_context"],
                ddl_context=rag_context_obj["ddl_context"],
                doc_context=rag_context_obj["doc_context"],
                sql_context=rag_context_obj["sql_context"],
                history_context=self.stringify_history(history),
                question=question  # 确保question参数被正确传递
            )
        except KeyError as e:
            print(f"[错误] 格式化提示模板时出错: {e}. 检查prompt_template.txt中的占位符是否与代码中的参数匹配。")
            return f'{{"error": "Error formatting prompt template: {e}"}}', f'{{"error": "Error formatting prompt template: {e}"}}', rag_context_obj
        except Exception as e:
            print(f"[错误] 格式化提示模板时出现未知错误: {e}")
            return f'{{"error": "Unknown error formatting prompt template: {e}"}}', f'{{"error": "Unknown error formatting prompt template: {e}"}}', rag_context_obj

        # --- 步骤 4: 准备并提交给大模型 ---
        messages = self._get_common_messages()
        messages.append({"role": "user", "content": final_prompt})

        print("正在提交给大模型生成最终SQL...")
        llm_response = self.submit_prompt(messages)
        
        print("收到大模型响应，正在清理...")
        sql = self._clean_llm_response(llm_response)
        print(f"模型已生成SQL: {sql}")

        # [修复] 同时返回 rag_context_obj 以便上层函数在需要时可以复用
        return sql, llm_response, rag_context_obj

    def ask(self, question: str, history: list = None, **kwargs) -> str:
        # 这个方法现在会调用我们重写过的 generate_sql
        # 注意：它的返回值可能是 SQL 字符串，也可能是包含澄清问题的字典
        return self.generate_sql(question=question, history=history, **kwargs)[0]

    def _execute_plan(self, plan_obj: dict) -> tuple[dict, any]:
        """
        [新增] 执行一个结构化的查询计划。
        """
        results_context = {}
        final_result = {"status": "success", "results": {}, "error": None}
        
        # 定义一个pysqldf可用的局部函数环境
        # 这种方式比直接使用 locals() 或 globals() 更安全
        pysqldf_env = {"pd": pd} 

        try:
            # 按照计划顺序执行
            for step in sorted(plan_obj.get("plan", []), key=lambda x: x["step"]):
                step_query = step["query"]
                output_var = step["output_variable"]
                print(f"正在执行计划步骤 {step['step']}: {step['description']}")
                print(f"查询: {step_query}")

                # 检查是否是针对DataFrame的查询
                if '@' in step_query:
                    # 使用正则表达式查找所有 @variable 引用
                    referenced_vars = re.findall(r'@(\w+)', step_query)
                    
                    # 准备pysqldf的环境，将DataFrame注入
                    for var in referenced_vars:
                        if var in results_context:
                            # 将DataFrame赋值给一个与变量名同名的键
                            pysqldf_env[var] = results_context[var]
                        else:
                            raise ValueError(f"计划执行错误: 步骤 {step['step']} 引用了未定义的变量 @{var}")
                    
                    # 使用pandasql执行查询
                    # query现在可以直接引用变量名，因为它们在pysqldf_env中
                    clean_query = step_query.replace('@', '')
                    step_df = sqldf(clean_query, pysqldf_env)
                else:
                    # 是普通数据库查询
                    step_df = self.run_sql(step_query)
                
                # 存储结果
                results_context[output_var] = step_df
                print(f"步骤 {step['step']} 完成，结果已存入变量: {output_var}")

            # 根据 final_presentation 组织最终结果
            presentation = plan_obj.get("final_presentation", {})
            ordered_results = {}
            if presentation.get("type") == "multiple_results":
                for var_name in presentation.get("results_order", []):
                    if var_name in results_context:
                        df = results_context[var_name]
                        ordered_results[var_name] = df.to_dict('records') if df is not None else []
            final_result["results"] = ordered_results
            
            # model_response 可以用最后一个DataFrame，或一个包含所有结果的字典
            model_response = {k: v for k, v in results_context.items()}

        except Exception as e:
            print(f"❌ 执行查询计划时出错: {e}")
            final_result["status"] = "error"
            final_result["error"] = f"执行计划失败: {e}"
            model_response = None
            
        return final_result, model_response

    def ask_and_run(self, question: str, history: list = None, visualize: bool = False) -> tuple[dict, any]:
        """
        [重构] 采用新的、基于计划的执行模型。
        - 生成SQL或查询计划。
        - 如果是计划，则执行计划。
        - 如果是简单SQL，则直接执行。
        - 不再使用旧的、脆弱的自我修正逻辑。
        """
        final_result = {"status": "error", "sql": "", "results": [], "error": "Internal Server Error"}
        model_response_data = None
        
        try:
            # --- 步骤 1: 生成SQL或查询计划 ---
            response_str, _, rag_context_obj = self.generate_sql(question=question, history=history)

            # -- 核心调试点 --
            print("\n" + "="*80)
            print("🕵️  DEBUGGER: RAW RESPONSE FROM LLM 🕵️")
            print(f"---BEGIN---\n{response_str}\n---END---")
            print("="*80 + "\n")

            # --- 步骤 2: 分析响应，确定执行路径 (优化逻辑) ---
            cleaned_response = response_str.strip()
            if cleaned_response.startswith('{'):
                # 路径 A: 响应看起来是JSON (查询计划或澄清问题)
                try:
                    parsed_json = json.loads(cleaned_response)
                    
                    if isinstance(parsed_json, dict):
                        if "plan" in parsed_json:
                            print("✅ 检测到查询计划，开始执行...")
                            final_result, model_response_data = self._execute_plan(parsed_json)
                            final_result["sql"] = json.dumps(parsed_json, indent=2, ensure_ascii=False)
                        
                        elif "clarification_needed" in parsed_json:
                            print("⚠️ 模型请求澄清，流程中止。")
                            final_result.update({
                                "status": "clarification_needed", 
                                "message": parsed_json["clarification_needed"],
                                "sql": None, 
                                "error": None,
                                "results": parsed_json
                            })
                            model_response_data = parsed_json
                        
                        else:
                            raise ValueError(f"模型返回了无法识别的JSON指令: {response_str}")
                    else:
                        raise ValueError(f"响应是JSON但不是预期的对象格式: {response_str}")

                except json.JSONDecodeError:
                    # 如果长得像JSON但解析失败，当作简单SQL处理
                    print(f"⚠️ 检测到疑似JSON的响应但解析失败，将作为简单SQL处理: {response_str}")
                    sql = response_str # 使用原始响应
                    final_result["sql"] = sql
                    df = self.run_sql(sql)
                    
                    final_result["results"] = df.to_dict('records') if df is not None else []
                    final_result["status"] = "success"
                    final_result["error"] = None
                    model_response_data = df

            else:
                # 路径 B: 这是一个简单的SQL语句
                print("✅ 检测到简单SQL语句，直接执行...")
                sql = response_str
                final_result["sql"] = sql
                df = self.run_sql(sql)
                
                final_result["results"] = df.to_dict('records') if df is not None else []
                final_result["status"] = "success"
                final_result["error"] = None
                model_response_data = df

        except Exception as e:
            # --- 步骤 3: 统一的错误捕获 ---
            print(f"❌ 在 ask_and_run 流程中发生严重错误: {e}")
            final_result["status"] = "error"
            final_result["error"] = str(e)
            
        # 可视化逻辑 (如果需要)
        if visualize and model_response_data is not None:
            # 确保我们有DataFrame来进行可视化
            df_to_visualize = None
            if isinstance(model_response_data, pd.DataFrame):
                df_to_visualize = model_response_data
            # 如果是计划结果，可以尝试可视化最后一个DataFrame
            elif isinstance(model_response_data, dict):
                last_df_key = next(reversed(model_response_data), None)
                if last_df_key and isinstance(model_response_data[last_df_key], pd.DataFrame):
                    df_to_visualize = model_response_data[last_df_key]
            
            if df_to_visualize is not None and not df_to_visualize.empty:
                 # ... (可视化代码保持不变)
                pass

        return final_result, model_response_data

    def run_sql(self, sql: str) -> pd.DataFrame:
        """
        [重构] 执行给定的SQL查询。
        成功时返回一个Pandas DataFrame。
        失败时，不再捕获异常，而是直接向上抛出，由调用者处理。
        """
        with self.get_cursor() as cursor:
            print(f"Executing SQL in run_sql: {sql}")
            cursor.execute(sql)
            
            # 获取列名
            columns = [column[0] for column in cursor.description]
            
            # 获取结果并转换为DataFrame
            rows = cursor.fetchall()
            # [新增] 将元组列表转换为Pandas DataFrame
            return pd.DataFrame([list(row) for row in rows], columns=columns)

    def get_training_data(self) -> list:
        df = super().get_training_data()
        return [] if df is None else df.to_dict('records')

    def remove_training_data(self, id: str) -> bool:
        return super().remove_training_data(id=id)

    def reset_connection_pool(self):
        """重置连接池状态，关闭所有连接并重新初始化"""
        try:
            print("正在重置数据库连接池...")
            if hasattr(self, 'connection_pool') and self.connection_pool:
                if self.db_type == "sqlserver":
                    self.connection_pool.close_all()
                self.connection_pool = None
            
            # 重新初始化
            self.init_connection_pool()
            return True
        except Exception as e:
            print(f"重置连接池失败: {e}")
            return False
            
    def get_connection_pool_status(self):
        """获取连接池状态信息"""
        status = {
            "enabled": self.use_connection_pool,
            "type": self.db_type,
            "max_connections": self.max_connections,
            "pool_initialized": self.connection_pool is not None
        }
        
        if self.connection_pool:
            if self.db_type == "sqlserver" and isinstance(self.connection_pool, SimpleConnectionPool):
                status.update({
                    "total_connections": len(self.connection_pool.connections),
                    "in_use_connections": len(self.connection_pool.in_use),
                    "available_connections": len(self.connection_pool.connections) - len(self.connection_pool.in_use)
                })
        
        return status

    def correct_sql(self, question: str, sql: str, error_message: str, rag_context_obj: dict, history: list = None) -> str:
        """
        [重构] 基于SQL执行错误和原始RAG上下文来修正SQL，不再进行新的检索。
        """
        print("启动轻量级SQL修正流程...")

        # 1. 格式化RAG上下文和历史对话 (与 generate_sql 保持一致)
        rag_context_str = self._format_rag_context_for_prompt(rag_context_obj)
        history_str = self.stringify_history(history)
        
        # 2. 构建修正Prompt
        system_prompt = f"""你是一个专业的SQL修正机器人。你的任务是根据用户提供的原始问题、上下文信息、失败的SQL查询以及数据库返回的错误信息，来修正SQL。

请严格遵守以下规则：
1.  仔细分析提供的所有信息，特别是数据库错误信息，它是定位问题的关键。
2.  **不要**进行任何新的信息检索或假设。只使用下面提供的上下文。
3.  返回的必须是且仅是一个可以直接在 {self.dialect} 数据库上执行的SQL查询语句。
4.  不要添加任何解释、注释或markdown标记（如 ```sql ... ```）。

这是相关的上下文信息，它包含了表结构(DDL)、业务知识和相似的查询案例:
{rag_context_str}

这是之前的对话历史:
{history_str}
"""

        user_prompt = f"""请根据以下信息修正SQL查询：

- **原始问题**: {question}
- **失败的SQL**: 
```sql
{sql}
```
- **数据库错误**: {error_message}

请提供修正后的SQL查询。
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # 3. 调用LLM进行修正
        try:
            print("正在请求LLM修正SQL...")
            corrected_sql_response = self.submit_prompt(messages)
            corrected_sql = self._clean_llm_response(corrected_sql_response)
            print(f"LLM返回的修正后SQL: \n{corrected_sql}")
            return corrected_sql
        except Exception as e:
            print(f"错误: 调用LLM修正SQL时失败 - {e}")
            # 如果修正失败，可以返回原始的错误SQL，或者抛出异常
            return sql

    def close(self):
        """
        关闭所有数据库连接。
        """
        try:
            print("正在关闭所有数据库连接...")
            if hasattr(self, 'connection_pool') and self.connection_pool:
                if self.db_type == "sqlserver":
                    self.connection_pool.close_all()
                self.connection_pool = None
            
            # 重新初始化
            self.init_connection_pool()
            return True
        except Exception as e:
            print(f"关闭数据库连接时出错: {e}")
            return False

# [新增] 暴露一个单一的、预配置的实例
# 在app.py中，我们将显式调用它的init_connection_pool方法
try:
    config = load_config()
    vanna_service = MyVanna(config)
except FileNotFoundError:
    print("\n[FATAL ERROR] 启动失败：找不到 `config.yaml` 文件！")
    # 创建一个无数据库配置的实例以允许应用启动
    vanna_service = MyVanna()
except Exception as e:
    import traceback
    print(f"\n[FATAL ERROR] 启动失败：初始化服务时遇到未知错误。")
    traceback.print_exc()
    # 创建一个无数据库配置的实例以允许应用启动
    vanna_service = MyVanna() 