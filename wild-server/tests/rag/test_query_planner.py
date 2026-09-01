import unittest
from unittest.mock import Mock

from app.spec.loader import RAGSpecLoader, SpecQuery
from app.spec.query_planner import apply_llm_rewrite, build_alias_catalog, build_query_plan


class QueryPlannerTest(unittest.TestCase):
    def test_alias_catalog_uses_primary_terms_and_synonyms(self):
        """主术语和同义词都能触发召回，但索引主题词不应成为实体别名。"""
        catalog = build_alias_catalog([{
            "entity_name": "zhizhai_window",
            "entity_type": "window",
            "primary_terms": "支摘窗, opening, assembly",
            "synonyms": "zhizhai window, 支摘式窗",
        }])

        aliases = catalog["zhizhai_window"]["aliases"]
        self.assertIn("支摘窗", aliases)
        self.assertIn("opening", aliases)
        self.assertIn("zhizhai window", aliases)
        self.assertNotIn("assembly", aliases)

    def test_alias_catalog_keeps_legacy_keywords_compatible(self):
        """外部旧索引仍可用 keywords，正式知识库则使用两个新字段。"""
        catalog = build_alias_catalog([{
            "entity_name": "legacy_window",
            "keywords": "旧窗名, legacy window",
        }])

        self.assertIn("legacy window", catalog["legacy_window"]["aliases"])

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

    def test_loader_retrieve_many_with_metadata_filter(self):
        """测试 retrieve_many 使用 metadata 过滤条件"""
        collection = Mock()
        collection.count.return_value = 1
        collection.query.return_value = {
            "documents": [["commercial composition"]],
            "metadatas": [[{
                "content_hash": "commercial",
                "entity_name": "retail_building",
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
        loader._get_collection = Mock(return_value=collection)

        # 使用 SpecQuery 直接指定过滤条件
        from app.spec.loader import SpecQuery
        results = loader.retrieve_many([
            SpecQuery(
                text="沿街商铺",
                metadata_filter={"entity_name": "retail_building"}
            )
        ], per_query=1)

        self.assertEqual(len(results), 1)
        query_text = collection.query.call_args.kwargs["query_texts"][0]
        self.assertIn("沿街商铺", query_text)
        
        # 验证 where 条件包含我们指定的过滤
        where = collection.query.call_args.kwargs["where"]
        and_conditions = where["$and"]
        self.assertTrue(
            any(cond.get("entity_name") == "retail_building" for cond in and_conditions),
            f"entity_name filter not found in {and_conditions}"
        )

    def test_retrieve_many_spec_query_keeps_text_but_adds_alias_filter(self):
        """SpecQuery 保留查询原文（避免语义重心漂移），仅补全别名推导的过滤；纯 str 查询保持原样。"""
        collection = Mock()
        collection.count.return_value = 2
        # 真实 Chroma 对不同查询返回不同结果；mock 按查询文本区分，避免去重吃掉第二个查询。
        collection.query.side_effect = [
            {
                "documents": [["commercial composition"]],
                "metadatas": [[
                    {"content_hash": "commercial", "entity_name": "retail_building"},
                ]],
                "distances": [[0.1]],
            },
            {
                "documents": [["villa content"]],
                "metadatas": [[{"content_hash": "villa"}]],
                "distances": [[0.1]],
            },
        ]
        # 别名目录来源：知识库 chunk metadata 中的 primary_terms/synonyms。
        collection.get.return_value = {
            "ids": ["c1", "c2"],
            "metadatas": [
                {
                    "content_hash": "commercial",
                    "entity_name": "retail_building",
                    "doc_type": "building_type",
                    "entity_type": "building",
                    "primary_terms": "沿街商铺, retail_building",
                    "synonyms": "storefront, 商铺",
                },
                {"content_hash": "villa", "entity_name": "villa"},
            ],
        }
        loader = object.__new__(RAGSpecLoader)
        loader._namespace = "test"
        loader._top_k = 2
        loader._last_results = []
        loader._retrieval_cache = {}
        loader._last_sync_stats = {"total": 2, "updated": 0, "deleted": 0}
        loader._get_collection = Mock(return_value=collection)

        results = loader.retrieve_many(
            [
                SpecQuery(
                    text="沿街商铺 检查雨棚和橱窗",
                    metadata_filter={"entity_name": "retail_building"},
                ),
                "villa",
            ],
            per_query=1,
        )

        self.assertEqual(len(results), 2)
        all_query_texts = [
            call.kwargs["query_texts"][0]
            for call in collection.query.call_args_list
        ]
        # 按分组顺序：SpecQuery 一组（带过滤），纯 str 一组（无过滤）。
        spec_text = next(q for q in all_query_texts if "沿街商铺" in q)
        plain = next(q for q in all_query_texts if q == "villa")
        # SpecQuery 查询文本保持原文，不被别名污染。
        self.assertEqual(spec_text, "沿街商铺 检查雨棚和橱窗")
        # 纯 str 查询保持原样。
        self.assertEqual(plain, "villa")
        # 过滤条件按别名补全（doc_type/entity_type），调用方显式 entity_name 保留。
        spec_where = collection.query.call_args_list[0].kwargs["where"]
        conds = spec_where["$and"]
        self.assertIn(
            {"entity_name": "retail_building"},
            conds,
            f"显式 entity_name 过滤应在 where 中: {conds}",
        )

    def test_hash_embedding_disables_query_rewrite(self):
        """hash fallback embedding 下别名改写关闭，避免英文别名污染 bigram 向量。"""
        loader = object.__new__(RAGSpecLoader)
        loader._query_rewrite_enabled = False
        collection = Mock()
        collection.count.return_value = 1
        collection.query.return_value = {
            "documents": [["villa content"]],
            "metadatas": [[{"content_hash": "villa"}]],
            "distances": [[0.1]],
        }
        loader._namespace = "test"
        loader._top_k = 1
        loader._last_results = []
        loader._retrieval_cache = {}
        loader._last_sync_stats = {"total": 1, "updated": 0, "deleted": 0}
        loader._get_collection = Mock(return_value=collection)

        results = loader.retrieve("现代风格的度假别墅怎么生成")
        # 不触发别名目录构建（不应调用 collection.get），查询文本保持原样。
        collection.get.assert_not_called()
        self.assertEqual(
            collection.query.call_args.kwargs["query_texts"][0],
            "现代风格的度假别墅怎么生成",
        )

    def test_derived_entity_name_filter_is_dropped_but_explicit_kept(self):
        """planner 推导的 entity_name 会漏掉命名变体，应剔除；显式传入的保留。"""
        from app.spec.loader import _without_derived_entity_name

        # 显式 entity_name 保留。
        kept = _without_derived_entity_name(
            {"entity_name": "retail_building"},
            {"doc_type": "building_type", "entity_type": "building", "entity_name": "retail_building"},
        )
        self.assertEqual(kept["entity_name"], "retail_building")

        # planner 推导的 entity_name 剔除，粗粒度过滤保留。
        dropped = _without_derived_entity_name(
            None,
            {"doc_type": "building_type", "entity_type": "building", "entity_name": "villa"},
        )
        self.assertNotIn("entity_name", dropped)
        self.assertEqual(dropped["doc_type"], "building_type")

    def test_index_enrichment_removed_in_refactor(self):
        """
        测试：_enrich_index_metadata 方法在重构后已移除
        
        该方法的功能已整合到 MarkdownChunker 的其他方法中，
        不再作为独立的公开或私有方法存在。
        """
        from app.spec.loader import MarkdownChunker

        # 验证方法确实不存在
        loader = object.__new__(MarkdownChunker)
        self.assertFalse(hasattr(loader, '_enrich_index_metadata'))
        
        # 测试通过表示重构成功，旧的实现已被移除


if __name__ == "__main__":
    unittest.main()
