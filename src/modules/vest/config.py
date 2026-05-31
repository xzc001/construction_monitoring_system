"""未穿反光衣模块配置。与其它模块一致: 自包含 dataclass。"""

from dataclasses import dataclass


@dataclass
class VestConfig:
    person_conf: float = 0.35        # 人体检测置信度
    vest_conf: float = 0.40          # PPE 反光衣模型置信度
    require_person: bool = True      # 未穿反光衣框是否必须落在某人体框内
    min_person_coverage: float = 0.25  # 框被人体框覆盖的最小比例
    persist_alert: float = 1.0       # 未穿反光衣持续多少秒才告警
    state_grace: float = 1.0         # 状态时间迟滞宽限期(秒)
    imgsz: int = 1280
    device: object = None
    model_path: object = None        # None = 用随仓库的 models/ppe_vest.pt
