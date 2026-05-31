"""未穿反光衣模块独立流水线。person + 反光衣两件事, 与其它模块完全解耦。

产出与其它模块一致: annotated.mp4 / events.json / violations/*.jpg
"""

import json
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from ...detectors.person import PersonDetector
from ...detectors.vest import VestDetector
from ...types import Alert
from ...visualizer import draw_alert_banner, draw_box, draw_hud, draw_thin_box
from .config import VestConfig
from .rules import VestStateSmoother, evaluate_frame

C_PERSON = (160, 160, 160)
C_VEST = (0, 200, 0)         # 绿 - 已穿反光衣
C_NO_VEST = (0, 0, 255)      # 红 - 未穿反光衣


class VestPipeline:
    """未穿反光衣告警流水线(独立模块)。"""

    def __init__(self, config: VestConfig):
        self.cfg = config
        self.person_detector = PersonDetector(
            conf=config.person_conf, device=config.device, imgsz=config.imgsz)
        self.vest_detector = VestDetector(
            model_path=config.model_path, conf=config.vest_conf,
            device=config.device, imgsz=config.imgsz)

    def process_video(self, video_in: Path, out_dir: Path, progress_cb=None) -> dict:
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
        print(f"\n>> [反光衣模块] {video_in.name}  {W}x{H} @ {fps:.1f}fps  {total} 帧")

        smoother = VestStateSmoother(grace_frames=max(1, int(self.cfg.state_grace * fps)))
        persist_frames = max(1, int(self.cfg.persist_alert * fps))

        writer = cv2.VideoWriter(str(video_out_path),
                                 cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        all_events: list[dict] = []
        cumulative = {"person": 0, "no_vest": 0}
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
            vest_dets = self.vest_detector.detect(frame)
            vests, no_vests, raw_state = evaluate_frame(
                vest_dets, persons, require_person=self.cfg.require_person,
                min_coverage=self.cfg.min_person_coverage)
            state = smoother.smooth(raw_state, frame_idx)

            cumulative["person"] += len(persons)
            cumulative["no_vest"] += len(no_vests)
            timeline.append(state)

            new_alerts: list[Alert] = []
            if state == "no_vest":
                if not episode_active:
                    episode_active = True
                    episode_start = frame_idx
                    episode_alerted = False
                if (not episode_alerted and no_vests
                        and frame_idx - episode_start >= persist_frames):
                    rep = max(no_vests, key=lambda d: d.area)
                    episode_seq += 1
                    episode_alerted = True
                    new_alerts.append(Alert(
                        kind="no_vest", track_id=episode_seq, frame_idx=frame_idx,
                        time_seconds=round(frame_idx / max(fps, 1), 2),
                        center=rep.center, bbox=rep.bbox,
                        note=f"{len(no_vests)}人未穿反光衣"))
            else:
                episode_active = False

            for p in persons:
                draw_thin_box(frame, p, C_PERSON)
            for d in vests:
                draw_box(frame, d, C_VEST, label="已穿反光衣", conf_in_label=False, label_size=16)
            for d in no_vests:
                draw_box(frame, d, C_NO_VEST, label="未穿反光衣", conf_in_label=False, label_size=18)

            draw_hud(frame, frame_idx, total,
                     {"p": cumulative["person"], "no_vest": cumulative["no_vest"]},
                     len(all_events))
            draw_alert_banner(frame, new_alerts)

            for a in new_alerts:
                shot = f"alert_f{a.frame_idx:05d}_{a.kind}_id{a.track_id}.jpg"
                cv2.imwrite(str(violations_dir / shot), frame)
                all_events.append({**asdict(a), "screenshot": shot})
                print(f"   [ALERT] f{a.frame_idx} ({a.time_seconds}s) 未穿反光衣 ({a.note})")

            writer.write(frame)
            if progress_cb is not None and frame_idx % 10 == 0:
                progress_cb(frame_idx, total)

        cap.release()
        writer.release()

        summary = {
            "module": "vest",
            "video": str(video_in), "video_out": str(video_out_path),
            "fps": fps, "width": W, "height": H, "total_frames": total,
            "elapsed_seconds": round(time.time() - t0, 1),
            "cumulative": cumulative,
            "alerts": all_events, "n_alerts": len(all_events),
            "timeline": timeline,
            "config": {"vest_conf": self.cfg.vest_conf,
                       "require_person": self.cfg.require_person,
                       "persist_alert": self.cfg.persist_alert,
                       "imgsz": self.cfg.imgsz},
        }
        events_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        print(f"   完成: {frame_idx} 帧, {len(all_events)} 告警, "
              f"{summary['elapsed_seconds']}s")
        return summary
