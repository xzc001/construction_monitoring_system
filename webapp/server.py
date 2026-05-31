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
from src.modules.intrusion import IntrusionConfig, IntrusionPipeline
from src.modules.intrusion.incident import build_intrusion_event
from src.modules.helmet import HelmetConfig, HelmetPipeline
from src.modules.helmet.incident import build_helmet_event
from src.modules.smoking import SmokingConfig, SmokingPipeline
from src.modules.smoking.incident import build_smoking_event
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
    {
        "id": "intrusion",
        "name": "危险区域闯入",
        "tagline": "多边形电子围栏, 人员闯禁区才告警, 警戒区仅提示",
        "status": "online",
        "metrics": [
            {"label": "判定方式", "value": "电子围栏 + 脚点归属"},
            {"label": "区域分级", "value": "禁区 / 警戒 / 监控"},
            {"label": "误报抑制", "value": "持续时长确认"},
        ],
        "href": "/intrusion",
    },
    {
        "id": "helmet",
        "name": "未戴安全帽识别",
        "tagline": "自训练 YOLO 直接判定戴帽/未戴帽, 人体二次校验滤假阳",
        "status": "online",
        "metrics": [
            {"label": "判定方式", "value": "安全帽 YOLO + 人体校验"},
            {"label": "类别", "value": "已戴 / 未戴"},
            {"label": "误报抑制", "value": "持续时长 + 时间迟滞"},
        ],
        "href": "/helmet",
    },
    {
        "id": "smoking",
        "name": "违规吸烟检测",
        "tagline": "香烟 YOLO + 人脸/上半身校验, 滤掉塔吊管道误报",
        "status": "online",
        "metrics": [
            {"label": "判定方式", "value": "香烟 YOLO + 上半身校验"},
            {"label": "类别", "value": "cigarette"},
            {"label": "误报抑制", "value": "框小 + 靠人 + 持续"},
        ],
        "href": "/smoking",
    },
]

STATE_CN = {
    # 配电箱模块
    "closed": "门已关 · 合规",
    "open_attended": "维修中 · 人员值守",
    "open_unattended": "无人值守 · 门未关",
    # 危险区域闯入模块
    "clear": "安全 · 无人闯入",
    "warning": "警戒 · 接近危险区",
    "intrusion": "闯入 · 危险区域有人",
    # 未戴安全帽模块
    "compliant": "合规 · 已戴安全帽",
    "violation": "违规 · 未戴安全帽",
    # 违规吸烟模块
    "no_smoking": "未见吸烟",
    "smoking": "违规 · 检测到吸烟",
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


# 每个模块如何从样本/上传参数构造自己的流水线对象。
# 新增模块 = 在此加一个分支(以及 EVENT_BUILDERS / MODULES / 前端页面), 各模块互不影响。
def build_pipeline_for_sample(s: dict):
    """根据样本清单里的 module 字段, 构造对应模块的流水线对象。"""
    module = s.get("module", "panel")
    if module == "panel":
        cfg = PanelConfig.from_roi_string(
            s["panel_roi"], threshold=s.get("threshold", 95.0),
            attended_grace=s.get("grace", 2.0), persist_alert=s.get("persist", 1.5))
        return PanelPipeline(cfg)
    if module == "intrusion":
        cfg = IntrusionConfig.from_zone_specs(
            s["zones"], persist_alert=s.get("persist", 1.5),
            state_grace=s.get("grace", 1.0))
        return IntrusionPipeline(cfg)
    if module == "helmet":
        cfg = HelmetConfig(
            helmet_conf=s.get("helmet_conf", 0.40),
            persist_alert=s.get("persist", 1.0),
            state_grace=s.get("grace", 1.0),
            require_person=s.get("require_person", True),
            min_person_coverage=s.get("min_coverage", 0.25))
        return HelmetPipeline(cfg)
    if module == "smoking":
        cfg = SmokingConfig(
            smoking_conf=s.get("smoking_conf", 0.50),
            persist_alert=s.get("persist", 1.0),
            state_grace=s.get("grace", 1.0),
            require_person=s.get("require_person", True))
        return SmokingPipeline(cfg)
    raise ValueError(f"未知模块: {module}")


def _run_pipeline(pipeline, video_path: Path, run: str, job_id: str = None):
    """通用: 跑任意模块的 process_video, 可选回传进度到 JOBS。"""
    def cb(i, total):
        if job_id:
            with _lock:
                JOBS[job_id]["progress"] = round(i / max(total, 1), 3)
    pipeline.process_video(video_path, RUNS / run, progress_cb=cb)


def _run_job(job_id: str, pipeline, video_path: Path, run: str):
    """后台线程: 跑任意模块流水线, 完成/失败写回 JOBS。"""
    try:
        _run_pipeline(pipeline, video_path, run, job_id)
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
        print(f"[样本] 首次生成预渲染结果: {s['id']} ({s.get('module','panel')}, "
              f"约 20-60 秒, 仅首次)...")
        try:
            _run_pipeline(build_pipeline_for_sample(s), video, run)
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
def get_samples(module: str | None = None):
    """内置样本清单。带 ?module=panel / intrusion 时只返回该模块的样本。"""
    out = []
    for s in load_samples():
        if module and s.get("module", "panel") != module:
            continue
        item = {k: s[k] for k in ("id", "title", "subtitle") if k in s}
        item["module"] = s.get("module", "panel")
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
    threading.Thread(target=_run_job,
                     args=(job_id, PanelPipeline(cfg), Path(tmp.name), run),
                     daemon=True).start()
    return {"job_id": job_id, "run": run}


@app.post("/api/intrusion/analyze")
async def intrusion_analyze(
    zone_roi: str = Form(...),
    kind: str = Form("no_entry"),
    name: str = Form("危险区域"),
    persist: float = Form(1.5),
    grace: float = Form(1.0),
    file: UploadFile = File(...),
):
    suffix = Path(file.filename or "upload.mp4").suffix or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    shutil.copyfileobj(file.file, tmp)
    tmp.close()
    try:
        cfg = IntrusionConfig.from_roi_string(
            zone_roi, kind=kind, name=name, persist_alert=persist, state_grace=grace)
    except Exception:
        raise HTTPException(400, "zone_roi 格式应为 x1,y1,x2,y2(多个用 ; 分隔)")

    job_id = uuid.uuid4().hex[:12]
    run = f"web_{job_id}"
    with _lock:
        JOBS[job_id] = {"status": "running", "progress": 0.0, "run": run}
    threading.Thread(target=_run_job,
                     args=(job_id, IntrusionPipeline(cfg), Path(tmp.name), run),
                     daemon=True).start()
    return {"job_id": job_id, "run": run}


@app.post("/api/helmet/analyze")
async def helmet_analyze(
    helmet_conf: float = Form(0.40),
    persist: float = Form(1.0),
    file: UploadFile = File(...),
):
    suffix = Path(file.filename or "upload.mp4").suffix or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    shutil.copyfileobj(file.file, tmp)
    tmp.close()
    cfg = HelmetConfig(helmet_conf=helmet_conf, persist_alert=persist)

    job_id = uuid.uuid4().hex[:12]
    run = f"web_{job_id}"
    with _lock:
        JOBS[job_id] = {"status": "running", "progress": 0.0, "run": run}
    threading.Thread(target=_run_job,
                     args=(job_id, HelmetPipeline(cfg), Path(tmp.name), run),
                     daemon=True).start()
    return {"job_id": job_id, "run": run}


@app.post("/api/smoking/analyze")
async def smoking_analyze(
    smoking_conf: float = Form(0.50),
    persist: float = Form(1.0),
    file: UploadFile = File(...),
):
    suffix = Path(file.filename or "upload.mp4").suffix or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    shutil.copyfileobj(file.file, tmp)
    tmp.close()
    cfg = SmokingConfig(smoking_conf=smoking_conf, persist_alert=persist)

    job_id = uuid.uuid4().hex[:12]
    run = f"web_{job_id}"
    with _lock:
        JOBS[job_id] = {"status": "running", "progress": 0.0, "run": run}
    threading.Thread(target=_run_job,
                     args=(job_id, SmokingPipeline(cfg), Path(tmp.name), run),
                     daemon=True).start()
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


# 各模块如何把一次告警整理成通用 AlertEvent(报告/邮件复用)。
# 新增模块时在此登记其 build_*_event 即可, 报告/邮件接口无需改动。
EVENT_BUILDERS = {
    "panel": build_panel_event,
    "intrusion": build_intrusion_event,
    "helmet": build_helmet_event,
    "smoking": build_smoking_event,
}


def _gen_report(run: str, alert_idx: int, location: str):
    run_dir = RUNS / run
    events_path = run_dir / "events.json"
    if not events_path.exists():
        raise HTTPException(404, f"结果不存在: {run}")
    module = json.loads(events_path.read_text(encoding="utf-8")).get("module", "panel")
    builder = EVENT_BUILDERS.get(module, build_panel_event)
    try:
        event = builder(run_dir, alert_idx, location=location or "演示点位")
    except ValueError as e:
        raise HTTPException(400, str(e))
    pdf = run_dir / "incident_report.pdf"
    now = datetime.now()
    report_no = f"{module.upper()}-{now:%Y%m%d}-{run[-4:]}"
    AlertDispatcher().generate_report(
        event, pdf, report_no=report_no, generated_at=now.strftime("%Y-%m-%d %H:%M"))
    return event, pdf


@app.post("/api/report")
def gen_report(run: str = Form(...), alert_idx: int = Form(0),
               location: str = Form("")):
    """生成事故报告 PDF(按 run 所属模块自动选叙事模板), 返回下载地址。"""
    _, pdf = _gen_report(run, alert_idx, location)
    return {"report_url": f"/media/{run}/{pdf.name}"}


@app.post("/api/panel/report")
def panel_report(run: str = Form(...), alert_idx: int = Form(0),
                 location: str = Form("")):
    """生成事故报告 PDF, 返回可下载地址(配电箱页历史接口, 等价于 /api/report)。"""
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


@app.get("/intrusion")
def intrusion_page():
    return FileResponse(STATIC / "intrusion.html")


@app.get("/helmet")
def helmet_page():
    return FileResponse(STATIC / "helmet.html")


@app.get("/smoking")
def smoking_page():
    return FileResponse(STATIC / "smoking.html")


app.mount("/media", StaticFiles(directory=str(RUNS)), name="media")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
