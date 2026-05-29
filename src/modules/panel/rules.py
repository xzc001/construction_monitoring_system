"""配电箱模块专属规则 —— 三态判定 + 时间平滑(防闪烁)。

本文件是这套逻辑的【唯一权威实现】。旧的 src/rules/alert.py 为兼容旧版
大流水线, 从这里 re-export。

三态:
  closed            门关          (合规)
  open_attended     门开 + 有人在  (维修中, 合规)
  open_unattended   门开 + 周边无人 (无人值守, 违规 → 告警)
"""

from ...rules.geometry import box_coverage
from ...types import Detection


def expand_box(bbox: tuple[int, int, int, int],
               ratio: float = 1.6,
               frame_w: int = None, frame_h: int = None) -> tuple[int, int, int, int]:
    """围绕 bbox 中心向外扩大 ratio 倍, 形成"周边区域"(维修安全区)。"""
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    w, h = x2 - x1, y2 - y1
    new_w, new_h = int(w * ratio), int(h * ratio)
    nx1 = max(0, cx - new_w // 2)
    ny1 = max(0, cy - new_h // 2)
    nx2 = cx + new_w // 2
    ny2 = cy + new_h // 2
    if frame_w is not None:
        nx2 = min(frame_w, nx2)
    if frame_h is not None:
        ny2 = min(frame_h, ny2)
    return (nx1, ny1, nx2, ny2)


def classify_panel_with_person(panel_dets: list[Detection],
                                persons: list[Detection],
                                safety_zone_ratio: float = 2.0,
                                min_overlap: float = 0.15) -> dict:
    """对每个 panel 检测, 判断三态(瞬时, 未做时间平滑)。

    Returns: {panel_idx: ('closed'|'open_attended'|'open_unattended', safety_zone_box)}
    """
    result = {}
    for i, panel in enumerate(panel_dets):
        if panel.label != "panel_open":
            result[i] = ("closed", None)
            continue
        # 门开了, 检查周边有没有人
        safety_zone = expand_box(panel.bbox, ratio=safety_zone_ratio)
        nearby = False
        for p in persons:
            px, py = (p.bbox[0] + p.bbox[2]) // 2, (p.bbox[1] + p.bbox[3]) // 2
            sx1, sy1, sx2, sy2 = safety_zone
            if sx1 <= px <= sx2 and sy1 <= py <= sy2:
                nearby = True
                break
            if box_coverage(p.bbox, safety_zone) >= min_overlap:
                nearby = True
                break
        state = "open_attended" if nearby else "open_unattended"
        result[i] = (state, safety_zone)
    return result


class PanelStateSmoother:
    """对配电箱三态做时间平滑, 消除"维修中 / 无人值守"快速闪烁。

    问题: classify_panel_with_person 每帧独立判断, 工人操作配电箱时,
    人体检测器偶尔漏检一帧、或人的中心点短暂移出安全区, 状态就会在
    open_attended(黄) 和 open_unattended(红) 之间反复横跳。

    方案 (迟滞 / 宽限期):
      - 只要某帧判定"维修中", 就记下时间戳, 进入并保持"维修中"。
      - 之后即使连续几帧判成"无人值守", 只要距上次有人不超过 grace_frames,
        仍视为"维修中"(把漏检/短暂走开当噪声吸收掉)。
      - 只有连续 grace_frames 帧都确实无人, 才真正翻成"无人值守"告警。
      - 门一旦关闭, 清空该配电箱的值守记忆 (下次开门重新计时)。
    """

    def __init__(self, grace_frames: int = 50):
        self.grace_frames = grace_frames
        self._last_attended: dict[int, int] = {}  # panel_idx -> 最近一次有人的帧号

    def smooth(self, raw_states: dict, frame_idx: int) -> dict:
        """输入 classify_panel_with_person 的原始结果, 返回平滑后的同结构 dict。"""
        out = {}
        for i, (state, zone) in raw_states.items():
            if state == "closed":
                self._last_attended.pop(i, None)
                out[i] = ("closed", zone)
            elif state == "open_attended":
                self._last_attended[i] = frame_idx
                out[i] = ("open_attended", zone)
            else:  # 原始判定为 open_unattended
                last = self._last_attended.get(i)
                if last is not None and frame_idx - last <= self.grace_frames:
                    out[i] = ("open_attended", zone)  # 仍在宽限期, 视为维修中
                else:
                    out[i] = ("open_unattended", zone)
        return out
