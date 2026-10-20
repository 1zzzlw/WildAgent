# 设计事实重构：用了什么

最终范围按用户最新指令收敛为设计图纸和 architecture 节点。后续节点不再查看或修改；不执行测试，模型效果由用户测试。

## 设计依据

- ../汀院别墅-过程证据/01-设计事实.json：体量、楼面、房间、动线与材料角色的原始决定。
- ../汀院别墅-过程证据/02-生成汀院别墅.py：核对原事实文件中没有显式保留的门窗、家具和局部构造决定。
- ../汀院别墅-Codex.wild：读取实体位置、尺寸、材料及方向，将其转写成新版示例。原 WILD 和作者脚本未改。
- 新样例把原材料名称补成中文材质描述，角度保留两位小数供阅读；未重新编译为 WILD，也未声称逐项渲染等价。

## 实现依据

- app/design 原字段定义、contracts、坐标/解析职责与新 facts.py、resolve_facts.py：区分设计输入和程序结果。
- app/agent/generation/architecture 的 workflow.py、design_workflow.py、profile.py、__init__.py：替换设计起草和校验路径，沿用固定粒度说明。
- app/agent/prompts/planning.py：只替换 build_architecture_plan_prompt，其他提示词保留。
- app/agent/state.py、runtime 入口、app/llm/client.py、invocation.py、errors.py、app/utils/json_extractor.py：沿用 State、回调、模型调用、用量、错误和 JSON 提取接口。
- AGENTS.md / 用户给出的行为约束、.codex/skills/building-blueprint-diagnostics/SKILL.md：控制改动范围，保留可追溯原因，避免案例规则堆积。
- C:/Users/Administrator/.codex/memories/MEMORY.md：仅回顾脏工作区保留、通用根因和用户保留测试等协作约束，不用作建筑设计知识。

## 工具与过程

- PowerShell：rg 定位、Get-Content 读取、git status 查看现有改动；未清理、提交或推送。
- Node REPL：文件快照、SHA-256、原 WILD 到新版示例的数据转写、生成源码补丁与记录文件。
- apply_patch：更新设计类型、派生函数、architecture、对应提示词及本轮说明。
- 起初记录了 199 个 app Python 文件的指纹；指纹统计不表示逐一阅读了全部源码。扩大范围的早期分析曾查看其他节点接口，随后按用户最新指令停止；最终不迁移这些节点。
- 早期曾运行 Python 离线字段回归，40 项通过，见 02-首轮回归.json。用户指定不测试后没有再运行；该结果不覆盖随后重写的 architecture，旧协议的节点测试仍待迁移。
- 没有联网检索、知识库检索、真实模型调用、服务启动或新 WILD 生成。追踪 helper 位于 app.rag.trace，不等于执行 RAG 检索。

## 文件记录

- 00-旧建筑字段.py：重构前的字段快照。
- 00-源码指纹.json：开始时的 app 源码指纹，区别原有脏改动和本轮工作。
- 01-设计节点修改前.py / 01-设计起草修改前.py / 01-提示词修改前.py：替换前的直接依据。
- 02-首轮回归.json：历史检查结果，保留原记录，不代表新版节点已验证。
- 03-本轮修改与范围.json：本轮源码路径、指纹、输出协议与未验证边界。

当前新设计路径是：固定粒度与 Schema → 模型事实 JSON → 字段/引用/参数校验和程序推导。旧分块、补丁、模型程序和旧图纸投影已从这条路径移除；旧链路其他文件未借机清理。

局限：矩形体量，直梯或等高双跑 U/L 梯；无曲线体量、旋梯或非等高分跑的实现承诺。当前校验不覆盖完整动线可达性、跨体量接合围护消解、所有通高窗与楼板交叉关系或局部配方实现。列出的复核清单不是已经完成的验证。
