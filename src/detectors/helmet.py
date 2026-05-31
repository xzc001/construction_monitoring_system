"""安全帽检测器 —— 用自训练 helmet_best.pt(类别 hardhat / no-hardhat)。

模型直接给出"头部戴帽 / 未戴帽"两类, 是头部级判定;
"未戴帽框是否真属于某个人体"由模块的 rules 层二次校验(滤假阳)。
"""

from pathlib import Path

from .base import BaseDetector
from ..types import Detection

# 随仓库提供的安全帽权重
_DEFAULT_WEIGHTS = Path(__file__).resolve().parents[2] / "models" / "helmet_best.pt"


class HelmetDetector(BaseDetector):
    """识别 'hardhat'(戴) → helmet, 'no-hardhat'(没戴) → no_helmet。"""

    def __init__(self, model_path: str | Path | None = None,
                 conf: float = 0.4, device=None, imgsz: int = 1280):
        super().__init__(model_path=str(model_path or _DEFAULT_WEIGHTS),
                         conf=conf, device=device, name="helmet", imgsz=imgsz)

    def _wrap_box(self, label, conf, bbox):
        lower = label.lower()
        if "no" in lower and "hardhat" in lower:
            normalized = "no_helmet"
        elif "hardhat" in lower or "helmet" in lower:
            normalized = "helmet"
        else:
            normalized = lower
        return Detection(label=normalized, conf=conf, bbox=bbox, source="helmet")
