#!/usr/bin/env python3
"""
确保使用虚拟环境启动Flask应用的脚本
Startup script that ensures virtual environment is used
"""

import os
import sys
import subprocess
import platform

def main():
    """启动Flask应用，确保使用虚拟环境"""
    
    # 获取当前目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 虚拟环境路径
    venv_dir = os.path.join(current_dir, 'venv')
    
    # 检查虚拟环境是否存在
    if not os.path.exists(venv_dir):
        print("错误：虚拟环境不存在，请先创建虚拟环境：")
        print("python -m venv venv")
        print("pip install -r requirements.txt")
        sys.exit(1)
    
    # 确定Python可执行文件路径
    if platform.system() == "Windows":
        python_exe = os.path.join(venv_dir, 'Scripts', 'python.exe')
        activate_script = os.path.join(venv_dir, 'Scripts', 'activate.bat')
    else:
        python_exe = os.path.join(venv_dir, 'bin', 'python')
        activate_script = os.path.join(venv_dir, 'bin', 'activate')
    
    if not os.path.exists(python_exe):
        print(f"错误：虚拟环境中的Python可执行文件不存在：{python_exe}")
        sys.exit(1)
    
    # 切换到项目目录
    os.chdir(current_dir)
    
    # 设置环境变量
    env = os.environ.copy()
    env['PYTHONPATH'] = current_dir
    env['PYTHONUNBUFFERED'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    
    # 启动Flask应用
    app_script = os.path.join(current_dir, 'app_root.py')
    
    print(f"使用虚拟环境Python: {python_exe}")
    print(f"启动Flask应用: {app_script}")
    print("=" * 50)
    
    try:
        # 直接运行app_root.py
        result = subprocess.run([python_exe, app_script], 
                              env=env, 
                              cwd=current_dir,
                              check=False)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n应用已停止")
        sys.exit(0)
    except Exception as e:
        print(f"启动应用时出错: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()