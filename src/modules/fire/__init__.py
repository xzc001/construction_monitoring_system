"""烟雾明火告警模块(自包含)。

用法:
    from src.modules.fire import FireConfig, FirePipeline
    FirePipeline(FireConfig()).process_video("in.mp4", "runs/out")

烟火本身即违规, 无需人体关联。与其它模块完全解耦, 只复用共享基建。
"""

from .config import FireConfig
from .rules import FireStateSmoother, evaluate_frame
from .pipeline import FirePipeline

__all__ = ["FireConfig", "FirePipeline", "evaluate_frame", "FireStateSmoother"]
