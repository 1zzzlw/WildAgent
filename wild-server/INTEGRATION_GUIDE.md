# P0 方案集成指南

本指南详细说明如何将结构自检和查询改写集成到现有的生成节点中。

---

## 📋 前置准备

### 1. 安装依赖

```bash
cd wild-server
.\.venv\Scripts\activate
uv pip install pytest-asyncio  # 如果还没安装
```

### 2. 验证安装

```bash
$env:PYTHONPATH="."
python examples/p0_usage_example.py
```

如果看到所有示例成功运行，说明安装正确。

---

## 🔧 集成步骤

### 方案 A: 在 skeleton_node.py 中集成

#### 步骤 1: 导入模块

在文件顶部添加导入：

```python
# wild-server/app/agent/nodes/skeleton_node.py

# 在现有导入后添加
from app.agent.validators import StructureValidator, JsonSchemaValidator
from app.agent.rag import QueryRewriter
from app.config import get_domain_config
```

#### 步骤 2: 集成查询改写（RAG 检索前）

在 `skeleton_generator` 函数中，找到 RAG 检索部分（约第 55 行）：

```python
async def skeleton_generator(state: GenerationState) -> dict:
    # ... 现有代码 ...
    
    # ── 1. RAG 检索（专注建筑类型知识）──
    rag_t0 = _time.time()
    
    # 🆕 添加查询改写
    rewritten_query = None
    try:
        domain_schema = get_domain_config().get_schema()
        rewriter = QueryRewriter(llm, domain_schema)
        rewritten_query = await rewriter.rewrite(user_message)
        
        # 使用改写后的关键词
        base_keywords = " ".join(rewritten_query.get("keywords", [])[:5])
        entity_type = rewritten_query.get("entity_type")
        
        logger.info(
            f"[skeleton] 查询改写: entity_type={entity_type}, "
            f"keywords={rewritten_query.get('keywords', [])[:3]}"
        )
    except Exception as e:
        logger.warning(f"[skeleton] 查询改写失败，使用原始查询: {e}")
        base_keywords = user_message
        entity_type = None
    
    # 构建查询（优化版）
    queries = [
        # 使用改写后的关键词
        SpecQuery(base_keywords, {"doc_type": "building_type"}),
        SpecQuery(base_keywords, {"doc_type": "recipe"}),
        SpecQuery(
            f"{base_keywords} 组合体量 退台 结构轴网 立面进深",
            {"doc_type": "pattern", "entity_type": entity_type or "building"},
        ),
        SpecQuery("墙体 楼板 柱子 梁", {"entity_type": "structural_component"}),
    ]
    
    # ... 继续现有的 RAG 检索代码 ...
```

#### 步骤 3: 集成结构自检（LLM 生成后）

在 blueprint 提取后、schema 验证前（约第 130 行）：

```python
async def skeleton_generator(state: GenerationState) -> dict:
    # ... LLM 调用和 blueprint 提取 ...
    
    if not blueprint:
        # ... 现有的回退逻辑 ...
    
    # ── 5. 归一化和 Schema 校验 ──
    blueprint = normalize_blueprint_input(blueprint)
    
    # 🆕 添加结构自检（在 validate_blueprint_schema 之前）
    struct_errors = []
    try:
        from app.utils.wild_schema import get_blueprint_schema  # 假设有统一 schema
        
        schema_validator = JsonSchemaValidator()
        validator = StructureValidator(schema_validator, llm)
        
        blueprint, struct_errors = await validator.validate_and_fix(
            blueprint,
            node_name="skeleton",
            schema=get_blueprint_schema(),  # 或使用现有的 schema
            max_retries=1  # 允许一次 LLM 修复
        )
        
        if struct_errors:
            logger.warning(
                f"[skeleton] 结构自检发现 {len(struct_errors)} 个错误，"
                "已尝试自动修复"
            )
    except Exception as e:
        logger.warning(f"[skeleton] 结构自检失败: {e}")
    
    # 继续现有的 schema 验证
    schema_issues = validate_blueprint_schema(blueprint)
    
    # ... 继续现有代码 ...
    
    # 在返回的 diag 中添加结构自检信息
    return {
        "skeleton_blueprint": blueprint,
        # ... 其他字段 ...
        "skeleton_diag": {
            # ... 现有字段 ...
            "structure_errors": struct_errors,  # 🆕 添加
            "query_rewrite": rewritten_query,   # 🆕 添加
        },
    }
```

---

### 方案 B: 在 base_component_node.py 中集成

#### 步骤 1: 在生成器中集成查询改写

修改 `create_component_generator` 函数：

```python
# wild-server/app/agent/nodes/base_component_node.py

def create_component_generator(config: ComponentConfig):
    """创建组件生成节点（只做 LLM 生成，不做工具校验）"""

    async def generator(state: GenerationState) -> dict:
        # ... 现有代码 ...
        
        # ── 1. RAG 检索 ──
        rag_t0 = _time.time()
        
        # 🆕 添加查询改写
        rewritten_query = None
        search_query = user_message
        try:
            from app.agent.rag import QueryRewriter
            from app.config import get_domain_config
            
            domain_schema = get_domain_config().get_schema()
            rewriter = QueryRewriter(llm, domain_schema)
            rewritten_query = await rewriter.rewrite(
                f"{user_message} {config.label} {config.component_type}"
            )
            
            # 优先使用改写后的关键词
            keywords = rewritten_query.get("keywords", [])
            if keywords:
                search_query = " ".join(keywords[:5])
                logger.info(
                    f"[{config.component_type}_gen] 查询改写: {keywords[:3]}"
                )
        except Exception as e:
            logger.warning(
                f"[{config.component_type}_gen] 查询改写失败: {e}"
            )
        
        # 构建查询（使用改写后的 query）
        queries = [
            SpecQuery(search_query, {"entity_type": config.entity_type}),
            SpecQuery(
                f"{search_query} {config.label}构件参数与位置规则",
                {"doc_type": "component"},
            ),
        ]
        for extra_query in config.rag_extra_queries:
            queries.append(SpecQuery(extra_query, {"doc_type": "component"}))
        
        # ... 继续现有代码 ...
```

#### 步骤 2: 在生成器中集成结构自检

在 JSON 提取后添加验证：

```python
def create_component_generator(config: ComponentConfig):
    async def generator(state: GenerationState) -> dict:
        # ... LLM 调用和 JSON 提取 ...
        
        # ── 4. 提取 JSON ──
        if config.is_list:
            fragments = extract_json_array(reply_text)
        else:
            obj = extract_json_object(reply_text)
            fragments = [obj] if obj else []
        
        # 🆕 添加结构自检
        if fragments and config.component_type:
            try:
                from app.agent.validators import StructureValidator, JsonSchemaValidator
                
                # 为每个 fragment 验证
                validated_fragments = []
                struct_errors = []
                
                schema_validator = JsonSchemaValidator()
                validator = StructureValidator(schema_validator, llm)
                
                # 简化的 component schema（根据实际调整）
                component_schema = {
                    "type": "object",
                    "required": ["type", "id"] + config.required_fields,
                    "properties": {
                        "type": {"type": "string"},
                        "id": {"type": "string"},
                        # ... 其他字段根据 component_type 定义
                    }
                }
                
                for frag in fragments:
                    validated, errors = await validator.validate_and_fix(
                        frag,
                        node_name=f"{config.component_type}_gen",
                        schema=component_schema,
                        max_retries=0  # 组件生成不做 LLM 修复，交给后续验证
                    )
                    validated_fragments.append(validated)
                    if errors:
                        struct_errors.extend(errors)
                
                fragments = validated_fragments
                
                if struct_errors:
                    logger.warning(
                        f"[{config.component_type}_gen] "
                        f"结构自检发现 {len(struct_errors)} 个错误"
                    )
                    
            except Exception as e:
                logger.warning(
                    f"[{config.component_type}_gen] 结构自检失败: {e}"
                )
        
        # ── 5. 基本校验（类型 + 必填字段）──
        valid = _validate_fragments(fragments, config)
        
        # ... 继续现有代码 ...
```

---

## 🎛️ 配置调整

### 自定义领域配置

如果需要为不同领域创建配置：

1. 复制 `config/domain_schema.yaml`
2. 修改为你的领域（如 `config/code_domain_schema.yaml`）
3. 在代码中指定配置路径：

```python
from app.config import DomainConfig

# 使用自定义配置
custom_config = DomainConfig("config/code_domain_schema.yaml")
rewriter = QueryRewriter(llm, custom_config.get_schema())
```

### 调整验证严格程度

```python
# 宽松模式：不进行 LLM 修复
validator = StructureValidator(schema_validator, llm)
output, errors = await validator.validate_and_fix(
    llm_output,
    "node_name",
    schema,
    max_retries=0  # 不修复，只检测
)

# 严格模式：多次修复
output, errors = await validator.validate_and_fix(
    llm_output,
    "node_name", 
    schema,
    max_retries=2  # 最多修复 2 次
)
```

---

## 📊 监控和诊断

### 在 diag 中添加 P0 指标

建议在每个节点的 diag 返回中添加：

```python
return {
    # ... 现有字段 ...
    "xxx_diag": {
        # ... 现有 diag 字段 ...
        
        # 🆕 P0 指标
        "query_rewrite": {
            "enabled": bool(rewritten_query),
            "entity_type": rewritten_query.get("entity_type") if rewritten_query else None,
            "keywords_count": len(rewritten_query.get("keywords", [])) if rewritten_query else 0,
        },
        "structure_validation": {
            "enabled": True,
            "errors_found": len(struct_errors),
            "auto_fixed": len(struct_errors) > 0 and not any("缺少" in e for e in struct_errors),
        },
    },
}
```

### 分析日志

启用后，日志中会出现：

```
[skeleton] 查询改写: entity_type=building, keywords=['现代', '建筑', '节能']
[skeleton] 结构自检发现 2 个错误，已尝试自动修复
[door_gen] 查询改写: ['门', '入口', '现代']
```

---

## 🧪 测试集成

### 单元测试

为集成的节点添加测试：

```python
# tests/test_skeleton_node_p0.py

import pytest
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_skeleton_with_query_rewrite():
    """测试 skeleton 节点的查询改写集成"""
    
    with patch("app.agent.rag.QueryRewriter") as mock_rewriter:
        # 模拟查询改写
        mock_instance = AsyncMock()
        mock_instance.rewrite.return_value = {
            "entity_type": "building",
            "keywords": ["modern", "building"]
        }
        mock_rewriter.return_value = mock_instance
        
        # 调用节点
        state = {"user_message": "生成现代建筑", "thinking_mode": False}
        result = await skeleton_generator(state)
        
        # 验证
        assert "skeleton_blueprint" in result
        assert result["skeleton_diag"]["query_rewrite"] is not None
```

### 集成测试

```bash
# 运行完整测试套件
$env:PYTHONPATH="."
python -m pytest tests/test_p0_implementation.py -v
python -m pytest tests/test_skeleton_node_p0.py -v  # 如果创建了新测试
```

---

## 🚀 渐进式集成策略

建议按以下顺序逐步集成：

### 阶段 1: 最小集成（推荐先做）
1. ✅ 只在 `skeleton_node` 集成查询改写
2. ✅ 观察 RAG 检索质量改善
3. ✅ 收集 diag 数据

### 阶段 2: 扩展到组件
1. ✅ 在 `base_component_node` 的生成器中集成查询改写
2. ✅ 观察组件生成的准确率

### 阶段 3: 添加结构自检
1. ✅ 在 `skeleton_node` 集成结构验证
2. ✅ 逐步添加到其他节点
3. ✅ 根据错误率调整 `max_retries`

### 阶段 4: 全面部署
1. ✅ 所有生成节点都集成 P0 方案
2. ✅ 监控指标，验证效果
3. ✅ 根据数据决定是否推进 P1 方案

---

## ⚠️ 注意事项

### 性能影响

- **查询改写**: 每次查询增加 ~100 tokens LLM 调用
- **结构自检**: 仅在检测到错误时才调用 LLM 修复
- **总成本**: 预计每次查询 <$0.0003（可忽略）

### 兼容性

- P0 方案与现有代码完全兼容
- 即使 P0 模块失败，也会回退到原有逻辑
- 不会破坏现有功能

### 最佳实践

1. **先在非关键路径测试**（如 chat_node）
2. **逐步扩展到关键节点**（skeleton → component）
3. **持续监控 diag 数据**，评估效果
4. **根据实际情况调整配置**（max_retries、schema 等）

---

## 📞 问题排查

### 问题 1: 模块导入失败

```
ModuleNotFoundError: No module named 'app.agent.validators'
```

**解决**: 确保设置了 `PYTHONPATH`：
```bash
$env:PYTHONPATH="."
```

### 问题 2: 领域配置加载失败

```
[领域配置] 加载失败: expected a single document
```

**解决**: 检查 YAML 文件中是否有 `---` 分隔符，删除它们。

### 问题 3: LLM 修复失败

```
[structure_validator] LLM 修复后未能提取有效 JSON
```

**解决**: 
- 降低 `max_retries`（设为 0 仅检测不修复）
- 或改进 prompt 使 LLM 输出更规范的 JSON

---

## 📈 效果评估

集成后，关注以下指标：

1. **输出解析失败率** - 期望从 27% 降到 <5%
2. **RAG 检索准确率** - 通过人工抽样评估
3. **生成成功率** - 期望从 70% 提升到 85%
4. **Token 成本** - 监控是否在预期范围内

---

**祝集成顺利！如有问题，参考 `examples/p0_usage_example.py` 或运行测试查看详细示例。** 🎉
