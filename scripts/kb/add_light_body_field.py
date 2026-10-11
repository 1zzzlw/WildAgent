"""给 lightComponent 增加参数化灯体字段 body，并同步写入 schema 两副本。

两副本必须字节一致（wild-core/schema.json ↔ wild-server/storage/knowledge_base/schema.json），
所以只在这里改一次、同时写两个路径，避免手工同步漂移。
"""

import collections
import hashlib
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parents[2]  # scripts/kb/ -> scripts/ -> 仓库根
TARGETS = [
    REPO / "wild-core/schema.json",
    REPO / "wild-server/storage/knowledge_base/schema.json",
]

#: body 的每段 = primitive 的几何字段 + position 可省 + interactive 命中标记。
#: 用 allOf 引用 primitive 再收紧，是为了不复制第二份形状枚举
#: —— 值合法性的唯一事实源必须是 schema 自己的 $defs.primitive。
BODY_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "description": (
        "参数化灯体几何。字段与 primitive 原语一致（shape/radius/dimensions/path/profile 等），"
        "给了 body 就直接展开成这些几何，fixtureType 不再参与。"
        "新增灯型写数据即可，不必扩充 fixtureType 枚举。"
    ),
    "items": {
        "allOf": [
            # 复用 primitive 而不是抄一份形状枚举 —— 值合法性的唯一事实源必须是 $defs.primitive。
            {"$ref": "#/$defs/primitiveBody"},
        ]
    },
}

#: 灯体段专用形状：与 primitive 同构，但去掉 `type` / `id`（编译期生成，调用方不写）。
#: 🔴 不能用 `"id": False` / `"type": False` 这种写法 —— JSON Schema 里布尔schema 等价于
#: `{"not": {}}`（几乎永不通过），**并不能取消 required**，primitive 的 required 照样会报
#: "'id' is a required property"。要"不要求且不接受"只能用 not/oneOf 排除或单开一份 defs。
BODY_PART_DEF = {
    "type": "object",
    "required": ["shape"],
    "additionalProperties": False,
    "properties": {
        "shape": {"enum": ["box", "sphere", "cylinder", "profile_sweep"]},
        "position": {"$ref": "#/$defs/vec3"},
        "rotation": {"$ref": "#/$defs/vec3"},
        "scale": {"$ref": "#/$defs/vec3"},
        "material": {"type": "string"},
        "dimensions": {"$ref": "#/$defs/vec3"},
        "radius": {"type": "number", "exclusiveMinimum": 0},
        "radiusTop": {"type": "number", "exclusiveMinimum": 0},
        "radiusBottom": {"type": "number", "exclusiveMinimum": 0},
        "height": {"type": "number", "exclusiveMinimum": 0},
        "segments": {"type": "integer", "minimum": 3, "maximum": 128},
        "heightSegments": {"type": "integer", "minimum": 2, "maximum": 64},
        "profile": {
            "type": "array",
            "minItems": 2,
            "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"}},
        },
        "path": {"type": "array", "minItems": 2, "items": {"$ref": "#/$defs/vec3"}},
        "closedProfile": {"type": "boolean", "default": True},
        "interactive": {
            "type": "boolean",
            "description": (
                "该段是否承载灯光交互（右键点灯的唯一命中体）。"
                "省略时默认最后一段；多段标 true 只认第一段。"
            ),
        },
    },
    # 与 $defs.primitive 的 oneOf 保持同构：形状与该形状的专属参数必须成对出现。
    "oneOf": [
        {"required": ["dimensions"], "properties": {"shape": {"const": "box"}}},
        {"required": ["radius"], "properties": {"shape": {"const": "sphere"}}},
        {
            "required": ["height"],
            "properties": {"shape": {"const": "cylinder"}},
            "oneOf": [
                {"required": ["radius"]},
                {"required": ["radiusTop", "radiusBottom"]},
            ],
        },
        {"required": ["path"], "properties": {"shape": {"const": "profile_sweep"}}},
    ],
}


def patch(schema: dict) -> bool:
    defs = schema["$defs"]
    props = defs["lightComponent"]["properties"]
    if "body" in props:
        return False
    # 新增 primitiveBody 定义：与 primitive 同构但去掉 type/id（编译期生成）。
    defs["primitiveBody"] = json.loads(json.dumps(BODY_PART_DEF))
    # 插在 fixtureType 之前：读 schema 的人先看到 body（推荐的现代写法），
    # 再看到 fixtureType（默认体型的快捷写法）。
    rebuilt = collections.OrderedDict()
    for key, value in props.items():
        if key == "fixtureType":
            rebuilt["body"] = json.loads(json.dumps(BODY_SCHEMA))
        rebuilt[key] = value
    defs["lightComponent"]["properties"] = rebuilt
    return True


def main() -> int:
    changed = []
    for path in TARGETS:
        raw = path.read_text(encoding="utf-8")
        schema = json.loads(raw, object_pairs_hook=collections.OrderedDict)
        if not patch(schema):
            print(f"skip (already patched): {path}")
            continue
        #沿用原文件的缩进与尾随换行，避免产生无意义的全文件 diff
        indent = 2 if raw.startswith("{\n  ") else 4
        text = json.dumps(schema, ensure_ascii=False, indent=indent)
        if raw.endswith("\n"):
            text += "\n"
        path.write_text(text, encoding="utf-8")
        changed.append(path)

    for path in TARGETS:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        print(f"{digest}  {path}")

    a, b = (p.read_bytes() for p in TARGETS)
    if a != b:
        print("FAIL: 两副本字节不一致")
        return 1
    print("OK: 两副本字节一致")
    return 0 if changed else 0


if __name__ == "__main__":
    raise SystemExit(main())