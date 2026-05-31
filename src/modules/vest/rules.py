"""未穿反光衣 —— 纯判定逻辑(无 I/O)。

PPE 模型给出 vest(已穿)/ no_vest(未穿)框;
no_vest 框须落在某人体框内(滤假阳)才算违规。
只依赖共享几何基建(box_coverage)。
"""

from ...rules.geometry import box_coverage
from ...types import Detection


def filter_no_vest(no_vests: list[Detection], persons: list[Detection],
                   min_coverage: float = 0.25) -> list[Detection]:
    keep = []
    for d in no_vests:
        cov = max((box_coverage(d.bbox, p.bbox) for p in persons), default=0.0)
        if cov >= min_coverage:
            keep.append(d)
    return keep


def evaluate_frame(vest_dets: list[Detection], persons: list[Detection],
                   require_person: bool = True, min_coverage: float = 0.25
                   ) -> tuple[list[Detection], list[Detection], str]:
    """返回 (已穿列表, 未穿列表, state)。state: vest_ok / no_vest。"""
    vests = [d for d in vest_dets if d.label == "vest"]
    no_vests = [d for d in vest_dets if d.label == "no_vest"]
    if require_person:
        no_vests = filter_no_vest(no_vests, persons, min_coverage)
    state = "no_vest" if no_vests else "vest_ok"
    return vests, no_vests, state


class VestStateSmoother:
    """逐帧状态时间迟滞平滑。进入 no_vest 后在宽限期内保持。"""

    def __init__(self, grace_frames: int = 25):
        self.grace_frames = max(1, int(grace_frames))
        self._last = -10 ** 9

    def smooth(self, raw_state: str, frame_idx: int) -> str:
        if raw_state == "no_vest":
            self._last = frame_idx
        return "no_vest" if frame_idx - self._last <= self.grace_frames else "vest_ok"
