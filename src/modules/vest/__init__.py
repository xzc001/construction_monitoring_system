"""未穿反光衣告警模块(自包含)。

用法:
    from src.modules.vest import VestConfig, VestPipeline
    VestPipeline(VestConfig()).process_video("in.mp4", "runs/out")

PPE 模型给出 已穿/未穿反光衣框, 未穿框经人体校验后 → 违规, 持续即告警。
与其它模块完全解耦, 只复用共享基建。
"""

from .config import VestConfig
from .rules import VestStateSmoother, evaluate_frame, filter_no_vest
from .pipeline import VestPipeline

__all__ = ["VestConfig", "VestPipeline", "evaluate_frame",
           "filter_no_vest", "VestStateSmoother"]
