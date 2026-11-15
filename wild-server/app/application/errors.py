"""业务错误分类；状态码与响应格式由 API 层映射。"""


class ApplicationError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail
