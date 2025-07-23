#!/usr/bin/env python3
"""
环境检查脚本 - 验证并发测试前的环境准备
Environment Check Script - Validate environment before concurrent testing
"""

import sys
import os
import importlib
from datetime import datetime

def check_python_version():
    """检查Python版本"""
    print("1. Python版本检查:")
    version = sys.version
    print(f"   当前Python版本: {version}")
    
    if sys.version_info >= (3, 7):
        print("   ✓ Python版本符合要求 (>=3.7)")
        return True
    else:
        print("   ✗ Python版本过低，需要3.7或更高版本")
        return False

def check_project_structure():
    """检查项目结构"""
    print("\n2. 项目结构检查:")
    
    required_files = [
        "start.py",
        "src/utils/smart_geo_extractor.py",
        "src/utils/param_converter.py", 
        "src/utils/parameter_deduplicator.py",
        "config/geo_mappings.json",
        "config/routing_config.yaml"
    ]
    
    missing_files = []
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"   ✓ {file_path}")
        else:
            print(f"   ✗ {file_path} (缺失)")
            missing_files.append(file_path)
    
    if not missing_files:
        print("   ✓ 所有必需文件存在")
        return True
    else:
        print(f"   ✗ 缺失 {len(missing_files)} 个必需文件")
        return False

def check_dependencies():
    """检查依赖包"""
    print("\n3. 依赖包检查:")
    
    required_packages = [
        ("yaml", "PyYAML"),
        ("thefuzz", "thefuzz"),
        ("logging", "内置模块"),
        ("threading", "内置模块"),
        ("concurrent.futures", "内置模块"),
        ("json", "内置模块"),
        ("dataclasses", "内置模块")
    ]
    
    missing_packages = []
    for module_name, package_name in required_packages:
        try:
            importlib.import_module(module_name)
            print(f"   ✓ {package_name}")
        except ImportError:
            print(f"   ✗ {package_name} (未安装)")
            missing_packages.append(package_name)
    
    if not missing_packages:
        print("   ✓ 所有依赖包可用")
        return True
    else:
        print(f"   ✗ 缺失 {len(missing_packages)} 个依赖包")
        return False

def check_project_modules():
    """检查项目模块导入"""
    print("\n4. 项目模块检查:")
    
    # 添加项目路径
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    
    modules_to_check = [
        ("src.utils.smart_geo_extractor", "智能地理位置提取器"),
        ("src.utils.param_converter", "参数转换器"),
        ("src.utils.parameter_deduplicator", "参数去重处理器")
    ]
    
    import_errors = []
    for module_name, description in modules_to_check:
        try:
            module = importlib.import_module(module_name)
            print(f"   ✓ {description} ({module_name})")
        except ImportError as e:
            print(f"   ✗ {description} ({module_name}) - 导入失败: {e}")
            import_errors.append((module_name, str(e)))
    
    if not import_errors:
        print("   ✓ 所有项目模块可正常导入")
        return True
    else:
        print(f"   ✗ {len(import_errors)} 个模块导入失败")
        return False

def test_basic_functionality():
    """测试基础功能"""
    print("\n5. 基础功能测试:")
    
    try:
        # 添加项目路径
        sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
        
        # 测试地理位置提取
        from src.utils.smart_geo_extractor import get_smart_geo_extractor
        geo_extractor = get_smart_geo_extractor()
        test_locations = geo_extractor.extract_locations("广州市今天空气质量")
        print(f"   ✓ 地理位置提取测试: {test_locations}")
        
        # 测试时间解析
        from src.utils.param_converter import get_param_converter
        param_converter = get_param_converter()
        test_time, error = param_converter.parse_time_description("昨天")
        if test_time:
            print(f"   ✓ 时间解析测试: {test_time}")
        else:
            print(f"   ✗ 时间解析测试失败: {error}")
            return False
        
        # 测试参数去重
        from src.utils.parameter_deduplicator import get_parameter_deduplicator
        deduplicator = get_parameter_deduplicator()
        print("   ✓ 参数去重处理器初始化成功")
        
        return True
        
    except Exception as e:
        print(f"   ✗ 基础功能测试失败: {e}")
        return False

def check_system_resources():
    """检查系统资源"""
    print("\n6. 系统资源检查:")
    
    try:
        import psutil
        
        # CPU信息
        cpu_count = psutil.cpu_count()
        print(f"   CPU核心数: {cpu_count}")
        
        # 内存信息
        memory = psutil.virtual_memory()
        print(f"   可用内存: {memory.available / (1024**3):.1f} GB / {memory.total / (1024**3):.1f} GB")
        
        # 磁盘空间
        disk = psutil.disk_usage('.')
        print(f"   可用磁盘空间: {disk.free / (1024**3):.1f} GB")
        
        print("   ✓ 系统资源充足")
        return True
        
    except ImportError:
        print("   ⚠ psutil未安装，跳过系统资源检查")
        return True
    except Exception as e:
        print(f"   ⚠ 系统资源检查失败: {e}")
        return True

def create_test_directories():
    """创建测试所需目录"""
    print("\n7. 创建测试目录:")
    
    directories = ["logs", "tests"]
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"   ✓ 创建目录: {directory}")
        else:
            print(f"   ✓ 目录已存在: {directory}")
    
    return True

def main():
    """主函数"""
    print("=" * 60)
    print("参数提取并发测试环境检查")
    print("=" * 60)
    print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"当前目录: {os.getcwd()}")
    
    checks = [
        check_python_version,
        check_project_structure,
        check_dependencies,
        check_project_modules,
        test_basic_functionality,
        check_system_resources,
        create_test_directories
    ]
    
    passed_checks = 0
    total_checks = len(checks)
    
    for check_func in checks:
        try:
            if check_func():
                passed_checks += 1
        except Exception as e:
            print(f"   ✗ 检查过程中出现异常: {e}")
    
    print("\n" + "=" * 60)
    print("环境检查结果汇总")
    print("=" * 60)
    print(f"通过检查: {passed_checks}/{total_checks}")
    
    if passed_checks == total_checks:
        print("✓ 环境检查全部通过，可以运行并发测试")
        return True
    elif passed_checks >= total_checks - 1:
        print("⚠ 环境检查基本通过，可以尝试运行并发测试")
        return True
    else:
        print("✗ 环境检查未通过，请解决问题后重新检查")
        return False

if __name__ == "__main__":
    success = main()
    
    print("\n" + "=" * 60)
    if success:
        print("下一步：运行 run_concurrent_test.bat 开始并发测试")
    else:
        print("请解决环境问题后重新运行环境检查")
    print("=" * 60)
    
    input("\n按回车键退出...")