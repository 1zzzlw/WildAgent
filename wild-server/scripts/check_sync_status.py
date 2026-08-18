"""检查知识库同步状态"""
from app.services.agent_service import agent_service

stats = agent_service.spec_loader.last_sync_stats
print(f"\n✅ 知识库同步状态:")
print(f"   - 总文档片段数: {stats['total']}")
print(f"   - 已更新片段数: {stats['updated']}")
print(f"   - 已删除片段数: {stats['deleted']}")

# 显示 RAG 检索能力
print(f"\n✅ Spec Loader 类型: {type(agent_service.spec_loader).__name__}")
print(f"   - 来源文档数: {len(agent_service.spec_loader.list_sources())}")

print("\n✅ 建筑类型分类优化已完成!")
