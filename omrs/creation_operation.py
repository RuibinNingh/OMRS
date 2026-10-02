"""可信领域的创建预留；客户端不能指定来源、预留身份或回调。"""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CreationOperation:
    identity: dict
    origin: dict
    operation_id: str
    digest: str
    validate: Callable
    save_artifacts: Callable

    def stamp(self):
        return {**self.origin, "operation_id": self.operation_id, "digest": self.digest}
