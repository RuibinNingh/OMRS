"""框选连接的稳定错误。"""
class ServiceError(ValueError):
    def __init__(self,message,code='boxdetect',status=400):
        super().__init__(message)
        self.code,self.status=code,status
