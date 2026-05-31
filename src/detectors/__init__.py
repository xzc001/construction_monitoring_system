"""检测器集合(配电箱模块版): 仅人体 + 配电箱门。

新增其它能力(安全帽/吸烟/...)时, 在此目录加 detector 并在这里导出即可。
"""

from .base import BaseDetector
from .person import PersonDetector
from .panel_door import PanelDoorDetector
from .helmet import HelmetDetector
from .smoking import SmokingDetector
from .fire_smoke import FireSmokeDetector
from .vest import VestDetector

__all__ = ["BaseDetector", "PersonDetector", "PanelDoorDetector",
           "HelmetDetector", "SmokingDetector", "FireSmokeDetector", "VestDetector"]
