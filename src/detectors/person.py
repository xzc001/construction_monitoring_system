"""人体检测器 —— 用 ultralytics 自带 yolov8n.pt（COCO 第 0 类 person）。"""

from .base import BaseDetector
from ..types import Detection


class PersonDetector(BaseDetector):
    """只保留 COCO class id=0 (person) 的检测结果。"""

    def __init__(self, conf: float = 0.35, device=None, imgsz: int = 640):
        super().__init__(model_path="yolov8n.pt", conf=conf, device=device,
                         name="person", imgsz=imgsz)

    def detect(self, frame, **kwargs):
        # 强制 classes=[0]，让 ultralytics 内部就过滤掉非 person 类，省算力
        kwargs.setdefault("classes", [0])
        return super().detect(frame, **kwargs)

    def _wrap_box(self, label, conf, bbox):
        # 统一改名 'person'（虽然 COCO 本来就是 'person'，但保险起见）
        return Detection(label="person", conf=conf, bbox=bbox, source="person")
