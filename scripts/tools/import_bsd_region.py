#!/usr/bin/env python3
"""
导入bsd_region.json文件到geo_mappings.json
将编码在前、名称在后的格式转换为名称在前、编码在后的格式
"""

import json
import sys
import os
from pathlib import Path

def load_bsd_region_file(file_path):
    """加载bsd_region.json文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"错误：无法读取文件 {file_path}: {e}")
        return None

def load_geo_mappings():
    """加载现有的geo_mappings.json文件"""
    geo_mappings_path = Path(__file__).parent.parent.parent / 'config' / 'geo_mappings.json'
    
    try:
        with open(geo_mappings_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data, geo_mappings_path
    except Exception as e:
        print(f"错误：无法读取geo_mappings.json: {e}")
        return None, geo_mappings_path

def convert_bsd_to_geo_format(bsd_data):
    """将bsd格式转换为geo_mappings格式"""
    converted = {}
    
    for item in bsd_data:
        areacode = item.get('areacode', '')
        areaname = item.get('areaname', '')
        
        if areacode and areaname:
            # 转换格式：名称作为key，编码作为value
            converted[areaname] = areacode
    
    return converted

def merge_cities_data(existing_geo, new_cities):
    """合并城市数据到现有的geo_mappings中"""
    if 'cities' not in existing_geo:
        existing_geo['cities'] = {}
    
    # 合并新的城市数据
    for city_name, city_code in new_cities.items():
        existing_geo['cities'][city_name] = city_code
    
    return existing_geo

def save_geo_mappings(geo_data, file_path):
    """保存更新后的geo_mappings.json"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(geo_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"错误：无法保存文件 {file_path}: {e}")
        return False

def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("使用方法: python import_bsd_region.py <bsd_region.json文件路径>")
        print("示例: python import_bsd_region.py C:\\Users\\47688\\Desktop\\bsd_region.json")
        return
    
    bsd_file_path = sys.argv[1]
    
    # 检查文件是否存在
    if not os.path.exists(bsd_file_path):
        print(f"错误：文件不存在: {bsd_file_path}")
        return
    
    print(f"正在导入文件: {bsd_file_path}")
    
    # 1. 加载bsd_region.json文件
    bsd_data = load_bsd_region_file(bsd_file_path)
    if not bsd_data:
        return
    
    print(f"成功加载 {len(bsd_data)} 条区域数据")
    
    # 2. 转换格式
    converted_cities = convert_bsd_to_geo_format(bsd_data)
    print(f"成功转换 {len(converted_cities)} 条城市映射")
    
    # 3. 加载现有的geo_mappings.json
    existing_geo, geo_file_path = load_geo_mappings()
    if not existing_geo:
        return
    
    # 4. 合并数据
    updated_geo = merge_cities_data(existing_geo, converted_cities)
    
    # 5. 保存更新后的文件
    if save_geo_mappings(updated_geo, geo_file_path):
        print(f"成功更新 geo_mappings.json")
        print(f"新增了 {len(converted_cities)} 条城市映射")
        
        # 显示部分导入的数据
        print("\n导入的部分城市数据:")
        for i, (city, code) in enumerate(list(converted_cities.items())[:10]):
            print(f"  {city}: {code}")
        
        if len(converted_cities) > 10:
            print(f"  ... 还有 {len(converted_cities) - 10} 条数据")
    else:
        print("保存失败")

if __name__ == "__main__":
    main()