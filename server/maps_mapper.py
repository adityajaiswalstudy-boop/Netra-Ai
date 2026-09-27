"""
Google Maps Routes API — Mapper/Adapter

Normalizes the Routes API v2 response into a clean internal format
that the rest of the application depends on.

Do NOT let other modules depend on Google's raw response structure.

Official docs:
  https://developers.google.com/maps/documentation/routes
  POST https://routes.googleapis.com/directions/v2:computeRoutes
  Auth: X-Goog-Api-Key header
  Field mask: X-Goog-FieldMask header
"""

from __future__ import annotations
import re
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

import requests


# ---------------------------------------------------------------------------
# Turn maneuver mapping
# ---------------------------------------------------------------------------

class Maneuver(str, Enum):
    """Simplified turn types for voice instructions."""
    LEFT = "left"
    RIGHT = "right"
    STRAIGHT = "straight"
    U_TURN = "u-turn"
    SLIGHTLY_LEFT = "slightly_left"
    SLIGHTLY_RIGHT = "slightly_right"
    DESTINATION = "destination"
    ROUNDABOUT = "roundabout"
    OTHER = "other"


MANEUVER_MAP = {
    "TURN_LEFT": Maneuver.LEFT,
    "TURN_RIGHT": Maneuver.RIGHT,
    "STRAIGHT": Maneuver.STRAIGHT,
    "TURN_SLIGHTLY_LEFT": Maneuver.SLIGHTLY_LEFT,
    "TURN_SLIGHTLY_RIGHT": Maneuver.SLIGHTLY_RIGHT,
    "TURN_LEFT_AND_MODERATE_LEFT": Maneuver.LEFT,
    "TURN_RIGHT_AND_MODERATE_RIGHT": Maneuver.RIGHT,
    "TURN_LEFT_AND_SLIGHT_RIGHT": Maneuver.LEFT,
    "TURN_RIGHT_AND_SLIGHT_LEFT": Maneuver.RIGHT,
    "TURN_HARD_LEFT": Maneuver.LEFT,
    "TURN_HARD_RIGHT": Maneuver.RIGHT,
    "TURN_SLIGHT_LEFT": Maneuver.SLIGHTLY_LEFT,
    "TURN_SLIGHT_RIGHT": Maneuver.SLIGHTLY_RIGHT,
    "TURN_SHARP_LEFT": Maneuver.LEFT,
    "TURN_SHARP_RIGHT": Maneuver.RIGHT,
    "UTURN_LEFT": Maneuver.U_TURN,
    "UTURN_RIGHT": Maneuver.U_TURN,
    "ROUNDABOUT_LEFT": Maneuver.ROUNDABOUT,
    "ROUNDABOUT_RIGHT": Maneuver.ROUNDABOUT,
    "ROUNDABOUT_NOT_TAKEN": Maneuver.ROUNDABOUT,
    "DESTINATION": Maneuver.DESTINATION,
    "TURN_LEFT_AT_MESSAGE": Maneuver.LEFT,
    "TURN_RIGHT_AT_MESSAGE": Maneuver.RIGHT,
    "TURN_SLIGHT_LEFT_AT_MESSAGE": Maneuver.SLIGHTLY_LEFT,
    "TURN_SLIGHT_RIGHT_AT_MESSAGE": Maneuver.SLIGHTLY_RIGHT,
    "TURN_HARD_LEFT_AT_MESSAGE": Maneuver.LEFT,
    "TURN_HARD_RIGHT_AT_MESSAGE": Maneuver.RIGHT,
    "TURN_SHARP_LEFT_AT_MESSAGE": Maneuver.LEFT,
    "TURN_SHARP_RIGHT_AT_MESSAGE": Maneuver.RIGHT,
    "TURN_LEFT_AND_POINT_END": Maneuver.DESTINATION,
    "TURN_RIGHT_AND_POINT_END": Maneuver.DESTINATION,
}


def parse_maneuver(raw: Optional[str]) -> Maneuver:
    """Convert a Routes API maneuver string to our simplified turn type."""
    if not raw:
        return Maneuver.OTHER
    return MANEUVER_MAP.get(raw, Maneuver.OTHER)


def maneuver_to_voice(m: Maneuver) -> str:
    """Convert a maneuver to a short voice-friendly string."""
    voice_map = {
        Maneuver.LEFT: "Turn left",
        Maneuver.RIGHT: "Turn right",
        Maneuver.STRAIGHT: "Continue straight",
        Maneuver.U_TURN: "Make a U-turn",
        Maneuver.SLIGHTLY_LEFT: "Slight left",
        Maneuver.SLIGHTLY_RIGHT: "Slight right",
        Maneuver.DESTINATION: "Arrive at destination",
        Maneuver.ROUNDABOUT: "At the roundabout",
        Maneuver.OTHER: "Continue",
    }
    return voice_map.get(m, "Continue")


# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------

DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$|^(\d+)s$")


def parse_duration(raw: str) -> int:
    """
    Parse a Routes API duration string into seconds.

    Handles:
      - ISO 8601: "PT3M", "PT1H30M", "PT45S"
      - Seconds format: "7812s"
    Returns integer seconds.
    """
    if not raw:
        return 0

    raw = raw.strip()

    # Handle "Ns" format
    m = re.match(r"^(\d+)s$", raw)
    if m:
        return int(m.group(1))

    # Handle ISO 8601 duration
    m = DURATION_RE.match(raw)
    if m:
        groups = m.groups()
        if groups[-1] is not None:
            # "Ns" format matched by second alternative
            return int(groups[-1])
        hours = int(groups[0]) if groups[0] else 0
        minutes = int(groups[1]) if groups[1] else 0
        seconds = int(groups[2]) if groups[2] else 0
        return hours * 3600 + minutes * 60 + seconds

    # Fallback: try to extract any number
    m = re.search(r"(\d+)", raw)
    if m:
        return int(m.group(1))

    return 0


# ---------------------------------------------------------------------------
# Normalized route data
# ---------------------------------------------------------------------------

@dataclass
class RouteStep:
    """A single navigation step."""
    instruction: str           # Human-readable instruction
    distance_m: int           # Distance in meters
    duration_s: int           # Duration in seconds
    maneuver: Maneuver        # Simplified turn type
    step_number: int          # 0-based step index
    start_location: dict      # {lat, lng}
    end_location: dict        # {lat, lng}


@dataclass
class WalkingRoute:
    """Normalized walking route — what the rest of the app uses."""
    route_id: str
    distance_m: int
    duration_s: int
    steps: list[RouteStep]
    polyline: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    start_location: dict = field(default_factory=dict)
    end_location: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# API adapter
# ---------------------------------------------------------------------------

ROUTES_API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
DEFAULT_FIELD_MASK = (
    "routes.duration,routes.distanceMeters,routes.polyline,"
    "routes.legs,routes.warnings"
)


def get_walking_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    api_key: str,
    alternatives: bool = False,
) -> WalkingRoute:
    """
    Call the Google Maps Routes API for a walking route and return
    a normalized WalkingRoute.

    Args:
        origin_lat, origin_lng: Origin coordinates.
        dest_lat, dest_lng: Destination coordinates.
        api_key: Google Maps API key (must have Routes API enabled).
        alternatives: Whether to request alternative routes.

    Returns:
        WalkingRoute with normalized steps.

    Raises:
        requests.HTTPError: On API error.
        ValueError: On malformed response.
    """
    payload = {
        "origin": {
            "location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}
        },
        "destination": {
            "location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}
        },
        "travelMode": "WALK",
        "routingPreference": "TRAFFIC_UNAWARE",
    }
    if alternatives:
        payload["computeAlternativeRoutes"] = True

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": DEFAULT_FIELD_MASK,
    }

    resp = requests.post(ROUTES_API_URL, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    return _normalize_route(data, api_key)


def _normalize_route(data: dict, api_key: str) -> WalkingRoute:
    """Convert a Routes API response to a WalkingRoute."""
    routes = data.get("routes", [])
    if not routes:
        raise ValueError("Routes API returned no routes")

    # Take the first (best) route
    route = routes[0]

    # Total distance
    distance_m = route.get("distanceMeters", 0)

    # Total duration
    raw_duration = route.get("duration", "0s")
    duration_s = parse_duration(raw_duration)

    # Polyline
    polyline = None
    polyline_data = route.get("polyline", {})
    if polyline_data:
        polyline = polyline_data.get("encodedPolyline")

    # Warnings
    warnings = route.get("warnings", [])

    # Legs (typically one leg for point-to-point)
    legs = route.get("legs", [])
    if not legs:
        raise ValueError("Route has no legs")

    # For walking, we use the first leg
    leg = legs[0]

    # Start/end locations
    start_location = _extract_latlng(leg.get("startLocation", {}))
    end_location = _extract_latlng(leg.get("endLocation", {}))

    # Steps
    raw_steps = leg.get("steps", [])
    steps = []
    for i, raw_step in enumerate(raw_steps):
        instruction = raw_step.get("navigationInstruction", {}).get("instructions", "Continue")
        maneuver_raw = raw_step.get("navigationInstruction", {}).get("maneuver")
        maneuver = parse_maneuver(maneuver_raw)
        step_distance = raw_step.get("distanceMeters", 0)
        step_duration_raw = raw_step.get("duration", "0s")
        step_duration = parse_duration(step_duration_raw)
        step_start = _extract_latlng(raw_step.get("startLocation", {}))
        step_end = _extract_latlng(raw_step.get("endLocation", {}))

        steps.append(RouteStep(
            instruction=instruction,
            distance_m=step_distance,
            duration_s=step_duration,
            maneuver=maneuver,
            step_number=i,
            start_location=step_start,
            end_location=step_end,
        ))

    return WalkingRoute(
        route_id=f"route_{distance_m}_{duration_s}",
        distance_m=distance_m,
        duration_s=duration_s,
        steps=steps,
        polyline=polyline,
        warnings=warnings,
        start_location=start_location,
        end_location=end_location,
    )


def _extract_latlng(loc: dict) -> dict:
    """Extract {lat, lng} from a location object."""
    if not loc:
        return {"lat": 0, "lng": 0}
    ll = loc.get("latLng", {})
    return {
        "lat": ll.get("latitude", 0),
        "lng": ll.get("longitude", 0),
    }


# ---------------------------------------------------------------------------
# Mock route (for testing without API key)
# ---------------------------------------------------------------------------

def make_mock_walking_route(
    origin_lat: float = 27.7169,
    origin_lng: float = 85.3230,
    dest_lat: float = 27.7275,
    dest_lng: float = 85.3155,
    distance_m: int = 1200,
    duration_s: int = 780,
    step_count: int = 4,
) -> WalkingRoute:
    """Create a mock walking route for testing without an API key."""
    steps = []
    for i in range(step_count):
        remaining = step_count - i
        seg_dist = distance_m // step_count
        seg_dur = duration_s // step_count
        steps.append(RouteStep(
            instruction=f"Step {i+1}: Head towards destination",
            distance_m=seg_dist,
            duration_s=seg_dur,
            maneuver=Maneuver.STRAIGHT if i < step_count - 1 else Maneuver.DESTINATION,
            step_number=i,
            start_location={
                "lat": origin_lat + (dest_lat - origin_lat) * i // step_count,
                "lng": origin_lng + (dest_lng - origin_lng) * i // step_count,
            },
            end_location={
                "lat": origin_lat + (dest_lat - origin_lat) * (i + 1) // step_count,
                "lng": origin_lng + (dest_lng - origin_lng) * (i + 1) // step_count,
            },
        ))

    return WalkingRoute(
        route_id="mock_route",
        distance_m=distance_m,
        duration_s=duration_s,
        steps=steps,
        polyline=None,
        warnings=[],
        start_location={"lat": origin_lat, "lng": origin_lng},
        end_location={"lat": dest_lat, "lng": dest_lng},
    )
