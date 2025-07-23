import os
import sys
import json
from datetime import datetime
import pandas as pd
import shutil

# Add project root to sys.path to allow imports from src
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

# Import the factory function to create a vanna service instance.
from src.vanna_service import create_vanna_service

class KnowledgeBaseBackup:
    def __init__(self, vn_service):
        self.vn = vn_service
        # 定义所有备份的基础目录
        self.backup_base_dir = os.path.join('data', 'backups')
        os.makedirs(self.backup_base_dir, exist_ok=True)

    def get_training_data_as_df(self) -> pd.DataFrame:
        """
        Fetches all training data from the vector store and returns it as a pandas DataFrame.
        """
        try:
            list_of_dicts = self.vn.get_training_data()
            if not list_of_dicts:
                return pd.DataFrame()
            return pd.DataFrame(list_of_dicts)
        except Exception as e:
            print(f"❌ Error retrieving training data from vector store: {e}")
            return pd.DataFrame()

    def _export_df_to_json(self, df: pd.DataFrame, data_type_name: str, output_dir: str, exported_files: list):
        """Helper to export a DataFrame to a JSON file."""
        if df.empty:
            # 这是一个正常情况（例如，没有通用业务知识），所以不打印警告
            print(f"  ℹ️ No data for type '{data_type_name}', skipping export.")
            return
        
        records = df.to_dict('records')
        file_path = os.path.join(output_dir, f"{data_type_name.lower()}_export.json")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=4)
            print(f"  ✅ Successfully exported {len(records)} records to {file_path}")
            exported_files.append(file_path)
        except Exception as e:
            print(f"  ❌ Error writing to file {file_path}: {e}")

    def export_all_knowledge(self):
        """
        Exports all types of training data (DDL, Q&A pairs, Documentation) 
        from the vector store, and directly backs up the primary station_info.json file.
        """
        print("--- Starting Full Knowledge Base Export ---")

        # 在基础备份目录中为此导出创建唯一目录
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        output_dir = os.path.join(self.backup_base_dir, timestamp)
        os.makedirs(output_dir, exist_ok=True)
        print(f"Exporting data to directory: {output_dir}")
        
        exported_files = []

        # --- Step 1: Directly back up the station_info.json file ---
        station_info_src_path = os.path.join('data', 'knowledge', 'station_info.json')
        if os.path.exists(station_info_src_path):
            try:
                shutil.copy(station_info_src_path, output_dir)
                print(f"  ✅ Successfully backed up {station_info_src_path}")
                exported_files.append(os.path.join(output_dir, os.path.basename(station_info_src_path)))
            except Exception as e:
                print(f"  ❌ Error backing up {station_info_src_path}: {e}")
        else:
            print(f"  ℹ️  '{station_info_src_path}' not found, skipping its backup.")

        # --- Step 2: Export all data from the vector store ---
        df = self.get_training_data_as_df()
        if df.empty:
            print("⚠️ No training data found in the vector store. Exporting only files.")
        else:
            # Use the correct column name 'training_data_type'
            type_column = 'training_data_type'
            if type_column not in df.columns:
                print(f"❌ Error: Column '{type_column}' not found in the data. Available columns: {df.columns.tolist()}")
                return
            
            # Iterate over each type of knowledge and export it without special handling
            for data_type in df[type_column].unique():
                print(f"Processing data type: {data_type}...")
                type_df = df[df[type_column] == data_type]
                self._export_df_to_json(type_df, data_type, output_dir, exported_files)

        print("\n--- Export Complete ---")
        if exported_files:
            print("Successfully exported files:")
            for file in exported_files:
                print(f"- {file}")
        else:
            print("No files were exported.")


if __name__ == '__main__':
    # Initialize the vanna_service instance using the factory function
    print("🚀 Initializing VannaService for backup...")
    vanna_service = create_vanna_service()
    
    if vanna_service is None:
        print("❌ Failed to create VannaService instance. Aborting backup.")
        sys.exit(1)
        
    print("✅ VannaService initialized successfully.")

    # Initialize the backup tool with our vanna_service instance
    backup_tool = KnowledgeBaseBackup(vn_service=vanna_service)
    # Run the export process
    backup_tool.export_all_knowledge() 