"""告警渠道基类。新增渠道(语音/企业微信/Bark...)实现 send() 即可。"""

from abc import ABC, abstractmethod

from ..event import AlertEvent


class Channel(ABC):
    name = "base"

    @abstractmethod
    def available(self) -> bool:
        """是否已正确配置、可用。"""
        ...

    @abstractmethod
    def send(self, event: AlertEvent) -> dict:
        """执行告警动作, 返回 {ok: bool, detail: str}。"""
        ...
