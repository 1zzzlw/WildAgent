"""
工具自检模块 (Tool Validator)

P2 方案：分析工具报错原因并生成修复建议（领域无关）

用法:
    validator = ToolValidator(llm, domain_context)
    diagnosis = await validator.diagnose_tool_error(tool_name, error_output, generated_output)
"""
import json
import re
from typing import Any
from loguru import logger


class ToolValidator:
    """
    工具自检：分析工具报错原因并生成修复建议（领域无关）
    """
    
    def __init__(self, llm: Any, domain_context: dict):
        """
        Args:
            llm: LLM 实例
            domain_context: 领域上下文
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
        
        Args:
            tool_name: 工具名称
            error_output: 工具错误输出
            generated_output: 生成的输出
            
        Returns:
            诊断结果:
            {
                "root_cause": "根本原因描述",
                "fix_actions": ["修复步骤列表"],
                "prevention": "预防建议"
            }
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
{json.dumps(self.domain_context.get('output_schema', {}), indent=2, ensure_ascii=False)[:2000]}

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

只输出 JSON，不要其他文字。
"""
        
        try:
            response = await self.llm.ainvoke([
                {"role": "system", "content": "你是一个工具错误诊断专家。"},
                {"role": "user", "content": diagnosis_prompt}
            ])
            
            diagnosis = self._parse_json(response.content)
            
            if diagnosis:
                logger.info(
                    f"[工具自检] {tool_name} 诊断完成: {diagnosis.get('root_cause', '')[:50]}..."
                )
            
            return diagnosis or self._fallback_diagnosis(error_output)
            
        except Exception as e:
            logger.warning(f"[工具自检] 诊断失败: {e}")
            return self._fallback_diagnosis(error_output)
    
    def _extract_relevant_part(self, output: dict, error_msg: str) -> dict:
        """
        从完整输出中提取与错误相关的部分（通用启发式）
        """
        relevant = {}
        
        # 提取错误消息中的字段名（如 "entity_1", "relationship_x"）
        mentioned_keys = re.findall(r'\b\w+\b', error_msg)
        
        for key in mentioned_keys:
            if key in output:
                relevant[key] = output[key]
            
            # 也检查嵌套字段
            if isinstance(output, dict):
                for k, v in output.items():
                    if isinstance(v, dict) and key in v:
                        if k not in relevant:
                            relevant[k] = {}
                        relevant[k][key] = v[key]
        
        # 如果没提取到，返回截断的完整输出
        if not relevant:
            output_str = json.dumps(output, indent=2, ensure_ascii=False)
            lines = output_str.split('\n')[:50]
            return {"_truncated": '\n'.join(lines)}
        
        return relevant
    
    def _parse_json(self, text: str) -> dict | None:
        """从 LLM 响应中提取 JSON"""
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
    
    def _fallback_diagnosis(self, error_output: str) -> dict:
        """回退诊断：基于规则的简单分析"""
        root_cause = "工具检测到错误，但无法获取详细诊断"
        fix_actions = ["检查工具输出", "手动修复错误"]
        prevention = "确保生成符合工具要求"
        
        # 简单的模式匹配
        if "超出" in error_output or "exceed" in error_output.lower():
            root_cause = "数值或尺寸超出允许范围"
            fix_actions = ["检查相关数值字段", "调整到允许范围内"]
        elif "缺少" in error_output or "missing" in error_output.lower():
            root_cause = "缺少必需的字段或值"
            fix_actions = ["补充缺失的字段", "确保所有必填项都有值"]
        elif "不匹配" in error_output or "mismatch" in error_output.lower():
            root_cause = "字段类型或值不匹配"
            fix_actions = ["检查字段类型", "确保值符合预期格式"]
        
        return {
            "root_cause": root_cause,
            "fix_actions": fix_actions,
            "prevention": prevention
        }
    
    async def execute_fix(
        self, 
        output: dict, 
        fix_actions: list[str],
        max_retries: int = 2
    ) -> dict:
        """
        执行修复动作（通用）
        
        策略：让 LLM 基于修复步骤重新生成完整输出
        
        Args:
            output: 当前输出
            fix_actions: 修复步骤列表
            max_retries: 最大重试次数
            
        Returns:
            修复后的输出
        """
        for retry in range(max_retries):
            fix_prompt = f"""
请执行以下修复动作，输出修复后的完整结果：

**修复步骤：**
{chr(10).join(f"{i+1}. {action}" for i, action in enumerate(fix_actions))}

**当前结果：**
{json.dumps(output, indent=2, ensure_ascii=False)}

**目标 Schema：**
{json.dumps(self.domain_context.get('output_schema', {}), indent=2, ensure_ascii=False)[:2000]}

请输出修复后的完整 JSON（确保符合 Schema）。
只输出 JSON，不要其他文字。
"""
            
            try:
                response = await self.llm.ainvoke([
                    {"role": "system", "content": "你是一个输出修复专家。"},
                    {"role": "user", "content": fix_prompt}
                ])
                
                fixed_output = self._parse_json(response.content)
                
                if fixed_output:
                    logger.info(f"[工具自检] 修复尝试 {retry+1}/{max_retries} 完成")
                    return fixed_output
                else:
                    logger.warning(f"[工具自检] 修复尝试 {retry+1} 未能提取有效 JSON")
                    
            except Exception as e:
                logger.warning(f"[工具自检] 修复尝试 {retry+1} 失败: {e}")
                if retry == max_retries - 1:
                    raise
        
        return output  # 修复失败，返回原始输出
