"""电动车违规停放告警模块(自包含)。

用法:
    from src.modules.ebike import EbikeConfig, EbikePipeline
    cfg = EbikeConfig.from_zone_specs(
        [{"name": "消防通道禁停区", "kind": "no_park",
          "polygon": [[0,90],[470,60],[470,480],[0,480]]}])
    EbikePipeline(cfg).process_video("in.mp4", "runs/out")

业务规则:
    禁停区 no_park   电动车(着地点)落入并持续 → 告警 (红)
    其它 kind       仅画区域 (不告警)

与其它模块完全解耦, 只复用共享基建(EbikeDetector / RoiZone / visualizer)。
"""

from .config import EbikeConfig
from .rules import anchor_point, evaluate_frame
from .pipeline import EbikePipeline

__all__ = [
    "EbikeConfig", "EbikePipeline", "evaluate_frame", "anchor_point",
]
