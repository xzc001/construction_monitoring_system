"""把一次配电箱告警(run + alert)整理成通用 AlertEvent。

配电箱模块最懂如何描述自己的事故, 所以叙事/证据在这里生成;
告警层(报告/邮件)只消费通用 AlertEvent。
"""

import json
from itertools import groupby
from pathlib import Path
from typing import Optional

import cv2

from ...alerting.event import AlertEvent, Evidence, TimelineSeg

STATE_CN = {
    "closed": "门已关",
    "open_attended": "维修中(人员值守)",
    "open_unattended": "无人值守 门未关",
}
STATE_COLOR = {
    "closed": "#2fd982",
    "open_attended": "#ffb020",
    "open_unattended": "#ff4242",
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


def build_panel_event(run_dir: Path, alert_idx: int = 0,
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

    segs = _segments(data.get("timeline", []), fps)
    # 时间线(给报告画条)
    timeline = [TimelineSeg(label=STATE_CN.get(s["state"], s["state"]),
                            start_s=s["start_s"], end_s=s["end_s"],
                            color=STATE_COLOR.get(s["state"], "#888"))
                for s in segs]

    # 关键时刻
    open_seg = next((s for s in segs if s["state"] in
                     ("open_attended", "open_unattended")), None)
    attended = next((s for s in segs if s["state"] == "open_attended"), None)
    unattended = next((s for s in segs if s["state"] == "open_unattended"), None)
    alert_t = alert.get("time_seconds", 0.0)

    # 叙事描述
    parts = []
    if open_seg:
        parts.append(f"监控视频第 {open_seg['start_s']:.1f} 秒,配电箱箱门被打开。")
    if attended:
        parts.append(f"第 {attended['start_s']:.1f}–{attended['end_s']:.1f} 秒期间有维修人员在场作业,"
                     f"系统判定为合规作业,未告警。")
    if unattended:
        dur = round(alert_t - unattended["start_s"], 1)
        parts.append(f"第 {unattended['start_s']:.1f} 秒起,人员离开但箱门仍未关闭;"
                     f"持续无人值守约 {dur} 秒后,于第 {alert_t:.1f} 秒触发告警。")
    parts.append("配电箱长时间敞开且无人看管,存在触电、误操作及异物侵入风险,应立即处置。")
    description = "".join(parts)

    # 证据图: 告警截图 + 各状态代表帧
    evidence = []
    shot = alert.get("screenshot")
    if shot and (run_dir / "violations" / shot).exists():
        evidence.append(Evidence(run_dir / "violations" / shot,
                                 f"告警时刻(第 {alert_t:.1f} 秒):无人值守,门未关"))
    annotated = run_dir / "annotated.mp4"
    assets = run_dir / "report_assets"
    if annotated.exists():
        for s in segs:
            if s["state"] == "open_unattended":
                continue  # 已有告警截图
            mid = (s["start_s"] + s["end_s"]) / 2
            img = _grab_frame(annotated, mid, assets / f"{s['state']}_{int(mid)}.jpg")
            if img:
                evidence.append(Evidence(img,
                                         f"{STATE_CN.get(s['state'], s['state'])}"
                                         f"(第 {mid:.1f} 秒)"))

    # 数据附录
    cfg = data.get("config", {})
    params = [
        ("配电箱 ROI", str(cfg.get("panel_rois", "—"))),
        ("开门亮度阈值", str(cfg.get("threshold", "—"))),
        ("维修宽限期(秒)", str(cfg.get("attended_grace", "—"))),
        ("无人值守告警延时(秒)", str(cfg.get("persist_alert", "—"))),
        ("视频分辨率", f"{data.get('width')}×{data.get('height')}"),
        ("帧率", f"{fps:.1f} fps"),
    ]

    return AlertEvent(
        module="panel", kind="panel_open",
        title="配电箱无人值守(门未关)",
        message="检测到配电箱门开启且无人值守,请立即关闭配电箱!",
        description=description, severity="high", location=location,
        time_seconds=alert_t, frame_idx=alert.get("frame_idx", 0),
        evidence=evidence, timeline=timeline,
        advice=[
            "立即派员到现场关闭配电箱箱门。",
            "核查现场是否存在带电作业、是否符合操作规程。",
            "如属常态化问题,建议加装箱门门磁/限位开关,并纳入交接班检查。",
        ],
        params=params,
    )
