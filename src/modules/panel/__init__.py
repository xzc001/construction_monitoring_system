"""配电箱"无人值守"告警模块(自包含)。

用法:
    from src.modules.panel import PanelConfig, PanelPipeline
    cfg = PanelConfig(panel_rois=[(195, 611, 477, 790)])
    PanelPipeline(cfg).process_video("in.mp4", "runs/out")

业务规则:
    门关          → 合规 (绿)
    门开 + 有人    → 维修中 (黄), 不告警
    门开 + 持续无人 → 无人值守 (红), 告警

与头盔/吸烟/禁区逻辑完全解耦, 只复用共享基建。
"""

# 导入顺序: 先加载本模块的纯逻辑(rules), 再加载会触发 rules 包初始化的 pipeline,
# 避免旧 alert.py 的 re-export 造成循环导入。
from .config import PanelConfig
from .detector import PanelDoorDetector
from .rules import (PanelStateSmoother, classify_panel_with_person, expand_box)
from .pipeline import PanelPipeline

__all__ = [
    "PanelConfig", "PanelPipeline", "PanelDoorDetector",
    "classify_panel_with_person", "expand_box", "PanelStateSmoother",
]
