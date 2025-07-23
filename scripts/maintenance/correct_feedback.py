import csv
import pandas as pd
import requests
import time

# --- 配置 ---
FEEDBACK_FILE = 'feedback_log.csv'
VANNA_API_ENDPOINT = "http://127.0.0.1:9090/add-example"
FIELDNAMES = ['timestamp', 'question', 'generated_sql', 'status', 'corrected_sql']

def correct_feedback():
    """
    一个交互式脚本，用于审查待处理的反馈，修正错误的SQL，并将正确的示例重新训练。
    """
    print("--- 启动交互式反馈修正流程 ---")

    # 1. 使用 pandas 读取 CSV，因为它能更好地处理空文件和数据操作
    try:
        df = pd.read_csv(FEEDBACK_FILE, encoding='utf-8')
        # 筛选出待处理的反馈
        pending_feedback = df[df['status'] == 'pending']
    except FileNotFoundError:
        print(f"✅ 未找到反馈日志文件 '{FEEDBACK_FILE}'。没有需要修正的内容。")
        return
    except pd.errors.EmptyDataError:
        print("✅ 反馈日志文件为空。没有需要修正的内容。")
        return

    if pending_feedback.empty:
        print("✅ 没有待处理的(pending)反馈。一切都已修正！")
        return

    print(f"找到 {len(pending_feedback)} 条待处理的反馈。现在开始逐条修正：\n")
    
    # 2. 逐条处理待处理的反馈
    for index, row in pending_feedback.iterrows():
        print("--------------------------------------------------")
        print(f"修正条目 {index+1}/{len(df)} (待处理的第 {list(pending_feedback.index).index(index)+1} 条)")
        print(f"  - 时间戳: {row['timestamp']}")
        print(f"  - 用户问题: {row['question']}")
        print(f"  - 模型生成的错误SQL: {row['generated_sql']}")
        print("--------------------------------------------------")

        # 3. 获取用户输入的正确 SQL
        try:
            corrected_sql = input("请输入正确的SQL (如果想跳过，请直接按 Enter): \n> ")
        except KeyboardInterrupt:
            print("\n\n用户中断操作。正在保存已有的修改...")
            break

        if not corrected_sql.strip():
            print("⏭️  已跳过此条目。\n")
            continue

        # 4. 将修正后的示例重新注入 Vanna
        try:
            payload = {"question": row['question'], "sql": corrected_sql}
            response = requests.post(VANNA_API_ENDPOINT, json=payload)
            response.raise_for_status()

            if response.json().get('status') == 'success':
                print("  ✅ 成功将修正后的示例注入 Vanna。")
                # 5. 更新 DataFrame 中的状态和修正后的 SQL
                df.loc[index, 'status'] = 'corrected'
                df.loc[index, 'corrected_sql'] = corrected_sql
                print("  ✅ 状态已更新为 'corrected'。")
            else:
                print(f"  ❌ 注入失败，API 返回错误: {response.json().get('message')}")

        except requests.exceptions.RequestException as e:
            print(f"  ❌ 调用 Vanna API 时出错: {e}")
            print("    请确保 Vanna 服务正在运行。修正流程已暂停。")
            break
        
        print("\n")
        time.sleep(0.5)

    # 6. 将更新后的 DataFrame 写回 CSV 文件
    try:
        df.to_csv(FEEDBACK_FILE, index=False, encoding='utf-8')
        print(f"\n--- 流程结束 ---")
        print(f"✅ 已将所有更改保存回 '{FEEDBACK_FILE}'。")
    except Exception as e:
        print(f"❌ 将更新后的数据写回CSV时出错: {e}")

if __name__ == '__main__':
    correct_feedback() 