"""未戴安全帽告警模块(自包含)。

用法:
    from src.modules.helmet import HelmetConfig, HelmetPipeline
    HelmetPipeline(HelmetConfig()).process_video("in.mp4", "runs/out")

业务规则:
    安全帽模型(helmet_best.pt)给出 戴帽/未戴帽 头框;
    未戴帽头框经人体框二次校验后 → 违规, 持续即告警。

与配电箱/闯入逻辑完全解耦, 只复用共享基建。
"""

from .config import HelmetConfig
from .rules import HelmetStateSmoother, evaluate_frame, filter_no_helmet
from .pipeline import HelmetPipeline

__all__ = [
    "HelmetConfig", "HelmetPipeline", "evaluate_frame",
    "filter_no_helmet", "HelmetStateSmoother",
]
