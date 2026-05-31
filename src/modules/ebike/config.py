"""电动车违规停放模块配置 —— 自包含 dataclass + 工厂方法, 与其它模块零耦合。

本质 = 在固定机位画面上把"电动车禁停区(消防/疏散通道等)"标成多边形,
电动车(着地点)落入该区域并持续即判定为违规停放。
"""

from dataclasses import dataclass, field

from ...rules.roi import RoiZone

Point = tuple[int, int]


@dataclass
class EbikeConfig:
    """电动车违规停放检测的全部参数。"""

    # 禁停区(摄像头固定时手动标定)。每个 zone:
    #   name    点位中文名(如 "消防通道禁停区")
    #   kind    no_park(禁停区·红·告警); 其它 kind 仅画区域不告警
    #   polygon 多边形顶点像素坐标 [(x,y), ...]
    zones: list[RoiZone] = field(default_factory=list)

    # --- 判定方式 ---
    anchor: str = "foot"             # 用车体框的哪个点判断在不在区域内:
                                     #   foot   = 车底中点(着地点, 默认)
                                     #   center = 框中心
    persist_alert: float = 1.5       # 车辆在禁停区内持续多少秒才正式告警(消除路过误报)
    state_grace: float = 1.0         # 状态时间迟滞宽限期(秒): 吸收瞬时漏检与边缘抖动

    # --- 推理参数 ---
    ebike_conf: float = 0.30         # 电动车检测置信度(yolov8n bicycle/motorcycle)
    imgsz: int = 1280
    device: object = None

    # ---------- 工厂方法 ----------
    @classmethod
    def from_roi_string(cls, roi_str: str, kind: str = "no_park",
                        name: str = "电动车禁停区", **kwargs) -> "EbikeConfig":
        """从矩形 "x1,y1,x2,y2"(可 ; 分隔多个)快速构造禁停区, 供网站上传分析用。"""
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
    def from_zone_specs(cls, specs: list[dict], **kwargs) -> "EbikeConfig":
        """从字典列表构造(用于 samples.json / 接口 JSON)。"""
        zones = [
            RoiZone(
                name=z.get("name", "电动车禁停区"),
                kind=z.get("kind", "no_park"),
                polygon=[(int(p[0]), int(p[1])) for p in z["polygon"]],
            )
            for z in specs
        ]
        return cls(zones=zones, **kwargs)
