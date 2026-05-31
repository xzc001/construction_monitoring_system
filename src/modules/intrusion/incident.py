"""把一次危险区域闯入告警(run + alert)整理成通用 AlertEvent。

闯入模块最懂如何描述自己的事故, 所以叙事/证据在这里生成;
告警层(报告/邮件/语音)只消费通用 AlertEvent。
"""

import json
from itertools import groupby
from pathlib import Path
from typing import Optional

import cv2

from ...alerting.event import AlertEvent, Evidence, TimelineSeg

STATE_CN = {
    "clear": "安全(无人闯入)",
    "warning": "警戒(接近危险区)",
    "intrusion": "危险区域有人闯入",
}
STATE_COLOR = {
    "clear": "#2fd982",
    "warning": "#ffb020",
    "intrusion": "#ff4242",
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
    """从视频抓取某时刻一帧存成图。"""
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


def build_intrusion_event(run_dir: Path, alert_idx: int = 0,
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

    # 关键时刻: 进入禁区那一段
    intrusion_seg = next((s for s in segs if s["state"] == "intrusion"), None)
    zones = data.get("config", {}).get("zones", [])
    zone_names = "、".join(z.get("name", "危险区域") for z in zones) or "危险区域"

    parts = []
    if intrusion_seg:
        parts.append(f"监控视频第 {intrusion_seg['start_s']:.1f} 秒,"
                     f"检测到人员进入「{zone_names}」。")
        dur = round(alert_t - intrusion_seg["start_s"], 1)
        parts.append(f"人员在禁区内持续停留约 {dur} 秒后,"
                     f"于第 {alert_t:.1f} 秒触发闯入告警。")
    else:
        parts.append(f"于第 {alert_t:.1f} 秒检测到人员闯入「{zone_names}」。")
    parts.append("无关人员进入划定危险区域存在人身安全风险(如机械伤害、坠落、触电等),"
                 "应立即制止并撤离。")
    description = "".join(parts)

    # 证据图: 告警截图 + 一帧"安全(无人)"对照
    evidence = []
    shot = alert.get("screenshot")
    if shot and (run_dir / "violations" / shot).exists():
        evidence.append(Evidence(run_dir / "violations" / shot,
                                 f"告警时刻(第 {alert_t:.1f} 秒):人员闯入禁区"))
    annotated = run_dir / "annotated.mp4"
    assets = run_dir / "report_assets"
    clear_seg = next((s for s in segs if s["state"] == "clear"
                      and (s["end_s"] - s["start_s"]) >= 0.4), None)
    if annotated.exists() and clear_seg:
        mid = (clear_seg["start_s"] + clear_seg["end_s"]) / 2
        img = _grab_frame(annotated, mid, assets / f"clear_{int(mid)}.jpg")
        if img:
            evidence.append(Evidence(img, f"安全状态(第 {mid:.1f} 秒):区域内无人"))

    # 数据附录
    cfg = data.get("config", {})
    params = [
        ("危险区域", zone_names),
        ("区域数量", str(len(zones))),
        ("判定基准点", "脚底中点" if cfg.get("anchor") == "foot" else "框中心"),
        ("闯入告警延时(秒)", str(cfg.get("persist_alert", "—"))),
        ("视频分辨率", f"{data.get('width')}×{data.get('height')}"),
        ("帧率", f"{fps:.1f} fps"),
    ]

    return AlertEvent(
        module="intrusion", kind="roi_intrusion",
        title="危险区域闯入",
        message="检测到人员闯入划定危险区域,请立即撤离!",
        description=description, severity="high", location=location,
        time_seconds=alert_t, frame_idx=alert.get("frame_idx", 0),
        evidence=evidence, timeline=timeline,
        advice=[
            "立即通过现场广播 / 喊话制止人员,引导其撤离危险区域。",
            "核查该人员是否为授权作业人员、是否已办理作业票。",
            "如属高频闯入点位,建议增设物理隔离(护栏 / 警示带)与声光报警。",
        ],
        params=params,
    )
