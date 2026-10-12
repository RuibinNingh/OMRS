"""OMRS只读网关状态/连接测试；账户管理只在独立服务面板。"""
from .. import vault_lifecycle as lifecycle
from ..locking import write_lock
from . import service_config
from .gateway import GatewayClient


def status(vault):
    config = service_config.snapshot(vault)
    account = GatewayClient(config).status()
    with lifecycle.lease(vault, config.generation), write_lock():
        service_config.assert_current(vault, config)
        return {**account, 'connected': True, 'service': service_config.project(config)}
