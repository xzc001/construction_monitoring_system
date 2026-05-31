"""把一次未戴安全帽告警(run + alert)整理成通用 AlertEvent。

安全帽模块最懂如何描述自己的事故, 叙事/证据在这里生成;
告警层(报告/邮件/语音)只消费通用 AlertEvent。
"""

import json
from itertools import groupby
from pathlib import Path
from typing import Optional

import cv2

from ...alerting.event import AlertEvent, Evidence, TimelineSeg

STATE_CN = {
    "compliant": "合规(已戴安全帽)",
    "violation": "未戴安全帽",
}
STATE_COLOR = {
    "compliant": "#2fd982",
    "violation": "#ff4242",
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


def build_helmet_event(run_dir: Path, alert_idx: int = 0,
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
    note = alert.get("note", "")

    segs = _segments(data.get("timeline", []), fps)
    timeline = [TimelineSeg(label=STATE_CN.get(s["state"], s["state"]),
                            start_s=s["start_s"], end_s=s["end_s"],
                            color=STATE_COLOR.get(s["state"], "#888"))
                for s in segs]

    viol_seg = next((s for s in segs if s["state"] == "violation"), None)
    parts = []
    if viol_seg:
        parts.append(f"监控视频第 {viol_seg['start_s']:.1f} 秒起, "
                     f"检测到作业人员未佩戴安全帽" + (f"({note})。" if note else "。"))
        parts.append(f"持续未整改, 于第 {alert_t:.1f} 秒触发告警。")
    else:
        parts.append(f"于第 {alert_t:.1f} 秒检测到人员未佩戴安全帽。")
    parts.append("进入作业区域未佩戴安全帽存在头部受伤(高处坠物、磕碰)风险, "
                 "应立即制止并要求规范佩戴。")
    description = "".join(parts)

    evidence = []
    shot = alert.get("screenshot")
    if shot and (run_dir / "violations" / shot).exists():
        evidence.append(Evidence(run_dir / "violations" / shot,
                                 f"告警时刻(第 {alert_t:.1f} 秒):人员未佩戴安全帽"))
    annotated = run_dir / "annotated.mp4"
    assets = run_dir / "report_assets"
    comp_seg = next((s for s in segs if s["state"] == "compliant"
                     and (s["end_s"] - s["start_s"]) >= 0.4), None)
    if annotated.exists() and comp_seg:
        mid = (comp_seg["start_s"] + comp_seg["end_s"]) / 2
        img = _grab_frame(annotated, mid, assets / f"compliant_{int(mid)}.jpg")
        if img:
            evidence.append(Evidence(img, f"合规对照(第 {mid:.1f} 秒)"))

    cfg = data.get("config", {})
    params = [
        ("安全帽模型置信度", str(cfg.get("helmet_conf", "—"))),
        ("人体二次校验", "开" if cfg.get("require_person") else "关"),
        ("告警延时(秒)", str(cfg.get("persist_alert", "—"))),
        ("累计未戴帽检出帧次", str(data.get("cumulative", {}).get("no_helmet", "—"))),
        ("视频分辨率", f"{data.get('width')}×{data.get('height')}"),
        ("帧率", f"{fps:.1f} fps"),
    ]

    return AlertEvent(
        module="helmet", kind="no_helmet",
        title="未佩戴安全帽",
        message="检测到作业人员未佩戴安全帽,请立即规范佩戴!",
        description=description, severity="high", location=location,
        time_seconds=alert_t, frame_idx=alert.get("frame_idx", 0),
        evidence=evidence, timeline=timeline,
        advice=[
            "立即制止未戴帽作业, 要求人员规范佩戴安全帽后再进入作业区。",
            "核查现场安全帽配备与班前检查制度是否落实。",
            "对高频未戴帽点位增设入口提示与定期巡检。",
        ],
        params=params,
    )
