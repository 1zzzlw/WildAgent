# -*- coding: utf-8 -*-
"""在 lantu 蓝图副本里插入 furniture / light，验证引擎能否真正重建。

不改原蓝图；产物写到 .workbuddy/diag/probe_furniture.wild。
"""
import io
import json

SRC = r'E:\AgentProject\WildAgent\wild-web\lantu\modern_pool_villa.wild'
DST = r'E:\AgentProject\WildAgent\.workbuddy\diag\probe_furniture.wild'

bp = json.load(io.open(SRC, encoding='utf-8'))

# 露台顶面 = deck_pool_side.from[1] + thickness = -0.2 + 0.2 = 0.0
DECK_Y = 0.0

new_elements = [
    # ── 泳池右侧的两张躺椅（用 chair 近似：宽 0.62 / 深 1.85 / 高 0.42）──
    {
        'type': 'furniture', 'id': 'lounger_a', 'subtype': 'chair',
        'position': [16.0, DECK_Y, -3.7], 'rotation': [0, -1.5708, 0],
        'dimensions': {'width': 0.62, 'depth': 1.85, 'height': 0.42},
        'material': 'wood_slat',
    },
    {
        'type': 'furniture', 'id': 'lounger_b', 'subtype': 'chair',
        'position': [16.0, DECK_Y, -5.5], 'rotation': [0, -1.5708, 0],
        'dimensions': {'width': 0.62, 'depth': 1.85, 'height': 0.42},
        'material': 'wood_slat',
    },
    # ── 正立面落地门前的餐桌 + 四把椅子 ──
    {
        'type': 'furniture', 'id': 'dining_table', 'subtype': 'table',
        'position': [8.6, DECK_Y, -1.5],
        'dimensions': {'width': 1.7, 'depth': 0.9, 'height': 0.75},
        'material': 'wood_slat',
    },
    {
        'type': 'furniture', 'id': 'dining_chair_n1', 'subtype': 'chair',
        'position': [7.9, DECK_Y, -1.15], 'rotation': [0, 3.1416, 0],
        'dimensions': {'width': 0.45, 'depth': 0.5, 'height': 0.85},
        'material': 'wood_slat',
    },
    {
        'type': 'furniture', 'id': 'dining_chair_n2', 'subtype': 'chair',
        'position': [9.3, DECK_Y, -1.15], 'rotation': [0, 3.1416, 0],
        'dimensions': {'width': 0.45, 'depth': 0.5, 'height': 0.85},
        'material': 'wood_slat',
    },
    {
        'type': 'furniture', 'id': 'dining_chair_f1', 'subtype': 'chair',
        'position': [7.9, DECK_Y, -1.85],
        'dimensions': {'width': 0.45, 'depth': 0.5, 'height': 0.85},
        'material': 'wood_slat',
    },
    {
        'type': 'furniture', 'id': 'dining_chair_f2', 'subtype': 'chair',
        'position': [9.3, DECK_Y, -1.85],
        'dimensions': {'width': 0.45, 'depth': 0.5, 'height': 0.85},
        'material': 'wood_slat',
    },
    # ── 一盏落地灯，验证 lamp 子型 ──
    {
        'type': 'furniture', 'id': 'floor_lamp', 'subtype': 'lamp',
        'position': [5.2, DECK_Y, -1.2],
        'dimensions': {'width': 0.42, 'depth': 0.42, 'height': 1.55},
        'material': 'wood_slat',
    },
]

ids = {e['id'] for e in bp['geometry']['elements']}
assert not any(e['id'] in ids for e in new_elements), 'id 撞车'
bp['geometry']['elements'].extend(new_elements)

io.open(DST, 'w', encoding='utf-8', newline='\n').write(
    json.dumps(bp, ensure_ascii=False, indent=2)
)
print('写入', DST)
print('elements %d → %d' % (len(ids), len(bp['geometry']['elements'])))
from collections import Counter
print(Counter(e['type'] for e in bp['geometry']['elements']))
