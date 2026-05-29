"""ROI 区域定义 + 加载。

ROI 配置格式（YAML 或 JSON 均可）:
    roi_zones:
      - name: "吊臂下方禁区"
        kind: "no_entry"           # 类型: no_entry / approach_warning
        polygon: [[100,200], [500,200], [500,600], [100,600]]
      - name: "临边预警"
        kind: "approach_warning"
        polygon: [[600,100], [900,100], [900,400], [600,400]]
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import yaml

from .geometry import point_in_polygon

Point = tuple[int, int]


@dataclass
class RoiZone:
    name: str
    kind: str                # 'no_entry' / 'approach_warning' / 自定义
    polygon: list[Point]

    def contains(self, point: Point) -> bool:
        return point_in_polygon(point, self.polygon)


def load_rois(config_path: str | Path) -> list[RoiZone]:
    """从 YAML/JSON 配置加载 ROI 列表。文件不存在时返回空列表。"""
    p = Path(config_path)
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8")
    data = yaml.safe_load(text) if p.suffix in (".yaml", ".yml") else json.loads(text)
    zones = []
    for z in data.get("roi_zones", []):
        zones.append(RoiZone(
            name=z["name"],
            kind=z.get("kind", "no_entry"),
            polygon=[tuple(pt) for pt in z["polygon"]],
        ))
    return zones
