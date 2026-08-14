"""diagnostics Schema 的单元测试。"""

import unittest

from app.agent.diagnostics import (
    VALIDATOR_VERSION,
    NodeDiagnostic,
    ValidationSnapshot,
    blueprint_fingerprint,
)


class BlueprintFingerprintTest(unittest.TestCase):
    def test_fingerprint_is_stable_across_key_order(self):
        first = blueprint_fingerprint({"geometry": {"elements": []}, "meta": {"name": "a"}})
        second = blueprint_fingerprint({"meta": {"name": "a"}, "geometry": {"elements": []}})
        self.assertEqual(first, second)

    def test_fingerprint_changes_with_content(self):
        first = blueprint_fingerprint({"meta": {"name": "a"}})
        second = blueprint_fingerprint({"meta": {"name": "b"}})
        self.assertNotEqual(first, second)

    def test_none_blueprint_has_stable_sentinel(self):
        self.assertEqual(blueprint_fingerprint(None), "none")


class ValidationSnapshotTest(unittest.TestCase):
    def test_matches_when_fingerprint_and_version_agree(self):
        blueprint = {"meta": {"name": "a"}, "geometry": {"elements": []}}
        snapshot = ValidationSnapshot(
            blueprint_fingerprint=blueprint_fingerprint(blueprint),
            validator_version=VALIDATOR_VERSION,
        )
        self.assertTrue(snapshot.matches(blueprint))

    def test_matches_false_when_blueprint_changed(self):
        snapshot = ValidationSnapshot(
            blueprint_fingerprint=blueprint_fingerprint({"meta": {"name": "a"}}),
        )
        self.assertFalse(snapshot.matches({"meta": {"name": "b"}}))

    def test_matches_false_when_validator_version_stale(self):
        blueprint = {"meta": {"name": "a"}}
        snapshot = ValidationSnapshot(
            blueprint_fingerprint=blueprint_fingerprint(blueprint),
            validator_version="0.9",
        )
        self.assertFalse(snapshot.matches(blueprint))


class NodeDiagnosticTest(unittest.TestCase):
    def test_to_dict_flattens_extra_fields(self):
        diag = NodeDiagnostic(node="skeleton", label="骨架", error=None, extra={"element_count": 3})
        payload = diag.to_dict()
        self.assertEqual(payload["node"], "skeleton")
        self.assertEqual(payload["element_count"], 3)
        self.assertNotIn("extra", payload)


if __name__ == "__main__":
    unittest.main()
