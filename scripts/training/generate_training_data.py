import os
import sys
import yaml
import json
import requests
import time

# -- Path setup --
# This ensures that we can import from the 'src' directory by adding the project root to sys.path.
# The script is in Vanna/scripts/training/, so we go up two levels to reach the project root.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.vanna_service import vanna_service, MyVanna, load_config

# --- 配置与常量 ---

# 定义 API 端点
VANNA_API_ENDPOINT = "http://127.0.0.1:9090/add-example"
# 定义要生成的问题数量
NUM_QUESTIONS_TO_GENERATE = 10
# 定义一次性让LLM生成多少个候选问题
QUESTIONS_BATCH_SIZE = 5

# --- 核心功能函数 ---

def get_database_connection(db_config, db_type):
    """根据配置和数据库类型建立并返回数据库连接"""
    try:
        if db_type == "mysql":
            import mysql.connector
            conn = mysql.connector.connect(**db_config)
            print("✅ MySQL 数据库连接成功。")
            return conn, "mysql"
        elif db_type == "sqlserver":
            import pyodbc
            conn_str_parts = []
            if 'driver' in db_config: conn_str_parts.append(f"DRIVER={db_config['driver']}")
            if 'server' in db_config: conn_str_parts.append(f"SERVER={db_config['server']}")
            if 'database' in db_config: conn_str_parts.append(f"DATABASE={db_config['database']}")
            if 'uid' in db_config: conn_str_parts.append(f"UID={db_config['uid']}")
            if 'pwd' in db_config: conn_str_parts.append(f"PWD={db_config['pwd']}")
            
            conn_str_parts.append("TrustServerCertificate=Yes")
            conn_str_parts.append("Encrypt=No")
            
            conn_str = ";".join(conn_str_parts)
            conn = pyodbc.connect(conn_str)
            print(f"✅ SQL Server 数据库 '{db_config.get('database')}' 连接成功。")
            return conn, "sqlserver"
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")
    except Exception as err:
        print(f"❌ 数据库连接失败: {err}")
        raise

def get_schema_ddl(connection, db_type, db_name):
    """
    [修改] 从特定数据库连接中提取所有表的 DDL，并为表名添加数据库前缀。
    """
    print(f"正在为数据库 '{db_name}' 提取 Schema (DDL)...")
    ddls = []
    try:
        cursor = connection.cursor()
        
        if db_type == "mysql":
            cursor.execute("SHOW TABLES")
            tables = [table[0] for table in cursor.fetchall()]
            for table in tables:
                cursor.execute(f"SHOW CREATE TABLE `{table}`")
                ddl = cursor.fetchone()[1]
                if not ddl.startswith(f"CREATE TABLE `{db_name}`"):
                    ddl = ddl.replace(f"CREATE TABLE `{table}`", f"CREATE TABLE `{db_name}`.`{table}`")
                ddls.append(ddl)
        
        elif db_type == "sqlserver":
            cursor.execute("SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
            tables = [(schema, table) for schema, table in cursor.fetchall()]
            
            for schema, table in tables:
                col_sql = f"""
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?
                    ORDER BY ORDINAL_POSITION
                """
                cursor.execute(col_sql, table, schema)
                columns_info = cursor.fetchall()

                ddl_parts = []
                for col in columns_info:
                    col_name, data_type, char_max_len, is_nullable = col
                    col_def = f"[{col_name}] {data_type}"
                    if char_max_len == -1:
                        col_def += "(max)"
                    elif char_max_len is not None:
                        col_def += f"({char_max_len})"
                    if is_nullable == 'NO':
                        col_def += " NOT NULL"
                    ddl_parts.append(col_def)
                
                pk_sql = f"""
                    SELECT KCU.COLUMN_NAME
                    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS TC
                    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS KCU
                        ON TC.CONSTRAINT_NAME = KCU.CONSTRAINT_NAME
                    WHERE TC.TABLE_NAME = ? AND TC.TABLE_SCHEMA = ? AND TC.CONSTRAINT_TYPE = 'PRIMARY KEY'
                    ORDER BY KCU.ORDINAL_POSITION;
                """
                cursor.execute(pk_sql, table, schema)
                pk_columns = [col[0] for col in cursor.fetchall()]
                if pk_columns:
                    ddl_parts.append(f"PRIMARY KEY ({', '.join([f'[{col}]' for col in pk_columns])})")

                ddl = f"CREATE TABLE [{db_name}].[{schema}].[{table}] (\n  " + ',\n  '.join(ddl_parts) + "\n);"
                ddls.append(ddl)
        
        cursor.close()
        return ddls
    except Exception as err:
        print(f"❌ 提取 DDL 时出错: {err}")
        connection.close()
        raise

def generate_qa_pairs(ddl_string, config, db_type):
    """[修改] 使用 LLM 基于多个数据库的 DDL 生成"问题-SQL"对，并鼓励跨库查询"""
    print(f"\n正在调用大语言模型生成 {NUM_QUESTIONS_TO_GENERATE} 个问答对...")

    vanna_instance = MyVanna(config=config)
    db_type_name = "MySQL" if db_type == "mysql" else "SQL Server"
    
    prompt = f"""
    你是一位顶尖的数据分析师和 SQL 专家。你的任务是根据下面提供的跨多个数据库的 Schema (DDL)，创造出 {NUM_QUESTIONS_TO_GENERATE} 个高质量、符合业务逻辑的"自然语言问题"以及它们对应的"{db_type_name}查询语句"。

    请遵循以下严格要求：
    1.  **跨库查询**: 生成的问题中必须包含需要连接不同数据库的表的查询 (例如, 'SELECT ... FROM db1.dbo.tableA JOIN db2.dbo.tableB ON ...')。这是最重要的要求。
    2.  **业务性**: 问题应该听起来像是真实的业务人员会问的问题，可以涉及数据对比、关联分析、趋势预测等。
    3.  **准确性**: SQL 必须语法正确，并且能够在 {db_type_name} 中成功执行。SQL中的表名必须使用 [数据库名].[schema名].[表名] 的三段式全名。
    4.  **多样性**: 问题应涵盖多种查询类型，如聚合（COUNT, SUM, AVG）、连接（JOIN）、子查询、窗口函数等。
    5.  **JSON 格式**: 返回结果必须是严格的 JSON 格式，一个包含多个对象的数组，每个对象都有 "question" 和 "sql" 两个键。不要在 JSON 内容前后添加任何额外的解释或标记。
    
    数据库 Schema (DDL) 如下 (包含来自多个数据库的表):
    ---
    {ddl_string}
    ---
    """

    try:
        prompt_messages = [{"role": "user", "content": prompt}]
        response_json_str = vanna_instance.submit_prompt(prompt_messages)
        
        cleaned_json_str = response_json_str.strip().replace('```json', '').replace('```', '')
        qa_pairs = json.loads(cleaned_json_str)
        print(f"✅ LLM 成功生成了 {len(qa_pairs)} 个问答对。")
        return qa_pairs
    except Exception as e:
        print(f"❌ 调用 LLM 或解析 JSON 时出错: {e}")
        if 'response_json_str' in locals() and response_json_str:
            print(f"LLM 原始返回内容: {response_json_str}")
        return None

def validate_and_inject(qa_pairs, connection, db_type):
    """验证 SQL 并将有效的问答对注入 Vanna"""
    if not qa_pairs:
        print("没有可供验证和注入的问答对。")
        return

    print("\n--- 开始验证和注入流程 ---")
    valid_count = 0
    total_count = len(qa_pairs)

    for i, pair in enumerate(qa_pairs):
        question = pair.get('question')
        sql = pair.get('sql')

        if not question or not sql:
            print(f"[{i+1}/{total_count}] ⏭️  跳过格式错误的条目: {pair}")
            continue

        print(f"[{i+1}/{total_count}] 正在验证: {question}")
        
        if not sql.strip().upper().startswith('SELECT'):
            print(f"  ❌ SQL 安全性验证失败: 只允许 SELECT 查询。SQL: {sql}")
            continue

        try:
            cursor = connection.cursor()
            cursor.execute(f"SET NOEXEC ON; {sql}; SET NOEXEC OFF;")
            print(f"  ✅ SQL 语法验证通过。")
            cursor.close()
        except Exception as err:
            print(f"  ❌ SQL 语法验证失败: {err}")
            print(f"    - 问题: {question}")
            print(f"    - 失败的 SQL: {sql}")
            continue

        try:
            payload = {"question": question, "sql": sql}
            response = requests.post(VANNA_API_ENDPOINT, json=payload)
            response.raise_for_status()
            
            if response.json().get('status') == 'success':
                print(f"  ✅ 成功注入 Vanna。")
                valid_count += 1
            else:
                print(f"  ❌ 注入失败，API 返回错误: {response.json().get('message')}")

        except requests.exceptions.RequestException as e:
            print(f"  ❌ 调用 Vanna API 时出错: {e}")
            print("    请确保您的 Vanna Flask 服务 (app.py) 正在运行中。")
            break
    
    print("\n--- 流程结束 ---")
    print(f"总共处理: {total_count} 个问答对")
    print(f"成功验证并注入: {valid_count} 个")

class TrainingDataGenerator:
    """
    一个用于生成高质量、经过验证的 Vanna 训练数据的工具。
    该工具模仿真实的用户查询流程：生成问题 -> RAG检索 -> 生成SQL -> 执行验证 -> 入库。
    """
    def __init__(self, vn_service: MyVanna, target_count: int, batch_size: int):
        self.vn = vn_service
        self.target_count = target_count
        self.batch_size = batch_size
        self.successful_pairs = 0

    def _generate_candidate_questions(self) -> list:
        """
        [新] 第一步：基于元数据，让LLM生成一批候选的业务问题。
        """
        print(f"\n--- 正在请求LLM生成 {self.batch_size} 个候选业务问题 ---")
        
        # 1. 构建高级上下文，只告诉LLM我们有什么，而不是具体细节
        metadata_context_parts = []
        if self.vn.table_metadata:
            table_info = "\n".join([
                f"- 表名: `{name}`, 业务用途: {meta.get('business_name', 'N/A')} - {meta.get('description', 'N/A')}" 
                for name, meta in self.vn.table_metadata.items()
            ])
            metadata_context_parts.append(f"我管理着以下数据表：\n{table_info}")

        if self.vn.field_mappings:
            # 只展示部分关键字段以激发思路
            field_info = ", ".join(list(self.vn.field_mappings.keys())[:20])
            metadata_context_parts.append(f"\n可以查询的指标和维度大致包括：{field_info} 等。")

        metadata_context_str = "\n".join(metadata_context_parts)
        if not metadata_context_str:
            print("❌ 错误：服务中缺少 table_metadata，无法生成问题。")
            return []

        # 2. 构建 Prompt
        prompt = f"""
        你是一位经验丰富的数据分析部门主管。你的任务是基于下述的数据库资产概览，提出 {self.batch_size} 个有深度、有价值的业务分析问题。

        要求：
        1.  问题应具有业务导向，模拟真实管理层或运营人员的提问风格。
        2.  问题应具有多样性，涵盖简单查询、对比分析、趋势分析、聚合统计等。
        3.  只返回一个JSON数组，其中每个元素都是一个字符串，即一个问题。
        4.  不要包含任何SQL代码或实现细节，只需提出问题。

        数据库资产概览：
        ---
        {metadata_context_str}
        ---

        请返回一个JSON格式的字符串数组，例如：["问题1", "问题2", ...]
        """
        try:
            response_str = self.vn.submit_prompt([{"role": "user", "content": prompt}])
            cleaned_json_str = self.vn._clean_llm_response(response_str)
            questions = json.loads(cleaned_json_str)
            if isinstance(questions, list):
                print(f"✅ LLM成功生成了 {len(questions)} 个候选问题。")
                return questions
            return []
        except Exception as e:
            print(f"❌ 生成候选问题时出错: {e}")
            return []

    def _generate_and_validate_sql(self, question: str):
        """
        [新] 第二步到第五步：为单个问题，执行 RAG -> 生成SQL -> 执行 -> 验证
        """
        print(f"\n处理问题: \"{question}\"")
        
        try:
            # 1. 模拟真实查询，通过RAG获取相关上下文
            print("  - [1/4] 正在执行RAG检索，获取相关上下文...")
            rag_context_obj = self.vn._perform_rag_retrieval(question=question)
            
            # 2. 基于RAG上下文，为问题生成SQL
            print("  - [2/4] 正在请求LLM生成SQL...")
            # 我们复用 correct_sql 的 prompt 结构，因为它很适合"给定上下文和问题生成SQL"
            system_prompt = self.vn._get_common_messages()[0]['content']
            rag_context_str = self.vn._format_rag_context_for_prompt(rag_context_obj)
            
            user_prompt = f"""
            请根据以下信息，为用户问题生成一个在 {self.vn.db_type} 上可执行的SQL查询。

            相关上下文信息（表结构、业务知识等）:
            ---
            {rag_context_str}
            ---
            用户问题: "{question}"
            """
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            sql_response = self.vn.submit_prompt(messages)
            sql = self.vn._clean_llm_response(sql_response)
            
            if not sql or not sql.strip().upper().startswith("SELECT"):
                print("  - ❌ 生成的SQL为空或不是SELECT查询，已跳过。")
                return

            print(f"  - ✅ 生成的SQL: {sql[:300]}...")

            # 3. 执行SQL
            print("  - [3/4] 正在执行SQL以验证其有效性...")
            df = self.vn.run_sql(sql)
            
            # 4. 验证结果并入库
            print("  - [4/4] 正在验证查询结果...")
            if df is not None and not df.empty:
                print(f"  - ✅ 验证成功！查询返回了 {len(df)} 条数据。")
                try:
                    self.vn.train(question=question, sql=sql)
                    print("  - ✅ 该高质量问答对已成功添加至知识库。")
                    self.successful_pairs += 1
                except Exception as e:
                    print(f"  - ❌ 添加入知识库时失败: {e}")
            else:
                print("  - ⚠️  验证失败。查询未返回任何数据，该问答对被丢弃。")

        except Exception as e:
            import traceback
            print(f"  - ❌ 处理问题 \"{question}\" 时遇到意外错误: {e}")
            traceback.print_exc()

    def run(self):
        """
        主执行函数。
        """
        print("--- 启动 Vanna 高质量训练数据生成脚本 ---")
        print(f"--- 目标: 生成 {self.target_count} 个经过验证的问答对 ---")

        while self.successful_pairs < self.target_count:
            # 生成一批候选问题
            candidate_questions = self._generate_candidate_questions()
            if not candidate_questions:
                print("未能生成候选问题，暂停5秒后重试...")
                time.sleep(5)
                continue
            
            # 依次处理每个问题
            for question in candidate_questions:
                self._generate_and_validate_sql(question)
                print("-" * 20)
                # 检查是否已达到目标
                if self.successful_pairs >= self.target_count:
                    break
            
            print(f"\n当前进度: {self.successful_pairs} / {self.target_count}\n")

        print("\n--- ✅ 任务完成 ---")
        print(f"成功生成并验证了 {self.successful_pairs} 个高质量的问答对。")

def main():
    """主入口"""
    try:
        # 确保服务已连接到数据库
        if not vanna_service.db_primary_connection_config:
            print("❌ 错误: Vanna服务未配置数据库连接，无法执行SQL验证。")
            return
        
        generator = TrainingDataGenerator(
            vn_service=vanna_service, 
            target_count=NUM_QUESTIONS_TO_GENERATE,
            batch_size=QUESTIONS_BATCH_SIZE
        )
        generator.run()

    except Exception as e:
        print(f"❌ 脚本执行时发生严重错误: {e}")

if __name__ == '__main__':
    main() 