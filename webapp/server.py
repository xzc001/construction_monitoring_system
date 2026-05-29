"""施工现场 AI 监控 —— Web 展示后端 (FastAPI)。

启动:
    cd codes/common
    python -m uvicorn webapp.server:app --host 127.0.0.1 --port 8000
    浏览器打开 http://127.0.0.1:8000

提供:
    GET  /                      首页(能力矩阵)
    GET  /panel                 配电箱模块页
    GET  /api/modules           功能模块清单
    GET  /api/samples           内置演示样本
    GET  /api/result/{run}      某次分析结果(含时间轴/告警/视频地址)
    POST /api/panel/analyze     上传视频 → 后台分析, 返回 job_id
    GET  /api/jobs/{job_id}     轮询分析进度
    /media/...                  标注视频 + 告警截图静态托管
    /static/...                 前端资源

【新增模块指南】见项目根 README.md
"""

import json
import shutil
import sys
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from itertools import groupby
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                       # codes/common
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from datetime import datetime

from src.modules.panel import PanelConfig, PanelPipeline
from src.modules.panel.incident import build_panel_event
from src.alerting import AlertDispatcher
from webapp.media import ensure_h264

RUNS = ROOT / "runs"
RUNS.mkdir(exist_ok=True)
STATIC = HERE / "static"
SAMPLES_DIR = ROOT / "data" / "samples"

# ---------------- 元数据 ----------------

MODULES = [
    {
        "id": "panel",
        "name": "配电箱门未关监测",
        "tagline": "区分「有人维修」与「无人值守」, 只在真违规时告警",
        "status": "online",          # online | planned
        "metrics": [
            {"label": "判定方式", "value": "亮度阈值 + 人员值守"},
            {"label": "误报抑制", "value": "时间迟滞平滑"},
            {"label": "推理速度", "value": "~28 FPS"},
        ],
        "href": "/panel",
    },
    {"id": "helmet", "name": "未戴安全帽识别", "tagline": "自训练 YOLO 检测安全帽佩戴",
     "status": "planned", "metrics": [], "href": None},
    {"id": "smoking", "name": "违规吸烟检测", "tagline": "明火 / 吸烟行为识别",
     "status": "planned", "metrics": [], "href": None},
    {"id": "intrusion", "name": "危险区域闯入", "tagline": "多边形电子围栏 + 多色分级",
     "status": "planned", "metrics": [], "href": None},
]

STATE_CN = {
    "closed": "门已关 · 合规",
    "open_attended": "维修中 · 人员值守",
    "open_unattended": "无人值守 · 门未关",
}


def load_samples() -> list[dict]:
    manifest = SAMPLES_DIR / "samples.json"
    if not manifest.exists():
        return []
    return json.loads(manifest.read_text(encoding="utf-8"))


# ---------------- 任务管理 ----------------

JOBS: dict[str, dict] = {}
_lock = threading.Lock()


def _segments_from_timeline(timeline: list[str], fps: float) -> list[dict]:
    segs, idx = [], 0
    for state, group in groupby(timeline):
        n = len(list(group))
        segs.append({
            "state": state,
            "state_cn": STATE_CN.get(state, state),
            "start_frame": idx, "end_frame": idx + n - 1,
            "start_s": round(idx / fps, 2), "end_s": round((idx + n) / fps, 2),
            "frames": n,
        })
        idx += n
    return segs


def _build_result(run: str) -> dict:
    run_dir = RUNS / run
    events_path = run_dir / "events.json"
    if not events_path.exists():
        raise HTTPException(404, f"结果不存在: {run}")
    data = json.loads(events_path.read_text(encoding="utf-8"))

    annotated = run_dir / "annotated.mp4"
    if annotated.exists():
        ensure_h264(annotated)

    fps = data.get("fps", 25.0)
    alerts = []
    for a in data.get("alerts", []):
        shot = a.get("screenshot")
        alerts.append({
            "kind": a.get("kind"), "track_id": a.get("track_id"),
            "frame_idx": a.get("frame_idx"), "time_seconds": a.get("time_seconds"),
            "screenshot_url": f"/media/{run}/violations/{shot}" if shot else None,
        })
    return {
        "run": run, "module": data.get("module", "panel"),
        "video_url": f"/media/{run}/web.mp4",
        "fps": fps, "width": data.get("width"), "height": data.get("height"),
        "total_frames": data.get("total_frames"),
        "duration_s": round(data.get("total_frames", 0) / fps, 1) if fps else None,
        "elapsed_seconds": data.get("elapsed_seconds"),
        "n_alerts": data.get("n_alerts", 0),
        "cumulative": data.get("cumulative", {}),
        "segments": _segments_from_timeline(data.get("timeline", []), fps),
        "alerts": alerts,
    }


def _run_panel(video_path: Path, cfg: PanelConfig, run: str, job_id: str = None):
    def cb(i, total):
        if job_id:
            with _lock:
                JOBS[job_id]["progress"] = round(i / max(total, 1), 3)
    PanelPipeline(cfg).process_video(video_path, RUNS / run, progress_cb=cb)


def _run_panel_job(job_id: str, video_path: Path, cfg: PanelConfig, run: str):
    try:
        _run_panel(video_path, cfg, run, job_id)
        with _lock:
            JOBS[job_id].update(status="done", progress=1.0, run=run)
    except Exception as e:  # noqa: BLE001
        with _lock:
            JOBS[job_id].update(status="error", error=str(e))


def ensure_samples_ready():
    """启动时确保每个内置样本已生成预渲染结果(首次启动会跑一次, 之后秒开)。"""
    for s in load_samples():
        run = s["id"]
        if (RUNS / run / "events.json").exists():
            continue
        video = SAMPLES_DIR / s["video"]
        if not video.exists():
            print(f"[样本] 缺少源视频, 跳过: {video}")
            continue
        print(f"[样本] 首次生成预渲染结果: {s['id']} (约 20-40 秒, 仅首次)...")
        cfg = PanelConfig.from_roi_string(
            s["panel_roi"], threshold=s.get("threshold", 95.0),
            attended_grace=s.get("grace", 2.0), persist_alert=s.get("persist", 1.5))
        try:
            _run_panel(video, cfg, run)
            print(f"[样本] {s['id']} 就绪。")
        except Exception as e:  # noqa: BLE001
            print(f"[样本] 生成失败 {s['id']}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_samples_ready()
    yield


app = FastAPI(title="施工现场 AI 智能监控系统", lifespan=lifespan)

# ---------------- API ----------------

@app.get("/api/modules")
def get_modules():
    return MODULES


@app.get("/api/samples")
def get_samples():
    out = []
    for s in load_samples():
        item = {k: s[k] for k in ("id", "title", "subtitle") if k in s}
        item["run"] = s["id"]
        item["ready"] = (RUNS / s["id"] / "events.json").exists()
        out.append(item)
    return out


@app.get("/api/result/{run}")
def get_result(run: str):
    return _build_result(run)


@app.post("/api/panel/analyze")
async def analyze(
    panel_roi: str = Form(...),
    threshold: float = Form(95.0),
    grace: float = Form(2.0),
    persist: float = Form(1.5),
    file: UploadFile = File(...),
):
    suffix = Path(file.filename or "upload.mp4").suffix or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    shutil.copyfileobj(file.file, tmp)
    tmp.close()
    try:
        cfg = PanelConfig.from_roi_string(
            panel_roi, threshold=threshold, attended_grace=grace, persist_alert=persist)
    except Exception:
        raise HTTPException(400, "panel_roi 格式应为 x1,y1,x2,y2")

    job_id = uuid.uuid4().hex[:12]
    run = f"web_{job_id}"
    with _lock:
        JOBS[job_id] = {"status": "running", "progress": 0.0, "run": run}
    threading.Thread(target=_run_panel_job,
                     args=(job_id, Path(tmp.name), cfg, run), daemon=True).start()
    return {"job_id": job_id, "run": run}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with _lock:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job 不存在")
    return job


# ---------------- 告警动作(报告 / 邮件) ----------------

@app.get("/api/alerting/status")
def alerting_status():
    """各告警渠道是否已配置可用(前端据此启用按钮)。"""
    return AlertDispatcher().status()


def _gen_report(run: str, alert_idx: int, location: str):
    run_dir = RUNS / run
    if not (run_dir / "events.json").exists():
        raise HTTPException(404, f"结果不存在: {run}")
    try:
        event = build_panel_event(run_dir, alert_idx, location=location or "演示点位")
    except ValueError as e:
        raise HTTPException(400, str(e))
    pdf = run_dir / "incident_report.pdf"
    now = datetime.now()
    report_no = f"PANEL-{now:%Y%m%d}-{run[-4:]}"
    AlertDispatcher().generate_report(
        event, pdf, report_no=report_no, generated_at=now.strftime("%Y-%m-%d %H:%M"))
    return event, pdf


@app.post("/api/panel/report")
def panel_report(run: str = Form(...), alert_idx: int = Form(0),
                 location: str = Form("")):
    """生成事故报告 PDF, 返回可下载地址。"""
    _, pdf = _gen_report(run, alert_idx, location)
    return {"report_url": f"/media/{run}/{pdf.name}"}


@app.post("/api/alerting/send")
def alerting_send(run: str = Form(...), alert_idx: int = Form(0),
                  location: str = Form("")):
    """生成报告并通过已启用渠道(邮件)发送。"""
    event, pdf = _gen_report(run, alert_idx, location)
    results = AlertDispatcher().dispatch(event, pdf=pdf)
    return {"results": results, "report_url": f"/media/{run}/{pdf.name}"}


# ---------------- 页面 + 静态 ----------------

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/panel")
def panel_page():
    return FileResponse(STATIC / "panel.html")


app.mount("/media", StaticFiles(directory=str(RUNS)), name="media")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
