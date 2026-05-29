"""几何工具 —— IoU、覆盖率、点-多边形判定。

这些是规则层的"基础设施"，不依赖任何 YOLO / OpenCV 业务概念。
"""

import math
from typing import Sequence

import cv2
import numpy as np

Box = tuple[int, int, int, int]   # (x1, y1, x2, y2)
Point = tuple[int, int]


def box_iou(a: Box, b: Box) -> float:
    """标准 IoU = 交集 / 并集"""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / max(area_a + area_b - inter, 1)


def box_coverage(inner: Box, outer: Box) -> float:
    """inner 被 outer 覆盖的比例 = inner ∩ outer / inner.area

    用途: 判断"小框（如帽子/香烟）是不是基本落在大框（人体）里"。
    返回 0-1。
    """
    x1 = max(inner[0], outer[0])
    y1 = max(inner[1], outer[1])
    x2 = min(inner[2], outer[2])
    y2 = min(inner[3], outer[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    inner_area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return inter / max(inner_area, 1)


def point_in_polygon(pt: Point, polygon: Sequence[Point]) -> bool:
    """点是否在闭合多边形内部（含边界）。
    cv2.pointPolygonTest 返回 +1/0/-1，我们 >=0 都算"在里面"。
    """
    poly = np.array(polygon, dtype=np.int32)
    return cv2.pointPolygonTest(poly, (float(pt[0]), float(pt[1])), False) >= 0


def distance(a: Point, b: Point) -> float:
    """两点欧氏距离"""
    return math.hypot(a[0] - b[0], a[1] - b[1])
