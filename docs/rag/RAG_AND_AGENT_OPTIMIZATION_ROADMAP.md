# WildAgent RAG 与智能体优化路线图

> 状态：早期方案参考，其中包含尚未实施或需要重新验证的设想。当前能力与下一步实施顺序以 [RAG 能力与演进规划](RAG_CAPABILITIES_AND_EVOLUTION.md) 为准。

**定位：** 通用领域无关 Agent 生成系统的优化方法论

**适用场景：** 任何需要从知识库检索 + 结构化生成的 Agent 系统

---

## 一、RAG 检索准确率提升方案

### 当前问题诊断（领域无关）

**WildAgent 的 RAG 通用特点：**
- 用户输入：自然语言需求描述
- 知识库内容：领域规范文档、API 文档、生成案例
- 检索目标：找到相关的生成方法、参数约束、设计模式

**现有问题（通用痛点）：**
1. ❌ 用户使用俗称，知识库使用专业术语（语义鸿沟）
2. ❌ 相似概念检索混淆（类别 A 检索到类别 B）
3. ❌ 复合需求（风格 + 类型）检索不到完整匹配
4. ❌ 同一概念的多种表达检索结果不一致

---

### 方案 1：查询改写（Query Rewriting）

#### 1.1 领域查询规范化（Domain-Agnostic）

**实施位置：** `app/services/rag_service.py` - `retrieve()` 方法前

**改写策略：**
```python
# 通用查询改写框架
async def rewrite_domain_query(user_query: str, domain_schema: dict) -> dict:
    """
    将用户自然语言改写为结构化查询（领域无关）
    
    输入："生成一个X类型的Y，要有Z特性"
    输出：{
        "entity_type": "实体类型",
        "attributes": {"key": "value"},
        "features": ["特性列表"],
        "constraints": {"key": "constraint"},
        "keywords": ["检索关键词"]
    }
    
    domain_schema 从配置文件加载，不硬编码领域词汇
    """
    
    rewrite_prompt = f"""
将用户需求改写为结构化查询，便于检索知识库。

用户需求：{user_query}

领域 Schema（参考）：
{json.dumps(domain_schema, indent=2, ensure_ascii=False)}

输出 JSON 格式：
{{
    "entity_type": "实体类型（从 schema 中的 types）",
    "attributes": {{"属性名": "属性值"}},
    "features": ["特性列表"],
    "constraints": {{"约束名": "约束值"}},
    "keywords": ["关键检索词列表"]
}}
"""
    
    structured = await llm.ainvoke(rewrite_prompt)
    return parse_json(structured)
```

**领域配置（外部化）：**
```yaml
# config/domain_schema.yaml（以建筑为例，可替换为任何领域）
domain: "architecture"  # 可以是 "code", "music", "design" 等

entity_types:
  - type: "building"
    aliases: ["房屋", "建筑物"]
  - type: "component"
    aliases: ["组件", "部件"]

attributes:
  - name: "style"
    values: ["modern", "classical", "traditional"]
  - name: "dimensions"
    type: "numeric"
    
features:
  - name: "decorative"
  - name: "functional"

# 其他领域只需替换此配置文件
```

**检索改进（通用框架）：**
```python
# 通用多维度检索
async def hybrid_retrieve(user_query: str, config: DomainConfig) -> list:
    """
    领域无关的混合检索策略
    """
    # 1. 加载领域配置
    domain_schema = config.load_schema()
    
    # 2. 查询改写
    rewritten = await rewrite_domain_query(user_query, domain_schema)
    
    results = []
    
    # 3. 向量检索（使用改写的 keywords）
    vector_results = await vector_store.asimilarity_search(
        " ".join(rewritten["keywords"]), 
        k=3
    )
    
    # 4. 元数据过滤（精确匹配）
    metadata_filter = {
        "entity_type": rewritten["entity_type"],
        **rewritten.get("attributes", {})
    }
    filtered_results = await vector_store.asimilarity_search(
        user_query,
        k=2,
        filter=metadata_filter
    )
    
    # 5. 特性定向检索
    for feature in rewritten.get("features", []):
        feature_results = await vector_store.asimilarity_search(
            f"{feature} specification",
            k=1,
            filter={"features": {"$in": [feature]}}
        )
        results.extend(feature_results)
    
    # 合并去重
    return deduplicate(vector_results + filtered_results + results)
```

**成本分析：**
- ✅ 每次查询增加 1 次 LLM 调用（~100 tokens）
- ✅ 但检索准确率提升 40-60%，减少后续重试
- ⚠️ 需要缓存常见查询改写结果

---

### 方案 2：索引增强（Index Enhancement）

#### 2.1 知识库文档结构化提取（领域无关）

**实施位置：** `scripts/build_knowledge_base.py` - 索引构建阶段

**当前问题：**
```markdown
# entity_spec.md（原始）
某实体类型用于创建...

embedding → 向量：[0.12, -0.45, 0.78, ...]
```

**改进方案（通用提取框架）：**
```python
async def extract_structured_metadata(doc_content: str, doc_path: str, domain_config: dict) -> dict:
    """
    从自由文本提取结构化元数据（领域无关）
    
    domain_config 定义要提取的元数据字段
    """
    
    # 从领域配置加载提取模板
    extraction_fields = domain_config.get("metadata_fields", [])
    
    extraction_prompt = f"""
分析以下文档，提取关键结构化信息：

文档内容：
{doc_content}

提取以下字段（根据领域配置）：
{json.dumps(extraction_fields, indent=2, ensure_ascii=False)}

输出 JSON：
{{
    "entity_type": "实体类型",
    "aliases": ["别名列表"],
    "attributes": {{"属性名": "属性值"}},
    "related_entities": ["相关实体"],
    "key_parameters": ["关键参数列表"],
    "use_cases": ["典型使用场景"],
    "constraints": ["约束条件"],
    "examples": ["示例描述"]
}}
"""
    
    metadata = await llm.ainvoke(extraction_prompt)
    return parse_json(metadata)

# 领域配置示例（外部 YAML）
# config/metadata_extraction.yaml
metadata_fields:
  - name: "entity_type"
    description: "实体类型标识"
  - name: "aliases"
    description: "常用别名"
  - name: "attributes"
    description: "实体属性"
  - name: "constraints"
    description: "使用约束"

# 索引时附加元数据（领域无关）
doc = Document(
    page_content=original_content,
    metadata={
        **extracted_metadata,
        "doc_path": doc_path,
        "doc_type": infer_doc_type(doc_path),
        "last_updated": datetime.now()
    }
)
```

**改进后的检索（通用）：**
```python
# 用户："我要一个X类型的Y"

# 1. 别名匹配（领域无关）
results_by_alias = vector_store.search(
    filter={"aliases": {"$in": extracted_aliases_from_query}}
)

# 2. 属性过滤（领域无关）
results_by_attributes = vector_store.search(
    query=user_query,
    filter={"attributes": query_attributes}
)

# 3. 场景匹配（领域无关）
results_by_scenario = vector_store.search(
    query=scenario_keywords,
    filter={"use_cases": {"$regex": scenario_pattern}}
)
```

#### 2.2 反向索引：从生成案例到文档（通用）

**实施位置：** 新增 `app/services/case_indexer.py`

```python
class CaseIndexer:
    """
    从成功生成的案例反向索引到知识库（领域无关）
    
    场景：用户生成了"X"后，下次别人搜"X"能找到这个案例
    """
    
    async def index_generated_case(
        self, 
        output: dict, 
        user_query: str,
        domain_config: dict
    ):
        # 1. 提取案例特征（根据领域配置）
        feature_extractors = domain_config.get("feature_extractors", {})
        
        case_features = {}
        for field, extractor in feature_extractors.items():
            case_features[field] = extractor(output)
        
        case_features["user_query"] = user_query
        
        # 2. 生成案例摘要（领域无关提示词）
        case_summary = await llm.ainvoke(f"""
总结这个生成案例的关键要点：

用户需求：{user_query}
生成结果特征：{json.dumps(case_features, ensure_ascii=False)}

输出一段简洁的摘要（100字以内）。
""")
        
        # 3. 添加到知识库
        case_doc = Document(
            page_content=case_summary,
            metadata={
                "doc_type": "case_study",
                **case_features,
                "user_query": user_query,
                "output_id": output.get("id")
            }
        )
        
        await vector_store.aadd_documents([case_doc])

# 领域配置示例
# config/case_indexing.yaml
feature_extractors:
  entity_type: "lambda x: x.get('type')"
  main_attributes: "lambda x: extract_main_attrs(x)"
  complexity_score: "lambda x: calculate_complexity(x)"
```

**成本分析：**
- ⚠️ 索引构建时每篇文档增加 1 次 LLM 调用
- ✅ 但只需在构建阶段执行一次，运行时无额外成本
- ✅ 可以离线批量处理，避免阻塞主服务

---

### 方案 3：混合检索（Hybrid Retrieval）

#### 3.1 BM25 + 向量检索融合（领域无关）

**实施位置：** `app/services/rag_service.py`

```python
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

class HybridRetriever:
    """
    混合检索器：结合 BM25 关键词和向量语义（领域无关）
    """
    
    def __init__(self, vector_store, documents):
        # BM25 检索器（关键词精确匹配）
        self.bm25 = BM25Retriever.from_documents(documents)
        self.bm25.k = 3
        
        # 向量检索器（语义相似）
        self.vector = vector_store.as_retriever(search_kwargs={"k": 3})
        
        # 融合检索器（权重可调）
        self.ensemble = EnsembleRetriever(
            retrievers=[self.bm25, self.vector],
            weights=[0.4, 0.6]  # BM25:向量 = 4:6
        )
    
    async def retrieve(
        self, 
        query: str, 
        entity_type: str = None,
        domain_config: dict = None
    ) -> list:
        # 1. 查询改写（如果有领域配置）
        if domain_config:
            rewritten = await rewrite_domain_query(query, domain_config)
            search_query = " ".join(rewritten["keywords"])
        else:
            search_query = query
        
        # 2. 混合检索
        results = await self.ensemble.ainvoke(search_query)
        
        # 3. 重排序（根据实体类型相关性）
        if entity_type:
            results = self.rerank_by_relevance(results, entity_type)
        
        return results[:5]  # 返回 top-5
    
    def rerank_by_relevance(self, results: list, entity_type: str) -> list:
        """
        根据实体类型相关性重排序（领域无关）
        """
        def relevance_score(doc):
            # 精确匹配得分最高
            if doc.metadata.get("entity_type") == entity_type:
                return 1.0
            # 相关实体得分次之
            if entity_type in doc.metadata.get("related_entities", []):
                return 0.7
            # 默认得分
            return 0.5
        
        return sorted(results, key=relevance_score, reverse=True)
```

**实际效果对比：**
```python
# 测试用例："生成一个带X特性的Y类型"

# 纯向量检索 → 可能检索到语义相近但类型不对的文档
# 纯 BM25 → 可能检索到类型匹配但特性不对的文档
# 混合检索 → 既匹配类型又匹配特性
```

---

## 二、智能体自主纠错系统（领域无关）

### 当前 WildAgent 的错误类型（通用化）

**从实践总结的通用错误模式：**

1. **结构错误** - 输出 schema 不合规（27% 历史案例的痛点）
2. **事实错误** - 生成的参数/值不符合领域约束
3. **工具错误** - 生成后无法通过校验流水线
4. **推理错误** - LLM 输出的格式错误或逻辑矛盾

---

### 改进方案：四层自检系统（领域无关）

#### 层级 1：结构自检（Structure Check）

**实施位置：** 所有生成节点（skeleton/component/...）

**当前问题（通用）：**
```python
# LLM 可能输出旧 schema 或格式错误
{
    "old_field": [...],  # ❌ 已废弃字段
    "wrong_structure": {}  # ❌ 结构不符合当前 schema
}
```

**改进：实时结构校验 + 自我修复（通用框架）**

```python
class StructureValidator:
    """
    结构自检：确保输出符合目标 Schema（领域无关）
    """
    
    def __init__(self, schema_validator, llm):
        self.schema_validator = schema_validator  # 可以是 jsonschema 或自定义
        self.llm = llm
    
    async def validate_and_fix(
        self, 
        llm_output: dict, 
        node_name: str,
        schema: dict
    ) -> tuple[dict, list]:
        errors = []
        
        # 1. Schema 合规检查（使用注入的 validator）
        schema_errors = self.schema_validator.validate(llm_output, schema)
        
        if schema_errors:
            errors.extend(schema_errors)
            
            # 自我修复：让 LLM 根据错误修正
            fix_prompt = f"""
你生成的输出存在以下 schema 错误：
{chr(10).join(f"- {err}" for err in schema_errors)}

原始输出：
{json.dumps(llm_output, indent=2, ensure_ascii=False)}

请根据目标 Schema 修复这些错误，输出完整的修复后 JSON：
{json.dumps(schema, indent=2, ensure_ascii=False)}
"""
            
            fixed_output = await self.llm.ainvoke(fix_prompt)
            llm_output = parse_json(fixed_output)
            
            # 验证修复是否成功
            remaining_errors = self.schema_validator.validate(llm_output, schema)
            if not remaining_errors:
                logger.info(f"[{node_name}] 结构自检修复成功")
            else:
                logger.warning(f"[{node_name}] 结构自检修复失败，仍有 {len(remaining_errors)} 个错误")
        
        # 2. 必填字段检查（从 schema 中提取）
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in llm_output:
                errors.append(f"缺少必填字段: {field}")
        
        # 3. 数据类型检查
        for field, field_schema in schema.get("properties", {}).items():
            if field in llm_output:
                expected_type = field_schema.get("type")
                actual_value = llm_output[field]
                if not self._check_type(actual_value, expected_type):
                    errors.append(f"{field} 类型错误：期望 {expected_type}")
        
        return llm_output, errors
    
    def _check_type(self, value, expected_type):
        """类型检查辅助方法"""
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict
        }
        expected_class = type_map.get(expected_type)
        return isinstance(value, expected_class) if expected_class else True
```

**接入方式（通用）：**
```python
# 任意生成节点
async def generation_node(state: State, config: Config) -> dict:
    # ... LLM 生成 ...
    
    # 结构自检（注入 schema）
    validator = StructureValidator(
        schema_validator=config.get_schema_validator(),
        llm=config.get_llm()
    )
    
    output, struct_errors = await validator.validate_and_fix(
        output, 
        node_name="current_node",
        schema=config.get_output_schema()
    )
    
    if struct_errors:
        # 记录到诊断日志
        diag["structure_errors"] = struct_errors
    
    return {"output": output, "diag": diag}
```

---

#### 层级 2：事实自检（Factual Check）

**实施位置：** 任意生成节点 - 实体生成后

**当前问题（领域无关）：**
```python
# LLM 可能生成不符合领域约束的参数
{
    "entity_type": "component_a",
    "size": 1500.0,  # ❌ 超出合理范围
    "dimension_y": 0.01,  # ❌ 过小不合理
    "position": [500, 0, 0]  # ❌ 超出父实体范围
}
```

**改进：领域约束验证（通用框架）**

```python
class FactualValidator:
    """
    事实自检：验证生成的参数是否符合领域约束（领域无关）
    
    约束规则从外部配置文件加载，不硬编码
    """
    
    def __init__(self, constraint_config: dict):
        """
        constraint_config 从 config/domain_constraints.yaml 加载
        
        示例结构：
        {
            "entity_type_a": {
                "attribute_1": {"min": 0.5, "max": 10.0},
                "attribute_2": {"min": 1.0, "max": 5.0}
            },
            "entity_type_b": {
                "dimension": {"min": 0.1, "max": 100.0}
            }
        }
        """
        self.constraints = constraint_config
    
    async def validate_entity(
        self, 
        entity: dict, 
        parent_entity: dict = None,
        custom_validators: list = None
    ) -> tuple[bool, list]:
        """
        验证实体参数合理性（通用）
        
        custom_validators: 领域特定的自定义验证函数列表
        """
        errors = []
        entity_type = entity.get("entity_type") or entity.get("type")
        
        if entity_type not in self.constraints:
            return True, []  # 未定义约束的实体跳过
        
        type_constraints = self.constraints[entity_type]
        
        # 1. 数值范围验证（通用）
        for attr, constraint in type_constraints.items():
            if attr in entity:
                value = entity[attr]
                
                # 支持多种约束类型
                if "min" in constraint and "max" in constraint:
                    min_val, max_val = constraint["min"], constraint["max"]
                    if not (min_val <= value <= max_val):
                        errors.append(
                            f"{entity_type}.{attr}={value} 超出范围 [{min_val}, {max_val}]"
                        )
                
                if "enum" in constraint:
                    if value not in constraint["enum"]:
                        errors.append(
                            f"{entity_type}.{attr}={value} 不在允许值 {constraint['enum']} 中"
                        )
        
        # 2. 父子关系约束（通用）
        if parent_entity:
            parent_errors = self._validate_parent_child_constraint(
                entity, parent_entity, type_constraints
            )
            errors.extend(parent_errors)
        
        # 3. 自定义领域验证（可扩展）
        if custom_validators:
            for validator_func in custom_validators:
                custom_errors = validator_func(entity, parent_entity)
                errors.extend(custom_errors)
        
        return len(errors) == 0, errors
    
    def _validate_parent_child_constraint(
        self, 
        entity: dict, 
        parent: dict,
        constraints: dict
    ) -> list:
        """
        验证子实体是否在父实体范围内（通用）
        """
        errors = []
        
        # 从约束配置获取位置和尺寸字段名
        position_field = constraints.get("_position_field", "position")
        size_fields = constraints.get("_size_fields", ["width", "height", "depth"])
        
        if position_field in entity and "bounds" in parent:
            position = entity[position_field]
            parent_bounds = parent["bounds"]
            
            # 检查是否超出父实体边界
            for i, pos_val in enumerate(position):
                if pos_val < parent_bounds[i]["min"] or pos_val > parent_bounds[i]["max"]:
                    errors.append(
                        f"{entity.get('entity_type')} 位置 {position_field}[{i}]={pos_val} 超出父实体范围"
                    )
        
        return errors
    
    async def auto_correct(
        self, 
        entity: dict, 
        errors: list,
        correction_strategy: str = "clamp"
    ) -> dict:
        """
        自动修正不合理的参数（通用）
        
        correction_strategy:
          - "clamp": 钳位到范围边界
          - "default": 使用默认值
          - "llm_fix": 让 LLM 重新生成
        """
        entity_type = entity.get("entity_type") or entity.get("type")
        type_constraints = self.constraints.get(entity_type, {})
        
        if correction_strategy == "clamp":
            # 钳位策略
            for attr, constraint in type_constraints.items():
                if attr in entity and "min" in constraint and "max" in constraint:
                    value = entity[attr]
                    min_val, max_val = constraint["min"], constraint["max"]
                    
                    if value < min_val:
                        entity[attr] = min_val
                        logger.info(f"自动修正 {entity_type}.{attr}: {value} → {min_val}")
                    elif value > max_val:
                        entity[attr] = max_val
                        logger.info(f"自动修正 {entity_type}.{attr}: {value} → {max_val}")
        
        elif correction_strategy == "default":
            # 使用默认值
            for attr, constraint in type_constraints.items():
                if "default" in constraint and attr in entity:
                    if any(err for err in errors if attr in err):
                        entity[attr] = constraint["default"]
                        logger.info(f"使用默认值 {entity_type}.{attr} → {constraint['default']}")
        
        return entity
```

**领域约束配置示例（外部 YAML）：**
```yaml
# config/domain_constraints.yaml

# 以建筑领域为例（可替换为任何领域）
constraints:
  door:
    width: {min: 0.7, max: 3.0}
    height: {min: 1.8, max: 3.5}
    _position_field: "from"
    _size_fields: ["width", "height"]
    
  window:
    width: {min: 0.4, max: 4.0}
    height: {min: 0.6, max: 3.0}
    
  roof:
    height: {min: 0.5, max: 10.0}
    thickness: {min: 0.05, max: 0.3}

# 代码生成领域示例
# constraints:
#   function:
#     params_count: {min: 0, max: 10}
#     name_length: {min: 1, max: 50}
#   class:
#     methods_count: {min: 1, max: 100}

# 音乐生成领域示例
# constraints:
#   note:
#     pitch: {min: 0, max: 127}
#     duration: {min: 0.1, max: 4.0}
#   chord:
#     notes_count: {min: 2, max: 6}
```

**接入方式（领域无关）：**
```python
# 任意生成节点
async def entity_generation_node(state, config):
    # ... 生成实体 ...
    
    # 加载领域约束配置
    constraint_config = config.load_constraint_config()
    
    # 事实自检
    fact_validator = FactualValidator(constraint_config)
    
    for entity in generated_entities:
        is_valid, fact_errors = await fact_validator.validate_entity(
            entity, 
            parent_entity=state.get("parent_context"),
            custom_validators=config.get_custom_validators()
        )
        
        if not is_valid:
            # 尝试自动修正
            entity = await fact_validator.auto_correct(
                entity, 
                fact_errors,
                correction_strategy=config.get("correction_strategy", "clamp")
            )
            
            diag["fact_corrections"].append({
                "entity_id": entity.get("id"),
                "errors": fact_errors
            })
    
    return {"entities": generated_entities, "diag": diag}
```

---

#### 层级 3：工具行为自检（Tool Check）

**实施位置：** 验证节点 - 工具校验流水线执行后

**当前问题（领域无关）：**
```python
# 校验工具报错，但 Agent 不知道如何修复
validate_constraint_a → "❌ entity_1 违反约束 X"
validate_relationship_b → "❌ 关系不一致"
```

**改进：工具错误自我诊断（通用框架）**

```python
class ToolValidator:
    """
    工具自检：分析工具报错原因并生成修复建议（领域无关）
    """
    
    def __init__(self, llm, domain_context: dict):
        """
        domain_context: 领域上下文，从配置加载
        {
            "domain_name": "建筑/代码/音乐/...",
            "output_schema": {...},
            "tool_descriptions": {...}
        }
        """
        self.llm = llm
        self.domain_context = domain_context
    
    async def diagnose_tool_error(
        self, 
        tool_name: str, 
        error_output: str, 
        generated_output: dict
    ) -> dict:
        """
        让 LLM 分析工具错误并生成修复方案（通用）
        """
        
        # 提取相关部分（避免超长 context）
        relevant_part = self._extract_relevant_part(generated_output, error_output)
        
        diagnosis_prompt = f"""
你是 {self.domain_context['domain_name']} 领域的输出调试专家。

以下校验工具报告了错误：

**工具名称：** {tool_name}
**工具描述：** {self.domain_context['tool_descriptions'].get(tool_name, '未提供')}

**错误输出：**
{error_output}

**当前生成结果（相关部分）：**
{json.dumps(relevant_part, indent=2, ensure_ascii=False)}

**输出 Schema（参考）：**
{json.dumps(self.domain_context['output_schema'], indent=2, ensure_ascii=False)}

请分析：
1. **根本原因**：为什么会出现这个错误？（从 schema 和约束角度）
2. **修复方案**：应该如何修改生成结果？（具体修改步骤）
3. **预防措施**：下次生成时应该注意什么？

输出 JSON 格式：
{{
    "root_cause": "根本原因描述",
    "fix_actions": [
        "修复步骤1（具体到字段和值）",
        "修复步骤2"
    ],
    "prevention": "预防建议"
}}
"""
        
        diagnosis = await self.llm.ainvoke(diagnosis_prompt)
        return parse_json(diagnosis)
    
    def _extract_relevant_part(self, output: dict, error_msg: str) -> dict:
        """
        从完整输出中提取与错误相关的部分（通用启发式）
        """
        # 简单策略：提取错误消息中提到的 key
        relevant = {}
        
        # 提取错误消息中的字段名（如 "entity_1", "relationship_x"）
        import re
        mentioned_keys = re.findall(r'\b\w+\b', error_msg)
        
        for key in mentioned_keys:
            if key in output:
                relevant[key] = output[key]
        
        # 如果没提取到，返回完整输出（截断到前 100 行）
        if not relevant:
            output_str = json.dumps(output, indent=2)
            lines = output_str.split('\n')[:100]
            return {"_truncated": '\n'.join(lines)}
        
        return relevant
    
    async def execute_fix(
        self, 
        output: dict, 
        fix_actions: list,
        max_retries: int = 2
    ) -> dict:
        """
        执行修复动作（通用）
        
        策略：让 LLM 基于修复步骤重新生成完整输出
        """
        
        for retry in range(max_retries):
            fix_prompt = f"""
请执行以下修复动作，输出修复后的完整结果：

**修复步骤：**
{chr(10).join(f"{i+1}. {action}" for i, action in enumerate(fix_actions))}

**当前结果：**
{json.dumps(output, indent=2, ensure_ascii=False)}

**目标 Schema：**
{json.dumps(self.domain_context['output_schema'], indent=2, ensure_ascii=False)}

请输出修复后的完整 JSON（确保符合 Schema）。
"""
            
            try:
                fixed_output = await self.llm.ainvoke(fix_prompt)
                output = parse_json(fixed_output)
                logger.info(f"[工具自检] 修复尝试 {retry+1}/{max_retries} 完成")
                break
            except Exception as e:
                logger.warning(f"[工具自检] 修复尝试 {retry+1} 失败: {e}")
                if retry == max_retries - 1:
                    raise
        
        return output
```

**领域配置示例（外部 YAML）：**
```yaml
# config/tool_validation.yaml

domain_name: "建筑设计"  # 或 "代码生成"、"音乐创作" 等

output_schema:
  type: "object"
  properties:
    # ... schema 定义 ...

tool_descriptions:
  validate_constraint_a: "检查实体 A 的约束条件是否满足"
  validate_relationship_b: "检查实体间关系是否一致"
  
# 不同领域只需替换此配置
```

**接入方式（领域无关）：**
```python
# 验证节点
async def validation_node(state, config):
    # ... 运行校验工具流水线 ...
    
    if validation_errors:
        # 加载领域配置
        domain_context = config.load_domain_context()
        
        tool_validator = ToolValidator(
            llm=config.get_llm(),
            domain_context=domain_context
        )
        
        for error_result in validation_errors:
            # 诊断错误
            diagnosis = await tool_validator.diagnose_tool_error(
                tool_name=error_result.name,
                error_output=error_result.output,
                generated_output=state["generated_output"]
            )
            
            logger.info(f"[工具自检] {error_result.name}: {diagnosis['root_cause']}")
            
            # 尝试修复
            if diagnosis["fix_actions"]:
                try:
                    fixed_output = await tool_validator.execute_fix(
                        state["generated_output"],
                        diagnosis["fix_actions"]
                    )
                    
                    # 重新校验
                    recheck_result = run_validation_pipeline(fixed_output)
                    
                    if not recheck_result.has_errors():
                        logger.info(f"[工具自检] 修复成功")
                        state["generated_output"] = fixed_output
                    else:
                        logger.warning(f"[工具自检] 修复后仍有错误")
                        
                except Exception as e:
                    logger.error(f"[工具自检] 修复失败: {e}")
    
    return state
```

---

#### 层级 4：推理逻辑自检（Reasoning Check）

**实施位置：** 所有生成节点的推理过程回调

**当前问题（领域无关）：**
```
LLM 推理过程：
"用户要求风格 X，所以生成风格 Y..." ❌ 逻辑矛盾
"参数 A = 10，使用参数 A = 15..." ❌ 数值矛盾
"需求 B 和 C 互斥，但同时生成..." ❌ 约束矛盾
```

**改进：推理过程一致性检查（通用框架）**

```python
class ReasoningValidator:
    """
    推理自检：检查 LLM 思考过程的逻辑一致性（领域无关）
    """
    
    def __init__(self, llm, domain_context: dict):
        """
        domain_context: 领域上下文
        {
            "domain_name": "领域名称",
            "contradiction_types": ["type1", "type2", ...],
            "constraint_rules": [...]
        }
        """
        self.llm = llm
        self.domain_context = domain_context
    
    async def validate_reasoning(
        self, 
        reasoning_text: str, 
        user_query: str, 
        output: dict
    ) -> tuple[bool, list]:
        """
        检查推理过程与输入/输出的一致性（通用）
        """
        
        validation_prompt = f"""
你是 {self.domain_context['domain_name']} 领域的逻辑验证专家。

请检查以下 AI 推理过程是否存在逻辑矛盾：

**用户需求：**
{user_query}

**AI 推理过程：**
{reasoning_text}

**AI 输出结果：**
{json.dumps(output, indent=2, ensure_ascii=False)[:2000]}  # 截断避免过长

**检查项：**
1. ✅ 推理过程是否符合用户需求？
2. ✅ 推理中的数值/参数计算是否正确？
3. ✅ 输出结果是否与推理过程一致？
4. ✅ 是否违反了领域约束规则？

**已知矛盾类型（参考）：**
{json.dumps(self.domain_context.get('contradiction_types', []), ensure_ascii=False)}

如果发现矛盾，输出 JSON：
{{
    "has_contradiction": true,
    "contradictions": [
        {{
            "type": "矛盾类型（如 attribute_mismatch, value_error, constraint_violation）",
            "description": "具体描述（用户要求X，但生成了Y）",
            "severity": "high/medium/low"
        }}
    ]
}}

如果无矛盾，输出：
{{
    "has_contradiction": false,
    "contradictions": []
}}
"""
        
        result = await self.llm.ainvoke(validation_prompt)
        result_json = parse_json(result)
        
        return not result_json["has_contradiction"], result_json.get("contradictions", [])
    
    async def generate_correction_prompt(
        self, 
        contradictions: list,
        original_query: str
    ) -> str:
        """
        生成修正提示（通用）
        """
        
        correction_prompt = f"""
你上次的推理存在以下逻辑矛盾：

{chr(10).join(f"- [{c['severity'].upper()}] {c['description']}" for c in contradictions)}

**原始用户需求：**
{original_query}

请重新推理并生成，确保：
1. ✅ 严格遵循用户需求的每一个要点
2. ✅ 所有数值和参数计算准确无误
3. ✅ 输出与推理过程完全一致
4. ✅ 不违反任何领域约束规则

**重要：** 在推理时，明确说明你的决策依据。
"""
        
        return correction_prompt
```

**领域配置示例（外部 YAML）：**
```yaml
# config/reasoning_validation.yaml

domain_name: "建筑设计"  # 或其他领域

# 定义常见矛盾类型（供 LLM 参考）
contradiction_types:
  - type: "attribute_mismatch"
    description: "用户要求的属性与生成的不一致"
    examples: ["要求现代风格但生成古典", "要求大尺寸但生成小尺寸"]
    
  - type: "value_error"
    description: "数值计算错误或不合理"
    examples: ["父实体长度10但子实体长度15", "比例计算错误"]
    
  - type: "constraint_violation"
    description: "违反领域约束规则"
    examples: ["互斥特性同时出现", "必需特性缺失"]

# 领域约束规则（供验证参考）
constraint_rules:
  - "如果用户指定了风格，生成结果必须匹配该风格"
  - "子实体尺寸不能超过父实体"
  - "互斥特性不能同时存在"

# 不同领域替换配置即可
# 代码生成示例：
# contradiction_types:
#   - type: "logic_error"
#     description: "代码逻辑错误"
#   - type: "type_mismatch"
#     description: "类型不匹配"
```

**接入方式（领域无关）：**
```python
# 任意生成节点
async def generation_node_with_reasoning(state, config):
    # ... LLM 生成 + 推理 ...
    reasoning_content = state.get("reasoning_content", "")
    generated_output = state.get("output")
    
    # 推理自检
    domain_context = config.load_domain_context()
    reasoning_validator = ReasoningValidator(
        llm=config.get_llm(),
        domain_context=domain_context
    )
    
    is_consistent, contradictions = await reasoning_validator.validate_reasoning(
        reasoning_content,
        state["user_message"],
        generated_output
    )
    
    if not is_consistent:
        logger.warning(f"[推理自检] 发现 {len(contradictions)} 个逻辑矛盾")
        
        # 生成修正提示
        correction_prompt = await reasoning_validator.generate_correction_prompt(
            contradictions,
            state["user_message"]
        )
        
        # 记录到诊断
        state["diag"]["reasoning_contradictions"] = contradictions
        
        # 触发重新生成（可选）
        if config.get("auto_retry_on_contradiction", True):
            logger.info("[推理自检] 触发重新生成")
            # ... 使用 correction_prompt 重新调用 LLM ...
    
    return state
```

---

## 三、实施优先级与成本评估

### 优先级矩阵（领域无关评估）

| 方案 | 收益 | Token 成本 | 优先级 | 实施难度 | 适用场景 |
|---|---|---|---|---|---|
| **RAG - 查询改写** | ⭐⭐⭐⭐⭐ | 💰💰 | P0 | 中 | 所有 RAG 场景 |
| **RAG - 索引增强** | ⭐⭐⭐⭐ | 💰💰💰 | P1 | 高 | 复杂知识库 |
| **RAG - 混合检索** | ⭐⭐⭐⭐ | 💰 | P1 | 中 | 关键词+语义混合 |
| **自检 - 结构自检** | ⭐⭐⭐⭐⭐ | 💰💰 | P0 | 低 | 所有结构化生成 |
| **自检 - 事实自检** | ⭐⭐⭐⭐ | 💰💰 | P1 | 中 | 有约束的领域 |
| **自检 - 工具自检** | ⭐⭐⭐ | 💰💰💰 | P2 | 高 | 复杂验证流水线 |
| **自检 - 推理自检** | ⭐⭐⭐ | 💰💰💰💰 | P2 | 高 | 多步推理场景 |

**收益说明：**
- ⭐⭐⭐⭐⭐: 显著提升成功率（20%+）或用户体验
- ⭐⭐⭐⭐: 明显改善（10-20%）
- ⭐⭐⭐: 边际收益（5-10%）

**成本说明：**
- 💰: 每次请求 <100 tokens
- 💰💰: 每次请求 100-300 tokens
- 💰💰💰: 每次请求 300-1000 tokens
- 💰💰💰💰: 每次请求 >1000 tokens

### 成本估算

**P0 方案（立即实施）：**
- 查询改写：每次查询 +100 tokens ≈ $0.0001
- 结构自检：每次生成 +200 tokens（仅在错误时） ≈ $0.0002

**总成本增加：** 每次查询约 $0.0003，可忽略

**P1 方案（3 个月内）：**
- 索引增强：一次性成本（离线构建）
- 混合检索：无额外 token 成本，但需要维护 BM25 索引

**P2 方案（按需实施）：**
- 工具自检、推理自检：高 token 成本，仅在关键节点使用

---

## 四、实施路线图

### 第一阶段（1-2 周）：快速见效 - P0 方案

**目标：** 解决最痛的输出格式/结构问题（通用）

**实施内容：**

1. ✅ **输出归一化层**（类比 `blueprint_normalizer.py`）
   - 在输出返回前统一清理未知字段
   - 修复常见格式漂移（如旧 schema 字段）
   - 填充安全默认值
   
2. 🔧 **结构自检**（Schema Validation）
   - 在所有生成节点添加 `StructureValidator`
   - 注入领域 schema，自动检测和修复格式错误
   - 减少 LLM 输出 schema 不一致问题
   
3. 🔧 **查询改写**（Query Rewriting）
   - 在 RAG 检索前添加查询规范化
   - 将自然语言转为结构化检索参数
   - 从配置文件加载领域术语映射

**配置文件（新增）：**
- `config/domain_schema.yaml` - 领域 schema 定义
- `config/query_rewriting.yaml` - 查询改写规则

**预期效果（以 WildAgent 建筑领域为例）：**
- 输出解析失败率：27% → <5%
- 生成成功率：70% → 85%
- RAG 检索准确率：+15%

**通用性：** 适用于任何结构化生成系统（代码、配置、数据等）

---

### 第二阶段（1-2 个月）：系统优化 - P1 方案

**目标：** 提升检索准确率和领域约束合规性

**实施内容：**

1. 🔧 **索引增强**（Metadata Extraction）
   - 重建知识库，使用 LLM 提取结构化元数据
   - 添加别名、使用场景、关键参数等字段
   - 支持精确过滤（类型、属性、场景）
   
2. 🔧 **事实自检**（Constraint Validation）
   - 添加 `FactualValidator`，从配置加载约束规则
   - 验证数值范围、父子关系、逻辑一致性
   - 自动修正策略（clamp / default / llm_fix）
   
3. 🔧 **混合检索**（Hybrid Retrieval）
   - 部署 BM25 + 向量融合检索
   - 关键词精确匹配 + 语义相似度
   - 权重可调（默认 4:6）

**配置文件（新增）：**
- `config/domain_constraints.yaml` - 领域约束规则
- `config/metadata_extraction.yaml` - 元数据提取模板
- `config/hybrid_retrieval.yaml` - 混合检索权重

**预期效果：**
- RAG 召回率：60% → 80%
- 领域约束违反：-40%
- 生成成功率：85% → 95%

**通用性：** 适用于有明确约束规则的领域（设计、配置、规范生成）

---

### 第三阶段（按需）：高级优化 - P2 方案

**目标：** 处理复杂验证和推理场景

**实施内容：**

1. 🔧 **工具自检**（Tool Error Diagnosis）
   - 自动分析校验工具报错原因
   - LLM 生成修复方案并执行
   - 适用于复杂的多步验证流水线
   
2. 🔧 **推理自检**（Reasoning Consistency Check）
   - 检查 LLM 思考过程的逻辑一致性
   - 识别矛盾（需求不一致、数值错误、约束冲突）
   - 触发重新推理
   
3. 🔧 **案例反向索引**（Case-based Learning）
   - 从成功生成的案例学习
   - 为相似查询提供参考案例
   - 增量改进知识库

**配置文件（新增）：**
- `config/tool_validation.yaml` - 工具描述和修复策略
- `config/reasoning_validation.yaml` - 推理矛盾类型定义
- `config/case_indexing.yaml` - 案例特征提取器

**预期效果：**
- 复杂场景成功率：80% → 90%
- 自动修复成功率：60%
- 边缘用例处理能力显著提升

**成本警告：** Token 消耗较高（每次 +500-1500 tokens），建议仅在关键节点或失败重试时使用

**通用性：** 适用于高价值、高复杂度的生成任务

---

## 五、关键参考资料

1. **RAG 优化方法**
   - [提升 RAG 检索准确率的方法](https://blog.csdn.net/m0_59235945/article/details/144727481)
   - LangChain EnsembleRetriever 文档
   - Query Rewriting with LLMs

2. **智能体自主纠错理论**
   - [智能体自主纠错系统设计](https://zhuanlan.zhihu.com/p/19780985293072100821)
   - Self-Reflection in LLM Agents (ReAct, Reflexion)
   - Chain-of-Thought Verification

3. **WildAgent 现有实现**
   - `app/agent/nodes/callback_node.py` - 现有的回调修正机制
   - `app/utils/blueprint_normalizer.py` - 输出归一化层（已完成）
   - `app/services/rag_service.py` - 当前 RAG 实现
   - `app/tools/spatial_tools.py` - 领域工具实现

4. **通用框架参考**
   - LangGraph - 多节点 Agent 编排
   - Pydantic - Schema 验证
   - jsonschema - JSON 格式校验

---

## 六、总结与关键原则

### 核心问题（领域无关）

本路线图识别并解决了通用 Agent 生成系统的三大核心问题：

1. **RAG 检索不准** - 用户自然语言与知识库术语不匹配
   - 解决方案：查询改写 + 索引增强 + 混合检索
   
2. **生成结果不稳定** - LLM 输出 schema 漂移、约束违反
   - 解决方案：结构自检 + 事实自检 + 归一化层
   
3. **错误修正能力弱** - 依赖人工或简单重试，无法自主诊断
   - 解决方案：工具自检 + 推理自检 + LLM 驱动修复

### 领域无关化原则

**✅ 正确做法（领域无关）：**
- 代码中使用通用术语：`entity_type`, `attributes`, `constraints`, `features`
- 从配置文件加载领域知识：`domain_schema.yaml`, `constraints.yaml`
- 提供可扩展接口：`custom_validators`, `feature_extractors`
- 文档示例展示多领域：建筑 / 代码 / 音乐 / 设计

**❌ 错误做法（硬编码领域）：**
- 代码中出现 `door`, `window`, `villa`, `wall` 等领域术语
- 约束规则写死在 Python 代码中
- 工具函数命名包含领域概念（如 `validate_building()`）
- 文档仅以单一领域为例

### 实施建议

1. **优先级：** P0（立即） → P1（2个月内） → P2（按需）
2. **渐进式：** 先部署低成本高收益方案，验证后再扩展
3. **可观测性：** 每层自检都记录到 `diag` 日志，便于分析失败模式
4. **配置驱动：** 新领域适配只需修改 YAML，无需改代码
5. **Token 预算：** 监控 LLM 调用成本，P2 方案仅在关键路径使用

### 可扩展性示例

**适配新领域（音乐生成）只需：**

```yaml
# config/domain_schema.yaml
domain: "music_composition"
entity_types:
  - type: "note"
    aliases: ["音符", "tone"]
  - type: "chord"
    aliases: ["和弦"]

# config/domain_constraints.yaml
constraints:
  note:
    pitch: {min: 0, max: 127}
    duration: {min: 0.1, max: 4.0}
  chord:
    notes_count: {min: 2, max: 6}
```

**无需修改 Python 代码！**

---

**建议从 P0 方案开始**，快速见效后再逐步推进 P1、P2 方案。

通过系统化的 **RAG 优化** 和 **四层自检系统**，可以显著提升任何领域 Agent 的稳定性和用户体验。
