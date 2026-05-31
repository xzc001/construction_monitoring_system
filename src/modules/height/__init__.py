"""高处作业临边告警模块(自包含)。

用法:
    from src.modules.height import HeightConfig, HeightPipeline
    cfg = HeightConfig.from_zone_specs(
        [{"name": "外架临边作业区", "kind": "edge_work",
          "polygon": [[270,345],[1180,360],[1190,485],[290,470]]}])
    HeightPipeline(cfg).process_video("in.mp4", "runs/out")

业务规则:
    临边作业区 edge_work   人员(脚点)落入并持续 → 告警 (红)
    其它 kind             仅画区域 (不告警)

与配电箱 / 闯入 / 头盔 / 吸烟逻辑完全解耦, 只复用共享基建。
"""

from .config import HeightConfig
from .rules import anchor_point, evaluate_frame
from .pipeline import HeightPipeline

__all__ = [
    "HeightConfig", "HeightPipeline", "evaluate_frame", "anchor_point",
]
