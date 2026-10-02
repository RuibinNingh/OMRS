"""领域请求的稳定错误，普通 Web 启动无需可选协议依赖。"""


class RequestError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
