"""建筑设计审核节点入口（含审核后的路由）。

流程：读取 GenerationState → ``interrupt`` 暂停等待人工批准 / 修订 → 写回
``design_review_status`` 与对应设计字段；``route_design_review`` 据此决定回
``compile``（建筑）/ ``skeleton``（物件）/ 方案链。
具体用例位于 ``design_flow.review``。
"""

from app.agent.design_flow.review import design_review, route_design_review

__all__ = ["design_review", "route_design_review"]
