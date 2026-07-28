# Implementation Plan: fix-element-elevation

## Overview

在 spatial_tools.py 新增 fix_element_elevations 工具，并在 agent_service.py 的流水线里接入为 Step 9b，修正柱子/楼梯/家具悬空问题。

## Tasks

- [ ] 1. 在 spatial_tools.py 新增 fix_element_elevations 工具
  - 实现 `@tool` 装饰的 `fix_element_elevations(blueprint: dict) -> str` 函数
  - 收集所有 floor.from[1] + Y=0 作为参考高度
  - 遍历 column/stair/furniture，计算 gap，超阈值时修正底部 Y
  - 返回修正摘要字符串（含各构件 ID、旧值、新值）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 3.2, 3.3_

- [ ]* 1.1 为 fix_element_elevations 编写单元测试
  - 测试 column 悬空（floor Y=0.9, column base Y=1.5 → 修正到 0.9）
  - 测试 column 穿入（floor Y=0.9, column base Y=0.7 → 修正到 0.9）
  - 测试无楼板时使用 Y=0 参考
  - 测试无需修正时返回通过消息
  - _Requirements: 1.2, 1.3, 1.6_

- [ ]* 1.2 为 fix_element_elevations 编写 Property 1 属性测试
  - **Property 1: 竖向构件高程对齐**
  - 使用 hypothesis 生成包含随机 floor 和 column/stair/furniture 的 Blueprint
  - 修正后验证所有构件 gap 满足 -0.1m <= gap <= 0.3m
  - **Validates: Requirements 1.2, 1.3, 1.4, 1.5**

- [ ]* 1.3 为 fix_element_elevations 编写 Property 3 属性测试
  - **Property 3: 字段修改隔离性**
  - 调用工具后验证只有 base[1]/from[1]/position[1] 可能被修改
  - **Validates: Requirements 3.2**

- [ ] 2. 在 agent_service.py 流水线接入 Step 9b
  - 从 spatial_tools 导入 fix_element_elevations
  - 在 run_validation_pipeline() 中 Step 9 之后新增 Step 9b 逻辑
  - Step 9 有 warning/error 时触发修正 + validate_collision recheck
  - Step 9 无问题时 skip_step("9b", ...)
  - 在 AgentService.__init__() 的 tools 列表中注册 fix_element_elevations
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1_

- [ ]* 2.1 为 Step 9b 流水线逻辑编写单元测试
  - 测试有悬空警告时 pipeline_results 包含 step="9b" 的条目
  - 测试无问题时 pipeline_results 包含 skip 标记的 "9b" 条目
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 3. Checkpoint —— 确保所有测试通过，向用户确认修复效果
  - 确保所有测试通过，ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- fix_element_elevations 是纯函数，直接原地修改 blueprint dict，与其他工具风格一致
- 阈值：悬空 > 0.3m 触发修正，穿入 > 0.1m 触发修正（与 validate_collision 的报警阈值对齐）
