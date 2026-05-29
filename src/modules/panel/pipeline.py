"""配电箱模块独立流水线。

只跑 person + 配电箱门两件事, 与头盔/吸烟/禁区逻辑【完全解耦】:
本文件不 import 任何其它业务模块, 只用共享基建
(PersonDetector / ViolationTracker / visualizer / types)。

产出与旧大流水线一致, 便于网站统一读取:
  out_dir/annotated.mp4   标注视频
  out_dir/events.json     统计 + 告警事件 + 截图名
  out_dir/violations/*.jpg 每次告警的现场截图
"""

import json
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from ...detectors.person import PersonDetector
from ...rules.tracker import ViolationTracker
from ...types import Alert, Violation
from ...visualizer import draw_alert_banner, draw_box, draw_hud, put_chinese
from .config import PanelConfig
from .detector import PanelDoorDetector
from .rules import PanelStateSmoother, classify_panel_with_person

# 三态配色 (BGR)
C_CLOSED = (0, 200, 0)        # 绿 - 门已关
C_ATTENDED = (0, 255, 255)    # 黄 - 维修中
C_UNATTENDED = (0, 0, 255)    # 红 - 无人值守
C_PERSON = (255, 128, 0)      # 蓝 - 人


class PanelPipeline:
    """配电箱"无人值守"检测流水线(独立模块)。"""

    def __init__(self, config: PanelConfig):
        self.cfg = config
        self.person_detector = PersonDetector(
            conf=config.person_conf, device=config.device, imgsz=config.imgsz)
        self.panel_detector = PanelDoorDetector(
            panel_rois=config.panel_rois, threshold=config.threshold)

    # ---------- 单帧三态绘制 ----------
    def _draw_panel(self, frame, det, state, safety_zone):
        if state == "closed":
            draw_box(frame, det, C_CLOSED, label="配电箱门已关",
                     conf_in_label=False, label_size=18)
        elif state == "open_attended":
            draw_box(frame, det, C_ATTENDED, label="维修中(人员值守)",
                     conf_in_label=False, label_size=20)
            if safety_zone is not None:
                self._draw_dashed_zone(frame, safety_zone, C_ATTENDED)
        else:  # open_unattended
            draw_box(frame, det, C_UNATTENDED, label="!! 无人值守 门未关",
                     conf_in_label=False, label_size=22)

    @staticmethod
    def _draw_dashed_zone(frame, zone, color):
        """画黄色虚线"维修安全区"。"""
        sx1, sy1, sx2, sy2 = zone
        for x in range(sx1, sx2, 16):
            cv2.line(frame, (x, sy1), (min(x + 8, sx2), sy1), color, 2)
            cv2.line(frame, (x, sy2 - 1), (min(x + 8, sx2), sy2 - 1), color, 2)
        for y in range(sy1, sy2, 16):
            cv2.line(frame, (sx1, y), (sx1, min(y + 8, sy2)), color, 2)
            cv2.line(frame, (sx2 - 1, y), (sx2 - 1, min(y + 8, sy2)), color, 2)

    # ---------- 主流程 ----------
    def process_video(self, video_in: Path, out_dir: Path,
                      progress_cb=None) -> dict:
        """progress_cb: 可选回调 fn(frame_idx, total), 供网站进度条用。"""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        violations_dir = out_dir / "violations"
        violations_dir.mkdir(exist_ok=True)
        video_out_path = out_dir / "annotated.mp4"
        events_path = out_dir / "events.json"

        cap = cv2.VideoCapture(str(video_in))
        if not cap.isOpened():
            raise RuntimeError(f"打不开视频: {video_in}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f"\n>> [配电箱模块] {video_in.name}  {W}x{H} @ {fps:.1f}fps  {total} 帧")

        tracker = ViolationTracker(
            persist_frames=max(1, int(self.cfg.persist_alert * fps)),
            match_dist=max(W, H) // 4,
        )
        smoother = PanelStateSmoother(
            grace_frames=max(1, int(self.cfg.attended_grace * fps)))

        writer = cv2.VideoWriter(str(video_out_path),
                                 cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        all_events: list[dict] = []
        cumulative = {"person": 0, "panel_open": 0}
        # 逐帧三态时间线(给网站画时间轴用)
        timeline: list[str] = []
        frame_idx = 0
        t0 = time.time()

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1

            persons = self.person_detector.detect(frame)
            panel_dets = self.panel_detector.detect(frame)
            raw_states = classify_panel_with_person(
                panel_dets, persons, safety_zone_ratio=self.cfg.safety_zone_ratio)
            states = smoother.smooth(raw_states, frame_idx)

            # 只有"无人值守"才进 tracker → 告警
            panel_violations = [
                Violation(kind="panel_open", detection=panel_dets[i], note="无人值守")
                for i in states
                if states[i][0] == "open_unattended"
            ]
            new_alerts = tracker.update(panel_violations, frame_idx, fps)

            cumulative["person"] += len(persons)
            cumulative["panel_open"] += sum(
                1 for d in panel_dets if d.label == "panel_open")
            # 记录主配电箱(idx 0)的本帧状态
            timeline.append(states.get(0, ("closed", None))[0])

            # ---- 可视化 ----
            for p in persons:
                x1, y1, x2, y2 = p.bbox
                cv2.rectangle(frame, (x1, y1), (x2, y2), C_PERSON, 1)
            for i, det in enumerate(panel_dets):
                state, zone = states.get(i, ("closed", None))
                self._draw_panel(frame, det, state, zone)

            draw_hud(frame, frame_idx, total,
                     {"p": cumulative["person"], "panel": cumulative["panel_open"]},
                     len(all_events))
            draw_alert_banner(frame, new_alerts)

            for a in new_alerts:
                shot = f"alert_f{a.frame_idx:05d}_{a.kind}_id{a.track_id}.jpg"
                cv2.imwrite(str(violations_dir / shot), frame)
                all_events.append({**asdict(a), "screenshot": shot})
                print(f"   [ALERT] f{a.frame_idx} ({a.time_seconds}s) "
                      f"配电箱无人值守 #{a.track_id}")

            writer.write(frame)
            if frame_idx % 200 == 0:
                fps_now = frame_idx / max(time.time() - t0, 1)
                print(f"   {frame_idx}/{total} ({fps_now:.1f} fps), "
                      f"alerts={len(all_events)}")
            if progress_cb is not None and frame_idx % 10 == 0:
                progress_cb(frame_idx, total)

        cap.release()
        writer.release()

        summary = {
            "module": "panel",
            "video": str(video_in),
            "video_out": str(video_out_path),
            "fps": fps,
            "width": W,
            "height": H,
            "total_frames": total,
            "elapsed_seconds": round(time.time() - t0, 1),
            "cumulative": cumulative,
            "alerts": all_events,
            "n_alerts": len(all_events),
            "timeline": timeline,   # 逐帧状态, 网站画三态时间轴
            "config": {             # 检测参数(报告附录 / 复现用)
                "panel_rois": self.cfg.panel_rois,
                "threshold": self.cfg.threshold,
                "safety_zone_ratio": self.cfg.safety_zone_ratio,
                "attended_grace": self.cfg.attended_grace,
                "persist_alert": self.cfg.persist_alert,
                "imgsz": self.cfg.imgsz,
            },
        }
        events_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   完成: {frame_idx} 帧, {len(all_events)} 告警, "
              f"{summary['elapsed_seconds']}s")
        return summary
