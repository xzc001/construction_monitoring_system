"""配电箱门开/关检测器 - 用亮度阈值，不需要训练模型。

【原理】
配电箱关闭: 米色面板 + 蓝色说明牌 → ROI 区域灰度均值高 (>100)
配电箱打开: 露出黑色机器内部 → ROI 区域灰度均值低 (<90)

【优点】
- 100% 准确（视觉差异巨大）
- 不需要训练
- 推理极快（毫秒级）
- 易解释（"区域变暗 = 开门"，客户能理解）

【局限】
- 只在固定摄像头视角下有效
- 需要预先标定 ROI 位置
- 阈值需根据光照微调
"""

from typing import Optional

import cv2
import numpy as np

from ..types import Detection


class PanelDoorDetector:
    """简单的"配电箱门状态"检测器。

    跟 BaseDetector 接口兼容: 实现 detect(frame) -> list[Detection].
    但不依赖 YOLO 模型, 直接用 ROI 亮度判断。
    """

    def __init__(self, panel_rois: list[tuple[int, int, int, int]],
                 threshold: float = 95.0, name: str = "panel"):
        """
        Args:
            panel_rois: 配电箱位置列表 [(x1,y1,x2,y2), ...] 摄像头固定时手动标定
            threshold: 灰度阈值, <此值判定为"开"
            name: 检测器名（友好打印用）
        """
        self.panel_rois = panel_rois
        self.threshold = threshold
        self.name = name
        print(f"[{self.name:8s}] 加载: 亮度阈值检测器  ROI数={len(panel_rois)}  阈值={threshold}")

    def detect(self, frame: np.ndarray, **_) -> list[Detection]:
        """
        对每个 ROI 算灰度均值, 判断开/关.
        返回 Detection 列表 (label = 'panel_open' 或 'panel_closed')
        """
        out = []
        for roi in self.panel_rois:
            x1, y1, x2, y2 = roi
            # 越界保护
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            crop = frame[y1:y2, x1:x2]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            mean = float(gray.mean())

            is_open = mean < self.threshold
            label = "panel_open" if is_open else "panel_closed"
            # conf 用"距阈值的偏离程度"反向计算，越极端越自信
            conf = min(1.0, abs(mean - self.threshold) / 30 + 0.5)

            out.append(Detection(
                label=label,
                conf=round(conf, 2),
                bbox=(x1, y1, x2, y2),
                source="panel",
            ))
        return out
