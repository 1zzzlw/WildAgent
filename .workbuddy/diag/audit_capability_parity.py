# -*- coding: utf-8 -*-
"""能力对齐审计：schema / 引擎 / KB 声明的能力 vs 流水线真的会派发的能力。

为什么需要它
------------
`furniture` 在四处都是"合法且已实现"：`schema.json::$defs`、`wild-core` 的
primitive 注册表、KB 的 `VALID_ELEMENT_TYPES` 与 `capability-boundaries.md`。
但生成侧 `COMPONENT_REGISTRY` 里没有它，验收侧 `_UNSUPPORTED_COMPONENT_ALIASES`
还把它判成"不支持"。结果是**能力存在却永远不派发** —— 用户说"要家具"，
模型再懂也生不出来（没有人负责生产），只会拿到一条 warning。

这类矛盾靠人眼翻四个文件发现不了，所以做成脚本，退出码即结论。
⚠️ 本脚本第一版写了 `_SKELETON_ONLY` 白名单把 furniture 排除了，于是"全绿"——
   而 furniture 恰恰就是它该抓的那个 case。**白名单是审计脚本的毒药**，
   现在改成"从各层真实注册点导出集合"，不写例外。

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
REQUIREMENTS = REPO / 'wild-server' / 'app' / 'agent' / 'planning' / 'requirements.py'
PROFILE = REPO / 'wild-server' / 'app' / 'agent' / 'generation' / 'architecture' / 'profile.py'


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
    """生成侧真正会派发节点的组件（COMPONENT_REGISTRY 顶层键）。"""
    text = read(GEN_COMPONENTS)
    block = text[text.index('COMPONENT_REGISTRY'):]
    return set(re.findall(r'^\s{4}"([a-z_]+)":\s*ComponentConfig\(', block, re.M))


def skeleton_emitted() -> set[str]:
    """骨架阶段直接写进 elements 的类型（第三个产出源，别漏）。

    骨架不是组件注册表，所以只看 COMPONENT_REGISTRY 会把 wall/floor/column/beam/stair
    全判成"无生产者"——第一版就是这么误报的。
    """
    return set(re.findall(r'"type":\s*"([a-z_]+)"', read(GEN_SKELETON)))


def declared_unsupported() -> set[str]:
    text = read(REQUIREMENTS)
    m = re.search(r'_UNSUPPORTED_COMPONENT_ALIASES\s*=\s*\{(.*?)\n\}', text, re.S)
    return set(re.findall(r'"([a-z_]+)":\s*\(', m.group(1))) if m else set()


def detail_quotas() -> set[str]:
    text = read(PROFILE)
    m = re.search(r'_DETAIL_COMPONENT_QUOTAS[^=]*=\s*\{(.*?)\n\}', text, re.S)
    return set(re.findall(r'^\s{4}"([a-z_]+)":\s*\{', m.group(1), re.M)) if m else set()


def architecture_profiles() -> dict[str, list[str]]:
    text = read(PROFILE)
    start = text.index('_ARCHITECTURE_PROFILES')
    body = text[start:]
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
    skeleton = skeleton_emitted()
    unsupported = declared_unsupported()
    quotas = detail_quotas()
    bases = architecture_profiles()

    implemented = schema_all | engine
    producers = dispatched | skeleton
    issues: list[tuple[str, str, str]] = []

    # ① 被声明"不支持"，但 schema 合法且引擎已实现 → 能力误判
    for t in sorted(unsupported & implemented):
        issues.append((
            '误判缺失', t,
            'schema 合法且 wild-core 已实现（%s），却被 requirements.py 判为 unsupported_capability'
            % ('注册于 primitive registry' if t in engine else '仅在 schema'),
        ))

    # ② schema 声明、引擎实现，但既非骨架直出、也无组件派发 → 永远不产出
    for t in sorted((schema_all & engine) - producers - unsupported):
        issues.append((
            '无生产者', t,
            '合法元素类型且引擎可重建，但骨架阶段不产出、组件注册表也不派发 → 除非模型自己写进 elements，否则永不出现',
        ))

    # ③ schema 声明的组合构件，注册表里没有 → 派发不到
    for t in sorted(schema_comps - dispatched - unsupported):
        issues.append(('无法派发', t, 'schema 定义了该组合构件，但 COMPONENT_REGISTRY 里没有'))

    # ④ 注册表可派发，schema 却没定义 → 幽灵构件
    for t in sorted(dispatched - schema_all):
        issues.append(('幽灵构件', t, '注册表可派发，但 schema 里没有对应类型定义'))

    # ⑤ 引擎实现但无任何默认配额 → 只能靠模型点名（只查"构件类"，骨架元素不受配额管辖）
    for t in sorted((dispatched | schema_comps) - quotas):
        if any(t in v for v in bases.values()):
            continue
        issues.append((
            '无默认配额', t,
            '不在任何 profile.base_components，也不在 _DETAIL_COMPONENT_QUOTAS → 除非用户点名，否则不生成',
        ))

    payload = {
        'schema_elements': sorted(schema_all),
        'schema_components': sorted(schema_comps),
        'engine_implemented': sorted(engine),
        'generation_dispatched': sorted(dispatched),
        'skeleton_emitted': sorted(skeleton),
        'declared_unsupported': sorted(unsupported),
        'detail_quotas': sorted(quotas),
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
    print('⑥ 声明不支持        %2d：%s' % (len(unsupported), ', '.join(sorted(unsupported)) or '（无）'))
    print('⑦ 细部默认配额      %2d：%s' % (len(quotas), ', '.join(sorted(quotas))))
    for pid, comps in bases.items():
        print('   %-24s base_components = %s' % (pid, comps))
    print()

    if not issues:
        print('✅ 四层口径一致，没有能力误判')
        return 0

    print('发现 %d 处能力口径不一致：' % len(issues))
    for kind, t, detail in issues:
        print('  [%s] %-10s %s' % (kind, t, detail))
    return 1


if __name__ == '__main__':
    sys.exit(main())
