"""
AI SafePath — Safety Decision Engine Tests

10 test scenarios covering:
  1. Clear path → STRAIGHT
  2. Pole center, left safe → LEFT
  3. Pole center, left blocked, right safe → RIGHT
  4. All paths blocked → STOP
  5. Vehicle approaching → STOP
  6. Low confidence → WAIT
  7. Maps route available → navigation context
  8. Maps failure → graceful fallback
  9. Malformed vision JSON → safe fallback
  10. Vehicle with unknown distance → STOP
"""

import sys
import os
import json
import unittest

# Add server dir to path so we can import the engine
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server"))

from safety_engine import (
    SafetyDecisionEngine,
    SafetyDecision,
    Action,
    validate_perception,
    validate_decision,
)

FIXTURES_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "scenarios.json")


def load_fixtures() -> list[dict]:
    with open(FIXTURES_PATH) as f:
        return json.load(f)


class TestSafetyDecisionEngine(unittest.TestCase):
    """Test the deterministic safety decision engine."""

    @classmethod
    def setUpClass(cls):
        cls.engine = SafetyDecisionEngine(confidence_threshold=0.45)
        cls.fixtures = load_fixtures()

    def test_01_clear_path(self):
        """Clear path → STRAIGHT"""
        f = self._fixture("test_01_clear_path")
        result = self.engine.decide(f["perception"])
        self.assertEqual(result.action, Action.STRAIGHT)
        self.assertIn("clear", result.reason.lower())
        self.assertGreaterEqual(result.confidence, 0.80)

    def test_02_pole_left_safe(self):
        """Pole center, left safe → LEFT"""
        f = self._fixture("test_02_pole_left_safe")
        result = self.engine.decide(f["perception"])
        self.assertEqual(result.action, Action.LEFT)
        self.assertIn("left", result.voice_instruction.lower())

    def test_03_pole_left_blocked_right_safe(self):
        """Pole center, left blocked, right safe → RIGHT"""
        f = self._fixture("test_03_pole_left_blocked_right_safe")
        result = self.engine.decide(f["perception"])
        self.assertEqual(result.action, Action.RIGHT)
        self.assertIn("right", result.voice_instruction.lower())

    def test_04_all_blocked(self):
        """All paths blocked → STOP"""
        f = self._fixture("test_04_all_blocked")
        result = self.engine.decide(f["perception"])
        self.assertEqual(result.action, Action.STOP)
        self.assertIn("stop", result.voice_instruction.lower())

    def test_05_vehicle_approaching(self):
        """Vehicle approaching → STOP"""
        f = self._fixture("test_05_vehicle_approaching")
        result = self.engine.decide(f["perception"])
        self.assertEqual(result.action, Action.STOP)
        self.assertIn("vehicle", result.voice_instruction.lower())
        self.assertIn("stop", result.voice_instruction.lower())

    def test_06_low_confidence(self):
        """Low confidence → WAIT"""
        f = self._fixture("test_06_low_confidence")
        result = self.engine.decide(f["perception"])
        self.assertEqual(result.action, Action.WAIT)
        self.assertIn("wait", result.voice_instruction.lower())

    def test_07_maps_route_available(self):
        """Maps route available → navigation context generated"""
        f = self._fixture("test_07_maps_route_available")
        result = self.engine.decide(f["perception"], f["navigation"])
        self.assertEqual(result.action, Action.STRAIGHT)
        ctx = result.navigation_context
        self.assertIn("current_step_instruction", ctx)
        self.assertIn("remaining_steps", ctx)
        self.assertGreater(ctx["remaining_steps"], 0)

    def test_08_maps_failure(self):
        """Maps failure → graceful fallback (no navigation context)"""
        f = self._fixture("test_08_maps_failure")
        result = self.engine.decide(f["perception"], f["navigation"])
        self.assertEqual(result.action, Action.STRAIGHT)
        # Navigation context should be empty since navigation is None
        self.assertEqual(result.navigation_context, {})

    def test_09_malformed_vision(self):
        """Malformed vision JSON → WAIT (validation catches missing fields)"""
        f = self._fixture("test_09_malformed_vision")
        errors = validate_perception(f["perception"])
        # Should have validation errors for missing fields
        self.assertTrue(len(errors) > 0, "Expected validation errors for malformed perception")
        # Engine should return WAIT when perception is incomplete
        result = self.engine.decide(f["perception"])
        self.assertEqual(result.action, Action.WAIT)

    def test_10_vehicle_unknown_distance(self):
        """Vehicle with unknown distance → STOP (conservative)"""
        f = self._fixture("test_10_vehicle_unknown_distance")
        result = self.engine.decide(f["perception"])
        self.assertEqual(result.action, Action.STOP)
        self.assertIn("vehicle", result.voice_instruction.lower())

    # ── helpers ──

    def _fixture(self, fixture_id: str) -> dict:
        for f in self.fixtures:
            if f["id"] == fixture_id:
                return f
        raise ValueError(f"Fixture not found: {fixture_id}")


class TestValidationFunctions(unittest.TestCase):
    """Test the perception and decision validation functions."""

    def test_validate_valid_perception(self):
        """Valid perception passes validation."""
        valid = {
            "scene_summary": "test",
            "objects": [],
            "left_path": {"clear": True, "risk": "LOW", "confidence": 0.9},
            "center_path": {"clear": True, "risk": "LOW", "confidence": 0.9},
            "right_path": {"clear": True, "risk": "LOW", "confidence": 0.9},
            "overall_risk": "LOW",
            "confidence": 0.9,
        }
        errors = validate_perception(valid)
        self.assertEqual(errors, [])

    def test_validate_missing_required_field(self):
        """Missing required field produces error."""
        invalid = {
            "scene_summary": "test",
            "objects": [],
            # missing left_path, center_path, etc.
        }
        errors = validate_perception(invalid)
        self.assertTrue(any("missing required field" in e for e in errors))

    def test_validate_invalid_risk_enum(self):
        """Invalid risk value produces error."""
        invalid = {
            "scene_summary": "test",
            "objects": [],
            "left_path": {"clear": True, "risk": "EXTREME", "confidence": 0.9},
            "center_path": {"clear": True, "risk": "LOW", "confidence": 0.9},
            "right_path": {"clear": True, "risk": "LOW", "confidence": 0.9},
            "overall_risk": "EXTREME",
            "confidence": 0.9,
        }
        errors = validate_perception(invalid)
        self.assertTrue(any("overall_risk" in e for e in errors))

    def test_validate_valid_decision(self):
        """Valid decision passes validation."""
        valid = {
            "action": "LEFT",
            "reason": "Pole ahead. Move left.",
            "confidence": 0.86,
            "timestamp": 1700000000.0,
        }
        errors = validate_decision(valid)
        self.assertEqual(errors, [])

    def test_validate_invalid_action(self):
        """Invalid action produces error."""
        invalid = {
            "action": "DIAGONAL",
            "reason": "test",
            "confidence": 0.8,
            "timestamp": 1700000000.0,
        }
        errors = validate_decision(invalid)
        self.assertTrue(any("action must be" in e for e in errors))


class TestDeterministicRules(unittest.TestCase):
    """Test that the engine always produces exactly one of the allowed actions."""

    ALLOWED_ACTIONS = {Action.LEFT, Action.RIGHT, Action.STRAIGHT, Action.STOP, Action.WAIT}

    def test_all_fixtures_produce_allowed_actions(self):
        """Every fixture produces an allowed action."""
        engine = SafetyDecisionEngine(confidence_threshold=0.45)
        for fixture in load_fixtures():
            perception = fixture["perception"]
            navigation = fixture.get("navigation")
            result = engine.decide(perception, navigation)
            self.assertIn(result.action, self.ALLOWED_ACTIONS,
                          f"Fixture {fixture['id']} produced disallowed action: {result.action}")

    def test_actions_are_case_exact(self):
        """Actions use exact uppercase strings."""
        engine = SafetyDecisionEngine(confidence_threshold=0.45)
        result = engine.decide({
            "scene_summary": "test",
            "objects": [],
            "left_path": {"clear": True, "risk": "LOW", "confidence": 0.9},
            "center_path": {"clear": True, "risk": "LOW", "confidence": 0.9},
            "right_path": {"clear": True, "risk": "LOW", "confidence": 0.9},
            "overall_risk": "LOW",
            "confidence": 0.9,
        })
        # Must be one of the exact enum values
        self.assertIn(result.action.value, ("LEFT", "RIGHT", "STRAIGHT", "STOP", "WAIT"))


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print("\n" + "=" * 60)
    print(f"TESTS RUN: {result.testsRun}")
    print(f"FAILURES: {len(result.failures)}")
    print(f"ERRORS: {len(result.errors)}")
    print(f"SKIPPED: {len(result.skipped)}")
    print(f"SUCCESS: {result.wasSuccessful()}")
    print("=" * 60)

    sys.exit(0 if result.wasSuccessful() else 1)
