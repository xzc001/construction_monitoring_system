"""高处作业临边模块配置 —— 所有可调参数收纳在一个 dataclass 里。

与危险区域闯入模块同构: 一个自包含 dataclass + 工厂方法, 与其它模块零耦合。
高处作业临边的本质 = 在固定机位画面上, 把"高处作业平台 / 临边区域"标成多边形,
人员(脚点)落入该区域并持续即判定为高处临边作业, 提示系挂安全带、远离边缘。
"""

from dataclasses import dataclass, field

from ...rules.roi import RoiZone

Point = tuple[int, int]


@dataclass
class HeightConfig:
    """高处作业临边检测的全部参数。"""

    # 临边作业区(摄像头固定时手动标定)。每个 zone:
    #   name    点位中文名(如 "外架临边作业区")
    #   kind    edge_work(临边作业区·红·告警); 其它 kind 仅画区域不告警
    #   polygon 多边形顶点像素坐标 [(x,y), ...]
    zones: list[RoiZone] = field(default_factory=list)

    # --- 判定方式 ---
    anchor: str = "foot"             # 用人体框的哪个点判断在不在区域内:
                                     #   foot   = 脚底中点(站平台/木板上时最准, 默认)
                                     #   center = 框中心
    persist_alert: float = 1.5       # 人员在临边区内持续多少秒才正式告警(消除路过误报)
    state_grace: float = 1.0         # 状态时间迟滞宽限期(秒): 吸收人体瞬时漏检与脚点抖动

    # --- 推理参数 ---
    person_conf: float = 0.35        # 人体检测置信度
    imgsz: int = 1280                # 推理分辨率(1280 利于远景小目标)
    device: object = None            # None = 自动选 GPU/CPU

    # ---------- 工厂方法 ----------
    @classmethod
    def from_roi_string(cls, roi_str: str, kind: str = "edge_work",
                        name: str = "高处临边作业区", **kwargs) -> "HeightConfig":
        """从矩形 "x1,y1,x2,y2"(可 ; 分隔多个)快速构造临边区, 供网站上传分析用。"""
        zones = []
        for idx, piece in enumerate(roi_str.split(";")):
            x1, y1, x2, y2 = map(int, piece.split(","))
            x1, x2 = sorted((x1, x2))
            y1, y2 = sorted((y1, y2))
            zone_name = name if idx == 0 else f"{name}{idx + 1}"
            zones.append(RoiZone(
                name=zone_name, kind=kind,
                polygon=[(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
            ))
        return cls(zones=zones, **kwargs)

    @classmethod
    def from_zone_specs(cls, specs: list[dict], **kwargs) -> "HeightConfig":
        """从字典列表构造(用于 samples.json / 接口 JSON):
            [{"name": "...", "kind": "edge_work", "polygon": [[x,y], ...]}, ...]
        """
        zones = [
            RoiZone(
                name=z.get("name", "高处临边作业区"),
                kind=z.get("kind", "edge_work"),
                polygon=[(int(p[0]), int(p[1])) for p in z["polygon"]],
            )
            for z in specs
        ]
        return cls(zones=zones, **kwargs)
