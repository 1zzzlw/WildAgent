"""
结构自检模块 (Structure Validator)

P0 方案：确保 LLM 输出符合目标 Schema（领域无关）

用法:
    validator = StructureValidator(schema_validator, llm)
    output, errors = await validator.validate_and_fix(llm_output, node_name, schema)
"""
import json
from typing import Any
from loguru import logger


class StructureValidator:
    """
    结构自检：确保输出符合目标 Schema（领域无关）
    
    支持 jsonschema 或自定义 validator
    """
    
    def __init__(self, schema_validator: Any, llm: Any):
        """
        Args:
            schema_validator: Schema 验证器（如 jsonschema.validate 包装器）
            llm: LLM 实例，用于自动修复
        """
        self.schema_validator = schema_validator
        self.llm = llm
    
    async def validate_and_fix(
        self, 
        llm_output: dict, 
        node_name: str,
        schema: dict,
        max_retries: int = 1
    ) -> tuple[dict, list[str]]:
        """
        验证并尝试自动修复 Schema 错误
        
        Args:
            llm_output: LLM 生成的原始输出
            node_name: 节点名称（用于日志）
            schema: 目标 Schema
            max_retries: 最大自动修复次数
            
        Returns:
            (修复后的输出, 错误列表)
        """
        errors = []
        
        # 1. Schema 合规检查
        schema_errors = self._validate_schema(llm_output, schema)
        
        if schema_errors:
            errors.extend(schema_errors)
            logger.warning(f"[{node_name}] 结构自检发现 {len(schema_errors)} 个错误")
            
            # 自我修复：让 LLM 根据错误修正
            for retry in range(max_retries):
                try:
                    fixed_output = await self._llm_fix(
                        llm_output, 
                        schema_errors, 
                        schema,
                        node_name
                    )
                    
                    # 验证修复是否成功
                    remaining_errors = self._validate_schema(fixed_output, schema)
                    
                    if not remaining_errors:
                        logger.info(f"[{node_name}] 结构自检修复成功（重试 {retry + 1}/{max_retries}）")
                        return fixed_output, errors
                    
                    logger.warning(
                        f"[{node_name}] 结构自检修复后仍有 {len(remaining_errors)} 个错误"
                    )
                    llm_output = fixed_output
                    schema_errors = remaining_errors
                    
                except Exception as e:
                    logger.error(f"[{node_name}] 结构自检修复失败: {e}")
                    break
        
        # 2. 必填字段检查
        required_errors = self._check_required_fields(llm_output, schema)
        errors.extend(required_errors)
        
        # 3. 数据类型检查
        type_errors = self._check_field_types(llm_output, schema)
        errors.extend(type_errors)
        
        return llm_output, errors
    
    def _validate_schema(self, output: dict, schema: dict) -> list[str]:
        """
        使用注入的 validator 检查 Schema
        
        返回错误列表
        """
        try:
            # 调用外部注入的 validator
            result = self.schema_validator.validate(output, schema)
            
            # 处理不同 validator 的返回格式
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                return result.get("errors", [])
            if result is None:
                return []
                
            return []
            
        except Exception as e:
            return [f"Schema 验证异常: {str(e)}"]
    
    async def _llm_fix(
        self, 
        output: dict, 
        errors: list[str], 
        schema: dict,
        node_name: str
    ) -> dict:
        """
        让 LLM 根据错误信息修复输出
        """
        fix_prompt = f"""
你生成的输出存在以下 schema 错误：

{chr(10).join(f"- {err}" for err in errors[:5])}  # 限制错误数量避免过长

原始输出：
```json
{json.dumps(output, indent=2, ensure_ascii=False)[:3000]}
```

请根据目标 Schema 修复这些错误，输出完整的修复后 JSON：

目标 Schema:
```json
{json.dumps(schema, indent=2, ensure_ascii=False)[:2000]}
```

只输出修复后的 JSON 对象，不要其他文字。
"""
        
        response = await self.llm.ainvoke([
            {"role": "system", "content": "你是一个 JSON 格式修复专家。"},
            {"role": "user", "content": fix_prompt}
        ])
        
        # 提取 JSON - 使用通用的 JSON 提取逻辑
        fixed = self._extract_json_from_text(response.content)
        
        if not fixed:
            raise ValueError("LLM 修复后未能提取有效 JSON")
        
        return fixed
    
    def _extract_json_from_text(self, text: str) -> dict | None:
        """
        从文本中提取 JSON 对象（通用方法）
        
        尝试多种策略：
        1. 直接解析
        2. 提取 code fence 中的内容
        3. 查找第一个 JSON 对象
        """
        import re
        
        # 策略 1: 直接解析
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # 策略 2: 提取 code fence
        code_fence_pattern = r'```(?:json)?\s*(\{.+?\})\s*```'
        match = re.search(code_fence_pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 策略 3: 查找第一个完整的 JSON 对象
        # 使用递归匹配括号
        brace_count = 0
        start_idx = text.find('{')
        
        if start_idx == -1:
            return None
        
        for i in range(start_idx, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                
                if brace_count == 0:
                    # 找到完整的 JSON 对象
                    json_str = text[start_idx:i+1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        # 继续查找下一个
                        next_start = text.find('{', i+1)
                        if next_start == -1:
                            return None
                        start_idx = next_start
                        brace_count = 0
        
        return None
    
    def _check_required_fields(self, output: dict, schema: dict) -> list[str]:
        """
        检查必填字段（从 schema 中提取）
        """
        errors = []
        required_fields = schema.get("required", [])
        
        for field in required_fields:
            if field not in output:
                errors.append(f"缺少必填字段: {field}")
        
        return errors
    
    def _check_field_types(self, output: dict, schema: dict) -> list[str]:
        """
        检查字段类型
        """
        errors = []
        properties = schema.get("properties", {})
        
        for field, field_schema in properties.items():
            if field in output:
                expected_type = field_schema.get("type")
                actual_value = output[field]
                
                if not self._check_type(actual_value, expected_type):
                    errors.append(
                        f"{field} 类型错误：期望 {expected_type}，"
                        f"实际 {type(actual_value).__name__}"
                    )
        
        return errors
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """类型检查辅助方法"""
        if expected_type is None:
            return True
        
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None)
        }
        
        expected_class = type_map.get(expected_type)
        if expected_class is None:
            return True
        
        return isinstance(value, expected_class)


# 简单的 jsonschema 包装器（如果项目已有 jsonschema，可以直接使用）
class JsonSchemaValidator:
    """jsonschema 包装器"""
    
    def __init__(self):
        try:
            import jsonschema
            self.jsonschema = jsonschema
        except ImportError:
            logger.warning("jsonschema 未安装，结构验证功能受限")
            self.jsonschema = None
    
    def validate(self, instance: dict, schema: dict) -> list[str]:
        """
        验证 instance 是否符合 schema
        
        返回错误列表（空列表表示验证通过）
        """
        if self.jsonschema is None:
            return []
        
        try:
            self.jsonschema.validate(instance=instance, schema=schema)
            return []
        except self.jsonschema.ValidationError as e:
            return [str(e.message)]
        except self.jsonschema.SchemaError as e:
            return [f"Schema 定义错误: {e.message}"]
        except Exception as e:
            return [f"验证异常: {str(e)}"]
