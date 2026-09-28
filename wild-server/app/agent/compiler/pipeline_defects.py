"""交付流水线 → 编译期缺陷的**唯一投影**（设计文档 §2.5）。

§2.5 的目标是让"能否编译"和"图纸是否合格"由同一个函数的两半回答。做法**不是**
再写一套校验器，而是复用交付那条流水线（``run_validation_pipeline``）——它才是
线上判定的唯一事实源。编译期只把它的 error 步骤投影成结构化缺陷。

为什么能直接复用而不是"抄一份"：编译期与交付期的输入蓝图**是同一种东西**
（``geometry.elements`` / ``geometry.components`` 的字典），校验器也全是
``blueprint -> 文本`` 的纯函数。两处各挑几个校验器调一遍，就是"同一口径两处实现"，
改了一处另一处不跟——正是这次重构要消掉的东西（`MEMORY.md`：唯一事实源 + 唯一规则函数）。

三条实现纪律：

1. 🔴 **在深拷贝上跑**。流水线里带 ``fix_*`` 步骤，会就地把蓝图修好（交付路径正是
   靠这个）。编译期只要**诊断**，不要一次隐式修复——否则"编译器产物"与"图纸"之间
   会多出一处没人记账的改动，而 ``compile_design`` 自称是纯函数。
2. 🔴 **口径复用 ``_final_errors``**，不另写"哪些步骤算没过"：它按校验器去重、
   只保留修复后的 ``[recheck]``，与交付路径完全同一个收敛口径。
3. **步骤日志默认可关**。交付路径需要逐步骤日志（线上排查用）；编译期一次生成里会
   调它很多次（收敛环每轮一次、试算工具每次调用一次），逐步骤日志会把真正的编译
   诊断淹掉，所以这里关掉。

⚠️ 复用的代价：流水线的 Step 1（顶层结构）**不过就短路**，后面的尺寸/引用校验不再跑。
这是交付路径本来就有的行为，这里照搬——"先把顶层结构修好再看细节"。
"""

from __future__ import annotations

import copy
from typing import Any


def pipeline_defect_messages(blueprint: dict[str, Any]) -> list[tuple[str, str]]:
    """把交付流水线在 ``error`` 上仍未通过的步骤投影成 ``[(步骤名, 消息), …]``。

    消息一律是校验器原文里的 ``❌`` 行（**不改写**）：证据必须能直接对得上
    ``spatial_tools`` 的输出，否则同一条缺陷在两处会有两种说法。
    """

    from app.services.agent_service import _final_errors, run_validation_pipeline

    target = copy.deepcopy(blueprint)
    found: list[tuple[str, str]] = []
    for step in _final_errors(run_validation_pipeline(target, log_steps=False)):
        for line in str(step.output).splitlines():
            message = line.strip()
            if "❌" in message:
                found.append((str(step.name), message))
    return found


__all__ = ["pipeline_defect_messages"]
