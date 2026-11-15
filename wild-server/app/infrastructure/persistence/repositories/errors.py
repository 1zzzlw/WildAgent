class AccessDenied(PermissionError):
    """仓储事务内检测到归属冲突，禁止通过并发创建占用他人资料。"""
