"""电动车违规停放 —— 纯判定逻辑(无 I/O, 无模型)。

只依赖共享几何基建(RoiZone), 不 import 其它业务模块。

业务规则:
    禁停区(no_park) 电动车(着地点)落入 → 违规停放, 持续即告警(红)
    其它 kind       仅画区域(不告警)
"""

from ...rules.roi import RoiZone
from ...types import Detection

Point = tuple[int, int]

STATE_PRIORITY = {"no_violation": 0, "illegal_park": 1}
ALERT_KINDS = {"no_park"}


def anchor_point(ebike: Detection, anchor: str = "foot") -> Point:
    """取车体框上用于判定"在不在区域内"的代表点。

    foot   车底中点(着地点, 默认)
    center 框中心
    """
    if anchor == "center":
        return ebike.center
    return (ebike.cx, ebike.bbox[3])     # 车底中点


def evaluate_frame(ebikes: list[Detection], zones: list[RoiZone],
                   anchor: str = "foot") -> tuple[list[tuple[Detection, RoiZone]], str]:
    """判定单帧。

    返回:
        hits  命中列表 [(ebike, zone), ...](着地点落入某禁停区的车)
        state 本帧状态: "no_violation" / "illegal_park"
    """
    hits: list[tuple[Detection, RoiZone]] = []
    state = "no_violation"
    for e in ebikes:
        pt = anchor_point(e, anchor)
        for z in zones:
            if z.kind in ALERT_KINDS and z.contains(pt):
                hits.append((e, z))
                state = "illegal_park"
                break
    return hits, state


class EbikeStateSmoother:
    """逐帧状态时间迟滞平滑(消除时间轴/状态条断续闪烁)。

    进入 illegal_park 后, 在宽限期(grace_frames)内即便瞬时掉回 no_violation
    (车体瞬时漏检 / 着地点边缘抖动), 仍保持 illegal_park。
    """

    def __init__(self, grace_frames: int = 25):
        self.grace_frames = max(1, int(grace_frames))
        self._last = -10 ** 9

    def smooth(self, raw_state: str, frame_idx: int) -> str:
        if raw_state == "illegal_park":
            self._last = frame_idx
        if frame_idx - self._last <= self.grace_frames:
            return "illegal_park"
        return "no_violation"
