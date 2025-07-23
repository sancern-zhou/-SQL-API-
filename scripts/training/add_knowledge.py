import yaml
import sys
import os

# -- Path setup --
# This ensures that we can import from the 'src' directory by adding the project root to sys.path.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# [修改] 直接从 vanna_service 导入已创建的 vanna_service 实例，避免重复初始化
from src.vanna_service import vanna_service, load_config

def add_knowledge():
    """
    一个专门用于向 Vanna 中添加业务知识文档的脚本。
    """
    print("--- 开始向 Vanna 添加业务知识 ---")
    
    # 1. 定义您的业务知识库
    # 您可以在这里添加任意数量的、关于业务规则、字段含义、同义词等的描述。
    knowledge_base = [] 
    # --- [新增] 从 业务知识训练文档.txt 文件加载内容并追加到知识库 ---
    print("\n--- 正在从 业务知识训练文档.txt 加载知识 ---")
    try:
        with open('业务知识训练文档.txt', 'r', encoding='utf-8') as f:
            documentation_content = f.read()
            if documentation_content:
                knowledge_base.append(documentation_content)
                print("✅ 成功加载'业务知识训练文档.txt'的内容并添加到知识库。")
            else:
                print("⚠️ '业务知识训练文档.txt' 文件为空，跳过添加。")
    except FileNotFoundError:
        print("❌ 错误：未找到'业务知识训练文档.txt'文件。将仅处理已有的业务知识。")
    except Exception as e:
        print(f"❌ 读取'业务知识训练文档.txt'时发生未知错误: {e}")
    # --- [新增] 逻辑结束 ---

    # [修改] 移除独立的Vanna服务初始化，因为我们已经导入了预先配置好的实例
    # 3. 循环注入知识
    total_items = len(knowledge_base)
    print(f"\n准备注入 {total_items} 条业务知识...")

    for i, doc in enumerate(knowledge_base):
        try:
            # 直接使用导入的 vanna_service 实例
            vanna_service.train(documentation=doc)
            print(f"  [{i+1}/{total_items}] ✅ 成功添加知识: \"{doc[:50]}...\"")
        except Exception as e:
            print(f"  [{i+1}/{total_items}] ❌ 添加知识失败: {doc}")
            print(f"    错误原因: {e}")

    print("\n--- 业务知识添加完毕 ---")

if __name__ == '__main__':
    add_knowledge() 