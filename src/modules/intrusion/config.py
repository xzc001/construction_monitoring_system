"""危险区域闯入模块配置 —— 所有可调参数收纳在一个 dataclass 里。

网站后端 / CLI 都只需构造一个 IntrusionConfig 传给 IntrusionPipeline。

设计与配电箱模块一致:一个自包含 dataclass + 工厂方法, 与其它模块零耦合。
"""

from dataclasses import dataclass, field

from ...rules.roi import RoiZone

Point = tuple[int, int]


@dataclass
class IntrusionConfig:
    """危险区域闯入检测的全部参数。"""

    # 监控区域(摄像头固定时手动标定)。每个 zone:
    #   name    点位中文名(如 "吊臂下方禁区")
    #   kind    no_entry(禁区·红·告警) / approach_warning(警戒区·黄·仅提示) / general(监控区·青)
    #   polygon 多边形顶点像素坐标 [(x,y), ...]
    zones: list[RoiZone] = field(default_factory=list)

    # --- 判定方式 ---
    anchor: str = "foot"             # 用人体框的哪个点判断在不在区域内:
                                     #   foot   = 脚底中点(站在地面区域时最准, 默认)
                                     #   center = 框中心
    persist_alert: float = 1.5       # 人员在禁区内持续多少秒才正式告警(消除路过误报)

    # --- 推理参数 ---
    person_conf: float = 0.35        # 人体检测置信度
    imgsz: int = 1280                # 推理分辨率(1280 利于远景小目标)
    device: object = None            # None = 自动选 GPU/CPU

    # ---------- 工厂方法 ----------
    @classmethod
    def from_roi_string(cls, roi_str: str, kind: str = "no_entry",
                        name: str = "危险区域", **kwargs) -> "IntrusionConfig":
        """从矩形 "x1,y1,x2,y2"(可 ; 分隔多个)快速构造禁区, 供网站上传分析用。

        矩形会展开成 4 顶点多边形。需要任意多边形时直接构造 zones。
        """
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
    def from_zone_specs(cls, specs: list[dict], **kwargs) -> "IntrusionConfig":
        """从字典列表构造(用于 samples.json / 接口 JSON):
            [{"name": "...", "kind": "no_entry", "polygon": [[x,y], ...]}, ...]
        """
        zones = [
            RoiZone(
                name=z.get("name", "危险区域"),
                kind=z.get("kind", "no_entry"),
                polygon=[(int(p[0]), int(p[1])) for p in z["polygon"]],
            )
            for z in specs
        ]
        return cls(zones=zones, **kwargs)
