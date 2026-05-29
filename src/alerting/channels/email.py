"""邮件告警渠道 —— SMTP 发送, 正文含截图, 附件带 PDF 事故报告。"""

import smtplib
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Optional

from ..config import EmailConfig
from ..event import AlertEvent
from .base import Channel

SEVERITY_COLOR = {"low": "#2fa84f", "medium": "#e08e0b", "high": "#d92d20"}


def _html_body(event: AlertEvent, has_inline_img: bool) -> str:
    color = SEVERITY_COLOR.get(event.severity, "#d92d20")
    advice = "".join(f"<li>{a}</li>" for a in event.advice)
    img = ('<img src="cid:shot" style="max-width:100%;border:1px solid #ddd;'
           'border-radius:6px;margin-top:12px"/>' if has_inline_img else "")
    occur = event.occurred_at or f"视频内 {event.time_seconds:.2f} 秒"
    return f"""\
<div style="font-family:'Microsoft YaHei',sans-serif;max-width:640px;margin:0 auto">
  <div style="background:{color};color:#fff;padding:16px 20px;border-radius:8px 8px 0 0">
    <div style="font-size:13px;opacity:.85">施工现场 AI 安全告警</div>
    <div style="font-size:22px;font-weight:bold;margin-top:4px">⚠ {event.title}</div>
  </div>
  <div style="border:1px solid #eee;border-top:0;padding:20px;border-radius:0 0 8px 8px">
    <p style="font-size:15px;color:#111">{event.message}</p>
    <table style="font-size:14px;color:#333;border-collapse:collapse;margin-top:8px">
      <tr><td style="padding:4px 12px 4px 0;color:#888">监控点位</td><td>{event.location or '—'}</td></tr>
      <tr><td style="padding:4px 12px 4px 0;color:#888">发生时刻</td><td>{occur}</td></tr>
      <tr><td style="padding:4px 12px 4px 0;color:#888">来源模块</td><td>{event.module}</td></tr>
    </table>
    <p style="font-size:14px;color:#444;line-height:1.7;margin-top:12px">{event.description}</p>
    {f'<p style="font-size:14px;color:#888;margin:14px 0 4px">处置建议:</p><ul style="font-size:14px;color:#444;line-height:1.7">{advice}</ul>' if advice else ''}
    {img}
    <p style="font-size:12px;color:#aaa;margin-top:18px">本邮件由 AI 监控系统自动发送, 详情见附件事故报告。</p>
  </div>
</div>"""


class EmailChannel(Channel):
    name = "email"

    def __init__(self, cfg: EmailConfig):
        self.cfg = cfg

    def available(self) -> bool:
        return self.cfg.enabled and self.cfg.configured

    def send(self, event: AlertEvent, pdf: Optional[Path] = None) -> dict:
        if not self.available():
            return {"ok": False, "detail": "邮件未配置(缺少 SMTP 账号/授权码/收件人)"}

        cfg = self.cfg
        msg = MIMEMultipart("related")
        msg["Subject"] = f"【安全告警】{event.title}"
        msg["From"] = formataddr((cfg.sender_name, cfg.smtp_user))
        msg["To"] = ", ".join(cfg.recipients)

        # 内嵌截图
        shot = None
        for ev in event.evidence:
            if ev.image and Path(ev.image).exists():
                shot = Path(ev.image)
                break
        msg.attach(MIMEText(_html_body(event, shot is not None), "html", "utf-8"))
        if shot:
            with open(shot, "rb") as f:
                img = MIMEImage(f.read())
            img.add_header("Content-ID", "<shot>")
            msg.attach(img)
        # PDF 附件
        if pdf and Path(pdf).exists():
            with open(pdf, "rb") as f:
                att = MIMEApplication(f.read(), _subtype="pdf")
            att.add_header("Content-Disposition", "attachment",
                           filename="事故报告.pdf")
            msg.attach(att)

        try:
            if cfg.smtp_port == 465:
                server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=20)
            else:
                server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20)
                server.starttls()
            server.login(cfg.smtp_user, cfg.smtp_password)
            server.sendmail(cfg.smtp_user, cfg.recipients, msg.as_string())
            try:
                server.quit()   # 关闭失败不影响"已发送"结论
            except Exception:
                pass
            return {"ok": True, "detail": f"已发送至 {', '.join(cfg.recipients)}"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "detail": f"发送失败: {type(e).__name__}: {e}"}
