"""检测器抽象基类。

设计目标:
  - 所有 detector 实现统一接口 detect(frame) -> list[Detection]
  - 后续即使换不同的模型 (YOLOv8/v11/RT-DETR/PaddleDetection)，对 pipeline 透明
"""

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

from ..types import Detection


class BaseDetector(ABC):
    """所有 detector 的基类。子类只需重写 _wrap_box 把 ultralytics 输出转 Detection。"""

    def __init__(self, model_path: str | Path, conf: float = 0.35,
                 device: int | str | None = None, name: str = "base",
                 imgsz: int = 640):
        self.model_path = str(model_path)
        self.conf = conf
        self.imgsz = imgsz   # 推理输入分辨率，1280 适合远景小目标
        self.device = device if device is not None else (
            0 if torch.cuda.is_available() else "cpu"
        )
        self.name = name
        self.model = YOLO(self.model_path)
        # 友好打印
        print(f"[{self.name:8s}] 加载: {Path(model_path).name}  类别: {self.model.names}  imgsz={imgsz}")

    def detect(self, frame: np.ndarray, **predict_kwargs) -> list[Detection]:
        """对单帧推理，返回 Detection 列表（已按 self.conf 过滤）"""
        predict_kwargs.setdefault("imgsz", self.imgsz)
        r = self.model.predict(frame, device=self.device, conf=self.conf,
                               verbose=False, **predict_kwargs)[0]
        out = []
        for b in r.boxes:
            cls_id = int(b.cls[0])
            conf = float(b.conf[0])
            x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
            label = self.model.names[cls_id]
            det = self._wrap_box(label, conf, (x1, y1, x2, y2))
            if det is not None:
                out.append(det)
        return out

    @abstractmethod
    def _wrap_box(self, label: str, conf: float,
                  bbox: tuple[int, int, int, int]) -> Detection | None:
        """子类决定：把原始 YOLO 输出包成什么样的 Detection（也可能返回 None 过滤掉）"""
        ...
