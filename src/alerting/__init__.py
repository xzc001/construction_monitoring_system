"""告警动作层 —— 把识别模块产生的告警变成实际动作。

设计: 识别模块 → 产出 AlertEvent → AlertDispatcher → 各渠道(报告/邮件/语音/推送)。

已实现: 事故报告 PDF + 邮件发送。
规划中: 浏览器/服务器语音播报, 企业微信/钉钉/Bark 手机推送。
"""

from .event import AlertEvent, Evidence, TimelineSeg
from .config import AlertingConfig, load_config
from .report import build_report
from .dispatcher import AlertDispatcher

__all__ = [
    "AlertEvent", "Evidence", "TimelineSeg",
    "AlertingConfig", "load_config",
    "build_report", "AlertDispatcher",
]
