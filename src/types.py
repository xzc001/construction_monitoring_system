"""统一的数据类型 —— 整个 pipeline 各模块之间传递的标准结构。"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Detection:
    """单个检测结果（一个框）。"""
    label: str              # 类别名，如 'person'、'hardhat'、'no-hardhat'、'cigarette'
    conf: float             # 置信度 0-1
    bbox: tuple[int, int, int, int]   # (x1, y1, x2, y2) 像素坐标
    source: str = ""        # 来自哪个 detector，调试用

    @property
    def cx(self) -> int:
        return (self.bbox[0] + self.bbox[2]) // 2

    @property
    def cy(self) -> int:
        return (self.bbox[1] + self.bbox[3]) // 2

    @property
    def center(self) -> tuple[int, int]:
        return (self.cx, self.cy)

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    @property
    def area(self) -> int:
        return max(self.width, 0) * max(self.height, 0)


@dataclass
class Violation:
    """规则层判定后的"违规事件候选"（还没到告警级别）。"""
    kind: str               # 'no_helmet' / 'smoking' / 'roi_intrusion'
    detection: Detection    # 主依据的检测框（如 no-hardhat 框 或 person 框）
    person: Optional[Detection] = None   # 关联的人体框（区域入侵时即为本人）
    note: str = ""

    @property
    def center(self) -> tuple[int, int]:
        return self.detection.center


@dataclass
class Alert:
    """跟踪器输出的"确认告警事件"（已经过时间平滑）。"""
    kind: str
    track_id: int
    frame_idx: int
    time_seconds: float
    center: tuple[int, int]
    bbox: tuple[int, int, int, int]
    note: str = ""
