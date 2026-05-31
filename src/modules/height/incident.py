"""把一次高处作业临边告警(run + alert)整理成通用 AlertEvent。

高处临边模块最懂如何描述自己的事故, 叙事/证据在这里生成;
告警层(报告/邮件/语音)只消费通用 AlertEvent。
"""

import json
from itertools import groupby
from pathlib import Path
from typing import Optional

import cv2

from ...alerting.event import AlertEvent, Evidence, TimelineSeg

STATE_CN = {
    "no_edge": "安全(无人在临边区)",
    "edge_work": "高处临边作业(风险)",
}
STATE_COLOR = {
    "no_edge": "#2fd982",
    "edge_work": "#ff4242",
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


def build_height_event(run_dir: Path, alert_idx: int = 0,
                       location: str = "") -> AlertEvent:
    """读取某次 run 的结果, 生成第 alert_idx 个告警的 AlertEvent。"""
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

    edge_seg = next((s for s in segs if s["state"] == "edge_work"), None)
    zones = data.get("config", {}).get("zones", [])
    zone_names = "、".join(z.get("name", "高处临边作业区") for z in zones) or "高处临边作业区"

    parts = []
    if edge_seg:
        parts.append(f"监控视频第 {edge_seg['start_s']:.1f} 秒,"
                     f"检测到人员进入「{zone_names}」进行高处作业。")
        dur = round(alert_t - edge_seg["start_s"], 1)
        parts.append(f"人员在临边区域持续作业约 {dur} 秒后,"
                     f"于第 {alert_t:.1f} 秒触发高处临边告警。")
    else:
        parts.append(f"于第 {alert_t:.1f} 秒检测到人员在「{zone_names}」进行高处临边作业。")
    parts.append("高处临边作业存在坠落风险, 作业人员须正确佩戴并挂设安全带、"
                 "确保临边防护(护栏 / 安全网)到位, 严禁无防护临边作业。")
    description = "".join(parts)

    evidence = []
    shot = alert.get("screenshot")
    if shot and (run_dir / "violations" / shot).exists():
        evidence.append(Evidence(run_dir / "violations" / shot,
                                 f"告警时刻(第 {alert_t:.1f} 秒):人员高处临边作业"))
    annotated = run_dir / "annotated.mp4"
    assets = run_dir / "report_assets"
    clear_seg = next((s for s in segs if s["state"] == "no_edge"
                      and (s["end_s"] - s["start_s"]) >= 0.4), None)
    if annotated.exists() and clear_seg:
        mid = (clear_seg["start_s"] + clear_seg["end_s"]) / 2
        img = _grab_frame(annotated, mid, assets / f"clear_{int(mid)}.jpg")
        if img:
            evidence.append(Evidence(img, f"安全状态(第 {mid:.1f} 秒):临边区无人作业"))

    cfg = data.get("config", {})
    params = [
        ("临边作业区", zone_names),
        ("区域数量", str(len(zones))),
        ("判定基准点", "脚底中点" if cfg.get("anchor") == "foot" else "框中心"),
        ("临边告警延时(秒)", str(cfg.get("persist_alert", "—"))),
        ("视频分辨率", f"{data.get('width')}×{data.get('height')}"),
        ("帧率", f"{fps:.1f} fps"),
    ]

    return AlertEvent(
        module="height", kind="edge_violation",
        title="高处作业临边",
        message="检测到人员高处临边作业, 请确认安全带与临边防护到位!",
        description=description, severity="high", location=location,
        time_seconds=alert_t, frame_idx=alert.get("frame_idx", 0),
        evidence=evidence, timeline=timeline,
        advice=[
            "立即确认作业人员是否正确佩戴并挂设安全带 / 安全绳。",
            "核查临边防护(护栏、挡脚板、安全网)是否齐全有效。",
            "确认该高处作业是否已办理作业许可、是否有专人监护。",
        ],
        params=params,
    )
