"""未戴安全帽模块配置 —— 所有可调参数收纳在一个 dataclass 里。

网站后端 / CLI 都只需构造一个 HelmetConfig 传给 HelmetPipeline。
与配电箱/闯入模块一致: 一个自包含 dataclass, 与其它模块零耦合。
"""

from dataclasses import dataclass


@dataclass
class HelmetConfig:
    """未戴安全帽检测的全部参数。"""

    # --- 检测置信度 ---
    person_conf: float = 0.35        # 人体检测置信度(yolov8n)
    helmet_conf: float = 0.40        # 安全帽模型置信度(hardhat / no-hardhat)

    # --- 未戴帽框的人体二次校验(滤假阳: 帽形物体/背景) ---
    require_person: bool = True      # 未戴帽头框是否必须落在某个人体框内才算数
    min_person_coverage: float = 0.25  # 头框被人体框覆盖的最小比例

    # --- 告警时序 ---
    persist_alert: float = 1.0       # 未戴帽持续多少秒才正式告警(消除一闪而过)
    state_grace: float = 1.0         # 状态时间迟滞宽限期(秒): 吸收瞬时漏检, 时间轴不闪烁

    # --- 推理参数 ---
    imgsz: int = 1280                # 推理分辨率(1280 利于远景小目标)
    device: object = None            # None = 自动选 GPU/CPU
    model_path: object = None        # 安全帽权重路径; None = 用随仓库的 models/helmet_best.pt
