"""未戴安全帽 —— 纯判定逻辑(无 I/O)。

与配电箱/闯入模块一样, 只依赖共享几何基建(box_coverage), 不 import 其它业务模块。

业务规则:
    安全帽模型给出 helmet(戴) / no_helmet(未戴) 头框;
    no_helmet 头框须落在某个人体框内(滤掉帽形物体/背景假阳)才算违规。
"""

from ...rules.geometry import box_coverage
from ...types import Detection

STATE_PRIORITY = {"compliant": 0, "violation": 1}


def filter_no_helmet(no_helmets: list[Detection], persons: list[Detection],
                     min_coverage: float = 0.25) -> list[Detection]:
    """未戴帽头框必须被某个人体框覆盖 >= min_coverage, 否则剔除(假阳)。"""
    keep = []
    for h in no_helmets:
        cov = max((box_coverage(h.bbox, p.bbox) for p in persons), default=0.0)
        if cov >= min_coverage:
            keep.append(h)
    return keep


def evaluate_frame(helmet_dets: list[Detection], persons: list[Detection],
                   require_person: bool = True,
                   min_coverage: float = 0.25
                   ) -> tuple[list[Detection], list[Detection], str]:
    """判定单帧。

    返回:
        helmets    戴帽头框列表(可视化为绿)
        no_helmets 未戴帽头框列表(已过人体校验, 可视化为红 / 触发告警)
        state      "compliant"(无未戴帽) / "violation"(有未戴帽)
    """
    helmets = [d for d in helmet_dets if d.label == "helmet"]
    no_helmets = [d for d in helmet_dets if d.label == "no_helmet"]
    if require_person:
        no_helmets = filter_no_helmet(no_helmets, persons, min_coverage)
    state = "violation" if no_helmets else "compliant"
    return helmets, no_helmets, state


class HelmetStateSmoother:
    """逐帧状态时间迟滞平滑(消除时间轴/状态条断续闪烁)。

    进入 violation 后在宽限期(grace_frames)内即便瞬时掉回 compliant
    (头部漏检/遮挡), 仍保持 violation。与配电箱 PanelStateSmoother 同思路。
    """

    def __init__(self, grace_frames: int = 25):
        self.grace_frames = max(1, int(grace_frames))
        self._last_violation = -10 ** 9

    def smooth(self, raw_state: str, frame_idx: int) -> str:
        if raw_state == "violation":
            self._last_violation = frame_idx
        if frame_idx - self._last_violation <= self.grace_frames:
            return "violation"
        return "compliant"
