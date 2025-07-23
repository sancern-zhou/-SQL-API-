#!/usr/bin/env python3
"""
地理编码映射管理工具
用于添加、查看、删除地理位置编码映射关系
"""

import json
import os
import sys
from typing import Dict

class GeoMappingManager:
    def __init__(self):
        # 获取配置文件路径
        self.config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'config', 'geo_mappings.json'
        )
        self.mappings = self.load_mappings()
    
    def load_mappings(self) -> Dict:
        """加载现有的映射配置"""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {"stations": {}, "districts": {}, "cities": {}}
    
    def save_mappings(self):
        """保存映射配置到文件"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.mappings, f, ensure_ascii=False, indent=2)
        print(f"映射配置已保存到: {self.config_path}")
    
    def add_station(self, name: str, code: str):
        """添加站点映射"""
        self.mappings["stations"][name] = code
        print(f"已添加站点: {name} -> {code}")
    
    def add_district(self, name: str, code: str):
        """添加区县映射"""
        self.mappings["districts"][name] = code
        print(f"已添加区县: {name} -> {code}")
    
    def add_city(self, name: str, code: str):
        """添加城市映射"""
        self.mappings["cities"][name] = code
        print(f"已添加城市: {name} -> {code}")
    
    def remove_station(self, name: str):
        """删除站点映射"""
        if name in self.mappings["stations"]:
            del self.mappings["stations"][name]
            print(f"已删除站点: {name}")
        else:
            print(f"站点不存在: {name}")
    
    def remove_district(self, name: str):
        """删除区县映射"""
        if name in self.mappings["districts"]:
            del self.mappings["districts"][name]
            print(f"已删除区县: {name}")
        else:
            print(f"区县不存在: {name}")
    
    def remove_city(self, name: str):
        """删除城市映射"""
        if name in self.mappings["cities"]:
            del self.mappings["cities"][name]
            print(f"已删除城市: {name}")
        else:
            print(f"城市不存在: {name}")
    
    def list_all(self):
        """列出所有映射"""
        print("=== 当前地理编码映射 ===")
        
        print(f"\n[站点] 站点映射 ({len(self.mappings['stations'])} 个):")
        for name, code in sorted(self.mappings["stations"].items()):
            print(f"  {name} -> {code}")
        
        print(f"\n[区县] 区县映射 ({len(self.mappings['districts'])} 个):")
        for name, code in sorted(self.mappings["districts"].items()):
            print(f"  {name} -> {code}")
        
        print(f"\n[城市] 城市映射 ({len(self.mappings['cities'])} 个):")
        for name, code in sorted(self.mappings["cities"].items()):
            print(f"  {name} -> {code}")
    
    def search(self, keyword: str):
        """搜索包含关键词的映射"""
        print(f"=== 搜索结果: '{keyword}' ===")
        
        found = False
        
        print("\n[站点]:")
        for name, code in self.mappings["stations"].items():
            if keyword in name or keyword in code:
                print(f"  {name} -> {code}")
                found = True
        
        print("\n[区县]:")
        for name, code in self.mappings["districts"].items():
            if keyword in name or keyword in code:
                print(f"  {name} -> {code}")
                found = True
        
        print("\n[城市]:")
        for name, code in self.mappings["cities"].items():
            if keyword in name or keyword in code:
                print(f"  {name} -> {code}")
                found = True
        
        if not found:
            print("未找到匹配的映射")
    
    def batch_add_from_file(self, file_path: str, mapping_type: str):
        """从文件批量添加映射"""
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            return
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        count = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            try:
                name, code = line.split('\t')  # 使用制表符分隔
                if mapping_type == 'station':
                    self.add_station(name, code)
                elif mapping_type == 'district':
                    self.add_district(name, code)
                elif mapping_type == 'city':
                    self.add_city(name, code)
                count += 1
            except ValueError:
                print(f"跳过无效行: {line}")
        
        print(f"批量添加完成，成功添加 {count} 个映射")

def main():
    manager = GeoMappingManager()
    
    if len(sys.argv) < 2:
        print("地理编码映射管理工具")
        print("用法:")
        print("  python manage_geo_mappings.py list                    # 列出所有映射")
        print("  python manage_geo_mappings.py search <关键词>         # 搜索映射")
        print("  python manage_geo_mappings.py add station <名称> <编码>    # 添加站点")
        print("  python manage_geo_mappings.py add district <名称> <编码>   # 添加区县")
        print("  python manage_geo_mappings.py add city <名称> <编码>       # 添加城市")
        print("  python manage_geo_mappings.py remove station <名称>       # 删除站点")
        print("  python manage_geo_mappings.py remove district <名称>      # 删除区县")
        print("  python manage_geo_mappings.py remove city <名称>          # 删除城市")
        print("  python manage_geo_mappings.py batch <文件路径> <类型>      # 批量添加")
        print("")
        print("批量添加文件格式（制表符分隔）:")
        print("  站点名称\t站点编码")
        print("  区县名称\t区县编码")
        return
    
    command = sys.argv[1]
    
    if command == "list":
        manager.list_all()
    
    elif command == "search" and len(sys.argv) >= 3:
        keyword = sys.argv[2]
        manager.search(keyword)
    
    elif command == "add" and len(sys.argv) >= 5:
        mapping_type = sys.argv[2]
        name = sys.argv[3]
        code = sys.argv[4]
        
        if mapping_type == "station":
            manager.add_station(name, code)
        elif mapping_type == "district":
            manager.add_district(name, code)
        elif mapping_type == "city":
            manager.add_city(name, code)
        else:
            print("无效的映射类型，请使用 station/district/city")
            return
        
        manager.save_mappings()
    
    elif command == "remove" and len(sys.argv) >= 4:
        mapping_type = sys.argv[2]
        name = sys.argv[3]
        
        if mapping_type == "station":
            manager.remove_station(name)
        elif mapping_type == "district":
            manager.remove_district(name)
        elif mapping_type == "city":
            manager.remove_city(name)
        else:
            print("无效的映射类型，请使用 station/district/city")
            return
        
        manager.save_mappings()
    
    elif command == "batch" and len(sys.argv) >= 4:
        file_path = sys.argv[2]
        mapping_type = sys.argv[3]
        
        if mapping_type not in ["station", "district", "city"]:
            print("无效的映射类型，请使用 station/district/city")
            return
        
        manager.batch_add_from_file(file_path, mapping_type)
        manager.save_mappings()
    
    else:
        print("无效的命令或参数不足")

if __name__ == "__main__":
    main()