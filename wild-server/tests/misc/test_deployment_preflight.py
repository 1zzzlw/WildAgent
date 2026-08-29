import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.deploy.deployment_preflight import run_preflight, select_smoke_response_text


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

    @patch("scripts.deploy.deployment_preflight.run_embedding_smoke")
    @patch("scripts.deploy.deployment_preflight.run_model_smoke")
    @patch("scripts.deploy.deployment_preflight.validate_image_and_config")
    def test_offline_preflight_does_not_call_providers(
        self,
        validate_image_and_config,
        run_model_smoke,
        run_embedding_smoke,
    ):
        run_preflight()

        validate_image_and_config.assert_called_once_with(
            require_provider_credentials=False
        )
        run_model_smoke.assert_not_called()
        run_embedding_smoke.assert_not_called()

    @patch("scripts.deploy.deployment_preflight.run_embedding_smoke")
    @patch("scripts.deploy.deployment_preflight.run_model_smoke")
    @patch("scripts.deploy.deployment_preflight.validate_image_and_config")
    def test_live_preflight_calls_both_providers(
        self,
        validate_image_and_config,
        run_model_smoke,
        run_embedding_smoke,
    ):
        run_preflight(live_providers=True)

        validate_image_and_config.assert_called_once_with(
            require_provider_credentials=True
        )
        run_model_smoke.assert_called_once_with()
        run_embedding_smoke.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
