import unittest
from unittest.mock import Mock

from app.spec.loader import RAGSpecLoader
from app.spec.query_planner import apply_llm_rewrite, build_query_plan


class QueryPlannerTest(unittest.TestCase):
    def test_build_plan_resolves_commercial_alias_without_inventing_facts(self):
        catalog = {
            "retail_building": {
                "aliases": {"沿街商铺", "storefront"},
                "filters": {"doc_type": "building_type", "entity_type": "building"},
                "constraints": {"commercial_identity"},
            },
        }
        plan = build_query_plan(
            "生成一个沿街商铺，检查雨棚和橱窗",
            alias_catalog=catalog,
        )

        self.assertEqual(plan.metadata_filter["entity_name"], "retail_building")
        self.assertEqual(plan.metadata_filter["doc_type"], "building_type")
        self.assertIn("storefront", plan.aliases)
        self.assertIn("composition", plan.topics)
        self.assertIn("assembly", plan.topics)

    def test_explicit_filter_wins_over_inferred_component_type(self):
        plan = build_query_plan(
            "阳台 parentWall",
            {"doc_type": "building_type", "entity_type": "building"},
        )

        self.assertEqual(plan.metadata_filter["doc_type"], "building_type")
        self.assertEqual(plan.metadata_filter["entity_type"], "building")
        self.assertNotIn("entity_name", plan.metadata_filter)
        self.assertIn("host", plan.constraints)

    def test_llm_rewrite_keeps_raw_query_and_uses_whitelist_metadata(self):
        plan = apply_llm_rewrite("社区商铺不要阳台", "改查社区商业 composition")

        self.assertIn("社区商铺不要阳台", plan.rewritten_query)
        self.assertEqual(plan.source, "llm+deterministic")
        self.assertNotIn("entity_name", plan.metadata_filter)

    def test_loader_retrieve_many_uses_rewritten_query_and_filter(self):
        collection = Mock()
        collection.count.return_value = 1
        collection.query.return_value = {
            "documents": [["commercial composition"]],
            "metadatas": [[{
                "content_hash": "commercial",
                "entity_name": "community_commercial",
                "doc_type": "building_type",
            }]],
            "distances": [[0.1]],
        }
        loader = object.__new__(RAGSpecLoader)
        loader._namespace = "test"
        loader._top_k = 1
        loader._last_results = []
        loader._retrieval_cache = {}
        loader._last_sync_stats = {"total": 1, "updated": 0, "deleted": 0}
        loader._alias_catalog = {
            "retail_building": {
                "aliases": {"沿街商铺", "storefront"},
                "filters": {"doc_type": "building_type", "entity_type": "building"},
                "constraints": set(),
            },
        }
        loader._get_collection = Mock(return_value=collection)

        results = loader.retrieve_many(["沿街商铺"], per_query=1)

        self.assertEqual(len(results), 1)
        query_text = collection.query.call_args.kwargs["query_texts"][0]
        self.assertIn("storefront", query_text)
        where = collection.query.call_args.kwargs["where"]
        self.assertIn({"entity_name": "retail_building"}, where["$and"])
        self.assertEqual(loader.last_query_plans[0]["source"], "deterministic")

    def test_index_enrichment_only_extracts_explicit_roles_and_constraints(self):
        from app.spec.loader import MarkdownChunker

        loader = object.__new__(MarkdownChunker)

        metadata = loader._enrich_index_metadata(
            {
                "entity_name": "retail_building",
                "topic": "composition",
                "keywords": ["沿街商铺", "storefront"],
            },
            "`required` 使用真实 parentWall；只有二层楼板存在时才添加阳台，检查碰撞。",
        )

        self.assertEqual(
            metadata["entity_aliases"],
            ["沿街商铺", "storefront", "retail_building"],
        )
        self.assertEqual(metadata["role_tags"], ["required", "conditional"])
        self.assertEqual(metadata["constraint_tags"], ["host", "level", "collision"])


if __name__ == "__main__":
    unittest.main()
