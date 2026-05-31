"""违规吸烟 —— 纯判定逻辑(无 I/O)。

吸烟模型(单类 cigarette)误报多, 本层做两道几何过滤:
  1. 香烟框宽度不能超过人体框宽度的一定比例(滤掉塔吊/管道/标牌等大块误报)
  2. 香烟框必须落在某人"上半身"(脸/手位置)

与其它模块一样, 只依赖共享几何基建(box_coverage), 不 import 其它业务模块。
"""

from ...rules.geometry import box_coverage
from ...types import Detection

STATE_PRIORITY = {"no_smoking": 0, "smoking": 1}


def filter_cigarettes(cigarettes: list[Detection], persons: list[Detection],
                      max_width_ratio: float = 0.30,
                      min_upper_coverage: float = 0.5
                      ) -> list[tuple[Detection, Detection]]:
    """返回 [(香烟, 所属人), ...]: 框够小且落在某人上半身的香烟。"""
    hits: list[tuple[Detection, Detection]] = []
    max_pw = max((p.width for p in persons), default=0)
    for c in cigarettes:
        if max_pw > 0 and c.width > max_width_ratio * max_pw:
            continue                       # 框过大 → 误报
        for p in persons:
            upper = (p.bbox[0], p.bbox[1], p.bbox[2],
                     p.bbox[1] + int(0.55 * p.height))
            if box_coverage(c.bbox, upper) >= min_upper_coverage:
                hits.append((c, p))
                break
    return hits


def evaluate_frame(cigarettes: list[Detection], persons: list[Detection],
                   require_person: bool = True,
                   max_width_ratio: float = 0.30,
                   min_upper_coverage: float = 0.5
                   ) -> tuple[list[tuple[Detection, Detection]], str]:
    """判定单帧。

    返回:
        hits  [(香烟, 所属人), ...](已过几何校验, 触发告警 / 标红)
        state "no_smoking"(无) / "smoking"(有人吸烟)
    """
    if require_person:
        hits = filter_cigarettes(cigarettes, persons, max_width_ratio, min_upper_coverage)
    else:
        hits = [(c, None) for c in cigarettes]
    state = "smoking" if hits else "no_smoking"
    return hits, state


class SmokingStateSmoother:
    """逐帧状态时间迟滞平滑(消除时间轴/状态条断续闪烁)。

    进入 smoking 后在宽限期内即便瞬时掉回 no_smoking(香烟瞬时漏检)仍保持 smoking。
    与配电箱 PanelStateSmoother 同思路。
    """

    def __init__(self, grace_frames: int = 25):
        self.grace_frames = max(1, int(grace_frames))
        self._last_smoking = -10 ** 9

    def smooth(self, raw_state: str, frame_idx: int) -> str:
        if raw_state == "smoking":
            self._last_smoking = frame_idx
        if frame_idx - self._last_smoking <= self.grace_frames:
            return "smoking"
        return "no_smoking"
