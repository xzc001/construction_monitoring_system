"""把一次未穿反光衣告警整理成通用 AlertEvent。"""

import json
from itertools import groupby
from pathlib import Path
from typing import Optional

import cv2

from ...alerting.event import AlertEvent, Evidence, TimelineSeg

STATE_CN = {"vest_ok": "已穿反光衣", "no_vest": "未穿反光衣"}
STATE_COLOR = {"vest_ok": "#2fd982", "no_vest": "#ff4242"}


def _segments(timeline: list[str], fps: float) -> list[dict]:
    segs, idx = [], 0
    for state, g in groupby(timeline):
        n = len(list(g))
        segs.append({"state": state, "start_s": round(idx / fps, 2),
                     "end_s": round((idx + n) / fps, 2)})
        idx += n
    return segs


def _grab_frame(video: Path, t_seconds: float, out: Path) -> Optional[Path]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(t_seconds * fps))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), frame)
    return out


def build_vest_event(run_dir: Path, alert_idx: int = 0, location: str = "") -> AlertEvent:
    run_dir = Path(run_dir)
    data = json.loads((run_dir / "events.json").read_text(encoding="utf-8"))
    fps = data.get("fps", 25.0)
    alerts = data.get("alerts", [])
    if not alerts:
        raise ValueError("该结果没有告警事件")
    alert_idx = max(0, min(alert_idx, len(alerts) - 1))
    alert = alerts[alert_idx]
    alert_t = alert.get("time_seconds", 0.0)
    note = alert.get("note", "")

    segs = _segments(data.get("timeline", []), fps)
    timeline = [TimelineSeg(label=STATE_CN.get(s["state"], s["state"]),
                            start_s=s["start_s"], end_s=s["end_s"],
                            color=STATE_COLOR.get(s["state"], "#888"))
                for s in segs]

    seg = next((s for s in segs if s["state"] == "no_vest"), None)
    parts = []
    if seg:
        parts.append(f"监控视频第 {seg['start_s']:.1f} 秒起检测到人员未穿反光衣"
                     + (f"({note})。" if note else "。"))
        parts.append(f"持续未整改, 于第 {alert_t:.1f} 秒触发告警。")
    else:
        parts.append(f"于第 {alert_t:.1f} 秒检测到人员未穿反光衣。")
    parts.append("作业区域未穿反光衣降低人员可见度, 在车辆/机械作业环境存在碰撞风险, 应要求规范穿戴。")
    description = "".join(parts)

    evidence = []
    shot = alert.get("screenshot")
    if shot and (run_dir / "violations" / shot).exists():
        evidence.append(Evidence(run_dir / "violations" / shot,
                                 f"告警时刻(第 {alert_t:.1f} 秒):人员未穿反光衣"))

    cfg = data.get("config", {})
    params = [
        ("反光衣模型置信度", str(cfg.get("vest_conf", "—"))),
        ("人体二次校验", "开" if cfg.get("require_person") else "关"),
        ("告警延时(秒)", str(cfg.get("persist_alert", "—"))),
        ("视频分辨率", f"{data.get('width')}×{data.get('height')}"),
        ("帧率", f"{fps:.1f} fps"),
    ]

    return AlertEvent(
        module="vest", kind="no_vest",
        title="未穿反光衣",
        message="检测到人员未穿反光衣,请规范穿戴!",
        description=description, severity="medium", location=location,
        time_seconds=alert_t, frame_idx=alert.get("frame_idx", 0),
        evidence=evidence, timeline=timeline,
        advice=[
            "要求人员穿戴反光衣后再进入车辆/机械作业区。",
            "核查反光衣配备与班前检查制度。",
            "在出入口增设穿戴提示与定期巡检。",
        ],
        params=params,
    )
