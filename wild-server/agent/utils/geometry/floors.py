"""WILD楼板的真实世界平面范围，供校验与装配共用；不把孔洞填成包围盒。"""

from math import isfinite

from shapely.geometry import Point, Polygon, box
from shapely.validation import explain_validity


def floor_region(floor: dict):
    """解析原生rect/circle/polygon楼板，返回包含孔洞的有效平面区域。"""

    def vector(value, count):
        if (
            not isinstance(value, (list, tuple))
            or len(value) != count
            or any(
                type(number) not in (int, float) or not isfinite(number)
                for number in value
            )
        ):
            raise ValueError(f"楼板坐标必须为{count}个有限数字")
        return value

    origin = vector(floor.get("from"), 3)
    shape = floor.get("shape", "rect")
    if shape == "polygon":

        def ring(points):
            if not isinstance(points, (list, tuple)) or len(points) < 3:
                raise ValueError("楼板多边形环至少需要三个二维点")
            return [
                (origin[0] + vector(point, 2)[0], origin[2] + point[1])
                for point in points
            ]

        region = Polygon(
            ring(floor.get("polygon")), [ring(hole) for hole in floor.get("holes", [])]
        )
    elif shape == "circle":
        radius = floor.get("radius")
        if type(radius) not in (int, float) or not isfinite(radius) or radius <= 0:
            raise ValueError("圆形楼板半径必须为正有限数字")
        region = Point(origin[0], origin[2]).buffer(radius, quad_segs=128)
    elif shape == "rect":
        end = vector(floor.get("to"), 3)
        region = box(
            min(origin[0], end[0]),
            min(origin[2], end[2]),
            max(origin[0], end[0]),
            max(origin[2], end[2]),
        )
    else:
        raise ValueError(f"不支持的楼板形状：{shape}")
    if not region.is_valid or region.is_empty or region.area <= 1e-8:
        raise ValueError("楼板轮廓无效或面积为零：" + explain_validity(region))
    return region


def region_shape(region):
    """兼容历史矩形区域与真实多边形记录；包围盒不能作为孔洞内的支承证据。"""
    if isinstance(region, dict):
        return Polygon(region["outer"], region.get("holes", []))
    return box(*region)
