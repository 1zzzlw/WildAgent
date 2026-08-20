import unittest
from types import SimpleNamespace

from scripts.deploy.deployment_preflight import select_smoke_response_text


class DeploymentPreflightTest(unittest.TestCase):
    def test_prefers_normal_content(self):
        response = SimpleNamespace(
            content="WILD_OK",
            additional_kwargs={"reasoning_content": "internal"},
            response_metadata={"finish_reason": "stop"},
        )

        self.assertEqual(select_smoke_response_text(response), ("WILD_OK", "content"))

    def test_accepts_reasoning_only_provider_response(self):
        response = SimpleNamespace(
            content="",
            additional_kwargs={"reasoning_content": "WILD_OK"},
            response_metadata={"finish_reason": "length"},
        )

        self.assertEqual(
            select_smoke_response_text(response),
            ("WILD_OK", "reasoning_content"),
        )

    def test_rejects_response_without_any_text(self):
        response = SimpleNamespace(
            content=[],
            additional_kwargs={},
            response_metadata={"finish_reason": "length"},
        )

        with self.assertRaisesRegex(
            AssertionError,
            r"content or reasoning_content.*finish_reason=length",
        ):
            select_smoke_response_text(response)


if __name__ == "__main__":
    unittest.main()
