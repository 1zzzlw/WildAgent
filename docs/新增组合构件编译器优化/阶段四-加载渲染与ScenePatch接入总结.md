# 阶段四：加载、渲染与 ScenePatch 接入总结

## 阶段目标

把已通过独立测试的组合构件编译器接入真实应用链路，使服务器保存的 Blueprint、前端加载、场景重建和 AI 增量修改都能保留并处理 `geometry.components`。

## 前端渲染接入

`wildCoreAdapter.reconstructWildEntity()` 现在执行：

```text
源 Blueprint
  → compileBlueprintComponents
  → 展开后的 Blueprint 副本
  → wild-core reconstructEntity
  → 合并编译诊断与 Core 诊断
```

关键行为：

- 源 Blueprint 继续保留高级组件，便于保存和后续修改。
- wild-core 只看到已经展开的基础元素。
- 组件编译错误与 `ELEMENT_BUILD_FAILED` 等原有诊断使用同一返回通道。
- `getWildCoreInfo()` 新增组合构件能力列表，调用方可以区分 Core 类型和高级组件类型。

## 前端校验接入

`sceneValidator` 已增加：

- 组合构件与基础元素的共享 ID 冲突检查。
- 调用编译器进行参数和父墙检查。
- 组件材质引用检查。
- 将编译错误转换成前端 `ValidationIssue`。

导入 Blueprint 时会立即执行校验，因此缺失父墙、越界门窗或非法栏杆路径可以在校验面板中出现，而不是只在最终 renderer 中报错。

## ScenePatch 接入

前端和后端同时增加三种操作：

```text
add_component
update_component
remove_component
```

示例：

```json
{
  "op": "add_component",
  "component": {
    "type": "railing",
    "id": "terrace_railing",
    "path": [[0, 3, 0], [4, 3, 0]],
    "height": 1.1
  }
}
```

同一个 Patch 无论由前端先应用还是由服务器落盘前应用，都会得到相同的 `geometry.components` 结果。

## 服务器存储与会话摘要

- 服务器仍保存语义 Blueprint，不保存浏览器缓存状态。
- REST `PUT /api/scenes/{filename}` 会原样持久化 `geometry.components`。
- 场景列表构件数量现在统计基础元素与组合构件之和。
- 前端会话卡片统计同步包含组合构件。
- 发送给 Agent 的场景摘要会列出组件 ID、类型和关键依附信息。

## 兼容性

- 旧 Blueprint 没有 `components` 时，编译器直接透传。
- 旧 ScenePatch 操作完全不变。
- 组合构件只在适配层展开，不会改变 Core registry。
- 编译使用 Blueprint 副本，重复重建不会把同一组件的子元素重复追加。

## 集成测试

`check:compiler` 已增加真实链路覆盖：

1. 使用 `parseWildBlueprint()` 解析含组件的 Blueprint。
2. 确认解析后仍保留三个语义组件。
3. 使用 `reconstructWildEntity()` 完成编译和 Core 重建。
4. 检查渲染网格中存在门洞、侧墙窗框和栏杆横杆的确定性 ID。
5. 检查没有 error 级诊断。
6. 检查 ScenePatch 的组件新增、修改和删除。

当前结果：

```text
Component compiler check passed: door, window, railing.
```

## 阶段结果

组合构件已经进入真实加载、渲染、会话保存和增量修改链路。下一阶段将完成正式 JSON Schema、后端工具校验、Agent Prompt、知识库边界和全量回归验证。
