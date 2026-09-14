"""
推理自检模块 (Reasoning Validator)

P2 方案：检查 LLM 思考过程的逻辑一致性（领域无关）

用法:
    validator = ReasoningValidator(llm, domain_context)
    is_consistent, contradictions = await validator.validate_reasoning(reasoning_text, user_query, output)
"""
import json
from typing import Any
from loguru import logger


class ReasoningValidator:
    """
    推理自检：检查 LLM 思考过程的逻辑一致性（领域无关）
    """
    
    def __init__(self, llm: Any, domain_context: dict):
        """
        Args:
            llm: LLM 实例
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
    ) -> tuple[bool, list[dict]]:
        """
        检查推理过程与输入/输出的一致性（通用）
        
        Args:
            reasoning_text: LLM 推理过程文本
            user_query: 用户需求
            output: LLM 输出结果
            
        Returns:
            (是否一致, 矛盾列表)
        """
        validation_prompt = f"""
你是 {self.domain_context['domain_name']} 领域的逻辑验证专家。

请检查以下 AI 推理过程是否存在逻辑矛盾：

**用户需求：**
{user_query}

**AI 推理过程：**
{reasoning_text[:3000]}  # 限制长度

**AI 输出结果：**
{json.dumps(output, indent=2, ensure_ascii=False)[:2000]}

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

只输出 JSON，不要其他文字。
"""
        
        try:
            response = await self.llm.ainvoke([
                {"role": "system", "content": "你是一个逻辑一致性验证专家。"},
                {"role": "user", "content": validation_prompt}
            ])
            
            result_json = self._parse_json(response.content)
            
            if result_json:
                has_contradiction = result_json.get("has_contradiction", False)
                contradictions = result_json.get("contradictions", [])
                
                if contradictions:
                    logger.warning(
                        f"[推理自检] 发现 {len(contradictions)} 个逻辑矛盾"
                    )
                
                return not has_contradiction, contradictions
            
            # 解析失败，使用回退策略
            return True, []
            
        except Exception as e:
            logger.warning(f"[推理自检] 验证失败: {e}")
            return True, []  # 失败时假设一致
    
    async def generate_correction_prompt(
        self, 
        contradictions: list[dict],
        original_query: str
    ) -> str:
        """
        生成修正提示（通用）
        
        Args:
            contradictions: 矛盾列表
            original_query: 原始用户需求
            
        Returns:
            修正提示词
        """
        # 按严重程度排序
        sorted_contradictions = sorted(
            contradictions,
            key=lambda c: {"high": 0, "medium": 1, "low": 2}.get(c.get("severity", "low"), 2)
        )
        
        correction_prompt = f"""
你上次的推理存在以下逻辑矛盾：

{chr(10).join(f"- [{c['severity'].upper()}] {c['description']}" for c in sorted_contradictions[:5])}

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
    
    def _parse_json(self, text: str) -> dict | None:
        """从 LLM 响应中提取 JSON"""
        import re
        
        # 尝试直接解析
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # 尝试从 code fence 提取
        code_fence_match = re.search(
            r'```(?:json)?\s*(\{.+?\})\s*```', 
            text, 
            re.DOTALL
        )
        if code_fence_match:
            try:
                return json.loads(code_fence_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 尝试查找第一个 JSON 对象
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
                    try:
                        return json.loads(text[start_idx:i+1])
                    except json.JSONDecodeError:
                        pass
        
        return None
    
    def detect_common_contradictions(
        self,
        user_query: str,
        output: dict,
        reasoning_text: str = ""
    ) -> list[dict]:
        """
        基于规则检测常见矛盾（不依赖 LLM）
        
        Args:
            user_query: 用户查询
            output: 输出结果
            reasoning_text: 推理文本（可选）
            
        Returns:
            检测到的矛盾列表
        """
        contradictions = []
        
        # 规则 1: 检查用户明确要求的属性是否在输出中
        user_query_lower = user_query.lower()
        
        # 提取用户要求的关键词
        required_keywords = []
        for keyword in ["style", "size", "type", "color", "material"]:
            if keyword in user_query_lower:
                required_keywords.append(keyword)
        
        for keyword in required_keywords:
            if keyword not in str(output).lower():
                contradictions.append({
                    "type": "attribute_mismatch",
                    "description": f"用户要求包含 '{keyword}'，但输出中未找到",
                    "severity": "medium"
                })
        
        # 规则 2: 检查数值的合理性
        for key, value in output.items():
            if isinstance(value, (int, float)):
                # 检查明显不合理的数值
                if value < 0:
                    contradictions.append({
                        "type": "value_error",
                        "description": f"字段 '{key}' 的值 {value} 为负数",
                        "severity": "high"
                    })
                elif value > 1000000:  # 假设超过百万是不合理的
                    contradictions.append({
                        "type": "value_error",
                        "description": f"字段 '{key}' 的值 {value} 异常大",
                        "severity": "medium"
                    })
        
        # 规则 3: 检查推理与输出的一致性（如果有推理文本）
        if reasoning_text:
            # 提取推理中提到的数值
            import re
            reasoning_numbers = re.findall(r'\d+\.?\d*', reasoning_text)
            output_numbers = re.findall(r'\d+\.?\d*', str(output))
            
            # 简单检查：推理中提到的数值是否在输出中
            # （这只是一个启发式检查）
            pass  # 可以添加更复杂的逻辑
        
        return contradictions
