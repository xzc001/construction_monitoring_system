"""烟雾明火模块独立流水线。只跑 fire/smoke 检测, 与其它模块完全解耦。

产出与其它模块一致: annotated.mp4 / events.json / violations/*.jpg
"""

import json
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from ...detectors.fire_smoke import FireSmokeDetector
from ...types import Alert
from ...visualizer import draw_alert_banner, draw_box, draw_hud
from .config import FireConfig
from .rules import FireStateSmoother, evaluate_frame

C_FIRE = (0, 0, 255)       # 红 - 明火
C_SMOKE = (0, 200, 255)    # 橙 - 烟雾


class FirePipeline:
    """烟雾明火告警流水线(独立模块)。"""

    def __init__(self, config: FireConfig):
        self.cfg = config
        self.detector = FireSmokeDetector(
            model_path=config.model_path, conf=config.fire_conf,
            device=config.device, imgsz=config.imgsz,
            include_fog=config.include_fog)

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
        print(f"\n>> [烟火模块] {video_in.name}  {W}x{H} @ {fps:.1f}fps  {total} 帧")

        smoother = FireStateSmoother(grace_frames=max(1, int(self.cfg.state_grace * fps)))
        persist_frames = max(1, int(self.cfg.persist_alert * fps))

        writer = cv2.VideoWriter(str(video_out_path),
                                 cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        all_events: list[dict] = []
        cumulative = {"fire": 0, "smoke": 0}
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

            dets = self.detector.detect(frame)
            fires, smokes, raw_state = evaluate_frame(dets)
            state = smoother.smooth(raw_state, frame_idx)

            cumulative["fire"] += len(fires)
            cumulative["smoke"] += len(smokes)
            timeline.append(state)

            new_alerts: list[Alert] = []
            if state == "fire_smoke":
                if not episode_active:
                    episode_active = True
                    episode_start = frame_idx
                    episode_alerted = False
                if (not episode_alerted and (fires or smokes)
                        and frame_idx - episode_start >= persist_frames):
                    rep = max(fires or smokes, key=lambda d: d.area)
                    kind = "fire" if fires else "smoke"
                    episode_seq += 1
                    episode_alerted = True
                    new_alerts.append(Alert(
                        kind=kind, track_id=episode_seq, frame_idx=frame_idx,
                        time_seconds=round(frame_idx / max(fps, 1), 2),
                        center=rep.center, bbox=rep.bbox,
                        note=("明火" if fires else "") + ("烟雾" if smokes else "")))
            else:
                episode_active = False

            for d in smokes:
                draw_box(frame, d, C_SMOKE, label="烟雾", conf_in_label=False, label_size=18)
            for d in fires:
                draw_box(frame, d, C_FIRE, label="明火", conf_in_label=False, label_size=18)

            draw_hud(frame, frame_idx, total,
                     {"fire": cumulative["fire"], "smoke": cumulative["smoke"]},
                     len(all_events))
            draw_alert_banner(frame, new_alerts)

            for a in new_alerts:
                shot = f"alert_f{a.frame_idx:05d}_{a.kind}_id{a.track_id}.jpg"
                cv2.imwrite(str(violations_dir / shot), frame)
                all_events.append({**asdict(a), "screenshot": shot})
                print(f"   [ALERT] f{a.frame_idx} ({a.time_seconds}s) 烟火 ({a.note})")

            writer.write(frame)
            if progress_cb is not None and frame_idx % 10 == 0:
                progress_cb(frame_idx, total)

        cap.release()
        writer.release()

        summary = {
            "module": "fire",
            "video": str(video_in), "video_out": str(video_out_path),
            "fps": fps, "width": W, "height": H, "total_frames": total,
            "elapsed_seconds": round(time.time() - t0, 1),
            "cumulative": cumulative,
            "alerts": all_events, "n_alerts": len(all_events),
            "timeline": timeline,
            "config": {"fire_conf": self.cfg.fire_conf,
                       "persist_alert": self.cfg.persist_alert,
                       "imgsz": self.cfg.imgsz},
        }
        events_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        print(f"   完成: {frame_idx} 帧, {len(all_events)} 告警, "
              f"{summary['elapsed_seconds']}s")
        return summary
