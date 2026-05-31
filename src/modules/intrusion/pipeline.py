"""危险区域闯入模块独立流水线。

只跑 person + 多边形电子围栏两件事, 与配电箱/头盔/吸烟逻辑【完全解耦】:
本文件不 import 任何其它业务模块, 只用共享基建
(PersonDetector / RoiZone / ViolationTracker / visualizer / types)。

产出与配电箱流水线一致, 便于网站统一读取:
  out_dir/annotated.mp4   标注视频
  out_dir/events.json     统计 + 告警事件 + 截图名 + 逐帧时间线
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
from ...visualizer import draw_alert_banner, draw_box, draw_hud, draw_roi
from .config import IntrusionConfig
from .rules import evaluate_frame

# 配色 (BGR)
C_PERSON_SAFE = (255, 128, 0)     # 蓝 - 区域外的人(安全)
C_PERSON_HIT = (0, 0, 255)        # 红 - 闯入禁区的人


class IntrusionPipeline:
    """危险区域闯入告警流水线(独立模块)。"""

    def __init__(self, config: IntrusionConfig):
        self.cfg = config
        self.person_detector = PersonDetector(
            conf=config.person_conf, device=config.device, imgsz=config.imgsz)

    # ---------- 主流程 ----------
    def process_video(self, video_in: Path, out_dir: Path,
                      progress_cb=None) -> dict:
        """progress_cb: 可选回调 fn(frame_idx, total), 供网站进度条用。"""
        video_in = Path(video_in)
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
        print(f"\n>> [闯入模块] {video_in.name}  {W}x{H} @ {fps:.1f}fps  {total} 帧")
        print(f"   监控区域: " + "; ".join(
            f"{z.name}({z.kind})" for z in self.cfg.zones))

        tracker = ViolationTracker(
            persist_frames=max(1, int(self.cfg.persist_alert * fps)),
            match_dist=max(W, H) // 4,
        )

        writer = cv2.VideoWriter(str(video_out_path),
                                 cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        all_events: list[dict] = []
        cumulative = {"person": 0, "intrusion": 0}
        timeline: list[str] = []           # 逐帧最坏状态(网站画时间轴)
        frame_idx = 0
        t0 = time.time()

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1

            persons = self.person_detector.detect(frame)
            hits, state = evaluate_frame(persons, self.cfg.zones, anchor=self.cfg.anchor)
            # 只有落在"禁区(no_entry)"里的人才标红/告警; 安全通道里的人保持蓝色
            hit_persons = {id(p) for p, z in hits if z.kind == "no_entry"}

            # 只有"闯入禁区(no_entry)"才进 tracker → 告警
            violations = [
                Violation(kind="roi_intrusion", detection=p, person=p,
                          note=z.name)
                for p, z in hits if z.kind == "no_entry"
            ]
            new_alerts = tracker.update(violations, frame_idx, fps)

            cumulative["person"] += len(persons)
            cumulative["intrusion"] += len(violations)
            timeline.append(state)

            # ---- 可视化 ----
            for z in self.cfg.zones:
                draw_roi(frame, z)
            for p in persons:
                color = C_PERSON_HIT if id(p) in hit_persons else C_PERSON_SAFE
                label = "闯入禁区" if id(p) in hit_persons else "人员"
                draw_box(frame, p, color, label=label,
                         conf_in_label=False, label_size=18)

            draw_hud(frame, frame_idx, total,
                     {"p": cumulative["person"], "roi": cumulative["intrusion"]},
                     len(all_events))
            draw_alert_banner(frame, new_alerts)

            for a in new_alerts:
                shot = f"alert_f{a.frame_idx:05d}_{a.kind}_id{a.track_id}.jpg"
                cv2.imwrite(str(violations_dir / shot), frame)
                all_events.append({**asdict(a), "screenshot": shot})
                print(f"   [ALERT] f{a.frame_idx} ({a.time_seconds}s) "
                      f"危险区域闯入 #{a.track_id}")

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
            "module": "intrusion",
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
            "timeline": timeline,          # 逐帧状态, 网站画时间轴
            "config": {                    # 检测参数(报告附录 / 复现用)
                "zones": [
                    {"name": z.name, "kind": z.kind,
                     "polygon": [list(pt) for pt in z.polygon]}
                    for z in self.cfg.zones
                ],
                "anchor": self.cfg.anchor,
                "persist_alert": self.cfg.persist_alert,
                "imgsz": self.cfg.imgsz,
            },
        }
        events_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   完成: {frame_idx} 帧, {len(all_events)} 告警, "
              f"{summary['elapsed_seconds']}s")
        return summary
