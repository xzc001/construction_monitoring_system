"""未戴安全帽模块独立流水线。

只跑 person + 安全帽(hardhat/no-hardhat)两件事, 与配电箱/闯入逻辑【完全解耦】:
本文件不 import 任何其它业务模块, 只用共享基建
(PersonDetector / HelmetDetector / visualizer / types)。

产出与其它模块一致, 便于网站统一读取:
  out_dir/annotated.mp4   标注视频
  out_dir/events.json     统计 + 告警事件 + 截图名 + 逐帧时间线
  out_dir/violations/*.jpg 每次告警的现场截图
"""

import json
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from ...detectors.helmet import HelmetDetector
from ...detectors.person import PersonDetector
from ...types import Alert
from ...visualizer import draw_alert_banner, draw_box, draw_hud, draw_thin_box
from .config import HelmetConfig
from .rules import HelmetStateSmoother, evaluate_frame

# 配色 (BGR)
C_PERSON = (160, 160, 160)     # 灰细线 - 人体(上下文)
C_HELMET = (0, 200, 0)         # 绿 - 已戴安全帽
C_NO_HELMET = (0, 0, 255)      # 红 - 未戴安全帽


class HelmetPipeline:
    """未戴安全帽告警流水线(独立模块)。"""

    def __init__(self, config: HelmetConfig):
        self.cfg = config
        self.person_detector = PersonDetector(
            conf=config.person_conf, device=config.device, imgsz=config.imgsz)
        self.helmet_detector = HelmetDetector(
            model_path=config.model_path, conf=config.helmet_conf,
            device=config.device, imgsz=config.imgsz)

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
        print(f"\n>> [安全帽模块] {video_in.name}  {W}x{H} @ {fps:.1f}fps  {total} 帧")

        smoother = HelmetStateSmoother(
            grace_frames=max(1, int(self.cfg.state_grace * fps)))
        persist_frames = max(1, int(self.cfg.persist_alert * fps))

        writer = cv2.VideoWriter(str(video_out_path),
                                 cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        all_events: list[dict] = []
        cumulative = {"person": 0, "no_helmet": 0}
        timeline: list[str] = []           # 逐帧状态(网站画时间轴)
        # 告警以"违规时段"为单位: 一段连续"未戴帽"只报一次(对检测抖动鲁棒)
        episode_active = False
        episode_start = 0
        episode_alerted = False
        episode_seq = 0
        frame_idx = 0
        t0 = time.time()

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1

            persons = self.person_detector.detect(frame)
            helmet_dets = self.helmet_detector.detect(frame)
            helmets, no_helmets, raw_state = evaluate_frame(
                helmet_dets, persons,
                require_person=self.cfg.require_person,
                min_coverage=self.cfg.min_person_coverage)
            state = smoother.smooth(raw_state, frame_idx)

            cumulative["person"] += len(persons)
            cumulative["no_helmet"] += len(no_helmets)
            timeline.append(state)

            # ---- 违规时段告警: 一段连续未戴帽只报一次 ----
            new_alerts: list[Alert] = []
            if state == "violation":
                if not episode_active:
                    episode_active = True
                    episode_start = frame_idx
                    episode_alerted = False
                if (not episode_alerted and no_helmets
                        and frame_idx - episode_start >= persist_frames):
                    p = max(no_helmets, key=lambda d: d.area)
                    episode_seq += 1
                    episode_alerted = True
                    new_alerts.append(Alert(
                        kind="no_helmet", track_id=episode_seq,
                        frame_idx=frame_idx,
                        time_seconds=round(frame_idx / max(fps, 1), 2),
                        center=p.center, bbox=p.bbox,
                        note=f"{len(no_helmets)}人未戴帽"))
            else:
                episode_active = False

            # ---- 可视化 ----
            for p in persons:
                draw_thin_box(frame, p, C_PERSON)
            for d in helmets:
                draw_box(frame, d, C_HELMET, label="已戴安全帽",
                         conf_in_label=False, label_size=16)
            for d in no_helmets:
                draw_box(frame, d, C_NO_HELMET, label="未戴安全帽",
                         conf_in_label=False, label_size=18)

            draw_hud(frame, frame_idx, total,
                     {"p": cumulative["person"], "no_h": cumulative["no_helmet"]},
                     len(all_events))
            draw_alert_banner(frame, new_alerts)

            for a in new_alerts:
                shot = f"alert_f{a.frame_idx:05d}_{a.kind}_id{a.track_id}.jpg"
                cv2.imwrite(str(violations_dir / shot), frame)
                all_events.append({**asdict(a), "screenshot": shot})
                print(f"   [ALERT] f{a.frame_idx} ({a.time_seconds}s) "
                      f"未戴安全帽 ({a.note})")

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
            "module": "helmet",
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
            "timeline": timeline,
            "config": {
                "helmet_conf": self.cfg.helmet_conf,
                "require_person": self.cfg.require_person,
                "min_person_coverage": self.cfg.min_person_coverage,
                "persist_alert": self.cfg.persist_alert,
                "imgsz": self.cfg.imgsz,
            },
        }
        events_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   完成: {frame_idx} 帧, {len(all_events)} 告警, "
              f"{summary['elapsed_seconds']}s")
        return summary
