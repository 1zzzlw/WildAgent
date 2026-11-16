class AccessDenied(PermissionError):
    """仓储事务内检测到归属冲突，禁止通过并发创建占用他人资料。"""


class AccountUnavailable(PermissionError):
    """账号已被封禁或删除。"""


class BlueprintLocked(PermissionError):
    """蓝图已锁定，所有身份都必须先解锁。"""


class QuotaExceeded(PermissionError):
    """普通用户的对应额度已用完。"""


class OperationConflict(ValueError):
    """同一操作标识被用于不同内容，或文档版本已经变化。"""
