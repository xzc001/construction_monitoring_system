"""告警分发器 —— 收到 AlertEvent, 生成报告并分发到已启用渠道。

目前已接渠道: 邮件(带 PDF 报告)。
后续可加: 语音(浏览器/服务器)、企业微信/钉钉/Bark 等, 在此注册即可。
"""

from pathlib import Path
from typing import Optional

from .channels.email import EmailChannel
from .config import AlertingConfig, load_config
from .event import AlertEvent
from .report import build_report


class AlertDispatcher:
    def __init__(self, config: Optional[AlertingConfig] = None):
        self.config = config or load_config()
        self.email = EmailChannel(self.config.email)

    # 渠道可用性(给前端按钮判断是否可点)
    def status(self) -> dict:
        return {"email": self.email.available()}

    def generate_report(self, event: AlertEvent, out_pdf: Path,
                        report_no: str = "", generated_at: str = "") -> Path:
        return build_report(event, out_pdf, report_no, generated_at)

    def dispatch(self, event: AlertEvent, pdf: Optional[Path] = None) -> dict:
        """执行所有已启用的告警动作, 返回每个渠道的结果。"""
        results = {}
        if self.email.available():
            results["email"] = self.email.send(event, pdf=pdf)
        else:
            results["email"] = {"ok": False, "detail": "未启用"}
        return results
