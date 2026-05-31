"""吸烟检测器 —— 用 Enos-123 YOLOv11(单类 'cigarette')。

【误报较多】模型容易把工地远景里的管道/线缆/塔吊/标牌等细长或矩形物体
误识别成 cigarette。本类默认把 conf 提到 0.5 作第一道过滤;
更关键的"烟头必须靠近某人上半身/脸 + 框足够小"几何约束在模块 rules 层做。
"""

from pathlib import Path

from .base import BaseDetector
from ..types import Detection

_DEFAULT_WEIGHTS = (Path(__file__).resolve().parents[2] / "models"
                    / "smoking_enos123_yolov11.pt")


class SmokingDetector(BaseDetector):
    """识别 cigarette(单类)。"""

    def __init__(self, model_path: str | Path | None = None,
                 conf: float = 0.5, device=None, imgsz: int = 1280):
        super().__init__(model_path=str(model_path or _DEFAULT_WEIGHTS),
                         conf=conf, device=device, name="smoking", imgsz=imgsz)

    def _wrap_box(self, label, conf, bbox):
        return Detection(label="cigarette", conf=conf, bbox=bbox, source="smoking")
