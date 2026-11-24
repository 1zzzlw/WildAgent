"""在应用启动或命令行入口显式创建模型和检索资源。"""
from loguru import logger

from agent.runtime import AgentRuntime, agent_runtime
from agent.llm.client import create_llm
from agent.rag.resources import create_spec_loader


class AgentResources(AgentRuntime):
    """一次明确创建的一组资源，供应用启动与离线知识维护使用。"""

    def __init__(self):
        self.model_factory = create_llm
        self.spec_loader = self._create_spec_loader()
        self.llm = create_llm(enable_thinking=False)
        self.thinking_llm = create_llm(enable_thinking=True, streaming=True)

    @staticmethod
    def _create_spec_loader():
        return create_spec_loader()


def initialize_agent_resources() -> None:
    if agent_runtime.spec_loader is not None:
        return
    resources = AgentResources()
    agent_runtime.spec_loader = resources.spec_loader
    agent_runtime.llm = resources.llm
    agent_runtime.thinking_llm = resources.thinking_llm
    agent_runtime.model_factory = resources.model_factory
    logger.info("Agent 模型与知识库资源初始化完成")


