import json
import time
import os
import glob
import sys
import shutil

# Add project root to sys.path to allow imports from src
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

# Import the factory function to create a vanna service instance.
from src.vanna_service import create_vanna_service

class KnowledgeBaseRestorer:
    """
    一个用于从备份文件中恢复所有类型知识（QA、DDL、Documentation）到 Vanna 知识库的工具。
    """
    def __init__(self, vn_service):
        self.vn = vn_service
        # 定义存放备份的基础目录
        self.backup_base_dir = os.path.join('data', 'backups')
        self.latest_backup_dir = self._find_latest_backup_dir()

    def _find_latest_backup_dir(self):
        """在 backup_base_dir 中查找最新的备份目录。"""
        # 模式现在在定义的备份目录内搜索
        backup_dirs_path = os.path.join(self.backup_base_dir, '*')
        
        # 获取目录中的所有项目，并仅筛选出目录
        all_items = glob.glob(backup_dirs_path)
        backup_dirs = [d for d in all_items if os.path.isdir(d)]
        
        if not backup_dirs:
            return None
        # 通过简单的字符串比较找到最新的目录，这对 YYYY-MM-DD 格式有效
        return max(backup_dirs)

    def restore(self):
        """
        执行恢复过程的主方法。
        """
        if not self.latest_backup_dir:
            print(f"❌ 错误: 在目录 '{self.backup_base_dir}' 中未找到任何备份。无法进行恢复。")
            return

        print(f"--- 开始从目录 '{self.latest_backup_dir}' 恢复知识库 ---")

        # --- 步骤 1: 直接通过复制文件恢复 station_info.json ---
        backed_up_station_info = os.path.join(self.latest_backup_dir, 'station_info.json')
        if os.path.exists(backed_up_station_info):
            try:
                # 目标路径是 data/knowledge/ 目录
                destination_path = os.path.join('data', 'knowledge', 'station_info.json')
                # 确保目标目录存在
                os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                shutil.copy(backed_up_station_info, destination_path)
                print(f"✅ 成功将 '{backed_up_station_info}' 恢复至 '{destination_path}'")
            except Exception as e:
                print(f"❌ 恢复 'station_info.json' 时出错: {e}")
        else:
            print(f"ℹ️  在备份目录中未找到 'station_info.json'，跳过文件恢复。")


        # --- 步骤 2: 从备份文件向向量数据库恢复知识 ---
        # 定义恢复计划：文件名 -> 处理该文件的方法 (已移除站点信息)
        restore_plan = {
            'sql_export.json': self._restore_sql,
            'ddl_export.json': self._restore_ddl,
            'documentation_export.json': self._restore_documentation,
        }

        # 依次执行恢复计划
        for filename, restore_func in restore_plan.items():
            file_path = os.path.join(self.latest_backup_dir, filename)
            restore_func(file_path)

        print("\n--- ✅ 知识库恢复流程全部完成 ---")

    def _restore_from_file(self, file_path, data_type_name, required_keys, train_function):
        """
        一个通用的方法，用于从单个JSON文件中读取数据并进行恢复。

        Args:
            file_path (str): JSON文件的路径。
            data_type_name (str): 正在处理的数据类型的可读名称 (例如, '问答对(QA)')。
            required_keys (list): 字典中必须存在的键列表。
            train_function (function): 一个接收单个数据项（字典）并调用相应训练方法的函数。
        """
        print(f"\n--- 正在处理文件: {os.path.basename(file_path)} ({data_type_name}) ---")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"ℹ️  信息: 文件未找到，跳过恢复。")
            return
        except json.JSONDecodeError:
            print(f"❌ 错误: 文件 '{file_path}' 格式不正确，无法解析为 JSON。")
            return

        if not isinstance(data, list) or not data:
            print("⚠️ 文件为空或格式不正确（应为列表），无需恢复。")
            return

        total_items = len(data)
        success_count = 0
        print(f"检测到 {total_items} 条数据，开始逐条恢复...")

        for i, item in enumerate(data):
            # 验证条目是否为字典且包含所有必需的键
            if not isinstance(item, dict) or not all(key in item and item[key] for key in required_keys):
                print(f"  [{i+1}/{total_items}] ⏭️  跳过格式错误或缺少必要信息的条目: {str(item)[:100]}...")
                continue
            
            try:
                # 调用包装好的训练函数
                train_function(item)
                # 使用 item.get('id', 'N/A') 安全地获取ID
                print(f"  [{i+1}/{total_items}] ✅ 成功恢复条目 ID: {item.get('id', 'N/A')}")
                success_count += 1
                time.sleep(0.05)  # 轻微延迟，避免对数据库造成冲击
            except Exception as e:
                print(f"  [{i+1}/{total_items}] ❌ 恢复条目 ID {item.get('id', 'N/A')} 时出错: {e}")
        
        print(f"'{data_type_name}' 类型数据处理完成。成功恢复: {success_count}/{total_items} 条。")

    def _restore_sql(self, file_path):
        """恢复SQL查询示例"""
        def train_func(item):
            # 使用 Vanna 的 train 方法恢复问答对
            self.vn.train(question=item['question'], sql=item['content'])
        self._restore_from_file(file_path, 'SQL查询示例(SQL)', ['question', 'content'], train_func)

    def _restore_ddl(self, file_path):
        """恢复数据定义语言 (DDL)"""
        def train_func(item):
            # 使用 Vanna 的 train 方法恢复 DDL
            self.vn.train(ddl=item['content'])
        self._restore_from_file(file_path, '数据定义语言(DDL)', ['content'], train_func)

    def _restore_documentation(self, file_path):
        """恢复业务知识 (Documentation)"""
        def train_func(item):
            # 使用 Vanna 的 train 方法恢复业务知识
            self.vn.train(documentation=item['content'])
        self._restore_from_file(file_path, '业务知识(Documentation)', ['content'], train_func)


if __name__ == '__main__':
    # Initialize the vanna_service instance using the factory function
    print("🚀 Initializing VannaService for restoration...")
    vanna_service = create_vanna_service()
    
    if vanna_service is None:
        print("❌ Failed to create VannaService instance. Aborting restoration.")
        sys.exit(1)
        
    print("✅ VannaService initialized successfully.")
    
    # 初始化恢复工具，并传入 vanna_service 实例
    restorer = KnowledgeBaseRestorer(vn_service=vanna_service)
    # 启动恢复过程
    restorer.restore() 