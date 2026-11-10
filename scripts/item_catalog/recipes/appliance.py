"""家电与设备：冰箱、冰柜、微波炉、烤箱、空调、吊扇、健身器材、安防小件。

这批大多是"箱体 + 一个特征面（门/格栅/屏/旋钮）"，所以用一个 `_box_unit`
族函数统一表达；特征面决定了它读起来是冰箱还是微波炉。
"""

from __future__ import annotations

import math

from ..dsl import PI, box, cyl, legs4, sphere
from .registry import item


def _box_unit(
    width: float,
    depth: float,
    height: float,
    *,
    body: str = "stone",
    door_split: float | None = None,
    handle: bool = True,
    plinth: float = 0.03,
    knobs: int = 0,
) -> list[dict]:
    """立式箱体。`door_split` 是门的水平分缝高度（None 表示单门通高）。"""

    body_h = height - plinth
    parts: list[dict] = [box("body", (width, body_h, depth), (0, plinth + body_h / 2, 0), body)]
    front = depth / 2
    if door_split is None:
        parts.append(box("door", (width - 0.02, body_h - 0.02, 0.02), (0, plinth + body_h / 2, front + 0.01), body))
        if handle:
            parts.append(box("handle", (0.025, body_h * 0.35, 0.025), (width / 2 - 0.06, plinth + body_h * 0.62, front + 0.035), "metal"))
    else:
        lower_h = door_split - plinth
        upper_h = height - door_split
        parts.append(box("door_lower", (width - 0.02, lower_h - 0.01, 0.02), (0, plinth + lower_h / 2, front + 0.01), body))
        parts.append(box("door_upper", (width - 0.02, upper_h - 0.01, 0.02), (0, door_split + upper_h / 2, front + 0.01), body))
        if handle:
            parts.append(box("handle_lower", (0.022, lower_h * 0.30, 0.022), (width / 2 - 0.06, plinth + lower_h * 0.72, front + 0.035), "metal"))
            parts.append(box("handle_upper", (0.022, upper_h * 0.30, 0.022), (width / 2 - 0.06, door_split + upper_h * 0.30, front + 0.035), "metal"))
    for index in range(knobs):
        parts.append(
            cyl(f"knob_{index}", 0.018, 0.02, (-width / 2 + 0.05 + index * 0.05, height - 0.07, front + 0.012), "metal", segments=12, rot=(PI / 2, 0, 0))
        )
    return parts


@item("fridge", "冰箱", "appliance", tags=("冰箱", "冷藏", "fridge"), footprint=(0.70, 1.92, 0.72), source_item="fridge")
def build_fridge() -> list[dict]:
    """上冷藏下冷冻，中间一条横缝。"""

    return _box_unit(0.70, 0.72, 1.92, body="stone", door_split=1.25, plinth=0.02)


@item("freezer", "冰柜", "appliance", tags=("冰柜", "冷冻", "freezer"), footprint=(0.60, 0.85, 0.60), source_item="freezer")
def build_freezer() -> list[dict]:
    """卧式：矮箱体 + 顶盖 + 前格栅。"""

    width, depth, height = 0.60, 0.60, 0.85
    parts: list[dict] = [box("body", (width, height - 0.10, depth), (0, (height - 0.10) / 2 + 0.10, 0), "stone")]
    parts.append(box("lid", (width + 0.02, 0.035, depth + 0.02), (0, height - 0.02, 0), "metal"))
    parts.append(box("grille", (width - 0.10, 0.10, 0.02), (0, 0.06, depth / 2), "metal"))
    return parts


@item("microwave", "微波炉", "appliance", tags=("微波炉", "厨房", "microwave"), footprint=(0.52, 0.27, 0.41), source_item="microwave")
def build_microwave() -> list[dict]:
    """箱体 + 深色门 + 右侧控制条。"""

    width, depth, height = 0.52, 0.41, 0.27
    parts: list[dict] = [box("body", (width, height, depth), (0, height / 2, 0), "metal")]
    parts.append(box("door", (width * 0.62, height - 0.05, 0.02), (-width * 0.15, height / 2, depth / 2 + 0.01), "glass"))
    parts.append(box("panel", (width * 0.28, height - 0.06, 0.02), (width * 0.32, height / 2, depth / 2 + 0.01), "metal"))
    for index in range(3):
        parts.append(cyl(f"button_{index}", 0.012, 0.012, (width * 0.32, height * 0.72 - index * 0.045, depth / 2 + 0.025), "accent", segments=10, rot=(PI / 2, 0, 0)))
    return parts


@item("dishwasher", "洗碗机", "kitchen", tags=("洗碗机", "厨房", "dishwasher"), footprint=(0.60, 0.86, 0.58), source_item="dishwasher-movn72ls")
def build_dishwasher() -> list[dict]:
    """落地式：面板 + 顶部控制条 + 内嵌把手。"""

    width, depth, height = 0.60, 0.58, 0.86
    parts: list[dict] = [box("body", (width, height, depth), (0, height / 2, 0), "metal")]
    parts.append(box("door", (width - 0.02, height - 0.12, 0.02), (0, (height - 0.12) / 2, depth / 2 + 0.01), "metal"))
    parts.append(box("control", (width - 0.04, 0.09, 0.02), (0, height - 0.06, depth / 2 + 0.012), "accent"))
    parts.append(box("handle", (width - 0.12, 0.022, 0.022), (0, height - 0.14, depth / 2 + 0.038), "metal"))
    return parts


@item("oven", "烤箱", "kitchen", tags=("烤箱", "厨房", "oven"), footprint=(0.60, 0.60, 0.56))
def build_oven() -> list[dict]:
    parts: list[dict] = [box("body", (0.60, 0.60, 0.56), (0, 0.30, 0), "metal")]
    parts.append(box("glass", (0.52, 0.38, 0.02), (0, 0.28, 0.29), "glass"))
    parts.append(box("handle", (0.52, 0.025, 0.03), (0, 0.47, 0.30), "metal"))
    for index in range(3):
        parts.append(cyl(f"knob_{index}", 0.02, 0.018, (-0.18 + index * 0.09, 0.56, 0.29), "metal", segments=12, rot=(PI / 2, 0, 0)))
    return parts


@item("toaster", "烤面包机", "kitchen", tags=("烤面包机", "厨房", "toaster"), footprint=(0.28, 0.23, 0.17), source_item="toaster")
def build_toaster() -> list[dict]:
    parts: list[dict] = [box("body", (0.28, 0.19, 0.17), (0, 0.095, 0), "metal")]
    for index in range(2):
        parts.append(box(f"slot_{index}", (0.22, 0.012, 0.02), (0, 0.19, -0.035 + index * 0.07), "accent"))
    parts.append(box("lever", (0.018, 0.06, 0.018), (0.145, 0.12, 0), "metal"))
    return parts


@item("kettle", "电水壶", "kitchen", tags=("水壶", "厨房", "kettle"), footprint=(0.24, 0.25, 0.18), source_item="kettle")
def build_kettle() -> list[dict]:
    parts: list[dict] = [cyl("body", 0.09, 0.20, (0, 0.10, 0), "metal", radius_top=0.065, segments=24)]
    parts.append(cyl("lid", 0.062, 0.02, (0, 0.21, 0), "metal", segments=20))
    parts.append(box("handle", (0.02, 0.13, 0.05), (-0.105, 0.14, 0), "accent"))
    parts.append(box("spout", (0.06, 0.02, 0.02), (0.10, 0.18, 0), "metal", rot=(0, 0, -0.5)))
    return parts


@item("coffee_machine", "咖啡机", "kitchen", tags=("咖啡机", "厨房", "coffee"), footprint=(0.16, 0.24, 0.23), source_item="coffee-machine")
def build_coffee_machine() -> list[dict]:
    parts: list[dict] = [box("body", (0.16, 0.24, 0.23), (0, 0.12, -0.02), "metal")]
    parts.append(box("head", (0.14, 0.07, 0.10), (0, 0.20, 0.09), "metal"))
    parts.append(cyl("cup", 0.035, 0.07, (0, 0.035, 0.08), "stone", segments=16))
    return parts


@item("iron", "电熨斗", "appliance", tags=("熨斗", "家务", "iron"), footprint=(0.36, 0.24, 0.21), source_item="iron")
def build_iron() -> list[dict]:
    parts: list[dict] = [box("sole", (0.11, 0.02, 0.26), (0, 0.01, 0), "metal")]
    parts.append(box("body", (0.09, 0.06, 0.22), (0, 0.05, 0), "accent"))
    parts.append(box("handle", (0.04, 0.04, 0.16), (0, 0.11, 0.02), "metal"))
    return parts


@item("ac_outdoor", "空调外机", "appliance", tags=("空调", "外机", "ac"), footprint=(1.06, 0.95, 1.06), source_item="ac-block")
def build_ac_outdoor() -> list[dict]:
    """箱体 + 正面圆形风扇格栅 + 管线接口。"""

    width, depth, height = 1.06, 1.06, 0.95
    parts: list[dict] = [box("body", (width, height, depth), (0, height / 2, 0), "metal")]
    parts.append(cyl("fan", 0.36, 0.02, (0, height * 0.52, depth / 2 + 0.005), "accent", segments=32, rot=(PI / 2, 0, 0)))
    parts.append(cyl("ring", 0.40, 0.025, (0, height * 0.52, depth / 2 + 0.012), "metal", segments=32, rot=(PI / 2, 0, 0)))
    parts.append(cyl("pipe", 0.03, 0.30, (-width / 2 + 0.10, 0.10, -depth / 2 + 0.05), "metal", segments=10, rot=(0, 0, 0)))
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"foot_{index}", (0.08, 0.10, depth - 0.10), (sx * (width / 2 - 0.10), 0.05, 0), "metal"))
    return parts


@item("ac_wall", "壁挂空调", "appliance", tags=("空调", "挂机", "ac"), footprint=(1.56, 0.60, 0.41), source_item="air-conditioning")
def build_ac_wall() -> list[dict]:
    """横长箱体 + 底部出风条 + 右侧进风格栅。原点在底面，挂装时整体抬到墙上。"""

    width, depth, height = 1.56, 0.41, 0.30
    parts: list[dict] = [box("body", (width, height, depth), (0, height / 2 + 0.02, 0), "stone")]
    parts.append(box("louver", (width - 0.10, 0.035, 0.06), (0, 0.035, depth / 2 - 0.09), "metal"))
    parts.append(box("grille", (0.30, height - 0.10, 0.02), (width / 2 - 0.20, height / 2 + 0.02, depth / 2 + 0.005), "metal"))
    parts.append(box("panel", (0.16, 0.05, 0.02), (-width / 2 + 0.12, height * 0.62, depth / 2 + 0.005), "accent"))
    return parts


@item("ceiling_fan", "吊扇", "appliance", tags=("吊扇", "风扇", "fan"), footprint=(1.04, 0.45, 1.04), source_item="ceiling-fan")
def build_ceiling_fan() -> list[dict]:
    """吊杆 + 电机罩 + 5 片扇叶。原点在扇叶平面，挂装时上抬。"""

    parts: list[dict] = [cyl("rod", 0.018, 0.26, (0, 0.30, 0), "metal", segments=10)]
    parts.append(cyl("cap", 0.07, 0.03, (0, 0.44, 0), "metal", segments=20))
    parts.append(cyl("motor", 0.10, 0.10, (0, 0.16, 0), "metal", radius_top=0.085, segments=24))
    for index in range(5):
        angle = 2 * PI * index / 5
        parts.append(
            box(
                f"blade_{index}",
                (0.46, 0.012, 0.14),
                (0.30 * math.cos(angle), 0.15, 0.30 * math.sin(angle)),
                "wood",
                rot=(0, -angle, 0.06),
            )
        )
    parts.append(cyl("light", 0.075, 0.06, (0, 0.09, 0), "glass", segments=20))
    return parts


@item("treadmill", "跑步机", "appliance", tags=("跑步机", "健身", "treadmill"), footprint=(0.90, 1.45, 2.10), source_item="threadmill")
def build_treadmill() -> list[dict]:
    """跑带 + 侧边框 + 前立柱 + 控制台。"""

    width, depth, height = 0.90, 2.10, 1.45
    parts: list[dict] = [box("deck", (width, 0.10, depth), (0, 0.12, 0), "metal")]
    parts.append(box("belt", (width - 0.16, 0.02, depth - 0.24), (0, 0.175, 0.02), "accent"))
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"rail_{index}", (0.05, 0.06, depth), (sx * (width / 2 - 0.03), 0.20, 0), "metal"))
        parts.append(box(f"post_{index}", (0.06, height - 0.20, 0.07), (sx * (width / 2 - 0.05), (height - 0.20) / 2 + 0.20, -depth / 2 + 0.16), "metal"))

    parts.append(box("console", (width * 0.72, 0.22, 0.06), (0, height - 0.10, -depth / 2 + 0.14), "metal", rot=(-0.35, 0, 0)))
    parts.append(box("screen", (width * 0.44, 0.14, 0.008), (0, height - 0.08, -depth / 2 + 0.10), "accent", rot=(-0.35, 0, 0)))
    parts.append(cyl("roller", 0.05, width - 0.16, (0, 0.10, depth / 2 - 0.10), "metal", segments=14, rot=(0, 0, PI / 2)))
    return parts


@item("barbell_bar", "杠铃", "outdoor", tags=("杠铃", "健身", "barbell"), footprint=(1.72, 0.38, 0.38), source_item="barbell")
def build_barbell() -> list[dict]:
    """横杆 + 两侧各 3 片配重。躺在地面（Y=0 是杆底）。"""

    parts: list[dict] = [cyl("bar", 0.016, 1.72, (0, 0.19, 0), "metal", segments=14, rot=(0, 0, PI / 2))]
    for side, sx in enumerate((-1, 1)):
        for index in range(3):
            radius = 0.175 - index * 0.020
            parts.append(
                cyl(
                    f"plate_{side}_{index}",
                    radius,
                    0.035,
                    (sx * (0.62 + index * 0.04), 0.19, 0),
                    "metal",
                    segments=28,
                    rot=(0, 0, PI / 2),
                )
            )
    return parts


@item("barbell_rack", "杠铃架", "outdoor", tags=("杠铃架", "健身", "rack"), footprint=(1.34, 1.22, 1.72), source_item="barbell-stand")
def build_barbell_rack() -> list[dict]:
    """两根 A 形立柱 + 底座横杆 + 挂钩。"""

    width, depth, height = 1.34, 1.72, 1.22
    parts: list[dict] = []
    for index, sx in enumerate((-1, 1)):
        x = sx * (width / 2 - 0.10)
        parts.append(box(f"post_{index}", (0.08, height, 0.08), (x, height / 2, 0), "metal"))
        parts.append(box(f"base_f_{index}", (0.08, 0.06, depth * 0.44), (x, 0.03, depth * 0.22), "metal"))
        parts.append(box(f"base_b_{index}", (0.08, 0.06, depth * 0.44), (x, 0.03, -depth * 0.22), "metal"))
        parts.append(box(f"hook_{index}", (0.14, 0.05, 0.05), (x - sx * 0.09, height - 0.10, 0), "metal"))
    parts.append(cyl("crossbar", 0.03, width - 0.20, (0, 0.30, -depth * 0.30), "metal", segments=12, rot=(0, 0, PI / 2)))
    return parts


@item("hydrant", "消防栓", "outdoor", tags=("消防栓", "室外", "hydrant"), footprint=(0.64, 0.88, 0.64), source_item="hydrant")
def build_hydrant() -> list[dict]:
    parts: list[dict] = [cyl("body", 0.11, 0.62, (0, 0.31, 0), "accent", segments=18)]
    parts.append(cyl("cap", 0.13, 0.06, (0, 0.65, 0), "accent", radius_top=0.09, segments=18))
    parts.append(sphere("top", 0.07, (0, 0.72, 0), "accent", segments=14))
    for index, sx in enumerate((-1, 1)):
        parts.append(cyl(f"outlet_{index}", 0.045, 0.10, (sx * 0.14, 0.48, 0), "metal", segments=12, rot=(0, 0, PI / 2)))
    parts.append(cyl("base", 0.15, 0.05, (0, 0.025, 0), "metal", segments=18))
    return parts


@item("fire_extinguisher", "灭火器", "appliance", tags=("灭火器", "消防", "extinguisher"), footprint=(0.16, 0.50, 0.16))
def build_fire_extinguisher() -> list[dict]:
    parts: list[dict] = [cyl("tank", 0.075, 0.40, (0, 0.21, 0), "accent", segments=18)]
    parts.append(cyl("neck", 0.025, 0.05, (0, 0.43, 0), "metal", segments=12))
    parts.append(box("handle", (0.05, 0.03, 0.10), (0, 0.47, 0.01), "metal"))
    parts.append(cyl("hose", 0.012, 0.14, (0.06, 0.36, 0.02), "metal", segments=8, rot=(0.4, 0, 0.3)))
    return parts


@item("electric_panel", "配电箱", "appliance", tags=("配电箱", "电气", "panel"), footprint=(0.40, 0.98, 0.11), source_item="electric-panel")
def build_electric_panel() -> list[dict]:
    """壁挂箱体 + 门 + 一排断路器。原点在底边，挂装时整体抬升。"""

    width, depth, height = 0.40, 0.11, 0.98
    parts: list[dict] = [box("body", (width, height, depth), (0, height / 2, 0), "metal")]
    parts.append(box("door", (width - 0.02, height - 0.02, 0.015), (0, height / 2, depth / 2 + 0.007), "metal"))
    for index in range(6):
        parts.append(box(f"breaker_{index}", (0.035, 0.10, 0.02), (-0.14 + index * 0.055, height * 0.62, depth / 2 + 0.017), "accent"))
    return parts


@item("ev_charger", "充电桩", "appliance", tags=("充电桩", "电动车", "ev"), footprint=(0.29, 0.65, 0.17), source_item="ev-wall-charger")
def build_ev_charger() -> list[dict]:
    parts: list[dict] = [box("body", (0.24, 0.42, 0.14), (0, 0.44, 0), "metal")]
    parts.append(box("screen", (0.14, 0.09, 0.006), (0, 0.50, 0.073), "accent"))
    parts.append(cyl("cable", 0.016, 0.55, (0.10, 0.30, 0.10), "metal", segments=8, rot=(0.5, 0, 0.2)))
    parts.append(box("post", (0.06, 0.24, 0.06), (0, 0.12, 0), "metal"))
    return parts


@item("thermostat", "温控面板", "appliance", tags=("温控", "面板", "thermostat"), footprint=(0.10, 0.10, 0.02), source_item="thermostat")
def build_thermostat() -> list[dict]:
    parts: list[dict] = [cyl("plate", 0.05, 0.018, (0, 0.05, 0), "metal", segments=24, rot=(PI / 2, 0, 0))]
    parts.append(cyl("screen", 0.038, 0.006, (0, 0.05, 0.012), "accent", segments=24, rot=(PI / 2, 0, 0)))
    return parts


@item("alarm_keypad", "报警键盘", "appliance", tags=("报警", "键盘", "alarm"), footprint=(0.18, 0.13, 0.03), source_item="alarm-keypad")
def build_alarm_keypad() -> list[dict]:
    parts: list[dict] = [box("body", (0.18, 0.13, 0.028), (0, 0.065, 0), "metal")]
    parts.append(box("screen", (0.14, 0.03, 0.006), (0, 0.105, 0.016), "accent"))
    for row in range(3):
        for col in range(4):
            parts.append(box(f"key_{row}_{col}", (0.026, 0.018, 0.006), (-0.054 + col * 0.036, 0.062 - row * 0.026, 0.016), "metal"))
    return parts


@item("smoke_detector", "烟雾报警器", "appliance", tags=("烟感", "消防", "smoke"), footprint=(0.16, 0.05, 0.16), source_item="smoke-detector")
def build_smoke_detector() -> list[dict]:
    parts: list[dict] = [cyl("plate", 0.08, 0.02, (0, 0.012, 0), "metal", segments=24)]
    parts.append(cyl("body", 0.072, 0.028, (0, -0.01, 0), "metal", radius_top=0.05, segments=24))
    parts.append(cyl("led", 0.008, 0.006, (0.03, 0.024, 0), "accent", segments=8))
    return parts


@item("power_outlet", "插座", "appliance", tags=("插座", "电气", "outlet"), footprint=(0.09, 0.09, 0.03), source_item="power-outlet-moa09g0o")
def build_power_outlet() -> list[dict]:
    parts: list[dict] = [box("plate", (0.09, 0.09, 0.012), (0, 0.045, 0), "metal")]
    for row in range(2):
        for col in range(2):
            parts.append(cyl(f"hole_{row}_{col}", 0.006, 0.006, (-0.018 + col * 0.036, 0.06 - row * 0.03, 0.008), "accent", segments=8, rot=(PI / 2, 0, 0)))
    return parts


@item("exit_sign", "安全出口标志", "appliance", tags=("指示牌", "消防", "exit"), footprint=(0.54, 0.27, 0.10), source_item="exit-sign")
def build_exit_sign() -> list[dict]:
    parts: list[dict] = [box("body", (0.54, 0.27, 0.08), (0, 0.135, 0), "accent")]
    for index, sx in enumerate((-1, 1)):
        parts.append(cyl(f"lamp_{index}", 0.028, 0.03, (sx * 0.16, 0.135, 0.045), "glass", segments=14, rot=(PI / 2, 0, 0)))
    return parts


@item("sprinkler", "喷淋头", "appliance", tags=("喷淋", "消防", "sprinkler"), footprint=(0.09, 0.10, 0.09), source_item="sprinkler")
def build_sprinkler() -> list[dict]:
    parts: list[dict] = [cyl("neck", 0.012, 0.05, (0, 0.09, 0), "metal", segments=8)]
    parts.append(cyl("head", 0.04, 0.015, (0, 0.055, 0), "metal", segments=14))
    parts.append(cyl("deflector", 0.045, 0.004, (0, 0.04, 0), "metal", segments=14))
    return parts


@item("sewing_machine", "缝纫机", "appliance", tags=("缝纫机", "家务", "sewing"), footprint=(0.83, 0.68, 0.32), source_item="sewing-machine")
def build_sewing_machine() -> list[dict]:
    """台板 + 机头 + 立柱 + 手轮。"""

    width, depth, height = 0.83, 0.32, 0.68
    parts: list[dict] = [box("table", (width, 0.045, depth), (0, 0.40, 0), "wood")]
    for index, sx in enumerate((-1, 1)):
        parts.append(box(f"leg_{index}", (0.05, 0.38, 0.05), (sx * (width / 2 - 0.06), 0.19, 0), "metal"))
    parts.append(box("arm", (0.30, 0.14, 0.16), (-0.10, 0.50, 0), "metal"))
    parts.append(box("column", (0.12, 0.24, 0.16), (-0.22, 0.56, 0), "metal"))
    parts.append(cyl("wheel", 0.055, 0.03, (-0.22, 0.56, -0.10), "metal", segments=20, rot=(PI / 2, 0, 0)))
    parts.append(box("needle", (0.008, 0.06, 0.008), (0.03, 0.42, 0), "metal"))
    return parts
