"""数据化构件配方的守卫测试。

守的是四件**不会让任何别的测试变红**的事：

1. 新增一份配方 JSON 却忘了在 `recipes/index.ts` 加 import —— 前端看不到它，
   编译、渲染、schema 全部正常；
2. 后端注册表读不到配方 —— 用户点名时不给配额，构件永远不出现；
3. `componentSpec.not.enum` 与 `$defs/*Component` 的 `const` 漂移 ——
   `oneOf` 从互斥变成多匹配，报的却是一句「不符合任何一个分支」；
4. 两份 schema 再次分叉 —— 服务端校验用的那份比引擎严。

判据一律从文件本身推导，不复制第二份清单。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
# 与同目录其它测试一致：把 wild-server 放进 sys.path 才能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
RECIPE_DIR = REPO_ROOT / "wild-core" / "src" / "compiler" / "declarative" / "recipes"
RECIPE_INDEX = RECIPE_DIR / "index.ts"
CORE_SCHEMA = REPO_ROOT / "wild-core" / "schema.json"
SERVER_SCHEMA = REPO_ROOT / "wild-server" / "storage" / "knowledge_base" / "schema.json"

RECIPE_FILES = sorted(RECIPE_DIR.glob("*.json"))


def _recipe(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_recipe_dir_is_not_empty() -> None:
    assert RECIPE_FILES, f"配方目录是空的: {RECIPE_DIR}"


def test_every_recipe_is_imported_by_frontend_index() -> None:
    """新增 JSON 必须同时进 `index.ts` —— 否则前端面板与属性面板都看不到它。"""

    index_text = RECIPE_INDEX.read_text(encoding="utf-8")
    imported = set(re.findall(r"from\s+'\./([A-Za-z0-9_\-]+)\.json'", index_text))
    on_disk = {path.stem for path in RECIPE_FILES}
    assert on_disk - imported == set(), (
        "这些配方没有被 recipes/index.ts 导入，前端不会加载它们: "
        + ", ".join(sorted(on_disk - imported))
    )
    assert imported - on_disk == set(), (
        "recipes/index.ts 导入了不存在的配方文件: " + ", ".join(sorted(imported - on_disk))
    )


@pytest.mark.parametrize("path", RECIPE_FILES, ids=lambda item: item.stem)
def test_recipe_shape(path: Path) -> None:
    recipe = _recipe(path)
    assert recipe["type"] == path.stem, f"{path.name} 的 type 必须与文件名一致"
    assert recipe.get("label"), f"{path.name} 缺少 label（面板显示名）"
    assert recipe.get("icon"), f"{path.name} 缺少 icon"
    assert recipe.get("host") in {"position", "none", "wall", "roof"}, f"{path.name} 宿主种类非法"
    assert recipe.get("elements"), f"{path.name} 没有 elements"
    assert recipe.get("keywords"), f"{path.name} 缺少 keywords（后端规划按点名触发）"
    defaults = recipe.get("defaults") or {}
    if recipe["host"] != "none":
        assert isinstance(defaults.get("position"), list), (
            f"{path.name} 缺 defaults.position —— 拖进场景会落到 NaN 坐标"
        )


@pytest.mark.parametrize("path", RECIPE_FILES, ids=lambda item: item.stem)
def test_recipe_reaches_backend_registry(path: Path) -> None:
    """配方必须能在后端注册表里查到，且规则/关键词非空。"""

    from app.agent.generation.component.registry import COMPONENT_REGISTRY

    recipe = _recipe(path)
    config = COMPONENT_REGISTRY.get(recipe["type"])
    assert config is not None, f"{recipe['type']} 没有进 COMPONENT_REGISTRY"
    assert config.label, f"{recipe['type']} 注册项缺 label"
    assert config.need_keywords, f"{recipe['type']} 注册项缺 need_keywords（点名不会触发）"
    assert config.extra_rules.strip(), f"{recipe['type']} 注册项缺 extra_rules（提示词无字段约束）"


def test_recipe_defaults_pass_component_spec() -> None:
    """用配方自己的默认值拼一个最小构件，必须能通过组件 schema。

    这是「数据和契约对得上」的端到端检查：配方加了 schema 不认的字段、
    或漏了必填字段，都会在这里暴露，而不是等到真正生成时才发现。
    """

    jsonschema = pytest.importorskip("jsonschema")

    schema = json.loads(SERVER_SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        {"$ref": "#/$defs/componentSpec", "$defs": schema["$defs"]},
    )
    for path in RECIPE_FILES:
        recipe = _recipe(path)
        params = recipe.get("params") or {}
        component: dict = {"type": recipe["type"], "id": "probe"}
        for key, spec in params.items():
            if "default" in spec:
                component[key] = spec["default"]
        component.update({k: v for k, v in (recipe.get("defaults") or {}).items() if k != "position"})
        component["position"] = list((recipe.get("defaults") or {}).get("position") or [0, 0, 0])
        errors = list(validator.iter_errors(component))
        assert errors == [], f"{recipe['type']} 的默认构件不合 schema: {errors[0].message}"


def test_schema_copies_are_identical() -> None:
    """两份 schema 必须逐字节一致。

    它们分别是引擎侧与**服务端校验实际使用**的那一份
    （`app/utils/blueprint_normalizer.py::SCHEMA_PATH`）。曾经分叉过一次：
    kb 那份落后 465 条叶路径，服务端拿旧契约卡新蓝图。
    """

    core = CORE_SCHEMA.read_bytes()
    server = SERVER_SCHEMA.read_bytes()
    assert core == server, (
        "wild-core/schema.json 与 storage/knowledge_base/schema.json 不一致；"
        "改动 schema 时必须同步两份"
    )


def test_recipe_component_excludes_exactly_the_known_types() -> None:
    """`recipeComponent.type.not.enum` 必须恰好等于已有 `*Component` 的 `const` 集合。

    这条列表是手写的，而同样的类型名在 `$defs` 里以 `const` 又出现一次。
    不守就会漂移：一旦某个已知类型漏在 enum 外，它会同时匹配专属定义和通用槽位，
    `oneOf` 报"不符合任何一个分支"——错误信息完全指不到根因。
    """

    schema = json.loads(CORE_SCHEMA.read_text(encoding="utf-8"))
    defs = schema["$defs"]
    known = {
        definition["properties"]["type"]["const"]
        for name, definition in defs.items()
        if name.endswith("Component") and name != "recipeComponent"
        and isinstance(definition.get("properties", {}).get("type"), dict)
        and "const" in definition["properties"]["type"]
    }
    excluded = set(defs["recipeComponent"]["properties"]["type"]["not"]["enum"])
    assert excluded == known, (
        f"not.enum 与已知类型不一致；只在一侧有: {sorted(excluded ^ known)}"
    )
    # 注：已迁移的构件（fan / chimney）同时有配方和专属 `$def` —— 这是刻意的。
    # 配方负责几何，schema 继续用那份严格定义校验字段，不因为变成数据化就放宽契约。
