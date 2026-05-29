"""事故报告 PDF 生成。

用 reportlab 内置的 CID 中文字体 STSong-Light, 无需附带字体文件, 跨平台可用。
时间线状态条用 PIL 画成图片嵌入。
"""

import tempfile
from pathlib import Path

from PIL import Image as PILImage, ImageDraw
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from .event import AlertEvent

# 注册中文字体(reportlab 自带, 简体中文)
_FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(_FONT))


def _styles():
    ss = getSampleStyleSheet()
    base = ss["Normal"]
    return {
        "title": ParagraphStyle("t", parent=base, fontName=_FONT, fontSize=20,
                                leading=26, alignment=TA_CENTER, spaceAfter=4),
        "sub": ParagraphStyle("s", parent=base, fontName=_FONT, fontSize=9,
                              leading=12, alignment=TA_CENTER, textColor=colors.grey),
        "h2": ParagraphStyle("h2", parent=base, fontName=_FONT, fontSize=13,
                             leading=18, spaceBefore=12, spaceAfter=6,
                             textColor=colors.HexColor("#b35900")),
        "body": ParagraphStyle("b", parent=base, fontName=_FONT, fontSize=10.5,
                               leading=17),
        "cap": ParagraphStyle("c", parent=base, fontName=_FONT, fontSize=8.5,
                              leading=11, alignment=TA_CENTER, textColor=colors.grey),
        "cell": ParagraphStyle("ce", parent=base, fontName=_FONT, fontSize=10,
                               leading=14),
    }


def _timeline_image(event: AlertEvent, out: Path, w=900, h=70) -> Path:
    """把三态时间线画成一张条带图。"""
    img = PILImage.new("RGB", (w, h), "#0f141d")
    d = ImageDraw.Draw(img)
    if not event.timeline:
        img.save(out)
        return out
    total = max(s.end_s for s in event.timeline) or 1
    bar_top, bar_bot = 18, h - 18
    for seg in event.timeline:
        x1 = int(seg.start_s / total * w)
        x2 = int(seg.end_s / total * w)
        d.rectangle([x1, bar_top, x2, bar_bot], fill=seg.color)
    # 告警时刻竖线
    ax = int(event.time_seconds / total * w)
    d.line([(ax, 4), (ax, h - 4)], fill="#ffffff", width=2)
    img.save(out)
    return out


def _label_table(rows, styles, col_w):
    data = [[Paragraph(k, styles["cell"]), Paragraph(str(v), styles["cell"])]
            for k, v in rows]
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


SEVERITY_CN = {"low": "一般", "medium": "较重", "high": "严重"}


def build_report(event: AlertEvent, out_pdf: Path,
                 report_no: str = "", generated_at: str = "") -> Path:
    """根据 AlertEvent 生成事故报告 PDF, 返回路径。"""
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    st = _styles()
    story = []
    content_w = A4[0] - 36 * mm

    # 抬头
    story.append(Paragraph("施工现场安全事故告警报告", st["title"]))
    meta = []
    if report_no:
        meta.append(f"报告编号 {report_no}")
    if generated_at:
        meta.append(f"生成时间 {generated_at}")
    story.append(Paragraph(" · ".join(meta) or "AI 自动生成", st["sub"]))
    story.append(Spacer(1, 8))

    # 一、事故概要
    story.append(Paragraph("一、事故概要", st["h2"]))
    occur = event.occurred_at or f"视频内 {event.time_seconds:.2f} 秒"
    story.append(_label_table([
        ("事故类型", event.title),
        ("严重等级", SEVERITY_CN.get(event.severity, event.severity)),
        ("发生时刻", occur),
        ("监控点位", event.location or "—"),
        ("来源模块", event.module),
    ], st, [content_w * 0.28, content_w * 0.72]))

    # 二、事故描述
    story.append(Paragraph("二、事故描述", st["h2"]))
    story.append(Paragraph(event.description or event.message, st["body"]))

    # 三、现场证据
    if event.evidence:
        story.append(Paragraph("三、现场证据", st["h2"]))
        for ev in event.evidence:
            if ev.image and Path(ev.image).exists():
                try:
                    iw, ih = PILImage.open(ev.image).size
                    disp_w = min(content_w, 150 * mm)
                    disp_h = disp_w * ih / iw
                    story.append(Image(str(ev.image), width=disp_w, height=disp_h))
                    if ev.caption:
                        story.append(Paragraph(ev.caption, st["cap"]))
                    story.append(Spacer(1, 6))
                except Exception:
                    pass

    # 四、事件时间线
    if event.timeline:
        story.append(Paragraph("四、事件时间线", st["h2"]))
        tmp = Path(tempfile.gettempdir()) / f"_tl_{out_pdf.stem}.png"
        _timeline_image(event, tmp)
        story.append(Image(str(tmp), width=content_w, height=content_w * 70 / 900))
        legend = "  ".join(f"{s.label}({s.start_s:.1f}-{s.end_s:.1f}s)"
                           for s in event.timeline)
        story.append(Paragraph(legend, st["cap"]))

    # 五、处置建议
    if event.advice:
        story.append(Paragraph("五、处置建议", st["h2"]))
        for i, a in enumerate(event.advice, 1):
            story.append(Paragraph(f"{i}. {a}", st["body"]))

    # 六、数据附录
    if event.params:
        story.append(Paragraph("六、检测数据附录", st["h2"]))
        story.append(_label_table(event.params, st,
                                  [content_w * 0.35, content_w * 0.65]))

    story.append(Spacer(1, 18))
    story.append(Paragraph("本报告由 AI 监控系统自动生成, 仅供安全管理参考。"
                           "现场处置请以实际核查为准。", st["cap"]))

    SimpleDocTemplate(
        str(out_pdf), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="施工现场安全事故告警报告",
    ).build(story)
    return out_pdf
