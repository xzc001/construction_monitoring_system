"""违规吸烟模块独立流水线。

只跑 person + 香烟(cigarette)两件事, 与其它模块【完全解耦】:
本文件不 import 任何其它业务模块, 只用共享基建
(PersonDetector / SmokingDetector / visualizer / types)。

产出与其它模块一致:
  out_dir/annotated.mp4 / events.json / violations/*.jpg
"""

import json
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from ...detectors.person import PersonDetector
from ...detectors.smoking import SmokingDetector
from ...types import Alert
from ...visualizer import draw_alert_banner, draw_box, draw_hud, draw_thin_box
from .config import SmokingConfig
from .rules import SmokingStateSmoother, evaluate_frame

# 配色 (BGR)
C_PERSON = (160, 160, 160)     # 灰细线 - 人体(上下文)
C_SMOKING = (0, 0, 255)        # 红 - 吸烟人员 / 香烟


class SmokingPipeline:
    """违规吸烟告警流水线(独立模块)。"""

    def __init__(self, config: SmokingConfig):
        self.cfg = config
        self.person_detector = PersonDetector(
            conf=config.person_conf, device=config.device, imgsz=config.imgsz)
        self.smoking_detector = SmokingDetector(
            model_path=config.model_path, conf=config.smoking_conf,
            device=config.device, imgsz=config.imgsz)

    def process_video(self, video_in: Path, out_dir: Path,
                      progress_cb=None) -> dict:
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
        print(f"\n>> [吸烟模块] {video_in.name}  {W}x{H} @ {fps:.1f}fps  {total} 帧")

        smoother = SmokingStateSmoother(
            grace_frames=max(1, int(self.cfg.state_grace * fps)))
        persist_frames = max(1, int(self.cfg.persist_alert * fps))

        writer = cv2.VideoWriter(str(video_out_path),
                                 cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        all_events: list[dict] = []
        cumulative = {"person": 0, "smoking": 0}
        timeline: list[str] = []
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
            cigarettes = self.smoking_detector.detect(frame)
            hits, raw_state = evaluate_frame(
                cigarettes, persons,
                require_person=self.cfg.require_person,
                max_width_ratio=self.cfg.max_cig_width_ratio,
                min_upper_coverage=self.cfg.min_upper_coverage)
            state = smoother.smooth(raw_state, frame_idx)
            smoker_ids = {id(p) for _, p in hits if p is not None}

            cumulative["person"] += len(persons)
            cumulative["smoking"] += len(hits)
            timeline.append(state)

            # ---- 违规时段告警: 一段连续吸烟只报一次 ----
            new_alerts: list[Alert] = []
            if state == "smoking":
                if not episode_active:
                    episode_active = True
                    episode_start = frame_idx
                    episode_alerted = False
                if (not episode_alerted and hits
                        and frame_idx - episode_start >= persist_frames):
                    cig, person = max(hits, key=lambda cp: cp[0].conf)
                    rep = person if person is not None else cig
                    episode_seq += 1
                    episode_alerted = True
                    new_alerts.append(Alert(
                        kind="smoking", track_id=episode_seq,
                        frame_idx=frame_idx,
                        time_seconds=round(frame_idx / max(fps, 1), 2),
                        center=rep.center, bbox=rep.bbox, note="违规吸烟"))
            else:
                episode_active = False

            # ---- 可视化 ----
            for p in persons:
                color = C_SMOKING if id(p) in smoker_ids else C_PERSON
                if id(p) in smoker_ids:
                    draw_box(frame, p, C_SMOKING, label="违规吸烟",
                             conf_in_label=False, label_size=18)
                else:
                    draw_thin_box(frame, p, C_PERSON)
            for cig, _ in hits:
                x1, y1, x2, y2 = cig.bbox
                cv2.rectangle(frame, (x1, y1), (x2, y2), C_SMOKING, 2)

            draw_hud(frame, frame_idx, total,
                     {"p": cumulative["person"], "cig": cumulative["smoking"]},
                     len(all_events))
            draw_alert_banner(frame, new_alerts)

            for a in new_alerts:
                shot = f"alert_f{a.frame_idx:05d}_{a.kind}_id{a.track_id}.jpg"
                cv2.imwrite(str(violations_dir / shot), frame)
                all_events.append({**asdict(a), "screenshot": shot})
                print(f"   [ALERT] f{a.frame_idx} ({a.time_seconds}s) 违规吸烟")

            writer.write(frame)
            if frame_idx % 200 == 0:
                fps_now = frame_idx / max(time.time() - t0, 1)
                print(f"   {frame_idx}/{total} ({fps_now:.1f} fps), alerts={len(all_events)}")
            if progress_cb is not None and frame_idx % 10 == 0:
                progress_cb(frame_idx, total)

        cap.release()
        writer.release()

        summary = {
            "module": "smoking",
            "video": str(video_in),
            "video_out": str(video_out_path),
            "fps": fps, "width": W, "height": H, "total_frames": total,
            "elapsed_seconds": round(time.time() - t0, 1),
            "cumulative": cumulative,
            "alerts": all_events,
            "n_alerts": len(all_events),
            "timeline": timeline,
            "config": {
                "smoking_conf": self.cfg.smoking_conf,
                "require_person": self.cfg.require_person,
                "max_cig_width_ratio": self.cfg.max_cig_width_ratio,
                "persist_alert": self.cfg.persist_alert,
                "imgsz": self.cfg.imgsz,
            },
        }
        events_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   完成: {frame_idx} 帧, {len(all_events)} 告警, "
              f"{summary['elapsed_seconds']}s")
        return summary
