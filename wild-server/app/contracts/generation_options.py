"""生成请求的粒度选项与设计范围。"""

from typing import Literal, cast


DetailLevel = Literal["minimal", "simple", "standard", "detailed"]

DETAIL_LEVEL_GUIDANCE = {
    "minimal": "低：完成建筑主体、必要的门窗、屋顶、多层建筑的楼梯和基础照明。采用简洁构造与材质表达，默认不增加装饰构件、家具或陈设。",
    "simple": "中：在基础建筑上，按功能与风格适量设计阳台、露台、雨棚、栏杆和入口构件，完善基本立面与材质层次。默认不配置家具或大量装饰。",
    "standard": "高：完整设计建筑外观与构造细节，包括开口分格、檐口、门廊、柱饰、屋面节点和分层材质；按功能与风格选择构件，默认不做全套室内家具。",
    "detailed": "极高：在完整外观与构造细节上，设计室内功能分区、通行空间及家具陈设，如客厅沙发与茶几、餐桌椅、卧室床与柜体、厨房橱柜及卫浴设施；按建筑用途安排，并补充室内外照明、入口与场地细节。家具逐件或按组合写成有位置、尺寸和造型的构件标记，不能只写在文字说明里。",
}


def normalize_detail_level(value: object = "minimal") -> DetailLevel:
    """未提供合法粒度时使用 minimal。"""
    return cast(DetailLevel, value) if isinstance(value, str) and value in DETAIL_LEVEL_GUIDANCE else "minimal"
