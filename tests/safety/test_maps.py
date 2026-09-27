"""
Google Maps Routes API — Mapper Tests

Tests for:
  - Duration parsing (ISO 8601 + seconds format)
  - Maneuver mapping
  - Route step normalization
  - Mock route generation
  - Malformed response handling

These tests do NOT require a real API key.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server"))

from maps_mapper import (
    parse_duration,
    parse_maneuver,
    maneuver_to_voice,
    Maneuver,
    make_mock_walking_route,
    _normalize_route,
    ROUTES_API_URL,
    DEFAULT_FIELD_MASK,
)


class TestDurationParsing(unittest.TestCase):
    """Test duration string parsing."""

    def test_seconds_format(self):
        self.assertEqual(parse_duration("7812s"), 7812)
        self.assertEqual(parse_duration("0s"), 0)
        self.assertEqual(parse_duration("924s"), 924)

    def test_iso_duration_minutes(self):
        self.assertEqual(parse_duration("PT3M"), 180)
        self.assertEqual(parse_duration("PT10M"), 600)

    def test_iso_duration_hours_minutes(self):
        self.assertEqual(parse_duration("PT1H30M"), 5400)
        self.assertEqual(parse_duration("PT2H"), 7200)

    def test_iso_duration_seconds(self):
        self.assertEqual(parse_duration("PT45S"), 45)
        self.assertEqual(parse_duration("PT1M30S"), 90)

    def test_iso_duration_complex(self):
        self.assertEqual(parse_duration("PT1H2M3S"), 3723)

    def test_empty_string(self):
        self.assertEqual(parse_duration(""), 0)
        self.assertEqual(parse_duration(None), 0)

    def test_malformed_returns_zero(self):
        self.assertEqual(parse_duration("abc"), 0)
        self.assertEqual(parse_duration("PT"), 0)


class TestManeuverMapping(unittest.TestCase):
    """Test maneuver string → simplified turn type mapping."""

    def test_common_maneuvers(self):
        self.assertEqual(parse_maneuver("TURN_LEFT"), Maneuver.LEFT)
        self.assertEqual(parse_maneuver("TURN_RIGHT"), Maneuver.RIGHT)
        self.assertEqual(parse_maneuver("STRAIGHT"), Maneuver.STRAIGHT)
        self.assertEqual(parse_maneuver("UTURN_LEFT"), Maneuver.U_TURN)
        self.assertEqual(parse_maneuver("DESTINATION"), Maneuver.DESTINATION)

    def test_slight_maneuvers(self):
        self.assertEqual(parse_maneuver("TURN_SLIGHTLY_LEFT"), Maneuver.SLIGHTLY_LEFT)
        self.assertEqual(parse_maneuver("TURN_SLIGHTLY_RIGHT"), Maneuver.SLIGHTLY_RIGHT)
        self.assertEqual(parse_maneuver("TURN_SLIGHT_LEFT"), Maneuver.SLIGHTLY_LEFT)

    def test_hard_sharp_maneuvers(self):
        self.assertEqual(parse_maneuver("TURN_HARD_LEFT"), Maneuver.LEFT)
        self.assertEqual(parse_maneuver("TURN_SHARP_RIGHT"), Maneuver.RIGHT)

    def test_roundabout(self):
        self.assertEqual(parse_maneuver("ROUNDABOUT_LEFT"), Maneuver.ROUNDABOUT)
        self.assertEqual(parse_maneuver("ROUNDABOUT_RIGHT"), Maneuver.ROUNDABOUT)

    def test_unknown_maneuver(self):
        self.assertEqual(parse_maneuver("UNKNOWN_MANEUVER"), Maneuver.OTHER)
        self.assertEqual(parse_maneuver(None), Maneuver.OTHER)
        self.assertEqual(parse_maneuver(""), Maneuver.OTHER)

    def test_maneuver_to_voice(self):
        voice = maneuver_to_voice(Maneuver.LEFT)
        self.assertIn("left", voice.lower())
        self.assertEqual(maneuver_to_voice(Maneuver.RIGHT), "Turn right")
        self.assertEqual(maneuver_to_voice(Maneuver.STRAIGHT), "Continue straight")
        self.assertEqual(maneuver_to_voice(Maneuver.U_TURN), "Make a U-turn")


class TestMockRoute(unittest.TestCase):
    """Test mock route generation (no API key needed)."""

    def test_mock_route_basic(self):
        route = make_mock_walking_route()
        self.assertEqual(route.distance_m, 1200)
        self.assertEqual(route.duration_s, 780)
        self.assertEqual(len(route.steps), 4)
        self.assertEqual(route.route_id, "mock_route")
        self.assertIsNone(route.polyline)
        self.assertEqual(route.warnings, [])

    def test_mock_route_custom_distance(self):
        route = make_mock_walking_route(distance_m=5000, duration_s=3000, step_count=5)
        self.assertEqual(route.distance_m, 5000)
        self.assertEqual(route.duration_s, 3000)
        self.assertEqual(len(route.steps), 5)

    def test_mock_route_steps_have_locations(self):
        route = make_mock_walking_route()
        for step in route.steps:
            self.assertIn("lat", step.start_location)
            self.assertIn("lng", step.start_location)
            self.assertIn("lat", step.end_location)
            self.assertIn("lng", step.end_location)

    def test_mock_route_last_step_is_destination(self):
        route = make_mock_walking_route(step_count=3)
        last_step = route.steps[-1]
        self.assertEqual(last_step.maneuver, Maneuver.DESTINATION)

    def test_mock_route_all_other_steps_straight(self):
        route = make_mock_walking_route(step_count=4)
        for step in route.steps[:-1]:
            self.assertEqual(step.maneuver, Maneuver.STRAIGHT)


class TestNormalizeRoute(unittest.TestCase):
    """Test Routes API response normalization (with mock data, no API call)."""

    def test_normalize_basic_response(self):
        mock_response = {
            "routes": [{
                "distanceMeters": 1200,
                "duration": "780s",
                "polyline": {"encodedPolyline": "some_polyline_here"},
                "warnings": [],
                "legs": [{
                    "distanceMeters": 1200,
                    "duration": "780s",
                    "startLocation": {"latLng": {"latitude": 27.7169, "longitude": 85.3230}},
                    "endLocation": {"latLng": {"latitude": 27.7275, "longitude": 85.3155}},
                    "steps": [
                        {
                            "distanceMeters": 300,
                            "duration": "180s",
                            "startLocation": {"latLng": {"latitude": 27.7169, "longitude": 85.3230}},
                            "endLocation": {"latLng": {"latitude": 27.7190, "longitude": 85.3220}},
                            "navigationInstruction": {
                                "maneuver": "STRAIGHT",
                                "instructions": "Head southwest on Durbar Marg"
                            }
                        },
                        {
                            "distanceMeters": 400,
                            "duration": "240s",
                            "startLocation": {"latLng": {"latitude": 27.7190, "longitude": 85.3220}},
                            "endLocation": {"latLng": {"latitude": 27.7220, "longitude": 85.3190}},
                            "navigationInstruction": {
                                "maneuver": "TURN_LEFT",
                                "instructions": "Turn left onto Bhimsen Marg"
                            }
                        },
                        {
                            "distanceMeters": 500,
                            "duration": "360s",
                            "startLocation": {"latLng": {"latitude": 27.7220, "longitude": 85.3190}},
                            "endLocation": {"latLng": {"latitude": 27.7275, "longitude": 85.3155}},
                            "navigationInstruction": {
                                "maneuver": "DESTINATION",
                                "instructions": "Arrive at Thamel"
                            }
                        },
                    ]
                }]
            }]
        }

        route = _normalize_route(mock_response, "dummy_key")

        self.assertEqual(route.distance_m, 1200)
        self.assertEqual(route.duration_s, 780)
        self.assertEqual(route.polyline, "some_polyline_here")
        self.assertEqual(route.warnings, [])
        self.assertEqual(len(route.steps), 3)
        self.assertEqual(route.start_location, {"lat": 27.7169, "lng": 85.3230})
        self.assertEqual(route.end_location, {"lat": 27.7275, "lng": 85.3155})

        # Check steps
        self.assertEqual(route.steps[0].instruction, "Head southwest on Durbar Marg")
        self.assertEqual(route.steps[0].maneuver, Maneuver.STRAIGHT)
        self.assertEqual(route.steps[0].distance_m, 300)
        self.assertEqual(route.steps[0].duration_s, 180)

        self.assertEqual(route.steps[1].instruction, "Turn left onto Bhimsen Marg")
        self.assertEqual(route.steps[1].maneuver, Maneuver.LEFT)

        self.assertEqual(route.steps[2].instruction, "Arrive at Thamel")
        self.assertEqual(route.steps[2].maneuver, Maneuver.DESTINATION)

    def test_normalize_missing_polyline(self):
        mock_response = {
            "routes": [{
                "distanceMeters": 500,
                "duration": "300s",
                "legs": [{
                    "distanceMeters": 500,
                    "duration": "300s",
                    "startLocation": {"latLng": {"latitude": 0, "longitude": 0}},
                    "endLocation": {"latLng": {"latitude": 0.01, "longitude": 0.01}},
                    "steps": []
                }]
            }]
        }
        route = _normalize_route(mock_response, "dummy")
        self.assertIsNone(route.polyline)
        self.assertEqual(len(route.steps), 0)

    def test_normalize_with_warnings(self):
        mock_response = {
            "routes": [{
                "distanceMeters": 1000,
                "duration": "600s",
                "warnings": ["This route includes a pedestrian bridge.", "Sidewalk may be narrow."],
                "legs": [{
                    "distanceMeters": 1000,
                    "duration": "600s",
                    "startLocation": {"latLng": {"latitude": 0, "longitude": 0}},
                    "endLocation": {"latLng": {"latitude": 0.01, "longitude": 0.01}},
                    "steps": []
                }]
            }]
        }
        route = _normalize_route(mock_response, "dummy")
        self.assertEqual(len(route.warnings), 2)
        self.assertIn("pedestrian bridge", route.warnings[0])

    def test_normalize_no_routes(self):
        with self.assertRaises(ValueError):
            _normalize_route({"routes": []}, "dummy")

    def test_normalize_no_legs(self):
        with self.assertRaises(ValueError):
            _normalize_route({"routes": [{"distanceMeters": 100, "duration": "60s"}]}, "dummy")

    def test_normalize_malformed_latlng(self):
        mock_response = {
            "routes": [{
                "distanceMeters": 100,
                "duration": "60s",
                "legs": [{
                    "distanceMeters": 100,
                    "duration": "60s",
                    "startLocation": {},
                    "endLocation": {},
                    "steps": []
                }]
            }]
        }
        route = _normalize_route(mock_response, "dummy")
        self.assertEqual(route.start_location, {"lat": 0, "lng": 0})


class TestRoutesAPIConstants(unittest.TestCase):
    """Test that API constants are correct."""

    def test_endpoint_url(self):
        self.assertIn("routes.googleapis.com", ROUTES_API_URL)
        self.assertIn("computeRoutes", ROUTES_API_URL)
        self.assertIn("v2", ROUTES_API_URL)

    def test_field_mask_includes_required_fields(self):
        self.assertIn("routes.duration", DEFAULT_FIELD_MASK)
        self.assertIn("routes.distanceMeters", DEFAULT_FIELD_MASK)
        self.assertIn("routes.polyline", DEFAULT_FIELD_MASK)
        self.assertIn("routes.legs", DEFAULT_FIELD_MASK)


class TestWalkingModeSpecifics(unittest.TestCase):
    """Test walking-specific considerations."""

    def test_travel_mode_is_walk(self):
        """Verify the travel mode used is WALK, not the old 'walking'."""
        # This is tested implicitly by the mapper code using "WALK"
        # We verify the constant in the payload construction
        import maps_mapper as mm
        # Read the source to verify
        with open(os.path.join(os.path.dirname(__file__), "..", "..", "server", "maps_mapper.py")) as f:
            source = f.read()
        self.assertIn('"travelMode": "WALK"', source)
        self.assertNotIn('"travelMode": "walking"', source)

    def test_routing_preference_for_walking(self):
        """Walking routes should use TRAFFIC_UNAWARE (traffic not relevant for walking)."""
        with open(os.path.join(os.path.dirname(__file__), "..", "..", "server", "maps_mapper.py")) as f:
            source = f.read()
        self.assertIn('"routingPreference": "TRAFFIC_UNAWARE"', source)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print(f"TESTS RUN: {result.testsRun}")
    print(f"FAILURES: {len(result.failures)}")
    print(f"ERRORS: {len(result.errors)}")
    print(f"SKIPPED: {len(result.skipped)}")
    print(f"SUCCESS: {result.wasSuccessful()}")
    print("=" * 60)

    sys.exit(0 if result.wasSuccessful() else 1)
