"""配电箱门检测器(亮度阈值法)。

实现本身已经独立、无机器学习依赖, 物理位置仍在 detectors/panel_door.py,
这里 re-export, 让"配电箱模块"对外是一个完整自包含的入口。
"""

from ...detectors.panel_door import PanelDoorDetector

__all__ = ["PanelDoorDetector"]
