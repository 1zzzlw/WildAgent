"""`COMPONENT_TOOLS` 的形态不变量：每一项都必须是**可调用的普通函数**。

`validate_component()` / `fix_component()` 的契约就是"取出函数直接调用"：

```python
return tools["validate"](blueprint)
```

所以表里混进一个 `@tool` 装饰过的 `StructuredTool` 就会抛
`'StructuredTool' object is not callable` —— 该构件类型的**每一次**校验都失败。

2026-09-23 实测缺陷：`furniture` 是**唯一**一项存了 `StructuredTool`
（它直接复用 `spatial_tools.validate_element_required_fields` /
`fix_element_elevations`，那两个是 `@tool`），其余 11 项都是普通函数。
因为建筑链从不派发 `furniture`，这个错位一直没暴露；真模型跑
`生成一个桌子` 时家具条目生成成功（`[furniture_gen] 完成: 1 个 家具`）、
紧接着在校验节点炸掉、条目转 `skipped`、最终蓝图里一件家具都没有——
而 801 个测试全绿。
"""

from __future__ import annotations

import unittest
from inspect import isfunction

from app.tools.component_tools import COMPONENT_TOOLS, fix_component, validate_component

_EMPTY_BLUEPRINT = {"meta": {"version": "1.1", "type": "asset", "name": "t"}, "geometry": {"elements": []}}


class ComponentToolsShapeTest(unittest.TestCase):
    def test_every_entry_is_a_plain_callable(self):
        offenders: list[str] = []
        for component_type, tools in sorted(COMPONENT_TOOLS.items()):
            for role in ("validate", "fix"):
                entry = tools.get(role)
                if entry is None:
                    offenders.append(f"{component_type}.{role} 缺失")
                    continue
                # `@tool` 装饰得到的 StructuredTool 有 `.func`；工具对象不可直接调用。
                if not isfunction(entry):
                    offenders.append(
                        f"{component_type}.{role} 是 {type(entry).__name__}（应为普通函数）"
                    )
        self.assertEqual(offenders, [], "COMPONENT_TOOLS 必须全表同形：" + "; ".join(offenders))

    def test_every_entry_is_callable_with_a_blueprint(self):
        for component_type, tools in sorted(COMPONENT_TOOLS.items()):
            for role in ("validate", "fix"):
                with self.subTest(component_type=component_type, role=role):
                    result = tools[role](dict(_EMPTY_BLUEPRINT))
                    self.assertIsInstance(result, str)


class ComponentEntryPointTest(unittest.TestCase):
    def test_validate_component_does_not_raise_for_any_registered_type(self):
        for component_type in sorted(COMPONENT_TOOLS):
            with self.subTest(component_type=component_type):
                result = validate_component(component_type, dict(_EMPTY_BLUEPRINT))
                self.assertIsInstance(result, str)
                self.assertNotIn("没有校验工具", result)

    def test_fix_component_does_not_raise_for_any_registered_type(self):
        for component_type in sorted(COMPONENT_TOOLS):
            with self.subTest(component_type=component_type):
                result = fix_component(component_type, dict(_EMPTY_BLUEPRINT))
                self.assertIsInstance(result, str)
                self.assertNotIn("没有修复工具", result)

    def test_unknown_component_type_reports_instead_of_raising(self):
        self.assertIn("没有校验工具", validate_component("no_such_component", dict(_EMPTY_BLUEPRINT)))


if __name__ == "__main__":
    unittest.main()
