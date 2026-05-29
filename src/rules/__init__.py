"""通用规则基建: 几何运算 / ROI / 跨帧跟踪。

业务专属规则放到对应模块里(如 src/modules/panel/rules.py), 保持本层通用。
"""

from .geometry import box_coverage, point_in_polygon, distance
from .roi import RoiZone, load_rois
from .tracker import ViolationTracker

__all__ = [
    "box_coverage", "point_in_polygon", "distance",
    "RoiZone", "load_rois",
    "ViolationTracker",
]
