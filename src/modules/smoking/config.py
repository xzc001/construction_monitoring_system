"""违规吸烟模块配置 —— 所有可调参数收纳在一个 dataclass 里。

与配电箱/闯入/安全帽模块一致: 一个自包含 dataclass, 与其它模块零耦合。
"""

from dataclasses import dataclass


@dataclass
class SmokingConfig:
    """违规吸烟检测的全部参数。"""

    # --- 检测置信度 ---
    person_conf: float = 0.35        # 人体检测置信度(yolov8n)
    smoking_conf: float = 0.50       # 香烟模型置信度(默认偏高, 主动压低误报)

    # --- 香烟框的几何校验(吸烟模型误报多, 必须靠人 + 框小) ---
    require_person: bool = True      # 香烟框必须落在某人"上半身"才算数
    min_upper_coverage: float = 0.5  # 香烟框落在人体上半身(前 55% 高)的最小覆盖比
    max_cig_width_ratio: float = 0.30  # 香烟框宽度 / 人体框宽度 上限(过大=误报)

    # --- 告警时序 ---
    persist_alert: float = 1.0       # 吸烟持续多少秒才正式告警
    state_grace: float = 1.0         # 状态时间迟滞宽限期(秒): 吸收瞬时漏检, 时间轴不闪烁

    # --- 推理参数 ---
    imgsz: int = 1280
    device: object = None
    model_path: object = None        # 香烟权重; None = 用随仓库的 models/smoking_enos123_yolov11.pt
