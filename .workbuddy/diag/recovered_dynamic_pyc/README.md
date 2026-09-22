# 已删 `app/agent/dynamic/` 的编译产物备份

## 这是什么

`wild-server/app/agent/dynamic/` 这个包**源码已被整体删除、且从未进入 git**
（`git log --all -- .../dynamic/furniture.py` 无任何记录，全仓也无源码引用），
现在只剩 `__pycache__` 里的 `.pyc`。

**`__pycache__` 会被清理工具或重建索引顺手删掉 —— 那样这套实现就永久消失了。**
所以在这里留一份。

## 备份内容

| 文件 | 大小 | 说明 |
|---|---|---|
| `furniture.cpython-312.pyc` | 4.5 KB | 🔴 **`plan_furniture()` —— 审核态平面图的家具布置**，复原详见下方链接 |
| `room_validation.cpython-312.pyc` | 24 KB | 房间层校验 |
| `schema_builder.cpython-312.pyc` | 40 KB | 设计 schema 构建 |
| `algorithms.cpython-312.pyc` | 35 KB | 算法 |
| `shell.cpython-312.pyc` | 32 KB | 主体结构生成（规划 §5.1 的 `shell` 节点角色） |
| `scheduler.cpython-312.pyc` | 29 KB | 调度 |
| `design_workflow.cpython-312.pyc` | 23 KB | 设计节点工作流 |
| `blueprint_renderer.cpython-312.pyc` | 24 KB | 蓝图 → 渲染 |
| `renderer.cpython-312.pyc` | 19 KB | 2D SVG 渲染（含家具描边色 `#6d4c41` / `#a1887f`） |
| `drafting` / `registry` / `repository` / `review` / `contracts` / `__init__` | 各 4~10 KB | 其余 |
| `test_furniture.cpython-312-pytest-9.1.1.pyc` | — | 配套测试（源码已删），钉住家具的四条规则 |

另各有少量 `cpython-313` 版本。

## 怎么读

`.pyc` 可用 `marshal` 直接反序列化（Python 3.12/3.13 魔数即可，本文档环境是 3.13）：

```python
import marshal
code = marshal.loads(open('furniture.cpython-312.pyc', 'rb').read()[16:])  # 跳过 16 字节头
print([c.co_name for c in code.co_consts if hasattr(c, 'co_name')])          # 顶层函数
# 常量表（含家具数据）在 co_consts 里递归找 tuple
```

⚠️ 3.12 与 3.13 的字节码格式不同：**用 3.12 的 pyc 在 3.13 下 `dis.dis` 会报
`IndexError: tuple index out of range`**（`co_consts`/`co_names` 索引口径变了）。
读常量与函数名不受影响；要完整反汇编就用对应的解释器版本。

## 复原文档

`furniture.py` 的完整设计（家具表、档位映射、四条规则、API 签名）已复原到：

`docs/面试难点解决过程/Agent工作流与中间状态设计问题/室内与家具能力现状：提示词闸门与被删实现复原.md`

## 注意

这是**历史产物，不是实现依据**。原包已废弃；恢复它之前先读上面那份文档 §二 的
「顺序红线」—— 能力与闸门有先后要求。
