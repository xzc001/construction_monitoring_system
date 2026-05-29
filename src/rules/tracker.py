"""跨帧跟踪 + 时间平滑告警生成。

设计:
  - 每种"违规类型"（no_helmet / smoking / roi_intrusion）有独立 tracker
  - 简化版多目标跟踪：用中心点 + 最近邻距离匹配（不引入 ByteTrack / DeepSort 这种重武器）
  - 同一个 track 连续 N 帧仍是违规才触发告警（首次触发只报一次，避免刷屏）
"""

from dataclasses import dataclass, field
from typing import Iterable

from ..types import Alert, Violation


@dataclass
class _Track:
    track_id: int
    kind: str
    center: tuple[int, int]
    bbox: tuple[int, int, int, int]
    count: int = 1                    # 连续命中帧数
    last_seen: int = 0
    alerted: bool = False


class ViolationTracker:
    """统一管理多种类型违规的跟踪 + 告警去抖。

    用法:
        tracker = ViolationTracker(persist_frames=15)
        for frame_idx, frame in ...:
            violations = run_detectors_and_rules(frame)
            alerts = tracker.update(violations, frame_idx, fps)
            for a in alerts:
                save_alert(a)
    """

    def __init__(self, persist_frames: int = 15, match_dist: int = 100,
                 expire_frames: int = 150):
        self.persist_frames = persist_frames
        self.match_dist = match_dist
        self.expire_frames = expire_frames
        self.tracks: list[_Track] = []
        self._next_id = 1

    def update(self, violations: Iterable[Violation], frame_idx: int,
               fps: float) -> list[Alert]:
        """根据本帧的 violation 列表更新 tracker，返回新触发的 Alert"""
        violations = list(violations)
        matched_track_ids: set[int] = set()

        # 1. 把每个 violation 匹配到最近的 track（同类型 + 距离 <= match_dist）
        for v in violations:
            best, best_d = None, self.match_dist + 1
            for t in self.tracks:
                if t.kind != v.kind or t.track_id in matched_track_ids:
                    continue
                d = ((t.center[0] - v.center[0]) ** 2 +
                     (t.center[1] - v.center[1]) ** 2) ** 0.5
                if d < best_d:
                    best, best_d = t, d
            if best is not None:
                best.center = v.center
                best.bbox = v.detection.bbox
                best.count += 1
                best.last_seen = frame_idx
                matched_track_ids.add(best.track_id)
            else:
                new_track = _Track(
                    track_id=self._next_id,
                    kind=v.kind,
                    center=v.center,
                    bbox=v.detection.bbox,
                    count=1,
                    last_seen=frame_idx,
                )
                self._next_id += 1
                self.tracks.append(new_track)
                matched_track_ids.add(new_track.track_id)

        # 2. 看哪些 track 达到告警阈值（首次触发只报一次）
        new_alerts: list[Alert] = []
        for t in self.tracks:
            if t.last_seen == frame_idx and t.count >= self.persist_frames and not t.alerted:
                t.alerted = True
                new_alerts.append(Alert(
                    kind=t.kind,
                    track_id=t.track_id,
                    frame_idx=frame_idx,
                    time_seconds=round(frame_idx / max(fps, 1), 2),
                    center=t.center,
                    bbox=t.bbox,
                ))

        # 3. 清理过期 track
        self.tracks = [t for t in self.tracks
                       if frame_idx - t.last_seen < self.expire_frames]
        return new_alerts
