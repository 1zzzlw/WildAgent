# Requirements Document

## Introduction

当 AI Agent 生成建筑蓝图后，校验流水线（Step 9）能检测到柱子（column）、家具（furniture）、楼梯（stair）等构件底部悬空或穿入楼板的问题，但目前**没有对应的自动修正步骤**。这导致这类问题被检测到后没有被修复，最终渲染出悬空柱子、透明穿插等错误效果。

本功能在现有 15 步流水线末尾新增一个 `fix_element_elevations` 工具和对应的 Step 9b，自动将竖向构件的底部 Y 对齐到最近楼板的顶面。

## Glossary

- **Blueprint**: `.wild` 格式的建筑蓝图 JSON，是场景唯一源文件
- **Element**: Blueprint 中 `geometry.elements` 数组里的单个构件
- **Floor top Y**: `floor` 构件的 `from[1]` 坐标，代表楼板顶面的世界 Y 坐标
- **Base Y**: `column` 的 `base[1]`，代表柱子底面的世界 Y 坐标
- **Elevation Gap**: 构件底部 Y 与最近楼板顶面 Y 的差值（gap = base_y - nearest_floor_y）
- **Floating**: gap > 0.3m，构件悬空在楼板上方
- **Embedded**: gap < -0.1m，构件底部穿入楼板内部
- **Pipeline**: `run_validation_pipeline()` 函数，按固定顺序执行所有校验+修正步骤
- **Spatial Tools**: `wild-server/app/tools/spatial_tools.py` 中的校验/修正工具集

## Requirements

### Requirement 1: 新增 fix_element_elevations 工具

**User Story:** As a developer, I want the server to automatically fix floating or embedded column/stair/furniture elements, so that the rendered model has no visible gaps or intersections.

#### Acceptance Criteria

1. THE `fix_element_elevations` tool SHALL be a `@tool`-decorated pure function in `spatial_tools.py` that accepts a `blueprint: dict` and returns a human-readable string
2. WHEN a `column` element's `base[1]` value is more than 0.3m above any floor top Y, THE tool SHALL update `base[1]` to the nearest floor top Y (including ground Y=0)
3. WHEN a `column` element's `base[1]` value is more than 0.1m below any floor top Y, THE tool SHALL update `base[1]` to the nearest floor top Y
4. WHEN a `stair` element's `from[1]` value is more than 0.3m above any floor top Y, THE tool SHALL update `from[1]` to the nearest floor top Y
5. WHEN a `furniture` element's `position[1]` value is more than 0.3m above any floor top Y, THE tool SHALL update `position[1]` to the nearest floor top Y
6. WHEN no elements require correction, THE tool SHALL return a message indicating all elements are correctly positioned
7. WHEN corrections are made, THE tool SHALL return a summary listing each corrected element ID, old Y value, and new Y value

### Requirement 2: 将 fix_element_elevations 接入校验流水线

**User Story:** As a developer, I want the fix_element_elevations tool to run automatically after collision detection, so that elevation errors found in Step 9 are corrected before the blueprint is returned.

#### Acceptance Criteria

1. WHEN `validate_collision` (Step 9) reports any floating or embedded warnings for column/stair/furniture, THE `run_validation_pipeline()` in `agent_service.py` SHALL invoke `fix_element_elevations` as Step 9b
2. WHEN Step 9b runs, THE pipeline SHALL re-run `validate_collision` as a recheck step (Step 9b recheck) to confirm the fix was successful
3. WHEN Step 9 reports no floating/embedding issues, THE pipeline SHALL skip Step 9b with a message indicating it was not needed
4. THE `fix_element_elevations` tool SHALL be registered in the `tools` list of `AgentService.__init__()` so the LLM Agent can also call it manually

### Requirement 3: fix_element_elevations 不破坏现有流水线

**User Story:** As a developer, I want the new step to be additive, so that all existing pipeline behavior remains unchanged.

#### Acceptance Criteria

1. WHEN `fix_element_elevations` is added to the pipeline, THE existing steps 1 through 9 SHALL continue to execute in the same order with the same logic
2. THE `fix_element_elevations` function SHALL NOT modify any element fields other than the Y coordinate of the bottom anchor point (`base[1]` for column, `from[1]` for stair, `position[1]` for furniture)
3. FOR ALL blueprints with no column/stair/furniture elements, THE `fix_element_elevations` tool SHALL return immediately without modification
