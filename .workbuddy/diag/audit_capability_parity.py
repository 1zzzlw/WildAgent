# -*- coding: utf-8 -*-
"""能力对齐审计：schema / 引擎 / 生成侧派发 / 能力缺口声明 / KB 能力分片 的口径比对。

为什么需要它
------------
`furniture` 曾在多处都是"合法且已实现"：`schema.json::$defs`、`wild-core` 的
primitive 注册表、KB 的 `VALID_ELEMENT_TYPES` 与 `capability-boundaries.md`。
但生成侧 `COMPONENT_REGISTRY` 里没有它，于是**能力存在却永远不派发** ——
用户说"要家具"，模型再懂也生不出来（没有人负责生产）。

这类矛盾靠人眼翻几个文件发现不了，所以做成脚本，退出码即结论。
⚠️ 本脚本第一版写了 `_SKELETON_ONLY` 白名单把 furniture 排除了，于是"全绿"——
   而 furniture 恰恰就是它该抓的那个 case。**白名单是审计脚本的毒药**，
   现在改成"从各层真实注册点导出集合"，不写例外。

plan 驱动链改造后的五层口径（《动态节点设计规划》§2.4 / §8.2 / §9.1）

| 层 | 来源 | 语义 |
| --- | --- | --- |
| ① schema | `wild-core/schema.json` | 蓝图里合法的元素与组合构件类型 |
| ② 引擎 | `wild-core/src/primitive/registry.ts` | wild-core 真的能重建出网格 |
| ③ 生成侧 | `COMPONENT_REGISTRY` + 骨架直出 | 谁负责生产它 |
| ④ 缺口声明 | `app/agent/plan/capability.py::CAPABILITY_GAPS` | 主链**声明**做不到的能力 |
| ⑤ 知识分片 | `storage/knowledge_base/knowledge/components/*.md` | §2.4 的开集来源（下沉进度） |

**判定依据**：合法且引擎已实现，却被声明做不到 → 能力误判；合法且引擎已实现，
却既无生产者也不在缺口声明里 → 无生产者。两者都不是"缺口"，是矛盾。

用法
----
    python .workbuddy/diag/audit_capability_parity.py          # 人类可读
    python .workbuddy/diag/audit_capability_parity.py --json   # 机器可读
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / 'wild-core' / 'schema.json'
CORE_REGISTRY = REPO / 'wild-core' / 'src' / 'primitive' / 'registry.ts'
GEN_COMPONENTS = REPO / 'wild-server' / 'app' / 'agent' / 'generation' / 'components.py'
GEN_SKELETON = REPO / 'wild-server' / 'app' / 'agent' / 'generation' / 'architecture' / 'skeleton.py'
#: plan 链里"已知做不到"的唯一声明处（`_UNSUPPORTED_INTERIOR_TERMS` 已并入此表）。
CAPABILITY = REPO / 'wild-server' / 'app' / 'agent' / 'plan' / 'capability.py'
PROFILE = REPO / 'wild-server' / 'app' / 'agent' / 'generation' / 'architecture' / 'profile.py'
OBJECT_SUBTYPES = REPO / 'wild-server' / 'app' / 'agent' / 'generation' / 'objects' / 'subtypes.py'
KB_COMPONENTS = REPO / 'wild-server' / 'storage' / 'knowledge_base' / 'knowledge' / 'components'


def read(path: Path) -> str:
    return io.open(path, encoding='utf-8').read()


def camel_to_snake(name: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def schema_contract() -> tuple[set[str], set[str]]:
    """(schema 声明的元素类型, schema 声明的组合构件类型)"""
    defs = json.loads(read(SCHEMA)).get('$defs', {})
    elements: set[str] = set()
    for name, spec in defs.items():
        const = (spec.get('properties', {}) or {}).get('type', {}).get('const')
        if isinstance(const, str):
            elements.add(const)
        elif name.endswith('Component'):
            elements.add(camel_to_snake(name[: -len('Component')]))
    comps = {camel_to_snake(n[: -len('Component')]) for n in defs if n.endswith('Component')}
    return elements, comps


def engine_types() -> set[str]:
    """wild-core primitive 注册表里 `type: 'x'` 且带 build 的条目。"""
    text = read(CORE_REGISTRY)
    return set(re.findall(r"\{\s*type:\s*'([a-z_]+)'\s*,\s*status:\s*'[a-z]+'", text))


def dispatched_types() -> set[str]:
    """生成侧真正会派发 generate 条目的组件（`COMPONENT_REGISTRY` 顶层键）。

    新链里这就是"谁能被 plan 展开"的唯一来源：`strategy.capability_catalog()` 直接读它，
    所以**这里少了什么，`plan` 就永远看不到什么**。
    """
    text = read(GEN_COMPONENTS)
    block = text[text.index('COMPONENT_REGISTRY'):]
    return set(re.findall(r'^\s{4}"([a-z_]+)":\s*ComponentConfig\(', block, re.M))


def skeleton_emitted(schema_all: set[str]) -> set[str]:
    """骨架阶段直接写进 elements 的类型（第二个产出源，别漏）。

    骨架不是组件注册表，所以只看 COMPONENT_REGISTRY 会把 wall/floor/column/beam/stair
    全判成"无生产者"——第一版就是这么误报的。只保留 schema 里合法的名字，
    避免把 `"type": "building"` 这类描述性字段当成元素类型。
    """
    found = set(re.findall(r'"type":\s*"([a-z_]+)"', read(GEN_SKELETON)))
    return found & schema_all


def engine_internal(schema_all: set[str], engine: set[str], producers: set[str],
                    comps: set[str], gap_types: set[str]) -> set[str]:
    """引擎能重建、但**生成链不负责**的元素类型（只报告，不判失败）。

    判定是**推导**出来的，不是列举白名单：除去组合构件、骨架直出、注册表派发与缺口声明
    之后剩下的，就是 ``opening`` / ``primitive`` / ``body`` / ``dense_brick`` 这一类
    —— 它们是**编译器产出**（`wild-core/src/compiler/**` 里实际构造 primitive/opening）
    或编辑器手工类型，用户不会向 agent 直接索要。把它们藏起来才是审计脚本的错，
    所以单独打印出来。
    """
    return (schema_all & engine) - producers - comps - gap_types


def declared_gaps() -> dict[str, str]:
    """`CAPABILITY_GAPS` 声明的缺口：构件类缺口 → {目标类型: 缺口 id}。

    只有 `target` 形如 ``component.<x>`` 的条目才映射到某个类型；``architecture.*``
    这类是阶段级缺口（室内平面、场地语义），没有对应的可派发构件，不参与本比对。
    """
    text = read(CAPABILITY)
    block = text[text.index('CAPABILITY_GAPS'):]
    out: dict[str, str] = {}
    for m in re.finditer(
        r'CapabilityGap\(\s*id="([a-z_]+)".*?target="([a-z_.]+)"', block, re.S
    ):
        gap_id, target = m.group(1), m.group(2)
        if target.startswith('component.'):
            out[target.split('.', 1)[1]] = gap_id
    return out


def kb_shards() -> dict[str, str]:
    """KB 里的**构件专属**能力分片：entity_type → status（§2.4 的开集来源）。

    只收 `doc_type: component` + `knowledge_role: capability` 且 `entity_type` 是具体
    构件名的文件；聚合文档（`entity_type: component`）不构成某个 kind 的分片。
    """
    out: dict[str, str] = {}
    if not KB_COMPONENTS.is_dir():
        return out
    for path in sorted(KB_COMPONENTS.glob('*.md')):
        text = read(path)
        head = text.split('---', 2)[1] if text.startswith('---') else ''
        if 'doc_type: component' not in head or 'knowledge_role: capability' not in head:
            continue
        m = re.search(r'^entity_type:\s*(\S+)', head, re.M)
        if not m or m.group(1) in {'component', 'facade'}:
            continue
        status = re.search(r'^status:\s*(\S+)', head, re.M)
        out[m.group(1)] = status.group(1) if status else 'unknown'
    return out


def object_chain_types() -> set[str]:
    """**物件链专用**的构件类型（`objects/subtypes.py::OBJECT_COMPONENT_KINDS`）。

    它们的配额来自物件方案（`ObjectDecisions.objects[].kind`），不来自
    `profile.base_components` 或 `_DETAIL_COMPONENT_QUOTAS` —— 建筑侧的"默认配额"
    对它们没有意义：物件场景里没有墙可挂门窗，也没有"默认该配几个"这回事。

    所以 ⑤ 项要排除它们。**不是白名单**：集合是从源码常量里读出来的，
    以后新增一条物件通道会自动跟着变，不需要回来改这个脚本。
    """

    text = read(OBJECT_SUBTYPES)
    block = re.search(r'OBJECT_COMPONENT_KINDS[^=]*=\s*\(([^)]*)\)', text, re.S)
    return set(re.findall(r'"([a-z_]+)"', block.group(1))) if block else set()


def detail_quotas() -> set[str]:
    text = read(PROFILE)
    m = re.search(r'_DETAIL_COMPONENT_QUOTAS[^=]*=\s*\{(.*?)\n\}', text, re.S)
    return set(re.findall(r'^\s{4}"([a-z_]+)":\s*\{', m.group(1), re.M)) if m else set()


def architecture_profiles() -> dict[str, list[str]]:
    text = read(PROFILE)
    body = text[text.index('_ARCHITECTURE_PROFILES'):]
    # 每个 profile 从 "    \"id\": {" 开始，到下一个同级键或块结束
    out: dict[str, list[str]] = {}
    for m in re.finditer(r'^\s{4}"([a-z_]+)":\s*\{', body, re.M):
        seg = body[m.end():]
        nxt = re.search(r'^\s{4}"[a-z_]+":\s*\{', seg, re.M)
        seg = seg[: nxt.start()] if nxt else seg
        bm = re.search(r'"base_components":\s*\[([^\]]*)\]', seg)
        if bm:
            out[m.group(1)] = re.findall(r'"([a-z_]+)"', bm.group(1))
    return out


def main() -> int:
    schema_all, schema_comps = schema_contract()
    engine = engine_types()
    dispatched = dispatched_types()
    skeleton = skeleton_emitted(schema_all)
    gaps = declared_gaps()
    shards = kb_shards()
    quotas = detail_quotas()
    bases = architecture_profiles()
    object_kinds = object_chain_types()

    # 缺口声明里的类型名：它们被显式宣称为"做不到"，所以不参与"无生产者"判定。
    gap_types = set(gaps)
    implemented = schema_all | engine
    producers = dispatched | skeleton
    internal = engine_internal(schema_all, engine, producers, schema_comps, gap_types)
    issues: list[tuple[str, str, str]] = []

    # ① 被声明"做不到"，但 schema 合法且引擎已实现 → 能力误判（这是 furniture 的老 case）
    for t in sorted(gap_types & implemented):
        issues.append((
            '误判缺失', t,
            'schema 合法且 wild-core 已实现（%s），却被 plan/capability.py 的 %r 声明为做不到'
            % ('注册于 primitive registry' if t in engine else '仅在 schema', gaps[t]),
        ))

    # ② schema 声明的组合构件，注册表里没有派发 → 派发不到
    for t in sorted(schema_comps - dispatched - gap_types):
        issues.append(('无法派发', t, 'schema 定义了该组合构件，但 COMPONENT_REGISTRY 里没有'))

    # ③ 注册表可派发，schema 却没定义 → 幽灵构件
    for t in sorted(dispatched - schema_all):
        issues.append(('幽灵构件', t, '注册表可派发，但 schema 里没有对应类型定义'))

    # ④ KB 分片说"不支持"，生成侧却在派发 → 知识库与代码互相打脸
    for t in sorted(dispatched & {k for k, v in shards.items() if v == 'unsupported'}):
        issues.append((
            '分片冲突', t,
            'KB 的 %s.md 标 status: unsupported，但 COMPONENT_REGISTRY 会派发它' % t,
        ))

    # ⑤ 引擎实现但无任何默认配额 → 只能靠模型点名（只查"构件类"，骨架元素不受配额管辖）
    #    物件链专用通道另算：它们的派发由物件方案的 kind 决定，见 object_chain_types()。
    for t in sorted((dispatched | schema_comps) - quotas - object_kinds):
        if any(t in v for v in bases.values()):
            continue
        issues.append((
            '无默认配额', t,
            '不在任何 profile.base_components，也不在 _DETAIL_COMPONENT_QUOTAS → 除非用户点名，否则不生成',
        ))

    # 下沉进度（§2.4）：可派发的 kind 里有多少已经有专属 KB 能力分片。
    # 这是 P2 的进度指标，**不作为失败**——分片缺失不会让 agent 生错东西，
    # 只是字段约束还得靠代码里的兜底规则。
    covered = sorted(dispatched & set(shards))
    uncovered = sorted(dispatched - set(shards))

    payload = {
        'schema_elements': sorted(schema_all),
        'schema_components': sorted(schema_comps),
        'engine_implemented': sorted(engine),
        'generation_dispatched': sorted(dispatched),
        'skeleton_emitted': sorted(skeleton),
        'declared_gaps': gaps,
        'kb_capability_shards': shards,
        'detail_quotas': sorted(quotas),
        'object_chain_types': sorted(object_kinds),
        'architecture_profiles': bases,
        'issues': [{'kind': k, 'type': t, 'detail': d} for k, t, d in issues],
    }

    if '--json' in sys.argv:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1 if issues else 0

    print('① schema 元素类型   %2d：%s' % (len(schema_all), ', '.join(sorted(schema_all))))
    print('② schema 组合构件   %2d：%s' % (len(schema_comps), ', '.join(sorted(schema_comps))))
    print('③ 引擎 primitive    %2d：%s' % (len(engine), ', '.join(sorted(engine))))
    print('④ 生成侧可派发      %2d：%s' % (len(dispatched), ', '.join(sorted(dispatched))))
    print('⑤ 骨架阶段直出      %2d：%s' % (len(skeleton), ', '.join(sorted(skeleton))))
    print('⑥ 声明做不到的构件  %2d：%s' % (len(gaps), ', '.join(f'{k}({v})' for k, v in sorted(gaps.items())) or '（无）'))
    print('⑦ 细部默认配额      %2d：%s' % (len(quotas), ', '.join(sorted(quotas))))
    print('⑧ KB 专属能力分片   %2d：%s' % (len(shards), ', '.join(f'{k}={v}' for k, v in sorted(shards.items())) or '（无）'))
    print('   引擎内部类型（编译器产出／编辑器手工，非生成链职责，不作为失败）：%s'
          % (', '.join(sorted(internal)) or '（无）'))
    print('   物件链专用通道（配额来自物件方案的 kind，不受建筑默认配额管辖）：%s'
          % (', '.join(sorted(object_kinds)) or '（无）'))
    print('   下沉进度：可派发 %d 类，其中 %d 类已有专属分片，%d 类仍靠代码兜底（§2.4，P2 进度，不作为失败）'
          % (len(dispatched), len(covered), len(uncovered)))
    if uncovered:
        print('   仍靠代码兜底：%s' % ', '.join(uncovered))
    for pid, comps in bases.items():
        print('   %-24s base_components = %s' % (pid, comps))
    print()

    if not issues:
        print('✅ 五层口径一致，没有能力误判')
        return 0

    print('发现 %d 处能力口径不一致：' % len(issues))
    for kind, t, detail in issues:
        print('  [%s] %-10s %s' % (kind, t, detail))
    return 1


if __name__ == '__main__':
    sys.exit(main())
