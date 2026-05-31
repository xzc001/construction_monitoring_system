"""高处作业临边 —— 纯判定逻辑(无 I/O, 无模型)。

与危险区域闯入模块同思路, 只依赖共享几何基建(RoiZone), 不 import 其它业务模块。

业务规则:
    临边作业区(edge_work) 人员(脚点)落入 → 高处临边作业, 持续即告警(红)
    其它 kind             仅画区域(不告警)
"""

from ...rules.roi import RoiZone
from ...types import Detection

Point = tuple[int, int]

# 逐帧状态优先级(给网站画时间轴 / 状态横幅用)
STATE_PRIORITY = {"no_edge": 0, "edge_work": 1}
# 哪些区域类型会触发"临边作业"告警
ALERT_KINDS = {"edge_work"}


def anchor_point(person: Detection, anchor: str = "foot") -> Point:
    """取人体框上用于判定"在不在区域内"的代表点。

    foot   脚底中点(站平台/木板上最准, 默认)
    center 框中心
    """
    if anchor == "center":
        return person.center
    return (person.cx, person.bbox[3])     # 脚底中点


def evaluate_frame(persons: list[Detection], zones: list[RoiZone],
                   anchor: str = "foot") -> tuple[list[tuple[Detection, RoiZone]], str]:
    """判定单帧。

    返回:
        hits  命中列表 [(person, zone), ...](脚点落入某临边作业区的人)
        state 本帧状态: "no_edge" / "edge_work"
    """
    hits: list[tuple[Detection, RoiZone]] = []
    state = "no_edge"
    for p in persons:
        pt = anchor_point(p, anchor)
        for z in zones:
            if z.kind in ALERT_KINDS and z.contains(pt):
                hits.append((p, z))
                state = "edge_work"
                break
    return hits, state


class HeightStateSmoother:
    """逐帧状态的时间迟滞平滑(消除时间轴/状态条断续闪烁)。

    进入 edge_work 后, 在宽限期(grace_frames)内即便后续帧瞬时掉回 no_edge
    (人体漏检 / 脚点在区域边缘抖动), 仍保持 edge_work。

    与配电箱 / 闯入的平滑器同思路, 各模块各自持有, 互不耦合。
    """

    def __init__(self, grace_frames: int = 25):
        self.grace_frames = max(1, int(grace_frames))
        self._last_edge = -10 ** 9

    def smooth(self, raw_state: str, frame_idx: int) -> str:
        if raw_state == "edge_work":
            self._last_edge = frame_idx
        if frame_idx - self._last_edge <= self.grace_frames:
            return "edge_work"
        return "no_edge"
