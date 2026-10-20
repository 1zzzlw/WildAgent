# architecture 包清理

已删除 6 个旧模块：`design_blocks.py`、`revision_patch.py`、`planning.py`、`skeleton.py`、`facade.py`、`recipes.py`。它们属于旧图纸分块补丁、旧方案归一化及骨架/立面实现，不在当前 architecture 生成图纸的调用链上。

`profile.py` 从 727 行缩至 140 行：保留粒度说明、当前分类与 API 使用的粒度规范化、建筑类型识别；删除旧构件配额、形状/尺寸解析和体量回退。建筑关键词及粒度说明保持原内容。

包内现保留 5 个 Python 文件：

| 文件 | 职责 |
| --- | --- |
| `workflow.py` | architecture 节点入口与 State 输出 |
| `design_workflow.py` | 完整图纸提交、统一检查工具和有限修订 |
| `profile.py` | 设计粒度及分类共用的建筑关键词 |
| `target_kind.py` | 分类仍使用的建筑/物件判定 |
| `__init__.py` | 分类共用函数的轻量导出 |

本轮包内源码 4300 → 495 行，净减少 3805 行；文件 11 → 5。统计相对本轮清理前工作区，不是相对 Git HEAD。

修改前全部源码见 [00-清理前源码.json](00-清理前源码.json)；删除清单、摘要、引用位置及工具使用记录见 [01-清理记录.json](01-清理记录.json)。

旧编译、装配、骨架和视觉修订仍有旧接口引用，已经列明；按用户此前仅优化设计节点/图纸的范围，本轮不修改这些调用方，也不添加兼容层。因此完整业务链仍待后续迁移。当前 Studio 的 classifier → architecture 调试入口未改。

仅做文件、源码和引用阅读，未运行测试、语法检查、服务、模型调用或 Studio 回放。
