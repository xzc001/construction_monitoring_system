"""烟雾明火 —— 纯判定逻辑(无 I/O)。烟火本身即违规, 无需人体关联。"""

from ...types import Detection


def evaluate_frame(fire_dets: list[Detection]
                   ) -> tuple[list[Detection], list[Detection], str]:
    """返回 (明火列表, 烟雾列表, state)。state: no_fire / fire_smoke。"""
    fires = [d for d in fire_dets if d.label == "fire"]
    smokes = [d for d in fire_dets if d.label == "smoke"]
    state = "fire_smoke" if (fires or smokes) else "no_fire"
    return fires, smokes, state


class FireStateSmoother:
    """逐帧状态时间迟滞平滑(消除时间轴闪烁)。进入 fire_smoke 后在宽限期内保持。"""

    def __init__(self, grace_frames: int = 25):
        self.grace_frames = max(1, int(grace_frames))
        self._last = -10 ** 9

    def smooth(self, raw_state: str, frame_idx: int) -> str:
        if raw_state == "fire_smoke":
            self._last = frame_idx
        return "fire_smoke" if frame_idx - self._last <= self.grace_frames else "no_fire"
