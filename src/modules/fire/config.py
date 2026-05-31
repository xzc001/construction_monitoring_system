"""烟雾明火模块配置。与其它模块一致: 自包含 dataclass。"""

from dataclasses import dataclass


@dataclass
class FireConfig:
    fire_conf: float = 0.40          # 烟火模型置信度
    persist_alert: float = 1.0       # 烟火持续多少秒才告警
    state_grace: float = 1.0         # 状态时间迟滞宽限期(秒)
    include_fog: bool = False        # 是否把模型的 fog 类也当烟雾计入。默认关(防雾天/强光误报);
                                     # 对"浓烟糊屏"的火灾监控片可单独开启(这类弥漫浓烟常被标为 fog)。
    imgsz: int = 1280
    device: object = None
    model_path: object = None        # None = 用随仓库的 models/fire_smoke.pt
