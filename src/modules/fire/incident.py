"""把一次烟雾明火告警整理成通用 AlertEvent。"""

import json
from itertools import groupby
from pathlib import Path
from typing import Optional

import cv2

from ...alerting.event import AlertEvent, Evidence, TimelineSeg

STATE_CN = {"no_fire": "未见烟火", "fire_smoke": "检测到烟雾/明火"}
STATE_COLOR = {"no_fire": "#2fd982", "fire_smoke": "#ff4242"}


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


def build_fire_event(run_dir: Path, alert_idx: int = 0, location: str = "") -> AlertEvent:
    run_dir = Path(run_dir)
    data = json.loads((run_dir / "events.json").read_text(encoding="utf-8"))
    fps = data.get("fps", 25.0)
    alerts = data.get("alerts", [])
    if not alerts:
        raise ValueError("该结果没有告警事件")
    alert_idx = max(0, min(alert_idx, len(alerts) - 1))
    alert = alerts[alert_idx]
    alert_t = alert.get("time_seconds", 0.0)

    segs = _segments(data.get("timeline", []), fps)
    timeline = [TimelineSeg(label=STATE_CN.get(s["state"], s["state"]),
                            start_s=s["start_s"], end_s=s["end_s"],
                            color=STATE_COLOR.get(s["state"], "#888"))
                for s in segs]

    seg = next((s for s in segs if s["state"] == "fire_smoke"), None)
    parts = []
    if seg:
        parts.append(f"监控视频第 {seg['start_s']:.1f} 秒起检测到烟雾/明火。")
        parts.append(f"持续未处置, 于第 {alert_t:.1f} 秒触发告警。")
    else:
        parts.append(f"于第 {alert_t:.1f} 秒检测到烟雾/明火。")
    parts.append("作业区域出现烟雾或明火存在重大火灾隐患, 应立即核实并启动应急处置。")
    description = "".join(parts)

    evidence = []
    shot = alert.get("screenshot")
    if shot and (run_dir / "violations" / shot).exists():
        evidence.append(Evidence(run_dir / "violations" / shot,
                                 f"告警时刻(第 {alert_t:.1f} 秒):检测到烟雾/明火"))

    cfg = data.get("config", {})
    params = [
        ("烟火模型置信度", str(cfg.get("fire_conf", "—"))),
        ("告警延时(秒)", str(cfg.get("persist_alert", "—"))),
        ("累计明火/烟雾检出帧次",
         f"{data.get('cumulative', {}).get('fire', 0)}/{data.get('cumulative', {}).get('smoke', 0)}"),
        ("视频分辨率", f"{data.get('width')}×{data.get('height')}"),
        ("帧率", f"{fps:.1f} fps"),
    ]

    return AlertEvent(
        module="fire", kind=alert.get("kind", "fire"),
        title="烟雾/明火预警",
        message="检测到烟雾或明火,请立即核实并处置!",
        description=description, severity="high", location=location,
        time_seconds=alert_t, frame_idx=alert.get("frame_idx", 0),
        evidence=evidence, timeline=timeline,
        advice=[
            "立即派员核实火情, 必要时启动灭火与疏散应急预案。",
            "确认动火作业审批与灭火器材是否就位。",
            "排查火源, 清理周边易燃物, 复查监控盲区。",
        ],
        params=params,
    )
