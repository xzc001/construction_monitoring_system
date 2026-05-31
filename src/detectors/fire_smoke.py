"""烟雾明火检测器 —— 用 fire_smoke.pt。

原始类别: fire-smoke / fog / sol / fire / factory-smoke。
只保留与"烟火"相关的 fire / fire-smoke / factory-smoke,
归一为 fire(明火)/ smoke(烟雾);fog(雾)、sol(疑似强光)视为噪声丢弃。
"""

from pathlib import Path

from .base import BaseDetector
from ..types import Detection

_DEFAULT_WEIGHTS = Path(__file__).resolve().parents[2] / "models" / "fire_smoke.pt"


class FireSmokeDetector(BaseDetector):
    """识别 fire(明火) / smoke(烟雾)。"""

    def __init__(self, model_path: str | Path | None = None,
                 conf: float = 0.40, device=None, imgsz: int = 1280):
        super().__init__(model_path=str(model_path or _DEFAULT_WEIGHTS),
                         conf=conf, device=device, name="fire", imgsz=imgsz)

    def _wrap_box(self, label, conf, bbox):
        low = label.lower().replace("_", "-")
        if low == "fire":
            return Detection(label="fire", conf=conf, bbox=bbox, source="fire")
        if "smoke" in low:                      # fire-smoke / factory-smoke
            return Detection(label="smoke", conf=conf, bbox=bbox, source="fire")
        return None                             # fog / sol 等噪声类丢弃
