"""
通用 JSON 提取工具 —— 从 LLM 回复中提取 JSON 对象或数组

消除 door/window/roof/railing 节点中重复的 _extract_component_array 和 _extract_roof_object。
"""
import json
import re
from loguru import logger


def extract_json_array(text: str) -> list:
    """从 LLM 回复中提取 JSON 数组"""
    json_text = _extract_from_code_block(text)

    array_pattern = r"\[[\s\S]*\]"
    array_matches = re.findall(array_pattern, json_text)

    if array_matches:
        json_text = max(array_matches, key=len)  # 取最长的数组

    try:
        data = json.loads(json_text)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError as e:
        logger.error(f"JSON 数组解析失败: {e}, 文本: {json_text[:200]}")
        return []


def extract_json_object(text: str) -> dict | None:
    """从 LLM 回复中提取 JSON 对象"""
    json_text = _extract_from_code_block(text)

    object_pattern = r"\{[\s\S]*\}"
    object_matches = re.findall(object_pattern, json_text)

    if object_matches:
        json_text = max(object_matches, key=len)  # 取最大的对象

    try:
        data = json.loads(json_text)
        if isinstance(data, dict):
            return data
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON 对象解析失败: {e}, 文本: {json_text[:200]}")
        return None


def _extract_from_code_block(text: str) -> str:
    """从 markdown 代码块中提取内容，失败则返回原文"""
    json_block_pattern = r"```(?:json)?\s*\n(.*?)\n```"
    matches = re.findall(json_block_pattern, text, re.DOTALL)

    if matches:
        return matches[0].strip()
    return text.strip()
