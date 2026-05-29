"""配电箱模块配置对象 —— 所有可调参数收纳在一个 dataclass 里。

网站后端 / CLI 都只需构造一个 PanelConfig 传给 PanelPipeline。
"""

from dataclasses import dataclass, field


@dataclass
class PanelConfig:
    """配电箱"无人值守"检测的全部参数。"""

    # 配电箱在画面中的位置(摄像头固定时手动标定) [(x1,y1,x2,y2), ...]
    panel_rois: list[tuple[int, int, int, int]] = field(default_factory=list)

    # --- 门开/关判定 ---
    threshold: float = 95.0          # ROI 灰度均值 < 此值 = 门开(露出黑色内部)

    # --- 维修中 / 无人值守 判定 ---
    safety_zone_ratio: float = 2.0   # 维修安全区相对门框向外扩大的倍数
    attended_grace: float = 2.0      # "维修中"宽限期(秒): 有人出现后保持多久,
                                     # 吸收人体漏检 / 短暂走开, 消除状态闪烁
    persist_alert: float = 1.5       # 门开且确实无人持续多少秒才正式告警

    # --- 推理参数 ---
    person_conf: float = 0.35        # 人体检测置信度
    imgsz: int = 1280                # 推理分辨率(1280 利于远景小目标)
    device: object = None            # None = 自动选 GPU/CPU

    @classmethod
    def from_roi_string(cls, roi_str: str, **kwargs) -> "PanelConfig":
        """从 "x1,y1,x2,y2" 或 "x1,y1,x2,y2;x1,y1,x2,y2" 解析 ROI。"""
        rois = []
        for piece in roi_str.split(";"):
            x1, y1, x2, y2 = map(int, piece.split(","))
            rois.append((x1, y1, x2, y2))
        return cls(panel_rois=rois, **kwargs)
