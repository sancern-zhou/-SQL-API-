# 集成智能路由、参数转换、错误恢复、多数据源统一查询的完整解决方案
*系统概述*：本项目是一个统一接口的数据查询的工具，帮助用户实现流畅的自然语言数据查询。从查询方式上，可以分为支持API接口查询和SQL直接数据库查询两种方式；从流程设计上，分为常规API查询、复杂API查询和开放式SQL查询。

*项目目标*：用户初期使用查询，能实现60%的查询通过API就能解决，通过API查询，80%的查询在5s内返回结果。API不能实现的查询自动流转到SQL查询，通过SQL查询在15s内返回结果。

*设计理念*：1、统一查询接口：一个接口处理所有类型的数据查询请求，释放更多的能力给到其他工 
             具。
             2、高效澄清：在最前端只做一次澄清交互，提升交互效率。
             3、高效路由识别：通过简单的关键词匹配，把10%的开放性查询路由至SQL查询，剩下90%的用户问题直接走API查询，同样的思路用于API接口选择，选择实现高效的一、二级路由。
             4、自适应参数提取转换：在路由至API查询后，地理位置、时间等信息提取和转换优先通过代码设计实现，确保在5s内实现80%的API查询，剩下20%API查询通过llm实现API选择和接口参数补全。
             5、自愈式系统：在API查询的每个阶段设计失败回退机制，使用SQL查询作为托底手段，确保用户的体验。
**注：API接口查询的特点是结果准确，相对较快，但查询的结果输出固定且有限。SQL查询的特点是灵活、开放，但统计计算可能不准确（修约计算不符合规则）。**




## 🏗️ 系统架构

### 核心设计

┌─────────────────────────────────────────────────────────────────────┐
│                    🚀 应用工厂 (start.py → app.py)                     │
├─────────────────────────────────────────────────────────────────────┤
│  🧠 智能路由层                          🛡️ 错误恢复层                   │
│  ├─ UQP统一查询路由器                    ├─ 错误分类器                  │
│  ├─ API优先决策引擎                     ├─ LLM错误恢复器               │
│  ├─ 路由监控器                         ├─ 智能工具重选择器             │
│  └─ 智能工具选择器                      └─ SQL回退处理器               │
├─────────────────────────────────────────────────────────────────────┤
│  🔧 参数处理层                          📊 数据访问层                   │
│  ├─ 智能地理位置提取器                   ├─ 外部API处理器               │
│  ├─ 参数转换器                         ├─ Vanna核心服务              │
│  ├─ 参数去重处理器                      ├─ 数据库管理器                │
│  └─ 增强参数提取器                      └─ RAG检索器                  │
├─────────────────────────────────────────────────────────────────────┤
│  ⚙️ 配置管理层                          🎛️ 监控统计层                   │
│  ├─ 路由策略配置                        ├─ 错误监控系统                │
│  ├─ 外部API配置                        ├─ 性能统计分析                │
│  ├─ 地理位置映射                        ├─ 决策链追踪                  │
│  └─ 提示词配置                         └─ 系统健康监控                │
└─────────────────────────────────────────────────────────────────────┘
```

统一API查询处理架构
  ├── 第一层：参数提取与预处理
  │   ├── 地理位置提取和分组
  │   ├── 时间参数提取（增强年份补全）
  │   └── 工具选择（综合/对比）
  ├── 第二层：参数完整性校验与智能补充
  │   ├── 综合查询参数校验
  │   ├── 对比查询参数校验（含对比时间）
  │   └── 统一LLM智能补充机制 ⭐
  ├── 第三层：参数转换与验证
  │   ├── 多层级地理编码转换
  │   ├── 统一时间解析（含兜底） ⭐
  │   └── API参数格式化
  ├── 第四层：API执行与错误处理
  │   ├── 多层级API调用
  │   ├── HTTP错误检测与分类 ⭐
  │   └── 统一错误恢复机制 ⭐
  └── 第五层：结果验证与最终兜底
      ├── 结果质量评估
      ├── 数据有效性检查
      └── SQL查询兜底 ⭐

### 🔥 核心组件

#### 🚀 应用工厂模式
- **`start.py`**: 唯一的应用启动入口，统一端口 9091
- **`src/app.py`**: 应用工厂，集成所有模块化蓝图，提供完整的依赖注入
- **模块化蓝图**: 各功能模块独立注册，便于扩展和维护

#### 🧠 智能路由系统
- **`src/uqp_router.py`**: 统一查询路由器，API优先策略的核心实现
- **`src/routing/decision_engine.py`**: 路由决策引擎，基于关键词的高效分流
- **`src/routing/api_priority_engine.py`**: API优先引擎，SQL排除关键词策略
- **`src/routing/routing_monitor.py`**: 路由监控器，完整的性能统计和分析

#### 🛡️ 四阶段智能错误恢复系统
- **`src/intelligence/error_classifier.py`**: 错误分类器，智能错误分类和恢复策略推荐
- **`src/intelligence/llm_error_recovery.py`**: LLM错误恢复器，基于大模型的智能错误处理
- **`src/intelligence/smart_tool_reselection.py`**: 智能工具重选择器，工具选择失败时的重选择机制
- **`src/intelligence/enhanced_param_extractor.py`**: 增强参数提取器，参数提取失败时的智能重提取
- **`src/intelligence/sql_fallback_handler.py`**: SQL回退处理器，API失败时自动降级到SQL查询
- **`src/intelligence/error_monitoring_system.py`**: 错误监控系统，完整的错误统计和分析

#### 🔧 智能参数处理
- **`src/utils/smart_geo_extractor.py`**: 智能地理位置提取器，支持全文模糊匹配和错误恢复
- **`src/utils/param_converter.py`**: 参数转换器，地理编码和时间解析的智能转换
- **`src/utils/parameter_deduplicator.py`**: 参数去重处理器，解决多参数冲突问题

#### 📊 数据访问层
- **`src/external_api_handler.py`**: 智能外部API处理器，支持第四阶段错误恢复机制
- **`src/vanna_service.py`**: Vanna核心服务，支持LLM工具调用能力
- **`src/api_registry.py`**: API工具注册中心，定义所有可用的外部API工具

## 🌟 核心设计理念

### 1. 🎯 API优先的智能路由策略

**设计思想**: 基于 **"API优先，SQL兜底"** 的策略，实现高效精准的查询路由

```
用户查询 → 关键词匹配 → 路由决策
    ↓
┌─────────────────┐         ┌─────────────────┐
│  🚀 API路径      │         │  💾 SQL路径      │
│  (优先选择)      │         │  (兜底方案)      │
│                │         │                │
│ • 标准数据查询   │         │ • 探索性查询     │
│ • 统计报表      │         │ • 实时数据       │
│ • 对比分析      │         │ • 复杂统计       │
│ • 专业指标      │         │ • 自定义查询     │
└─────────────────┘         └─────────────────┘
```

**关键特性**:
- ⚡ **极速分流**: 基于53个精心设计的SQL排除关键词，毫秒级路由决策
- 🎯 **精准识别**: 识别探索性查询（如"哪些"、"最大"、"统计"）自动走SQL路径
- 🔄 **策略切换**: 支持运行时动态切换路由策略
- 📊 **性能监控**: 完整的分流比例、响应时间统计

### 2. 🔧 双模式工具选择机制

**设计思想**: **"快速匹配 + LLM智能分析"** 的混合模式，兼顾效率与准确性

```
工具选择请求
    ↓
┌─────────────────┐    失败    ┌─────────────────┐
│ 🏃 关键词匹配模式 │ --------→ │ 🧠 LLM分析模式    │
│ (主要模式)       │           │ (备用模式)       │
│                │           │                │
│ • 毫秒级响应     │           │ • 深度理解       │
│ • 基于关键词     │           │ • 语义分析       │
│ • 高效稳定       │           │ • 复杂推理       │
└─────────────────┘           └─────────────────┘
```

**核心工具**:
- **`get_summary_report`**: 综合统计报表（单一时间段查询）
- **`get_comparison_report`**: 对比分析报表（时间段对比查询）

### 3. 🛡️ 四阶段智能错误恢复机制

**设计思想**: **"预防为主，智能恢复，全链路监控"** 的自愈式系统设计

```
第一阶段: 预防性设计          第二阶段: 智能参数重提取
├─ 参数验证                 ├─ 增强参数提取器
├─ 配置检查                 ├─ LLM智能推断
└─ 连接测试                 └─ 多策略尝试
    ↓ 错误发生                  ↓ 仍然失败
第三阶段: 工具智能重选择       第四阶段: SQL回退机制
├─ 错误分类分析             ├─ 自动降级到SQL
├─ 工具适用性判断           ├─ 保持响应格式一致
└─ LLM重新选择工具          └─ 完整错误监控统计
```

### 4. 🔍 智能参数转换系统

**设计思想**: **"全文模糊匹配 + 层级优先选择 + LLM智能托底"** 的参数处理策略

```
用户输入: "昨天广雅中学的空气质量"
    ↓
智能地理位置提取器
├─ 时间前缀过滤: "昨天" → 移除
├─ 全文模糊匹配: "广雅中学" → 匹配度95%
├─ 层级优先选择: 站点 > 区县 > 城市
└─ 编码转换: "广雅中学" → "1001A"
    ↓
参数去重处理器
├─ 地理位置去重: 保留最精确的位置
├─ 时间精度评分: 选择最高精度时间
└─ API参数去重: 避免参数冲突
    ↓
LLM智能托底（必要时）
├─ 时间参数补充: 未指定时间推断为"今天"
├─ 对比时间推算: 智能推断同比/环比时间
└─ 工具适用性判断: 探索性查询转向SQL
```

### 5. ⚙️ 配置化与可扩展性设计

**设计思想**: **"配置驱动，热更新，工具注册"** 的可扩展架构

```
配置文件体系
├─ config/config.yaml              # 主配置文件
├─ config/routing_config.yaml      # 路由策略配置
├─ config/external_api_config.yaml # 外部API配置
├─ config/geo_mappings.json        # 地理位置映射
├─ config/external_api_prompts.yaml# API提示词配置
└─ config/sql_prompts.yaml         # SQL提示词配置
    ↓
工具注册机制
├─ src/api_registry.py             # API工具注册中心
├─ 结构化工具定义                   # 标准化工具描述格式
├─ 参数类型约束                     # 自动参数验证
└─ 热插拔支持                       # 动态添加新工具
```

## 🚀 快速开始

### 环境准备

**Windows 环境**:
```bash
# 创建并激活虚拟环境
python -m venv venv
.\venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

**Linux 环境**:
```bash
# 创建并激活虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 启动系统

```bash
# 统一启动方式 (推荐使用) - 端口9091
python start.py
```

### 核心API测试

**1. 智能统一查询测试** (推荐使用)

```bash
# 基础健康检查
curl http://127.0.0.1:9091/health

# 标准数据查询 (API路径)
curl -X POST http://127.0.0.1:9091/api/uqp/query \
  -H "Content-Type: application/json" \
  -d '{"question": "查询广雅中学上周的空气质量数据"}'

# 对比分析查询 (API路径)
curl -X POST http://127.0.0.1:9091/api/uqp/query \
  -H "Content-Type: application/json" \
  -d '{"question": "比较广州市今年5月和去年5月的空气质量"}'

# 探索性查询 (SQL路径)
curl -X POST http://127.0.0.1:9091/api/uqp/query \
  -H "Content-Type: application/json" \
  -d '{"question": "哪些城市的空气质量最差？"}'
```

**2. 系统监控测试**

```bash
# 路由状态检查
curl http://127.0.0.1:9091/api/uqp/status

# 外部API状态检查
curl http://127.0.0.1:9091/api/external/status

# 错误监控系统状态
curl http://127.0.0.1:9091/api/external/error-monitoring/health
```

**3. 智能地理位置提取器测试**

```bash
# 测试智能地理位置提取
python -c "from src.utils.smart_geo_extractor import get_smart_geo_extractor; extractor = get_smart_geo_extractor(); print(extractor.extract_locations('昨天广州市O3-8h是多少？'))"

# 测试模糊匹配功能
python -c "from src.utils.smart_geo_extractor import get_smart_geo_extractor; extractor = get_smart_geo_extractor(); print(extractor.extract_locations('广雅的PM2.5浓度'))"
```

**4. 智能错误恢复系统测试**

```bash
# 错误监控API测试
curl http://127.0.0.1:9091/api/external/error-monitoring/statistics?time_range=24h
curl http://127.0.0.1:9091/api/external/error-monitoring/performance
curl http://127.0.0.1:9091/api/external/error-monitoring/recovery-analysis
curl http://127.0.0.1:9091/api/external/error-monitoring/trend?hours=24
```

**5. 路由策略测试**

```bash
# 测试路由分流功能
python tests/test_routing_phase1.py

# 查看当前路由策略
python -c "from src.routing.decision_engine import get_routing_engine; print(get_routing_engine().get_stats())"

# 路由策略性能测试
python tests/test_routing_strategy.py
```

## 🔧 核心功能详解

### 🧠 智能路由系统

#### API优先策略
- **核心思想**: 优先使用专业API接口，保证数据准确性和查询性能
- **SQL排除关键词**: 精心设计的53个关键词，识别需要走SQL路径的探索性查询
- **实时策略切换**: 支持运行时切换路由策略，无需重启服务

#### 关键词配置
```yaml
# config/routing_config.yaml
sql_exclusion_keywords:
  - "哪些"    # 探索性查询
  - "最大"    # 排序分析
  - "统计"    # 复杂统计
  - "实时"    # 实时数据
  - "小时"    # 细粒度时间
  # ... 更多关键词
```

### 🔧 智能参数处理

#### 智能地理位置提取器
```python
# 核心特性展示
from src.utils.smart_geo_extractor import get_smart_geo_extractor

extractor = get_smart_geo_extractor()

# 全文模糊匹配
result = extractor.extract_locations("昨天广雅中学的PM2.5浓度")
# 输出: [{'name': '广雅中学', 'code': '1001A', 'type': '站点', 'confidence': 95}]

# 时间前缀自动过滤
result = extractor.extract_locations("上周广州市空气质量")  
# 自动过滤"上周"，识别"广州市"

# 层级优先选择
result = extractor.extract_locations("广州增城新塘空气质量")
# 优先选择站点级别的"增城新塘"而不是城市级别的"广州"
```

#### 参数转换器
```python
# 时间解析示例
from src.utils.param_converter import ParamConverter

converter = ParamConverter()

# 相对时间解析
time_range = converter.parse_time_description("上周")
# 输出: ("2024-07-08 00:00:00", "2024-07-14 23:59:59")

# 绝对时间解析
time_range = converter.parse_time_description("2024年5月")
# 输出: ("2024-05-01 00:00:00", "2024-05-31 23:59:59")
```

### 🛡️ 四阶段错误恢复系统

#### 第一阶段: 预防性设计
- 参数验证和配置检查
- 连接池健康监控
- API可用性预检

#### 第二阶段: 智能参数重提取
- 增强参数提取器自动重试
- LLM智能推断缺失参数
- 多策略参数解析

#### 第三阶段: 工具智能重选择
- 错误分类和原因分析
- 工具适用性重新评估
- LLM重新选择合适工具

#### 第四阶段: SQL回退机制
- API失败时自动降级到SQL查询
- 保持UQP响应格式一致性
- 完整的错误监控统计

#### 错误监控系统
```python
# 错误统计查询
from src.intelligence.error_monitoring_system import get_error_monitoring_system

monitor = get_error_monitoring_system()

# 获取错误统计
stats = monitor.get_error_statistics(time_range='24h')
print(f"总错误数: {stats['total_errors']}")
print(f"恢复成功率: {stats['recovery_success_rate']}%")

# 获取性能指标
performance = monitor.get_performance_metrics()
print(f"平均响应时间: {performance['avg_response_time']}ms")
```

### 📊 地理位置映射管理

#### 命令行管理工具
```bash
# 查看所有映射
python scripts/tools/manage_geo_mappings.py list

# 添加站点映射
python scripts/tools/manage_geo_mappings.py add station "华师附中" "1008A"

# 搜索映射
python scripts/tools/manage_geo_mappings.py search "广雅"

# 批量导入
python scripts/tools/manage_geo_mappings.py batch stations.txt station
```

#### 配置文件管理
```json
{
  "stations": {
    "广雅中学": "1001A",
    "广雅": "1001A",
    "华师附中": "1008A"
  },
  "districts": {
    "天河区": "440106",
    "天河": "440106"
  },
  "cities": {
    "广州市": "440100",
    "广州": "440100"
  }
}
```

## ⚙️ 配置管理

### 主要配置文件

#### 1. 主配置文件 (`config/config.yaml`)
```yaml
# LLM配置
llm:
  provider: "openai"
  model: "gpt-4"
  api_key: "${OPENAI_API_KEY}"
  
# 数据库配置
database:
  host: "localhost"
  port: 3306
  database: "air_quality"
  
# 外部API配置
external_api:
  primary_mode: "keyword_matching"
  fallback_mode: "llm_analysis"
  auto_upgrade_enabled: true
```

#### 2. 路由策略配置 (`config/routing_config.yaml`)
```yaml
# 一级路由配置
primary_routing:
  strategy: "api_priority"
  sql_exclusion_keywords:
    - "哪些"
    - "最大"
    - "统计"
    # ... 更多关键词
  debug_enabled: true
  performance_monitoring: true

# 二级路由配置  
secondary_routing:
  tool_selection:
    primary_method: "keyword_matching"
    fallback_method: "llm_analysis"
  keyword_matching:
    comparison_keywords:
      - "环比"
      - "同比"
      - "对比"
      # ... 更多关键词
```

#### 3. 外部API配置 (`config/external_api_config.yaml`)
```yaml
# API基础配置
api_config:
  base_url: "https://api.example.com"
  username: "${API_USERNAME}"
  password: "${API_PASSWORD}"
  timeout: 30
  
# 性能配置
performance:
  max_retries: 3
  retry_delay: 1
  cache_enabled: true
```

### 配置管理命令

```bash
# 查看路由配置
type config\routing_config.yaml

# 查看外部API配置
type config\external_api_config.yaml

# 查看地理位置映射
type config\geo_mappings.json
```

## 📊 监控与运维

### 系统监控

#### 健康检查
```bash
# 整体健康检查
curl http://127.0.0.1:9091/health

# UQP路由器状态
curl http://127.0.0.1:9091/api/uqp/status

# 外部API状态
curl http://127.0.0.1:9091/api/external/status

# 数据库连接池状态
curl http://127.0.0.1:9091/db-connection-status
```

#### 性能监控
```bash
# 路由性能统计
python -c "from src.routing.decision_engine import get_routing_engine; print(get_routing_engine().get_stats())"

# 错误监控统计
curl http://127.0.0.1:9091/api/external/error-monitoring/statistics?time_range=24h

# 系统性能指标
curl http://127.0.0.1:9091/api/external/error-monitoring/performance
```

### 日志管理

#### 日志级别配置
```yaml
# config/routing_config.yaml
monitoring:
  enabled: true
  log_level: "INFO"  # DEBUG/INFO/WARNING/ERROR
  
  performance_metrics:
    track_response_time: true
    track_route_distribution: true
    track_success_rate: true
```

#### 日志文件位置
- **应用日志**: `logs/app.log`
- **路由统计**: `logs/routing_stats.json`
- **错误监控**: `logs/error_monitoring.log`

## 🔧 开发指南

### 添加新的API工具

#### 1. 在API注册中心定义工具
```python
# src/api_registry.py
{
    "name": "get_new_report",
    "description": "获取新类型报表",
    "parameters": {
        "location": {
            "type": "string",
            "description": "地理位置",
            "required": True
        },
        "time_range": {
            "type": "array", 
            "description": "时间范围",
            "required": True
        }
    }
}
```

#### 2. 在外部API处理器中实现
```python
# src/external_api_handler.py
def get_new_report(self, location, time_range):
    """新报表获取实现"""
    # 实现具体的API调用逻辑
    pass
```

#### 3. 更新工具选择配置
```yaml
# config/routing_config.yaml
tool_selection_rules:
  get_new_report:
    condition: "匹配特定关键词"
    keywords: ["新报表", "特殊查询"]
```

### 扩展参数转换器

```python
# src/utils/param_converter.py
class ParamConverter:
    def parse_new_parameter(self, param_text):
        """添加新的参数解析逻辑"""
        # 实现新的参数解析
        pass
```

### 自定义错误恢复策略

```python
# src/intelligence/error_classifier.py
def classify_new_error_type(self, error):
    """添加新的错误类型分类"""
    # 实现错误分类逻辑
    pass
```

## 🌟 核心特性总览

### ✅ 智能路由系统
- **API优先策略**: 基于SQL排除关键词的高效路由决策
- **双模式工具选择**: 关键词匹配 + LLM智能分析
- **实时策略切换**: 支持运行时切换路由策略
- **完整性能监控**: 路由分布、响应时间、成功率统计

### ✅ 智能参数处理
- **智能地理位置提取**: 全文模糊匹配、层级优先选择、自动错误过滤
- **参数智能转换**: 地理编码、时间解析、模糊匹配
- **参数去重处理**: 地理位置去重、时间精度评分、API参数去重
- **LLM智能托底**: 时间参数补充、对比时间推算、工具适用性判断

### ✅ 四阶段错误恢复
- **预防性设计**: 参数验证、配置检查、连接池监控
- **智能参数重提取**: 增强参数提取、LLM推断、多策略尝试
- **工具智能重选择**: 错误分类、适用性评估、LLM重选择
- **SQL回退机制**: 自动降级、格式一致、完整监控

### ✅ 地理位置映射
- **三级地理编码**: 站点、区县、城市三个层级
- **模糊匹配算法**: 支持别名和模糊匹配
- **命令行管理**: 便捷的增删改查操作
- **批量导入功能**: 从文件批量导入映射关系

### ✅ 系统可扩展性
- **模块化架构**: 应用工厂 + 蓝图注册模式
- **配置化管理**: YAML配置文件 + 热更新支持
- **工具注册机制**: 标准化工具定义和热插拔
- **完整调试支持**: 详细的执行路径和错误信息

### ✅ 性能优化
- **连接池管理**: 数据库连接池自动管理和监控
- **缓存机制**: 多级缓存提升响应速度
- **极简路由**: 毫秒级路由决策
- **异步处理**: 支持异步API调用

### ✅ 监控运维
- **健康检查**: 多层级系统健康状态监控
- **性能统计**: 完整的性能指标和趋势分析
- **错误监控**: 实时错误统计和恢复成功率
- **日志管理**: 分级日志和结构化日志输出

## 🚀 技术栈

- **后端框架**: Flask + 应用工厂模式
- **AI引擎**: Vanna.AI + OpenAI GPT
- **数据库**: MySQL / SQL Server + 连接池
- **向量数据库**: ChromaDB
- **配置管理**: YAML + 环境变量
- **监控统计**: 自研监控系统 + 性能统计
- **智能匹配**: TF-IDF + 模糊匹配算法
- **错误恢复**: 多阶段智能恢复机制

## 📝 版本信息

- **系统版本**: 1.0.0
- **配置版本**: 1.0.0
- **最后更新**: 2024-07-20
- **兼容性**: Python 3.8+

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交变更 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

---

> 💡 **设计理念**: 我们相信智能化不是简单的功能堆砌，而是通过精心设计的架构和算法，让系统具备真正的"理解"和"自愈"能力。Vanna智能统一查询系统正是这一理念的完美体现。