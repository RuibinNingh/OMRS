"""仅稳定中文错误；禁止向 HTTP 或审计传播异常原文。"""
class ApiError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)
