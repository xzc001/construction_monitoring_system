"""违规吸烟告警模块(自包含)。

用法:
    from src.modules.smoking import SmokingConfig, SmokingPipeline
    SmokingPipeline(SmokingConfig()).process_video("in.mp4", "runs/out")

业务规则:
    香烟模型(单类 cigarette)给出香烟框;
    经"框够小 + 落在人上半身"几何校验后 → 违规吸烟, 持续即告警。

与其它模块完全解耦, 只复用共享基建。
"""

from .config import SmokingConfig
from .rules import SmokingStateSmoother, evaluate_frame, filter_cigarettes
from .pipeline import SmokingPipeline

__all__ = [
    "SmokingConfig", "SmokingPipeline", "evaluate_frame",
    "filter_cigarettes", "SmokingStateSmoother",
]
