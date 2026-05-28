from __future__ import annotations

from typing import Any

from src.connectors.factory import ConnectorFactory
from src.models.tenant import TenantConfig


class TenantContext:
    def __init__(self, config: TenantConfig, factory: ConnectorFactory, debug_log: list[str] | None = None):
        self.config = config
        self._factory = factory
        self._debug_log: list[str] = debug_log if debug_log is not None else []

    @property
    def tenant_id(self) -> str:
        return self.config.tenant_id

    def get_connector(self, interface_name: str) -> Any:
        return self._factory.resolve(interface_name)

    def append_debug(self, msg: str) -> None:
        self._debug_log.append(msg)

    def get_debug_log(self) -> list[str]:
        return self._debug_log

    @classmethod
    def from_config(cls, config: TenantConfig) -> TenantContext:
        factory = ConnectorFactory(config)
        return cls(config=config, factory=factory)
