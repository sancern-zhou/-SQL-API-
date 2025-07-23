#!/usr/bin/env python3
"""
API注册表 - 定义所有可供LLM调用的外部API工具
API Registry - Defines all external API tools available for the LLM to call.
"""

# 这是一个工具列表，每个工具都描述了一个外部API接口。
# LLM将根据用户的提问，从这个列表中选择最合适的工具，并提取所需的参数。
EXTERNAL_API_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_summary_report",
            "description": """获取指定时间范围内，一个或多个地理位置的综合统计报表数据。
            
适用场景：
- 单一时间段的数据查询（如"查询广州市上月空气质量"）
- 现状分析和监测报告（如"广雅中学今天的空气质量怎么样"）
- 周报、月报、季报、年报等定期报告
- 多地点同时间段的数据汇总（如"查询广州各区县上周空气质量"）
- 趋势分析但不涉及时间对比的查询

不适用场景：
- 包含"对比"、"比较"、"同比"、"环比"、"变化"等对比意图的查询
- 需要两个不同时间段数据比较的查询

典型查询示例：
✓ "广州市上月空气质量报告"
✓ "广雅中学今天PM2.5浓度"
✓ "查询越秀区本周空气质量数据"
✗ "广州市今年5月与去年5月空气质量对比"（应使用get_comparison_report）""",
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "用户想要查询的地理位置名称列表，例如 ['广雅中学', '广州市', '越秀区']。系统将自动进行模糊匹配和编码转换。注意：系统现支持多结果返回，会同时查询所有匹配到的地理位置。"
                    },
                    "time_description": {
                        "type": "string",
                        "description": "描述查询时间范围的自然语言文本，例如 '上周', '2024年5月', '昨天到今天'。如果用户没有明确提供，请不要编造。"
                    },
                    "area_type": {
                        "type": "string",
                        "enum": ["站点", "区县", "城市"],
                        "description": "查询的区域类型。'站点'表示具体的监测点，'区县'表示行政区，'城市'表示整个城市。"
                    },
                    "data_source": {
                        "type": "string",
                        "enum": ["原始实况", "审核实况", "原始标况", "审核标况"],
                        "description": "查询的数据来源类型。如果用户未指定，默认为'审核实况'。"
                    }
                },
                "required": ["locations", "time_description", "area_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_comparison_report",
            "description": """获取两个不同时间范围的数据并进行对比分析，生成对比报表。
            
适用场景：
- 时间对比查询（如"今年5月与去年5月空气质量对比"）
- 同比分析（如"广州市空气质量同比变化"）
- 环比分析（如"这个月与上个月的空气质量比较"）
- 变化趋势分析（如"PM2.5浓度相比去年同期变化了多少"）
- 改善效果评估（如"治理后空气质量改善情况"）

必要条件：
- 查询中明确包含两个时间段
- 用户明确表达对比意图
- 包含"对比"、"比较"、"同比"、"环比"、"变化"、"改善"等关键词

典型查询示例：
✓ "广州市今年5月与去年5月空气质量对比"
✓ "广雅中学空气质量同比变化了多少"
✓ "这个月PM2.5相比上个月有什么变化"
✓ "越秀区空气质量环比改善情况"
✗ "广州市上月空气质量报告"（应使用get_summary_report）

注意：如果用户只提到一个时间段，即使包含"变化"等词汇，也应优先考虑get_summary_report。""",
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "用户想要查询的地理位置名称列表，例如 ['广雅中学', '广州市', '越秀区']。系统将自动进行模糊匹配和编码转换。注意：系统现支持多结果返回，会同时查询所有匹配到的地理位置。"
                    },
                    "time_description": {
                        "type": "string",
                        "description": "描述主要查询时间范围的自然语言文本，例如 '上个月', '今年5月'。"
                    },
                    "comparison_time_description": {
                        "type": "string",
                        "description": "描述用于对比的时间范围的自然语言文本，例如 '去年同期', '上上个月'。"
                    },
                    "area_type": {
                        "type": "string",
                        "enum": ["站点", "区县", "城市"],
                        "description": "查询的区域类型。'站点'表示具体的监测点，'区县'表示行政区，'城市'表示整个城市。"
                    },
                    "data_source": {
                        "type": "string",
                        "enum": ["原始实况", "审核实况", "原始标况", "审核标况"],
                        "description": "查询的数据来源类型。如果用户未指定，默认为'审核实况'。"
                    }
                },
                "required": ["locations", "time_description", "comparison_time_description", "area_type"]
            }
        }
    }
] 