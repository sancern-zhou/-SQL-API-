# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 用户习惯
需要用中文回复用户。
不要做任何假设，确认后再修改。
用户是在windows系统CMD环境下进行开发和测试，所以提供的测试用例请按windows系统的方法提供。
每次测试的时候都必须激活虚拟环境，不是依赖缺失，不要尝试去下载依赖。
对于无法定位的问题，优先添加日志信息，进行测试，方便定位问题。
必须采取模块化开发的设计思路，遵循最佳实践。
不要删除文件里的疑难问题。
你负责开发，不需要生成任何的测试，每次修改完后跟用户确认是否需要生成测试说明，给到专门的测试人员进行测试。

## 统一启动方式 (Recommended)

```bash
# 启动应用 (推荐使用此方式) - 端口9091
python start.py
```

## 开发命令

### 环境设置
```bash
# 创建并激活虚拟环境
python -m venv venv

# Windows
.\venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### API 测试 (端口 9091)
```bash
# 基础健康检查
curl http://127.0.0.1:9091/health

# NL2SQL 生成测试
curl -X POST http://127.0.0.1:9091/nl2sql \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"查询今天的空气质量数据\"}"

# 智能统一查询测试 (推荐使用)
curl -X POST http://127.0.0.1:9091/api/uqp/query \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"查询广雅中学上周的空气质量数据\"}"

# 空气质量对比查询测试
curl -X POST http://127.0.0.1:9091/api/uqp/query \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"比较广州市今年5月和去年5月的空气质量\"}"

# 探索性查询测试 (会走SQL路由)
curl -X POST http://127.0.0.1:9091/api/uqp/query \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"哪些城市的空气质量最差？\"}"

# 外部API状态检查
curl http://127.0.0.1:9091/api/external/status

# 路由策略状态检查
curl http://127.0.0.1:9091/api/uqp/status
```

### 路由策略测试
```bash
# 测试路由分流功能
python tests/test_routing_phase1.py

# 查看当前路由策略
python -c "from src.routing.decision_engine import get_routing_engine; print(get_routing_engine().get_stats())"

# 路由策略性能测试
python tests/test_routing_strategy.py
```

### 智能地理位置提取器测试
```bash
# 测试智能地理位置提取器
python -c "from src.utils.smart_geo_extractor import get_smart_geo_extractor; extractor = get_smart_geo_extractor(); print('智能地理位置提取器可用')"

# 测试特定地理位置提取
python -c "from src.utils.smart_geo_extractor import get_smart_geo_extractor; extractor = get_smart_geo_extractor(); print(extractor.extract_locations('昨天广州市O3-8h是多少？'))"

# 测试模糊匹配功能
python -c "from src.utils.smart_geo_extractor import get_smart_geo_extractor; extractor = get_smart_geo_extractor(); print(extractor.extract_locations('广雅的PM2.5浓度'))"
```

### 智能错误恢复系统测试
```bash
# 测试错误分类器
python -c "from src.intelligence.error_classifier import get_error_classifier; print('错误分类器可用')"

# 测试LLM错误恢复器
python -c "from src.intelligence.llm_error_recovery import get_llm_error_recovery; print('LLM错误恢复器可用')"

# 测试智能工具重选择器
python -c "from src.intelligence.smart_tool_reselection import get_smart_tool_reselection; print('智能工具重选择器可用')"

# 测试增强参数提取器
python -c "from src.intelligence.enhanced_param_extractor import get_enhanced_param_extractor; print('增强参数提取器可用')"

# 测试SQL回退处理器
python -c "from src.intelligence.sql_fallback_handler import get_sql_fallback_handler; print('SQL回退处理器可用')"

# 测试错误监控系统
python -c "from src.intelligence.error_monitoring_system import get_error_monitoring_system; print('错误监控系统可用')"

# 错误监控API测试
curl http://127.0.0.1:9091/api/external/error-monitoring/statistics?time_range=24h
curl http://127.0.0.1:9091/api/external/error-monitoring/performance
curl http://127.0.0.1:9091/api/external/error-monitoring/health
curl http://127.0.0.1:9091/api/external/error-monitoring/recovery-analysis
curl http://127.0.0.1:9091/api/external/error-monitoring/trend?hours=24
```

### 系统架构优化测试
```bash
# 测试优化后的参数提取流程
curl -X POST http://127.0.0.1:9091/api/uqp/query \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"深圳宝安福永上月空气质量同比变化了多少？\"}"

# 测试LLM智能时间参数补充
curl -X POST http://127.0.0.1:9091/api/uqp/query \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"广雅中学空气质量怎么样？\"}"  # 未指定时间，LLM智能补充

# 测试LLM工具重选择功能
curl -X POST http://127.0.0.1:9091/api/uqp/query \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"哪些城市的空气质量最差？\"}"  # 探索性查询，LLM判断转SQL

# 测试LLM直接API参数生成功能 (2025-07-22 新增)
curl -X POST http://127.0.0.1:9091/api/uqp/query \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"深圳宝安区今天空气质量同比去年变化了多少？\"}"  # 复杂查询，LLM直接生成API参数

# 测试多地理位置查询 (2025-07-22 新增)
curl -X POST http://127.0.0.1:9091/api/uqp/query \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"广州市天河区、海珠区和越秀区本月空气质量情况如何？\"}"  # 多地理位置查询
```

### 配置文件管理
```bash
# 查看路由配置
type config\routing_config.yaml

# 查看外部API配置
type config\external_api_config.yaml

# 查看主配置文件
type config\config.yaml

# 查看地理位置映射
type config\geo_mappings.json
```

## 系统架构 (应用工厂模式)

### 核心组件
- **启动脚本 (`start.py`)**: 唯一的应用启动入口，调用应用工厂 `create_app`，启动在9091端口
- **应用工厂 (`src/app.py`)**: 定义 `create_app` 函数，负责：
    1. 创建 Flask `app` 实例
    2. 初始化 `VannaService` 核心服务
    3. 初始化 `ExternalAPIHandler` 外部API处理器
    4. 注册所有模块化蓝图 (Blueprint)
- **Vanna Service (`src/vanna_service.py`)**: 核心业务逻辑，支持LLM工具调用能力
- **智能路由模块**:
    - **UQP统一查询路由器 (`src/uqp_router.py`)**: 统一查询处理入口，使用API优先策略进行分流
    - **路由决策引擎 (`src/routing/decision_engine.py`)**: 基于关键词的高效路由决策引擎
    - **API优先引擎 (`src/routing/api_priority_engine.py`)**: 基于SQL排除关键词的路由策略
    - **路由监控器 (`src/routing/routing_monitor.py`)**: 路由决策的性能监控和统计分析
    - **外部API处理器 (`src/external_api_handler.py`)**: 智能API处理器，支持第四阶段错误恢复机制
    - **工具选择器 (`src/routing/tool_selector.py`)**: 基于关键词匹配的工具选择策略
    - **参数去重处理器 (`src/utils/parameter_deduplicator.py`)**: 参数去重和单位置约束处理
    - **参数转换器 (`src/utils/param_converter.py`)**: 地理编码和时间解析的智能转换
- **智能错误恢复模块**（第四阶段）:
    - **错误分类器 (`src/intelligence/error_classifier.py`)**: 智能错误分类和恢复策略推荐
    - **LLM错误恢复器 (`src/intelligence/llm_error_recovery.py`)**: 基于LLM的智能错误恢复处理
    - **智能工具重选择器 (`src/intelligence/smart_tool_reselection.py`)**: 工具选择失败时的智能重选择
    - **增强参数提取器 (`src/intelligence/enhanced_param_extractor.py`)**: 参数提取失败时的智能重提取
    - **SQL回退处理器 (`src/intelligence/sql_fallback_handler.py`)**: API失败时的SQL回退机制
    - **错误监控系统 (`src/intelligence/error_monitoring_system.py`)**: 完整的错误监控和统计分析
    - **统一LLM托底管理器 (`src/intelligence/unified_llm_fallback_manager.py`)**: 统一的LLM兜底处理机制 (2025-07-22 新增)
- **API注册中心 (`src/api_registry.py`)**: 定义所有可用的外部API工具，包含两个主要工具：
    - `get_summary_report`: 综合统计报表（单一时间段查询）
    - `get_comparison_report`: 对比分析报表（时间段对比查询）
- **功能模块 (`src/modules/`)**: 底层功能模块
    - **数据库管理器 (`database_manager.py`)**: 连接池管理
    - **RAG检索器 (`rag_retriever.py`)**: 向量数据库检索
    - **SQL生成器 (`sql_generator.py`)**: 自然语言转SQL

## 重要文件 (新架构)

### 核心代码
- `start.py`: **唯一的应用启动脚本** 调用 `create_app` 来运行应用，端口9091
- `src/app.py`: **应用工厂** 包含 `create_app` 函数，是所有组件的集成中心
- `src/vanna_service.py`: 核心服务类，支持LLM工具调用
- `src/uqp_router.py`: **统一查询路由器**，使用API优先策略进行路由分流
- `src/external_api_handler.py`: **智能外部API处理器**，支持工具选择和参数处理，集成LLM直接API调用机制 (2025-07-22 增强)
- `src/routing/tool_selector.py`: **工具选择器**，基于关键词匹配的工具选择策略
- `src/utils/parameter_deduplicator.py`: **参数去重处理器**，解决多地理位置冲突问题
- `src/api_registry.py`: **API工具注册中心**，定义所有可用的外部API工具
- `src/utils/param_converter.py`: **参数转换器**，处理地理编码和时间解析，支持多时间参数提取 (2025-07-22 增强)
- `src/utils/smart_geo_extractor.py`: **智能地理位置提取器**，支持全文模糊匹配和错误恢复
- `src/intelligence/unified_llm_fallback_manager.py`: **统一LLM托底管理器**，统一处理所有类型的LLM兜底场景 (2025-07-22 新增)
- `src/modules/`: 业务逻辑子模块目录

### 配置文件结构
- `config/config.yaml`: **主要配置文件**，包含LLM配置、数据库连接、RAG设置等
- `config/routing_config.yaml`: **路由策略配置文件**，包含：
  - API优先策略和SQL排除关键词配置
  - 参数提取模式和地理位置配置
  - 时间解析配置和监控设置
- `config/external_api_config.yaml`: **外部API配置文件**，包含：
  - API基础连接配置（用户名、密码、端点）
  - 性能配置和测试模式设置
- `config/external_api_prompts.yaml`: **外部API提示词配置文件**，统一LLM托底提示词，支持多地理位置查询 (2025-07-22 增强)
- `config/sql_prompts.yaml`: **SQL生成提示词配置文件**
- `config/geo_mappings.json`: **地理位置映射数据**，包含站点、区县、城市的编码映射

### 知识与数据
- `data/knowledge/`: 存放用于RAG的业务知识文件
- `data/backups/`: 向量数据库备份文件
- `storage/vanna_chroma_db/`: ChromaDB向量数据库存储目录

### 集成与工具
- `integrations/dify/`: Dify工作流定义文件
- `scripts/tools/manage_geo_mappings.py`: 地理位置映射管理工具
- `tests/`: 测试文件目录

## 开发指南

### 智能查询系统（统一架构）
- **统一入口**: 使用 `/api/uqp/query` 进行所有查询，系统会自动路由到合适的处理器
- **API优先策略**: 基于SQL排除关键词的高效路由策略
  - 包含SQL关键词 → NL2SQL处理器（探索性查询）
  - 不包含SQL关键词 → 外部API处理器（标准查询）
- **关键词配置**: 所有SQL排除关键词统一配置在 `config/routing_config.yaml` 中
- **性能监控**: 完整的路由决策监控，包括分流比例、响应时间、系统健康度
- **参数转换**: 自动处理地理位置编码、时间解析等复杂参数转换
- **智能参数处理**:
  - **智能地理位置提取**: 基于地理位置映射的智能模糊匹配，自动层级优先选择
  - **多时间参数处理**: 支持提取和识别多个时间参数，用于复杂性检测 (2025-07-22 新增)
  - **复杂查询智能检测**: 基于时间参数数量(≥2个)的查询复杂性判断 (2025-07-22 新增)
  - **LLM直接API参数生成**: 复杂查询时LLM直接生成完整API参数，跳过传统转换流程 (2025-07-22 新增)
  - **LLM智能托底**: 专注于时间参数补充和工具重选择
    - 时间参数智能推断（如未指定时间时推断为"今天"或"本月"）
    - 对比时间智能补全（同比/环比查询的智能推断）
    - 工具适用性判断（探索性查询自动转向SQL）
  - **参数去重处理**: 地理位置去重和API参数去重
  - **多地理位置支持**: LLM能正确处理多个地理位置的API参数生成 (2025-07-22 增强)
- **智能错误恢复**（第四阶段）: 
  - 错误分类和智能恢复处理
  - LLM错误分析和参数重提取
  - SQL回退机制，API失败时自动降级到SQL查询
  - 完整的错误监控和统计分析
  - **统一LLM托底机制**: 所有托底场景使用统一的提示词和处理逻辑 (2025-07-22 新增)

### 外部API系统
- **工具注册**: 在 `src/api_registry.py` 中定义新的API工具
- **参数转换**: 在 `src/utils/param_converter.py` 中添加新的参数转换逻辑
- **执行层**: 在 `src/external_api_handler.py` 中实现具体的API调用逻辑
- **配置管理**: 在 `config/external_api_config.yaml` 中管理API连接参数

### 地理编码映射管理
- **配置文件**: `config/geo_mappings.json` 存储站点、区县、城市的名称和编码映射
- **管理工具**: 使用 `scripts/tools/manage_geo_mappings.py` 进行映射管理
- **添加映射**: `python scripts/tools/manage_geo_mappings.py add station "新站点" "编码"`
- **查看所有**: `python scripts/tools/manage_geo_mappings.py list`
- **搜索映射**: `python scripts/tools/manage_geo_mappings.py search "关键词"`
- **批量添加**: 从文件批量导入映射关系

### 连接池管理
- 使用 `vanna_service.db_manager` 来管理数据库连接
- 通过 `/db-connection-status` 端点监控连接池状态
- 通过 `/reset-connection-pool` 端点重置连接池

### 向量数据库操作
- ChromaDB集合分为：DDL、文档(documentation)、SQL范例(sql)
- 可通过 `vanna_service.get_training_data()` 检查向量数据库内容
- 意图分类使用独立的TF-IDF向量化器，不依赖ChromaDB
- API优先策略不依赖向量数据库，基于关键词匹配实现高效分流

### 路由策略配置
- **配置文件**: `config/routing_config.yaml` 包含所有路由相关配置
- **SQL排除关键词**: 精心设计的关键词用于识别探索性查询
- **策略切换**: 支持运行时切换路由策略，无需重启服务
- **性能监控**: 内置完整的监控体系，提供实时性能统计
- **调试模式**: 可开启详细的决策过程日志

### 提示词工程
- **SQL生成**: 配置在 `config/sql_prompts.yaml`
- **API工具选择**: 配置在 `config/external_api_prompts.yaml`
- **动态知识**: 通过RAG流程在运行时注入
- **调试模式**: 在 `config/config.yaml` 中设置 `debug: true` 可查看最终发送给LLM的完整提示

## 疑难解答 (Troubleshooting)

### 错误: `TypeError: object of type 'method' has no len()`

- **症状**: 在生成SQL时，应用日志中反复出现 `调用LLM失败: object of type 'method' has no len()` 的错误。即使代码看起来是正确的，清除缓存和重建环境后问题依旧。

- **根本原因**: 这是由 `vanna` 库的一个内部缺陷引起的。`vanna.base.base.VannaBase` 类中的 `_get_common_messages` 方法本应返回一个包含字符串的消息列表，但它错误地返回了一个其 `content` 值为**方法本身**（而不是字符串）的列表。当后续代码尝试计算这个"方法"的长度时，便会引发 `TypeError`。

- **解决方案**: 在 `src/modules/sql_generator.py` 的 `_call_llm` 方法中，**不要**调用 `self.vanna._get_common_messages()`。而是通过手动构建消息列表来绕过这个有问题的库函数，将包含完整上下文的提示作为 `system` 消息，将用户的原始问题作为 `user` 消息。这已在当前代码中实现。

### 错误: 启动时或运行时出现各种依赖相关的 `ModuleNotFoundError` 或 `AttributeError`

- **症状**: 在重建虚拟环境后，应用启动时报告 `ModuleNotFoundError: No module named 'openai'` 或 `'chromadb'`。或者在运行时出现与 `chromadb` 遥测相关的奇怪错误。

- **根本原因**: `vanna` 库将其一些核心依赖（如 `openai`, `chromadb`）声明为"可选"依赖。因此，仅仅 `pip install vanna` 并不会将它们全部安装。

- **解决方案**: 必须在 `requirements.txt` 文件中**明确地**列出所有这些核心依赖。当前 `requirements.txt` 文件已包含所有已知必需的库。如果未来遇到类似问题，应首先检查是否是 `vanna` 的某个可选依赖没有被安装。

### 路由策略配置

- **配置文件**: `config/routing_config.yaml` 包含完整的路由配置
- **关键词管理**: SQL排除关键词统一在配置文件中管理
- **策略使用**: 当前系统使用API优先策略，基于关键词匹配实现高效分流
- **高效分流**: 基于关键词匹配的快速路由决策

- **配置示例**:
```yaml
primary_routing:
  strategy: "api_priority"  # 统一使用API优先策略
  sql_exclusion_keywords:   # SQL排除关键词
    - "哪些"
    - "最大"
    - "统计"
    - "实时"
    - "小时"
    - "分钟"
    - "探索"
  debug_enabled: true
  performance_monitoring: true
```

### 错误: 地理位置无法识别

- **症状**: 系统提示 "无法确定位置 'XXX' 的具体含义"。

- **根本原因**: 地理位置提取器无法识别用户输入的位置名称。

- **解决方案**:
  1. **已优化**: 系统现在使用智能地理位置提取器 (`src/utils/smart_geo_extractor.py`)
  2. **全文模糊匹配**: 支持从用户问题中直接进行模糊匹配
  3. **自动错误恢复**: 智能处理"昨天广州市"→"广州市"等常见错误
  4. **LLM后备**: 复杂情况自动交给LLM处理

#### 智能地理位置提取器特性
- **全文匹配**: 不再依赖正则表达式，直接对用户问题进行模糊匹配
- **时间前缀过滤**: 自动识别并移除"昨天"、"上周"等时间前缀
- **动态阈值**: 根据地理位置类型(城市/区县/站点)动态调整匹配阈值
- **地理层级识别**: 支持"广州增城新塘"→"增城新塘"的智能层级识别
- **优先级排序**: 基于地理位置类型、常用程度、名称长度的综合优先级排序

### 错误: 多个地理位置导致API调用失败

- **症状**: 日志显示"检测到多个位置，请选择一个进行查询"，导致API调用失败。

- **根本原因**: 智能地理位置提取器成功识别了多个位置（如"广州"和"增城新塘"），但参数去重器无法智能识别它们的层级关系。

- **解决方案**: 
  1. **已修复**: 优化了参数去重器 (`src/utils/parameter_deduplicator.py`) 的地理层级识别能力
  2. **层级关系识别**: 系统现在能够识别"广州-增城新塘"等城市-站点层级关系
  3. **自动选择最精确位置**: 优先选择站点级别位置，其次是区县，最后是城市
  4. **智能判断**: 基于名称包含关系和位置类型关键词的智能判断

### 错误: LLM调用失败 `'VannaService' object has no attribute 'vanna'`

- **症状**: 在LLM智能判断时出现 `'VannaService' object has no attribute 'vanna'` 错误。

- **根本原因**: VannaService继承了LLM相关的基类，但调用时错误地使用了 `self.vanna.submit_prompt()`，而应该直接使用 `self.submit_prompt()`。

- **解决方案**: 已修复 `src/vanna_service.py` 中的LLM调用方法，使用正确的继承方法调用。

### 错误: 时间解析失败

- **症状**: 系统提示 "无法解析的时间描述" 或要求提供更具体的时间范围。

- **根本原因**: 时间描述不在预定义的解析模式中，或格式不够明确。

- **解决方案**:
  1. 使用标准的时间表达（如"上周"、"今年5月"、"2024年3月"）
  2. 在 `src/utils/param_converter.py` 中添加更多时间解析模式
  3. 避免使用模糊的时间表达（如"最近"、"前段时间"）

### 路由策略性能问题

- **症状**: 路由决策响应时间过长，或分流不准确。

- **根本原因**: 
  1. 使用了向量分类器但训练样本不足
  2. SQL排除关键词配置不当
  3. 监控功能影响性能

- **解决方案**:
  1. **性能优化**: 确保使用API优先策略，响应速度最快
  2. **关键词优化**: 检查并优化`config/routing_config.yaml`中的SQL排除关键词
  3. **监控调优**: 在生产环境中可关闭调试日志和详细监控
  4. **策略测试**: 运行`python tests/test_routing_phase1.py`验证路由性能
  5. **实时切换**: 使用路由决策引擎的`switch_strategy()`方法切换策略

### API优先策略配置

- **配置示例**:
```yaml
# config/routing_config.yaml
primary_routing:
  strategy: "api_priority"  # 使用API优先策略
  sql_exclusion_keywords:   # 自定义SQL排除关键词
    - "哪些"
    - "最大"
    - "统计"
    # ... 更多关键词
  debug_enabled: false      # 生产环境关闭调试
  performance_monitoring: true  # 保持性能监控
```

- **实时策略切换**:
```python
from src.routing.decision_engine import get_routing_engine
engine = get_routing_engine()

# 切换到API优先策略
result = engine.switch_strategy('api_priority')
print(result['message'])

# 查看当前状态
stats = engine.get_stats()
print(f"当前策略: {stats['current_strategy']}")
```

### 错误监控系统

- **监控模块**: 系统内置完整的智能错误恢复和监控模块
- **监控指标**: 包含错误统计、性能分析、恢复成功率等
- **API接口**: 提供完整的监控API接口供外部调用
- **自动恢复**: 支持多种自动错误恢复策略

### 外部API配置

- **配置文件**: `config/external_api_config.yaml` 包含完整的外部API配置
- **测试模式**: 支持测试模式，可使用模拟数据进行开发调试
- **认证管理**: 支持环境变量覆盖用户名密码配置
- **性能设置**: 包含超时、缓存等性能相关配置

## 最新疑难问题与解决方案 (2025-07-22 更新)

### 错误: LLM生成正确参数但系统未使用

- **症状**: 日志显示LLM成功生成了完整正确的API参数，但系统仍然进入传统参数转换流程，最终失败。

- **根本原因**: 复杂查询检测到LLM托底成功后，代码只是`pass`继续执行，没有实际使用LLM生成的参数。

- **解决方案**: 
  1. **已修复**: 在`src/external_api_handler.py:354-362`实现了LLM参数直接使用机制
  2. **参数检查**: 新增`_is_complete_api_params()`方法验证LLM参数完整性
  3. **直接调用**: 完整参数直接调用API，跳过传统转换流程
  4. **兼容处理**: 不完整参数仍整合到标准流程

### 错误: 字段名不匹配导致API调用失败

- **症状**: 系统报错`KeyError: 'endpoint'`，导致API调用失败。

- **根本原因**: `src/routing/tool_selector.py`中`get_tool_info()`返回的是`api_endpoint`字段，但`src/external_api_handler.py`中期望的是`endpoint`字段。

- **解决方案**:
  1. **已修复**: 在`external_api_handler.py:1125-1127`实现字段名兼容处理
  2. **优先级**: 优先查找`endpoint`，回退到`api_endpoint`
  3. **错误检查**: 两个字段都不存在时返回明确错误信息

### 错误: Token管理方法不存在

- **症状**: 系统报错`'ExternalAPIHandler' object has no attribute '_ensure_token_valid'`。

- **根本原因**: 新增的直接API调用代码中使用了不存在的`_ensure_token_valid()`方法，实际的token管理方法是`_get_token()`。

- **解决方案**:
  1. **已修复**: 在`external_api_handler.py:1191-1193`使用正确的`_get_token()`方法
  2. **Token使用**: 同步更新headers中的token使用方式
  3. **方法验证**: 调用前验证方法存在性

### 错误: LLM提示词缺少多地理位置支持

- **症状**: LLM在处理多地理位置查询时可能生成错误的参数格式。

- **根本原因**: 统一托底提示词中缺少多地理位置查询的示例和指导。

- **解决方案**:
  1. **已完善**: 在`config/external_api_prompts.yaml`中新增完整的多地理位置示例
  2. **示例覆盖**: 包含单地理位置、多地理位置、多站点对比的所有场景
  3. **核心原则**: 明确添加多地理位置支持和地理层级识别原则

## 开发经验教训总结

### 常见错误模式

1. **接口不匹配错误**: 
   - **表现**: 字段名、方法名不一致导致的运行时错误
   - **原因**: 新功能开发时未充分检查现有接口定义
   - **预防**: 开发前必须检查现有接口，确保一致性

2. **方法存在性假设错误**:
   - **表现**: 调用不存在的方法导致AttributeError
   - **原因**: 基于假设或复制粘贴代码，未验证方法存在性
   - **预防**: 调用任何方法前先确认其在当前类中存在

3. **流程逻辑断裂错误**:
   - **表现**: 前置步骤成功但后续步骤未有效利用结果
   - **原因**: 修改了流程某一环节但未同步更新后续流程
   - **预防**: 端到端测试，验证完整数据流

### 质量保证措施

1. **接口一致性检查清单**:
   ```bash
   # 检查方法是否存在
   grep -n "def method_name" src/target_file.py
   
   # 检查字段名定义
   grep -n "field_name" src/config_file.py
   
   # 检查调用链完整性
   grep -rn "method_call" src/
   ```

2. **分层测试验证**:
   - **单元测试**: 验证单个方法的正确性
   - **集成测试**: 验证模块间接口匹配
   - **端到端测试**: 验证完整查询流程

3. **错误恢复机制验证**:
   - **主流程测试**: 正常情况下的处理流程
   - **异常流程测试**: 各种错误情况的恢复机制
   - **边界条件测试**: 极端参数下的系统表现

## important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.