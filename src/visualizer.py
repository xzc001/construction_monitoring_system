"""可视化层 —— 画框、ROI、告警 HUD。

【中文支持】cv2.putText 不支持中文（显示 ????）, 我们用 PIL 渲染中文文本
再贴回到 cv2 图上。

【多色 ROI】支持 ROI.kind 决定颜色:
  no_entry           红色 (严重 - 禁止进入)
  approach_warning   黄色 (警告 - 接近危险)
  general            青色 (普通 - 监控区)
"""

from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .rules.roi import RoiZone
from .types import Alert, Detection


# BGR 颜色 (cv2 用 BGR)
COLOR_PERSON = (255, 128, 0)            # 蓝
COLOR_HELMET = (0, 200, 0)              # 绿
COLOR_NO_HELMET_RAW = (180, 105, 255)   # 粉
COLOR_NO_HELMET_CONFIRMED = (0, 0, 255) # 红
COLOR_CIGARETTE_RAW = (200, 200, 200)   # 灰
COLOR_CIGARETTE_CONFIRMED = (0, 0, 255) # 红
COLOR_ALERT_BANNER = (0, 0, 255)        # 红

# ROI 多色分级 (按 kind)
ROI_COLORS = {
    "no_entry":         (0, 0, 255),    # 红 BGR - 严重(禁区)
    "approach_warning": (0, 255, 255),  # 黄 BGR - 警告(警戒区)
    "safe":             (0, 210, 0),    # 绿 BGR - 安全(人行通道, 不告警)
    "general":          (255, 255, 0),  # 青 BGR - 普通(监控区)
}
ROI_COLOR_DEFAULT = (0, 255, 255)       # 黄

# ROI 类型中文名
ROI_KIND_CN = {
    "no_entry":         "禁区",
    "approach_warning": "警戒区",
    "safe":             "安全通道",
    "general":          "监控区",
}

# 告警类型中文名
ALERT_KIND_CN = {
    "no_helmet":     "未戴安全帽",
    "smoking":       "违规吸烟",
    "roi_intrusion": "闯入禁区",
    "panel_open":    "配电柜门未关",
}


# ---------- 中文字体支持 ----------
_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}
_FONT_PATH = "C:/Windows/Fonts/msyh.ttc"   # 微软雅黑

def _get_font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _FONT_CACHE:
        try:
            _FONT_CACHE[size] = ImageFont.truetype(_FONT_PATH, size, index=0)
        except Exception:
            _FONT_CACHE[size] = ImageFont.load_default()
    return _FONT_CACHE[size]


def put_chinese(img, text: str, pos: tuple[int, int], color, size: int = 16,
                bg: tuple = None):
    """用 PIL 在 cv2 BGR 图上画中文。
    img: BGR numpy 数组 (cv2 格式)
    color: BGR 颜色
    bg: 文字背景色 BGR，None 表示透明
    """
    # cv2 BGR → PIL RGB
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font = _get_font(size)
    # 颜色 BGR → RGB
    rgb = (color[2], color[1], color[0])
    if bg is not None:
        bg_rgb = (bg[2], bg[1], bg[0])
        # 估算文字宽高
        bbox = draw.textbbox(pos, text, font=font)
        # 加点 padding
        bbox = (bbox[0] - 2, bbox[1] - 2, bbox[2] + 4, bbox[3] + 2)
        draw.rectangle(bbox, fill=bg_rgb)
    draw.text(pos, text, font=font, fill=rgb)
    # 回写到原 img (in-place)
    out = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    img[:] = out


# ---------- 标签 / 框 ----------

def draw_box(img, det: Detection, color, label: str = None,
             conf_in_label: bool = True, label_size: int = 16):
    """画检测框 + 中文标签."""
    x1, y1, x2, y2 = det.bbox
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
    if label is None:
        label = det.label
    text = f"{label} {det.conf:.2f}" if conf_in_label else label
    # 用 PIL 画中文 + 背景
    put_chinese(img, text, (x1 + 2, max(y1 - label_size - 6, 0)),
                color=(255, 255, 255), size=label_size, bg=color)


def draw_thin_box(img, det: Detection, color):
    """轻量级"原始检测"的细线框"""
    x1, y1, x2, y2 = det.bbox
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 1)


# ---------- ROI ----------

def draw_roi(img, roi: RoiZone):
    """画 ROI 多边形, 颜色按 kind 自动选."""
    color = ROI_COLORS.get(roi.kind, ROI_COLOR_DEFAULT)
    pts = np.array(roi.polygon, dtype=np.int32)
    # 半透明填充
    overlay = img.copy()
    cv2.fillPoly(overlay, [pts], color)
    cv2.addWeighted(overlay, 0.18, img, 0.82, 0, img)
    # 边线 (粗 + 双线)
    cv2.polylines(img, [pts], isClosed=True, color=color, thickness=3)
    # 中文名字标签 (左上角)
    kind_cn = ROI_KIND_CN.get(roi.kind, roi.kind)
    label = f"{kind_cn}: {roi.name}"
    put_chinese(img, label, (int(pts[0][0]) + 4, int(pts[0][1]) + 4),
                color=(255, 255, 255), size=18, bg=color)


# ---------- 顶部告警条 ----------

def draw_alert_banner(img, alerts: list[Alert]):
    """触发告警时, 画红色边框 + 顶部条."""
    if not alerts:
        return
    h, w = img.shape[:2]
    # 6 像素红边框
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), COLOR_ALERT_BANNER, 6)
    # 顶部红色背景条
    cv2.rectangle(img, (0, 0), (w, 48), COLOR_ALERT_BANNER, -1)
    # 中文告警文本
    msg_parts = []
    for a in alerts[:3]:
        kind_cn = ALERT_KIND_CN.get(a.kind, a.kind)
        msg_parts.append(f"{kind_cn} #{a.track_id}")
    msg = " | ".join(msg_parts)
    if len(alerts) > 3:
        msg += f"  +{len(alerts)-3} more"
    put_chinese(img, f"!! 违规告警: {msg}", (10, 12),
                color=(255, 255, 255), size=22)


# ---------- 底部 HUD ----------

# HUD 字段名翻译
HUD_KEY_CN = {
    "p": "人",
    "h": "戴帽",
    "no_h": "未戴",
    "cig": "烟",
    "roi": "闯入",
    "panel": "柜门",
}


def draw_hud(img, frame_idx: int, total_frames: int,
             counts: dict, total_alerts: int):
    """画面底部 HUD."""
    h, w = img.shape[:2]
    # 翻译 key
    items = "  ".join(f"{HUD_KEY_CN.get(k, k)}:{v}" for k, v in counts.items())
    text = f"帧 {frame_idx}/{total_frames}   {items}   告警:{total_alerts}"
    # 半透明黑色背景
    overlay = img.copy()
    cv2.rectangle(overlay, (0, h - 36), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.7, img, 0.3, 0, img)
    put_chinese(img, text, (10, h - 30),
                color=(0, 255, 255), size=18)
