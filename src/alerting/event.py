"""告警事件 —— 各识别模块与告警动作层之间的标准结构。

识别模块(配电箱/安全帽/...)只负责把一次告警描述成 AlertEvent,
告警层(报告/邮件/语音/推送)只消费 AlertEvent, 两边解耦。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Evidence:
    """一张证据图 + 说明。"""
    image: Path
    caption: str = ""


@dataclass
class TimelineSeg:
    """事件时间线上的一段(用于报告里画状态条)。"""
    label: str
    start_s: float
    end_s: float
    color: str = "#888888"   # 十六进制


@dataclass
class AlertEvent:
    """一次告警的完整描述(与具体业务模块无关)。"""
    module: str                       # 来源模块, 如 "panel"
    kind: str                         # 事件类型, 如 "panel_open"
    title: str                        # 标题, 如 "配电箱无人值守"
    message: str                      # 简短消息(语音/推送用)
    description: str = ""             # 详细经过描述
    severity: str = "high"           # low | medium | high
    location: str = ""               # 点位/摄像头
    time_seconds: float = 0.0        # 事件在视频内的时刻
    frame_idx: int = 0
    occurred_at: str = ""            # 实际发生时间(ISO字符串), 回放场景可空

    evidence: list[Evidence] = field(default_factory=list)
    timeline: list[TimelineSeg] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)        # 处置建议
    params: list[tuple[str, str]] = field(default_factory=list)  # 数据附录(k,v)

    def short_summary(self) -> str:
        loc = f"[{self.location}] " if self.location else ""
        t = self.occurred_at or f"视频 {self.time_seconds:.1f}s"
        return f"{loc}{self.title} —— {self.message} ({t})"
