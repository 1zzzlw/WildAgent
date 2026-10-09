# -*- coding: utf-8 -*-
"""知识库去 AI 化：emoji 符号统一替换为规范文字标签。

规范（对 RAG 语料的通用写法）：
- 列表项语义前缀用文字：「支持：」「不支持：」「注意：」「关键：」「提示：」
- 表格/代码注释里的对错标记用「正确」「错误」文字
- 替换不改变行结构（对 Markdown 切分与向量检索友好）
"""
import pathlib
import re

ROOT = pathlib.Path(r"E:\AgentProject\WildAgent\wild-server\storage\knowledge_base\knowledge")

# 顺序执行的替换规则：(模式, 替换, 说明)
RULES = [
    # 1. 行首列表项
    (re.compile(r"- ✅ "), "- 支持："),
    (re.compile(r"- ❌ (?=(不|没|禁|勿|避免))"), "- "),          # 动词禁令句直接去符号
    (re.compile(r"- ❌ "), "- 不支持："),
    (re.compile(r"- ⚠️ "), "- 注意："),
    (re.compile(r"- ⚠(?!️) "), "- 注意："),
    # 2. 标题与加粗里的符号
    (re.compile(r"^(#{2,4}) ⚠️ "), r"\1 "),
    (re.compile(r"^(#{2,4}) ✅ "), r"\1 "),
    (re.compile(r"^(#{2,4}) ❌ "), r"\1 "),
    (re.compile(r"\*\*⚠️ "), "**"),
    (re.compile(r"\*\*✅ "), "**"),
    (re.compile(r"\*\*❌ "), "**"),
    # 3. 表格单元格
    (re.compile(r"\| ✅ "), "| "),
    (re.compile(r"\| ❌ "), "| 错误："),
    (re.compile(r"\| ⚠️ "), "| 注意："),
    (re.compile(r"\| ⚠(?!️) "), "| 注意："),
    # 4. 代码注释
    (re.compile(r"// ✅ "), "// "),
    (re.compile(r"// ❌ "), "// 错误："),
    (re.compile(r"// ⚠️ "), "// 注意："),
    # 5. 行内红黄（含表格内）
    (re.compile(r"\s*"), "关键："),
    (re.compile(r"🟡\s*"), "提示："),
    # 6. 其余行内 ⚠️：语境各异，脚本只处理通用搭配，剩余报出来手工改
]

MANUAL = [
    ('否则判"孤立端点"⚠️。', '否则判"孤立端点"（警告级）。'),
    ('两者都是 ⚠️ 警告级', '两者都是警告级'),
    ('校验只报 ⚠️（能力缺失不阻断）', '校验只报警告（能力缺失不阻断）'),
]

changed = {}
for p in sorted(ROOT.rglob("*.md")):
    text = original = p.read_text(encoding="utf-8")
    for old, new in MANUAL:
        text = text.replace(old, new)
    for pat, rep in RULES:
        text = pat.sub(rep, text)
    if text != original:
        p.write_text(text, encoding="utf-8", newline="\n")
        rel = str(p.relative_to(ROOT))
        marks = sum(text.count(m) for m in ("✅", "❌", "⚠️", "⚠", "", "🟡"))
        changed[rel] = marks

print("已改文件及剩余符号数：")
for f, c in sorted(changed.items()):
    print(f"  {c:3d}  {f}")
