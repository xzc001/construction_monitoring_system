"""反光衣检测器 —— 用 PPE 模型 ppe_vest.pt。

原始类别含 Hardhat/Mask/Person/Safety Vest/NO-Safety Vest/... ,
本检测器只取反光衣相关两类, 归一为 vest(已穿)/ no_vest(未穿)。
人体二次校验由模块 rules 层完成。
"""

from pathlib import Path

from .base import BaseDetector
from ..types import Detection

_DEFAULT_WEIGHTS = Path(__file__).resolve().parents[2] / "models" / "ppe_vest.pt"


class VestDetector(BaseDetector):
    """识别 Safety Vest → vest, NO-Safety Vest → no_vest(其余类别丢弃)。"""

    def __init__(self, model_path: str | Path | None = None,
                 conf: float = 0.40, device=None, imgsz: int = 1280):
        super().__init__(model_path=str(model_path or _DEFAULT_WEIGHTS),
                         conf=conf, device=device, name="vest", imgsz=imgsz)

    def _wrap_box(self, label, conf, bbox):
        low = label.lower()
        if "no" in low and "vest" in low:
            return Detection(label="no_vest", conf=conf, bbox=bbox, source="vest")
        if "vest" in low:
            return Detection(label="vest", conf=conf, bbox=bbox, source="vest")
        return None
