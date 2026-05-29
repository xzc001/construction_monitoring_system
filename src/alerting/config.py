"""告警配置加载 —— 从 config/alerting.yaml 读取(密钥不入库)。

优先读 config/alerting.yaml(被 .gitignore, 放真实密钥);
不存在时回退到 config/alerting.example.yaml(入库模板, 密钥为空)。
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]   # codes/common
CONFIG_DIR = ROOT / "config"


@dataclass
class EmailConfig:
    enabled: bool = False
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""        # QQ 邮箱填"授权码", 非登录密码
    sender_name: str = "施工现场AI监控"
    recipients: list[str] = field(default_factory=list)

    @property
    def configured(self) -> bool:
        return bool(self.smtp_user and self.smtp_password and self.recipients)


@dataclass
class AlertingConfig:
    email: EmailConfig = field(default_factory=EmailConfig)


def _load_raw() -> dict:
    real = CONFIG_DIR / "alerting.yaml"
    example = CONFIG_DIR / "alerting.example.yaml"
    path = real if real.exists() else example
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_config() -> AlertingConfig:
    raw = _load_raw()
    e = (raw.get("email") or {})
    email = EmailConfig(
        enabled=e.get("enabled", False),
        smtp_host=e.get("smtp_host", "smtp.qq.com"),
        smtp_port=int(e.get("smtp_port", 465)),
        smtp_user=e.get("smtp_user", ""),
        smtp_password=e.get("smtp_password", ""),
        sender_name=e.get("sender_name", "施工现场AI监控"),
        recipients=list(e.get("recipients") or []),
    )
    return AlertingConfig(email=email)
