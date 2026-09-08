"""Embedding 调用层的自适应分批回归测试。

覆盖：不同网关/模型对单批条数限制不同（如阿里云百炼限 20、部分兼容网关更小），
遇到"输入类 400"时自动把本批减半重试，而不是让整批报废；
网络类错误（超时/连接）不在此层消化，仍由 _embed_batch 重试。
"""
import unittest
from unittest.mock import patch

from app.spec.loader import OpenAICompatibleEmbeddingFunction


class _BadRequestError(Exception):
    """模拟 OpenAI SDK 的 BadRequestError。"""


class _ResponseItem:
    def __init__(self, index: int, embedding: list[float]):
        self.index = index
        self.embedding = embedding


class _Response:
    def __init__(self, count: int):
        self.data = [_ResponseItem(index, [float(index), 0.0, 0.0, 0.0]) for index in range(count)]


class _MarkedResponse:
    """向量首位携带文本身份（texts 形如 "c<序号>"），用于核对无重复/无遗漏。"""

    def __init__(self, texts: list[str]):
        self.data = [
            _ResponseItem(index, [float(int(text[1:]))])
            for index, text in enumerate(texts)
        ]


class AdaptiveBatchEmbedTest(unittest.TestCase):
    def make_function(self, reject_greater_than: int) -> OpenAICompatibleEmbeddingFunction:
        function = OpenAICompatibleEmbeddingFunction(
            api_key="k", base_url="https://example.invalid", model_name="m",
            batch_size=8, timeout=5, max_retries=1,
        )
        client = object()

        def fake_create(model, input, encoding_format):  # noqa: A002 - 模拟 SDK 签名
            if len(input) > reject_greater_than:
                raise _BadRequestError(
                    "Error code: 400 - {'error': {'code': 'InvalidParameter', "
                    "'message': 'The input is invalid, too many items'}}"
                )
            return _Response(len(input))

        function._get_client = lambda: client  # type: ignore[method-assign]
        function._embed_with_heartbeat = (  # type: ignore[method-assign]
            lambda client_, input_, attempt: fake_create(client_, input_, "float")
        )
        return function

    def test_batch_is_halved_when_gateway_rejects_item_count(self):
        function = self.make_function(reject_greater_than=4)
        texts = [f"chunk-{index}" for index in range(10)]

        with patch("app.spec.loader.logger") as log:
            vectors = function(texts)

        self.assertEqual(len(vectors), 10)
        # 前 8 条被拒绝一次后减半为 4 条/批，最终 10 条全部向量化。
        warnings = [call.args[0] for call in log.warning.call_args_list]
        self.assertTrue(any("减半" in message for message in warnings))

    def test_all_texts_vectorized_exactly_once_after_halving(self):
        """多次减半后每个文本恰好向量化一次（按文本身份核对，与切分顺序无关）。"""
        function = self.make_function(reject_greater_than=3)
        texts = [f"c{index}" for index in range(10)]
        # 8 条首段会被拒两次（8→4→2）才成功，后续切片沿用减半后的 2 条/批。

        def heartbeat(client_, input_, attempt):
            if len(input_) > 3:
                raise _BadRequestError(
                    "Error code: 400 - {'error': {'code': 'InvalidParameter', "
                    "'message': 'The input is invalid, too many items'}}"
                )
            return _MarkedResponse(input_)

        function._embed_with_heartbeat = heartbeat  # type: ignore[method-assign]

        vectors = function(texts)

        self.assertEqual(len(vectors), 10)
        self.assertEqual(sorted(int(vector[0]) for vector in vectors), list(range(10)))

    def test_network_timeout_is_not_swallowed_by_halving(self):
        function = self.make_function(reject_greater_than=4)
        function._embed_with_heartbeat = (  # type: ignore[method-assign]
            lambda client_, input_, attempt: (_ for _ in ()).throw(
                TimeoutError("Request timed out.")
            )
        )
        with self.assertRaises(TimeoutError):
            function(["a", "b", "c", "d"])


if __name__ == "__main__":
    unittest.main()
