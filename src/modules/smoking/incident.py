"""把一次违规吸烟告警(run + alert)整理成通用 AlertEvent。"""

import json
from itertools import groupby
from pathlib import Path
from typing import Optional

import cv2

from ...alerting.event import AlertEvent, Evidence, TimelineSeg

STATE_CN = {
    "no_smoking": "未见吸烟",
    "smoking": "违规吸烟",
}
STATE_COLOR = {
    "no_smoking": "#2fd982",
    "smoking": "#ff4242",
}


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


def build_smoking_event(run_dir: Path, alert_idx: int = 0,
                        location: str = "") -> AlertEvent:
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

    viol_seg = next((s for s in segs if s["state"] == "smoking"), None)
    parts = []
    if viol_seg:
        parts.append(f"监控视频第 {viol_seg['start_s']:.1f} 秒起, "
                     f"检测到人员吸烟。")
        parts.append(f"持续未制止, 于第 {alert_t:.1f} 秒触发告警。")
    else:
        parts.append(f"于第 {alert_t:.1f} 秒检测到人员吸烟。")
    parts.append("在禁烟作业区域吸烟存在火灾隐患, 应立即制止并清理烟头火源。")
    description = "".join(parts)

    evidence = []
    shot = alert.get("screenshot")
    if shot and (run_dir / "violations" / shot).exists():
        evidence.append(Evidence(run_dir / "violations" / shot,
                                 f"告警时刻(第 {alert_t:.1f} 秒):检测到人员吸烟"))
    annotated = run_dir / "annotated.mp4"
    assets = run_dir / "report_assets"
    clear_seg = next((s for s in segs if s["state"] == "no_smoking"
                      and (s["end_s"] - s["start_s"]) >= 0.4), None)
    if annotated.exists() and clear_seg:
        mid = (clear_seg["start_s"] + clear_seg["end_s"]) / 2
        img = _grab_frame(annotated, mid, assets / f"clear_{int(mid)}.jpg")
        if img:
            evidence.append(Evidence(img, f"未见吸烟(第 {mid:.1f} 秒)"))

    cfg = data.get("config", {})
    params = [
        ("香烟模型置信度", str(cfg.get("smoking_conf", "—"))),
        ("人体上半身校验", "开" if cfg.get("require_person") else "关"),
        ("告警延时(秒)", str(cfg.get("persist_alert", "—"))),
        ("视频分辨率", f"{data.get('width')}×{data.get('height')}"),
        ("帧率", f"{fps:.1f} fps"),
    ]

    return AlertEvent(
        module="smoking", kind="smoking",
        title="违规吸烟",
        message="检测到人员违规吸烟,请立即制止并清理火源!",
        description=description, severity="high", location=location,
        time_seconds=alert_t, frame_idx=alert.get("frame_idx", 0),
        evidence=evidence, timeline=timeline,
        advice=[
            "立即制止吸烟行为, 清理烟头, 确认无遗留火源。",
            "核查该区域禁烟标识与巡查制度是否落实。",
            "对动火/易燃区域加强禁烟巡检与监控告警联动。",
        ],
        params=params,
    )
