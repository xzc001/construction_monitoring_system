"""电动车违规停放模块独立流水线。

只跑 电动车检测 + 多边形禁停区两件事, 与其它业务模块【完全解耦】:
只用共享基建(EbikeDetector / RoiZone / visualizer / types)。

产出与其它模块一致: annotated.mp4 / events.json / violations/*.jpg
"""

import json
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from ...detectors.ebike import EbikeDetector
from ...types import Alert
from ...visualizer import draw_alert_banner, draw_box, draw_hud, draw_roi
from .config import EbikeConfig
from .rules import EbikeStateSmoother, evaluate_frame

# 配色 (BGR)
C_EBIKE_SAFE = (255, 128, 0)     # 蓝 - 禁停区外的电动车
C_EBIKE_HIT = (0, 0, 255)        # 红 - 禁停区内违规停放的电动车


class EbikePipeline:
    """电动车违规停放告警流水线(独立模块)。"""

    def __init__(self, config: EbikeConfig):
        self.cfg = config
        self.detector = EbikeDetector(
            conf=config.ebike_conf, device=config.device, imgsz=config.imgsz)

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
        print(f"\n>> [电动车违停模块] {video_in.name}  {W}x{H} @ {fps:.1f}fps  {total} 帧")
        print(f"   禁停区: " + "; ".join(
            f"{z.name}({z.kind})" for z in self.cfg.zones))

        smoother = EbikeStateSmoother(
            grace_frames=max(1, int(self.cfg.state_grace * fps)))
        persist_frames = max(1, int(self.cfg.persist_alert * fps))

        writer = cv2.VideoWriter(str(video_out_path),
                                 cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        all_events: list[dict] = []
        cumulative = {"ebike": 0, "illegal": 0}
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

            ebikes = self.detector.detect(frame)
            hits, raw_state = evaluate_frame(ebikes, self.cfg.zones, anchor=self.cfg.anchor)
            state = smoother.smooth(raw_state, frame_idx)
            hit_ids = {id(e) for e, z in hits}

            cumulative["ebike"] += len(ebikes)
            cumulative["illegal"] += len(hits)
            timeline.append(state)

            new_alerts: list[Alert] = []
            if state == "illegal_park":
                if not episode_active:
                    episode_active = True
                    episode_start = frame_idx
                    episode_alerted = False
                if (not episode_alerted and hits
                        and frame_idx - episode_start >= persist_frames):
                    e = max((e for e, _ in hits), key=lambda d: d.area)
                    episode_seq += 1
                    episode_alerted = True
                    new_alerts.append(Alert(
                        kind="ebike_illegal_park", track_id=episode_seq,
                        frame_idx=frame_idx,
                        time_seconds=round(frame_idx / max(fps, 1), 2),
                        center=e.center, bbox=e.bbox, note="电动车违规停放"))
            else:
                episode_active = False

            for z in self.cfg.zones:
                draw_roi(frame, z)
            for e in ebikes:
                color = C_EBIKE_HIT if id(e) in hit_ids else C_EBIKE_SAFE
                label = "违规停放" if id(e) in hit_ids else "电动车"
                draw_box(frame, e, color, label=label,
                         conf_in_label=False, label_size=18)

            draw_hud(frame, frame_idx, total,
                     {"ebk": cumulative["ebike"], "illegal": cumulative["illegal"]},
                     len(all_events))
            draw_alert_banner(frame, new_alerts)

            for a in new_alerts:
                shot = f"alert_f{a.frame_idx:05d}_{a.kind}_id{a.track_id}.jpg"
                cv2.imwrite(str(violations_dir / shot), frame)
                all_events.append({**asdict(a), "screenshot": shot})
                print(f"   [ALERT] f{a.frame_idx} ({a.time_seconds}s) "
                      f"电动车违规停放 #{a.track_id}")

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
            "module": "ebike",
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
