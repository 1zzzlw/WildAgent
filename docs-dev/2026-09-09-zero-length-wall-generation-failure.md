# 零长度墙体导致组件全被拒绝的生成故障

请求：`req_1788922258743_zkvy9h23h`；会话：`session_1788879630652`；用户输入：生成一个别墅。

## 确认证据

- 从会话 JSON、RAGTrace 和只读 SQLite checkpoint 对齐同一请求。新 rules-v2 过滤已出现在真实检索记录中；本次并非没有运行到组件节点。
- checkpoint 的 skeleton_blueprint 有 8 面墙，其 XZ 起终点相同。以 wall_front_1 为例，from=[0,0,0]、to=[0,3,0]，水平长度为 0，高度为 3；墙不能承载门窗。
- 旧骨架检查将角点墙组算成 4 个体量，meets_target=true；尺寸检查只报告长度警告，所以后续节点继续执行。
- door_gen 生成 1 个门，window_gen 生成 16 个窗；各自校验后 rejected_fragment_count 为 1 和 16，最终 fragment_count 均为 0。只有屋顶片段进入合并。
- architecture_plan 中存在 sunshade 最小数量 2，但当前注册表中没有 sunshade，required_components 也不包含它。此前配额和派发采用了不同的允许范围。
- 补墙使用修改前收集的孤立端点，添加墙段后未重新判断剩余端点，导致同一段重复补建；旧结构质量结果也未在补墙后及时刷新。

## 修复

1. 所有复杂度等级都检查墙体水平长度，退化墙无法通过骨架门禁。已有确定性生成器依据已选方案重建，再次检查失败就停止组件派发；不按案例坐标猜测墙体。
2. 空间尺寸检查将零水平长度提升为错误。补墙工具拒绝使用这些退化墙猜测新墙。
3. 建筑方案的可执行配额与派发共同使用组件注册表。模型提出的未知类型记录在 unsupported_component_types，并提示能力限制，不自动伪装成另一种已实现构件。
4. 补建每段墙前重新检查当前连接，防止一次或多次修复重复加墙；补墙后重新执行模型结构质量检查。

## 验证边界

真实失败状态提取为 tests/fixtures/degenerate_wall_hosts.json，只用于回归，不进入知识库。测试覆盖三个复杂度等级、两种平面尺寸、未知配额、重建后门窗槽位数量和宿主范围、补墙幂等性。

隔离 loguru 和 LangChain @tool 包装后，实际建筑方案、空间校验和新增回归共 75 项通过；未替换几何算法或 Blueprint 输入。另增加了骨架节点的异步恢复回归，正常环境执行命令见下方。

本机正常 Python 导入仍受到 WinError 10106 阻断，因此完整 LangGraph、真实模型调用和渲染尚未重新验证。历史失败会话与检查点保持不变；此次没有把离线重建样本发布到场景。

```powershell
# 在 wild-server 目录运行
& .venv/Scripts/python.exe -X utf8 -m pytest tests/validators/test_wall_host_regression.py tests/validators/test_spatial_validation.py tests/components/test_architecture_plan.py tests/repair/test_skeleton_blueprint_recovery.py tests/validators/test_validation_pipeline_repairs.py -q
```

后续排查方法见 [生成失败记录排查](../docs/agent/生成失败记录排查.md)。
