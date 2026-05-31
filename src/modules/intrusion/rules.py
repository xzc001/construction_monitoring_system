"""危险区域闯入 —— 纯判定逻辑(无 I/O, 无模型)。

与配电箱模块一样, 本文件只依赖共享几何基建(RoiZone), 不 import 其它业务模块。

业务规则:
    禁区(no_entry)         人员落入 → 违规, 持续即告警(红)
    警戒区(approach_warning) 人员落入 → 仅提示, 不告警(黄)
    监控区(general)         仅画区域(青)
"""

from ...rules.roi import RoiZone
from ...types import Detection

Point = tuple[int, int]

# 逐帧"最坏状态"优先级(给网站画时间轴 / 状态横幅用)
STATE_PRIORITY = {"clear": 0, "warning": 1, "intrusion": 2}
# 哪些区域类型会触发"闯入"告警
ALERT_KINDS = {"no_entry"}


def anchor_point(person: Detection, anchor: str = "foot") -> Point:
    """取人体框上用于判定"在不在区域内"的代表点。

    foot   脚底中点(站地面区域最准, 默认)
    center 框中心
    """
    if anchor == "center":
        return person.center
    return (person.cx, person.bbox[3])     # 脚底中点


def evaluate_frame(persons: list[Detection], zones: list[RoiZone],
                   anchor: str = "foot") -> tuple[list[tuple[Detection, RoiZone]], str]:
    """判定单帧。

    返回:
        hits  命中列表 [(person, zone), ...](一个人只记其命中的第一个区域)
        state 本帧最坏状态: "clear" / "warning" / "intrusion"
    """
    hits: list[tuple[Detection, RoiZone]] = []
    state = "clear"
    severity_rank = {"no_entry": 2, "approach_warning": 1}
    for p in persons:
        pt = anchor_point(p, anchor)
        # 一个人可能同时落在多个区域(如安全通道与禁区重叠), 取严重度最高的那个
        best: tuple[int, RoiZone] | None = None
        for z in zones:
            if z.contains(pt):
                rank = severity_rank.get(z.kind, 0)
                if best is None or rank > best[0]:
                    best = (rank, z)
        if best is None:
            continue
        z = best[1]
        hits.append((p, z))
        cand = "intrusion" if z.kind == "no_entry" else (
            "warning" if z.kind == "approach_warning" else "clear")
        if STATE_PRIORITY[cand] > STATE_PRIORITY[state]:
            state = cand
    return hits, state


class IntrusionStateSmoother:
    """逐帧状态的时间迟滞平滑(消除时间轴/状态条断续闪烁)。

    进入 intrusion / warning 后, 在宽限期(grace_frames)内即便后续帧
    瞬时掉回 clear(人体漏检 / 脚点在禁区边缘抖动), 仍保持该状态;
    并优先保持更严重的状态(intrusion > warning)。

    与配电箱 PanelStateSmoother 同思路, 各模块各自持有, 互不耦合。
    """

    _ORDER = ("intrusion", "warning")     # 从高到低: 优先保持更严重的状态

    def __init__(self, grace_frames: int = 25):
        self.grace_frames = max(1, int(grace_frames))
        self._last_seen = {"warning": -10 ** 9, "intrusion": -10 ** 9}

    def smooth(self, raw_state: str, frame_idx: int) -> str:
        if raw_state in self._last_seen:
            self._last_seen[raw_state] = frame_idx
        for st in self._ORDER:
            if frame_idx - self._last_seen[st] <= self.grace_frames:
                return st
        return "clear"
