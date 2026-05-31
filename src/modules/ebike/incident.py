"""把一次电动车违规停放告警(run + alert)整理成通用 AlertEvent。"""

import json
from itertools import groupby
from pathlib import Path
from typing import Optional

import cv2

from ...alerting.event import AlertEvent, Evidence, TimelineSeg

STATE_CN = {
    "no_violation": "正常(禁停区无电动车)",
    "illegal_park": "电动车违规停放",
}
STATE_COLOR = {
    "no_violation": "#2fd982",
    "illegal_park": "#ff4242",
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


def build_ebike_event(run_dir: Path, alert_idx: int = 0,
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

    seg = next((s for s in segs if s["state"] == "illegal_park"), None)
    zones = data.get("config", {}).get("zones", [])
    zone_names = "、".join(z.get("name", "电动车禁停区") for z in zones) or "电动车禁停区"

    parts = []
    if seg:
        parts.append(f"监控视频第 {seg['start_s']:.1f} 秒,"
                     f"检测到电动车停放在「{zone_names}」内。")
        dur = round(alert_t - seg["start_s"], 1)
        parts.append(f"车辆在禁停区内持续停放约 {dur} 秒后,"
                     f"于第 {alert_t:.1f} 秒触发违规停放告警。")
    else:
        parts.append(f"于第 {alert_t:.1f} 秒检测到电动车违规停放于「{zone_names}」。")
    parts.append("电动车违规停放(尤其占用消防/疏散通道、堆放充电)存在火灾与逃生风险, "
                 "应及时清理并引导至指定停放点充电。")
    description = "".join(parts)

    evidence = []
    shot = alert.get("screenshot")
    if shot and (run_dir / "violations" / shot).exists():
        evidence.append(Evidence(run_dir / "violations" / shot,
                                 f"告警时刻(第 {alert_t:.1f} 秒):电动车违规停放"))
    annotated = run_dir / "annotated.mp4"
    assets = run_dir / "report_assets"
    clear_seg = next((s for s in segs if s["state"] == "no_violation"
                      and (s["end_s"] - s["start_s"]) >= 0.4), None)
    if annotated.exists() and clear_seg:
        mid = (clear_seg["start_s"] + clear_seg["end_s"]) / 2
        img = _grab_frame(annotated, mid, assets / f"clear_{int(mid)}.jpg")
        if img:
            evidence.append(Evidence(img, f"正常状态(第 {mid:.1f} 秒):禁停区无车"))

    cfg = data.get("config", {})
    params = [
        ("禁停区", zone_names),
        ("区域数量", str(len(zones))),
        ("判定基准点", "车底中点" if cfg.get("anchor") == "foot" else "框中心"),
        ("违停告警延时(秒)", str(cfg.get("persist_alert", "—"))),
        ("视频分辨率", f"{data.get('width')}×{data.get('height')}"),
        ("帧率", f"{fps:.1f} fps"),
    ]

    return AlertEvent(
        module="ebike", kind="ebike_illegal_park",
        title="电动车违规停放",
        message="检测到电动车违规停放于禁停区, 请及时清理!",
        description=description, severity="medium", location=location,
        time_seconds=alert_t, frame_idx=alert.get("frame_idx", 0),
        evidence=evidence, timeline=timeline,
        advice=[
            "及时清理禁停区/消防通道内的电动车, 恢复通道畅通。",
            "引导车主到指定停放点并使用合规充电设施, 严禁飞线充电。",
            "如属高频违停点位, 建议增设物理隔离与声光提示。",
        ],
        params=params,
    )
