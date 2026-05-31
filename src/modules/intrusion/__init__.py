"""危险区域闯入告警模块(自包含)。

用法:
    from src.modules.intrusion import IntrusionConfig, IntrusionPipeline
    from src.rules.roi import RoiZone
    cfg = IntrusionConfig(zones=[RoiZone("吊臂下方禁区", "no_entry",
                                         [(150, 640), (820, 640), (820, 1080), (150, 1080)])])
    IntrusionPipeline(cfg).process_video("in.mp4", "runs/out")

业务规则:
    禁区   no_entry          人员闯入并持续 → 告警 (红)
    警戒区 approach_warning  人员落入 → 仅提示, 不告警 (黄)
    监控区 general           仅画区域 (青)

与配电箱/头盔/吸烟逻辑完全解耦, 只复用共享基建。
"""

from .config import IntrusionConfig
from .rules import anchor_point, evaluate_frame
from .pipeline import IntrusionPipeline

__all__ = [
    "IntrusionConfig", "IntrusionPipeline", "evaluate_frame", "anchor_point",
]
