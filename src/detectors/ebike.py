"""电动车/自行车检测器 —— 用 ultralytics 自带 yolov8n.pt。

电动车在 COCO 里通常落在 motorcycle(3), 少数细车架落在 bicycle(1)。
两类统一归为 'ebike'(电动车), 供"违规停放"等模块使用。
"""

from .base import BaseDetector
from ..types import Detection


class EbikeDetector(BaseDetector):
    """保留 COCO bicycle(1)/motorcycle(3), 统一标为 ebike。"""

    def __init__(self, conf: float = 0.30, device=None, imgsz: int = 1280):
        super().__init__(model_path="yolov8n.pt", conf=conf, device=device,
                         name="ebike", imgsz=imgsz)

    def detect(self, frame, **kwargs):
        kwargs.setdefault("classes", [1, 3])     # 只跑自行车/摩托车两类, 省算力
        return super().detect(frame, **kwargs)

    def _wrap_box(self, label, conf, bbox):
        return Detection(label="ebike", conf=conf, bbox=bbox, source="ebike")
