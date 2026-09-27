"""
Vision Provider Adapter for Netra AI — AI SafePath

Unified entry point: analyze_frame()
Supports multiple vision providers behind a common interface.

Providers:
  - MOCK: Generates structured perception from test fixtures (no API key)
  - GOOGLE_VISION: Google Cloud Vision API (label detection + object localization)
  - GEMINI: Google Gemini multimodal API (gemini-3.8-flash, structured JSON output)

Every response (real or mock) passes through validate_perception_dict() before
being returned. Malformed responses trigger safe_fallback().

Monocular distance estimation:
  - estimated_distance_m is ALWAYS an estimate, never exact
  - distance_confidence accompanies every distance estimate
  - null is used when distance cannot reasonably be estimated
  - Based on bounding box vertical position heuristic
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import requests

# ---------------------------------------------------------------------------
# Provider enum
# ---------------------------------------------------------------------------

class VisionProvider(str, Enum):
    GOOGLE_VISION = "google_vision"
    GEMINI = "gemini"
    MOCK = "mock"


# ---------------------------------------------------------------------------
# Perception data structures
# ---------------------------------------------------------------------------

@dataclass
class DetectedObject:
    type: str
    position: str = "center"
    estimated_distance_m: Optional[float] = None
    distance_confidence: float = 0.5
    blocks_path: bool = False
    risk: str = "LOW"


@dataclass
class PathAnalysis:
    clear: bool = True
    risk: str = "LOW"
    confidence: float = 0.85


@dataclass
class PerceptionResult:
    scene_summary: str = ""
    objects: list[DetectedObject] = field(default_factory=list)
    left_path: PathAnalysis = field(default_factory=PathAnalysis)
    center_path: PathAnalysis = field(default_factory=PathAnalysis)
    right_path: PathAnalysis = field(default_factory=PathAnalysis)
    overall_risk: str = "LOW"
    confidence: float = 0.85


# ---------------------------------------------------------------------------
# Validation functions (schema validation for perception and decision dicts)
# ---------------------------------------------------------------------------

VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
VALID_ACTIONS = {"LEFT", "RIGHT", "STRAIGHT", "STOP", "WAIT"}

PERCEPTION_REQUIRED_FIELDS = {
    "scene_summary": str,
    "objects": list,
    "left_path": dict,
    "center_path": dict,
    "right_path": dict,
    "overall_risk": str,
    "confidence": (int, float),
}

PATH_REQUIRED_FIELDS = {
    "clear": bool,
    "risk": str,
    "confidence": (int, float),
}

OBJECT_REQUIRED_FIELDS = {
    "type": str,
    "position": str,
    "estimated_distance_m": (int, float, type(None)),
    "distance_confidence": (int, float),
    "blocks_path": bool,
    "risk": str,
}

VALID_OBJECT_TYPES = {
    "pole", "person", "vehicle", "motorcycle", "bicycle", "tree",
    "wall", "fence", "stairs", "curb", "pothole", "construction_barrier",
    "bench", "bin", "sign", "door", "animal", "sidewalk", "road",
    "unknown_obstacle",
}

VALID_POSITIONS = {"left", "center", "right"}


def validate_perception_dict(data: dict) -> list[str]:
    """Validate a perception dict against the perception schema.

    Returns:
        List of error strings. Empty list = valid.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["Input must be a JSON object"]

    # Check required top-level fields
    for field_name, expected_type in PERCEPTION_REQUIRED_FIELDS.items():
        if field_name not in data:
            errors.append(f"Missing required field: {field_name}")
        elif not isinstance(data[field_name], expected_type):
            errors.append(
                f"Field '{field_name}': expected {expected_type}, got {type(data[field_name])}"
            )

    # Validate overall_risk
    if "overall_risk" in data and data["overall_risk"] not in VALID_RISK_LEVELS:
        errors.append(
            f"Invalid overall_risk: '{data['overall_risk']}' not in {VALID_RISK_LEVELS}"
        )

    # Validate confidence range
    if "confidence" in data:
        conf = data["confidence"]
        if not (0.0 <= conf <= 1.0):
            errors.append(f"Confidence {conf} out of range [0, 1]")

    # Validate objects array
    if "objects" in data and isinstance(data["objects"], list):
        for i, obj in enumerate(data["objects"]):
            if not isinstance(obj, dict):
                errors.append(f"Object {i}: not a dict")
                continue

            for field_name, expected_type in OBJECT_REQUIRED_FIELDS.items():
                if field_name not in obj:
                    errors.append(f"Object {i}: missing field '{field_name}'")
                elif not isinstance(obj[field_name], expected_type):
                    errors.append(
                        f"Object {i}.'{field_name}': expected {expected_type}, "
                        f"got {type(obj[field_name])}"
                    )

            # Validate type
            if "type" in obj and obj["type"] not in VALID_OBJECT_TYPES:
                errors.append(
                    f"Object {i}: invalid type '{obj['type']}'"
                )

            # Validate position
            if "position" in obj and obj["position"] not in VALID_POSITIONS:
                errors.append(
                    f"Object {i}: invalid position '{obj['position']}'"
                )

            # Validate risk
            if "risk" in obj and obj["risk"] not in VALID_RISK_LEVELS:
                errors.append(
                    f"Object {i}: invalid risk '{obj['risk']}'"
                )

            # Validate distance_confidence range
            if "distance_confidence" in obj:
                dc = obj["distance_confidence"]
                if not (0.0 <= dc <= 1.0):
                    errors.append(
                        f"Object {i}: distance_confidence {dc} out of range [0, 1]"
                    )

    # Validate path objects
    for path_name in ("left_path", "center_path", "right_path"):
        if path_name in data and isinstance(data[path_name], dict):
            path = data[path_name]
            for field_name, expected_type in PATH_REQUIRED_FIELDS.items():
                if field_name not in path:
                    errors.append(f"{path_name}: missing field '{field_name}'")
                elif not isinstance(path[field_name], expected_type):
                    errors.append(
                        f"{path_name}.'{field_name}': expected {expected_type}, "
                        f"got {type(path[field_name])}"
                    )
            if "risk" in path and path["risk"] not in VALID_RISK_LEVELS:
                errors.append(f"{path_name}: invalid risk '{path['risk']}'")
            if "confidence" in path:
                pc = path["confidence"]
                if not (0.0 <= pc <= 1.0):
                    errors.append(f"{path_name}: confidence {pc} out of range [0, 1]")

    return errors


def validate_decision_dict(data: dict) -> list[str]:
    """Validate a decision dict against the decision schema.

    Returns:
        List of error strings. Empty list = valid.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["Decision data must be a dict"]

    if "action" not in data:
        errors.append("Missing required field: action")
    elif data["action"] not in VALID_ACTIONS:
        errors.append(
            f"Invalid action: '{data['action']}' not in {VALID_ACTIONS}"
        )

    if "risk_level" in data and data["risk_level"] not in VALID_RISK_LEVELS:
        errors.append(f"Invalid risk_level: '{data['risk_level']}'")

    if "confidence" in data:
        conf = data["confidence"]
        if not (0.0 <= conf <= 1.0):
            errors.append(f"Confidence {conf} out of range [0, 1]")

    return errors


def safe_fallback(
    perception: Optional[dict] = None,
) -> dict:
    """Return a safe fallback perception when vision analysis fails.

    The fallback signals WAIT/STOP — the safety engine will decide.
    """
    return {
        "scene_summary": "Vision analysis unavailable — falling back to safe default",
        "objects": [],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.0},
        "center_path": {"clear": False, "risk": "HIGH", "confidence": 0.0},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.0},
        "overall_risk": "HIGH",
        "confidence": 0.0,
        "debug": {
            "provider": "fallback",
            "fallback_reason": "vision_analysis_failed",
        },
    }


# ---------------------------------------------------------------------------
# API constants
# ---------------------------------------------------------------------------

GOOGLE_VISION_URL = "https://vision.googleapis.com/v1/images:annotate"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_MODEL = "gemini-3.8-flash"

GEMINI_PERCEPTION_PROMPT = json.dumps(
    {
        "type": "text",
        "text": (
            "You are a pedestrian safety analyzer. Analyze this street/sidewalk image "
            "for walking safety. Return ONLY a valid JSON object with this exact structure — "
            "no other text, no markdown fences, no explanation:\n\n"
            '{\n'
            '    "scene_summary": "short description of the scene and any hazards",\n'
            '    "objects": [\n'
            '        {\n'
            '            "type": "pole|person|vehicle|motorcycle|bicycle|tree|wall|fence|'
            'stairs|curb|pothole|construction_barrier|bench|bin|sign|door|animal|'
            'sidewalk|road|unknown_obstacle",\n'
            '            "position": "left|center|right",\n'
            '            "estimated_distance_m": <number or null>,\n'
            '            "distance_confidence": <0.0-1.0>,\n'
            '            "blocks_path": true|false,\n'
            '            "risk": "LOW|MEDIUM|HIGH|CRITICAL"\n'
            '        }\n'
            '    ],\n'
            '    "left_path": {"clear": true|false, "risk": "LOW|MEDIUM|HIGH|CRITICAL", '
            '"confidence": <0.0-1.0>},\n'
            '    "center_path": {"clear": true|false, "risk": "LOW|MEDIUM|HIGH|CRITICAL", '
            '"confidence": <0.0-1.0>},\n'
            '    "right_path": {"clear": true|false, "risk": "LOW|MEDIUM|HIGH|CRITICAL", '
            '"confidence": <0.0-1.0>},\n'
            '    "overall_risk": "LOW|MEDIUM|HIGH|CRITICAL",\n'
            '    "confidence": <0.0-1.0>\n'
            '}\n\n'
            "Rules:\n"
            "- estimated_distance_m is an ESTIMATE from monocular camera — use null if uncertain\n"
            "- distance_confidence must reflect uncertainty (lower for farther objects)\n"
            "- blocks_path=true for obstacles that block the walking path\n"
            "- risk: CRITICAL for vehicles/motorcycles, HIGH for people/construction in path, "
            "MEDIUM for poles/barriers, LOW for distant minor objects\n"
            "- position: left if object center is in left third of image, center if middle third, "
            "right if right third\n"
            "- If no objects detected, return empty objects array and all paths clear:LOW\n"
            "- NEVER return text outside the JSON object"
        ),
    },
    indent=2,
)

GOOGLE_VISION_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
]


# ---------------------------------------------------------------------------
# Helper: label → object type mapping
# ---------------------------------------------------------------------------

LABEL_TYPE_MAP = {
    "person": "person",
    "people": "person",
    "car": "vehicle",
    "cars": "vehicle",
    "truck": "vehicle",
    "bus": "vehicle",
    "motorcycle": "motorcycle",
    "motorbike": "motorcycle",
    "bicycle": "bicycle",
    "bike": "bicycle",
    "pole": "pole",
    "tree": "tree",
    "building": "wall",
    "wall": "wall",
    "stairs": "stairs",
    "bench": "bench",
    "bin": "bin",
    "trash": "bin",
    "door": "door",
    "fence": "fence",
    "road": "road",
    "sidewalk": "sidewalk",
    "sign": "sign",
    "traffic light": "sign",
    "animal": "animal",
    "construction": "construction_barrier",
    "barrier": "construction_barrier",
    "cone": "construction_barrier",
    "curb": "curb",
    "pothole": "pothole",
    "dog": "animal",
    "cat": "animal",
    "bird": "animal",
}

_BLOCKING_TYPES = frozenset({
    "vehicle", "motorcycle", "bicycle", "person",
    "construction_barrier", "pole", "wall", "fence",
    "stairs", "curb", "pothole", "unknown_obstacle",
})


def _infer_risk(
    obj_type: str,
    estimated_distance_m: Optional[float],
    distance_confidence: float,
    blocks_path: bool,
) -> str:
    """Infer risk level from object type, distance, and blocking status."""
    if obj_type in ("vehicle", "motorcycle"):
        return "CRITICAL"
    if obj_type == "person" and blocks_path:
        return "HIGH"
    if blocks_path:
        if estimated_distance_m is not None and estimated_distance_m < 3:
            return "HIGH"
        return "MEDIUM"
    if estimated_distance_m is not None and estimated_distance_m < 2:
        return "MEDIUM"
    return "LOW"


def _analyze_path(objects: list[dict], position: str) -> dict:
    """Analyze a path direction given detected objects."""
    path_objects = [o for o in objects if o.get("position", "").startswith(position)]

    if not path_objects:
        return {"clear": True, "risk": "LOW", "confidence": 0.85}

    danger_values = []
    for obj in path_objects:
        base_risk = {
            "vehicle": 0.95, "motorcycle": 0.90, "bicycle": 0.70,
            "person": 0.65, "construction_barrier": 0.60,
            "pole": 0.45, "wall": 0.50, "fence": 0.40,
            "stairs": 0.55, "curb": 0.30, "pothole": 0.35,
            "tree": 0.20, "bench": 0.15, "bin": 0.10,
            "sign": 0.12, "door": 0.18, "animal": 0.50,
            "sidewalk": 0.05, "road": 0.15, "unknown_obstacle": 0.40,
        }.get(obj.get("type", ""), 0.3)

        dist_mod = 0.5
        est_dist = obj.get("estimated_distance_m")
        if est_dist is not None:
            if est_dist < 2:
                dist_mod = 1.0
            elif est_dist < 5:
                dist_mod = 0.8
            elif est_dist < 10:
                dist_mod = 0.5

        conf = obj.get("distance_confidence", 0.5)
        if conf < 0.5:
            dist_mod *= 0.6

        if obj.get("blocks_path", False):
            base_risk += 0.25

        danger = min(base_risk * dist_mod, 1.0)
        danger_values.append(danger)

    max_danger = max(danger_values)
    if max_danger >= 0.85:
        risk = "CRITICAL"
    elif max_danger >= 0.65:
        risk = "HIGH"
    elif max_danger >= 0.4:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    has_blocker = any(o.get("blocks_path", False) for o in path_objects)
    clear = max_danger < 0.3 and not has_blocker
    confidence = min(0.95, 0.5 + 0.05 * len(path_objects))

    return {"clear": clear, "risk": risk, "confidence": round(confidence, 2)}


def _highest_risk(risk_levels: list[str]) -> str:
    """Return the highest risk level from a list."""
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    return max(risk_levels, key=lambda r: order.get(r, 0))


def _estimate_distance(
    cy: float, confidence: float
) -> Optional[float]:
    """Estimate distance from vertical position (monocular heuristic).

    Args:
        cy: Center y of bounding box in [0, 1] (0 = top, 1 = bottom).
        confidence: Detection confidence.

    Returns:
        Estimated distance in meters, or None if too uncertain/far.
    """
    if confidence < 0.3 or cy < 0.1:
        return None

    rough_m = 20.0 * (1.0 - cy)
    if rough_m < 0.5:
        return 0.5
    if rough_m > 18.0:
        return None

    return round(rough_m, 1)


def _make_request(
    url: str, headers: dict, payload: dict
) -> Optional[requests.Response]:
    """Make an HTTP POST request with error handling."""
    try:
        req = requests.post(url, json=payload, headers=headers, timeout=10)
        if req.status_code == 200:
            return req
        return None
    except requests.RequestException:
        return None


# ---------------------------------------------------------------------------
# Google Vision API provider
# ───────────────────────────────────────────────────────────────────────────

def analyze_frame_google_vision(
    image_base64: str,
    api_key: str,
    *,
    scenario: Optional[str] = None,
    timestamp_ms: Optional[int] = None,
) -> dict:
    """Analyze a frame using Google Cloud Vision API.

    Uses LABEL_DETECTION (max 15) + OBJECT_LOCALIZATION (max 10) features.
    Maps labels to our object type enum and uses bounding polygons for
    position estimation.

    Args:
        image_base64: Base64-encoded JPEG image data (URLEncoded format).
        api_key: Google Cloud Vision API key.
        scenario: Optional scenario name for benchmark tagging.
        timestamp_ms: Optional frame timestamp.

    Returns:
        Validated perception dict. On failure: safe_fallback().
    """
    benchmark_note = f" [benchmark: {scenario}]" if scenario else ""

    try:
        payload = {
            "requests": [
                {
                    "image": {
                        "content": image_base64,
                    },
                    "features": [
                        {"type": "LABEL_DETECTION", "maxResults": 15},
                        {"type": "OBJECT_LOCALIZATION", "maxResults": 10},
                    ],
                }
            ]
        }

        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }

        req = _make_request(GOOGLE_VISION_URL, headers, payload)
        if req is None:
            return safe_fallback(f"Vision API request failed{benchmark_note}")

        response_data = req.json()
        responses = response_data.get("responses", [])
        if not responses:
            return safe_fallback(f"Vision API returned empty response{benchmark_note}")

        vision_result = responses[0]

        # Extract labels
        labels = []
        label_annotations = vision_result.get("labelAnnotations", [])
        for label in label_annotations:
            labels.append({
                "name": label.get("description", ""),
                "score": label.get("score", 0),
            })

        # Extract localized objects
        localized_objects = []
        obj_annotations = vision_result.get("localizedObjectAnnotations", [])
        for obj in obj_annotations:
            localized_objects.append({
                "name": obj.get("name", ""),
                "score": obj.get("score", 0),
                "boundingPoly": obj.get("boundingPoly", {}),
            })

        # Map to our schema
        objects = []
        seen_types = set()

        # Process localized objects (have spatial info)
        for obj in localized_objects:
            obj_type = LABEL_TYPE_MAP.get(
                obj["name"].lower(), "unknown_obstacle"
            )
            if not obj_type:
                continue

            poly = obj.get("boundingPoly", {})
            position = _get_position_from_poly(poly)
            cy = _get_center_y(poly)

            key = f"{obj_type}_{position}"
            if key in seen_types:
                continue
            seen_types.add(key)

            est_dist = _estimate_distance(cy, obj["score"])
            dist_conf = min(0.6, obj["score"] * 0.5 + 0.2)

            objects.append({
                "type": obj_type,
                "position": position,
                "estimated_distance_m": est_dist,
                "distance_confidence": round(dist_conf, 2),
                "blocks_path": obj_type in _BLOCKING_TYPES,
                "risk": _infer_risk(obj_type, est_dist, dist_conf, obj_type in _BLOCKING_TYPES),
            })

        # Supplement with labels (no spatial info)
        for label in labels:
            obj_type = LABEL_TYPE_MAP.get(label["name"].lower())
            if not obj_type or obj_type in seen_types:
                continue
            seen_types.add(obj_type)

            objects.append({
                "type": obj_type,
                "position": "center",
                "estimated_distance_m": None,
                "distance_confidence": 0.15,
                "blocks_path": obj_type in _BLOCKING_TYPES,
                "risk": _infer_risk(obj_type, None, 0.15, obj_type in _BLOCKING_TYPES),
            })

        # Limit objects
        objects = objects[:15]

        # Analyze paths
        left_path = _analyze_path(objects, "left")
        center_path = _analyze_path(objects, "center")
        right_path = _analyze_path(objects, "right")

        # Overall risk
        risk_levels = [center_path["risk"], left_path["risk"], right_path["risk"]]
        for obj in objects:
            risk_levels.append(obj["risk"])
        overall_risk = _highest_risk(risk_levels)

        confidence = min(0.90, 0.5 + 0.05 * len(objects))

        # Scene summary
        if objects:
            types = list(dict.fromkeys(o["type"] for o in objects))[:5]
            scene_summary = "Detected: " + ", ".join(types)
            if any(o["position"] == "center" and o["blocks_path"] for o in objects):
                scene_summary += ". Hazard ahead."
        else:
            scene_summary = "Scene analyzed. No prominent obstacles detected."

        perception = {
            "scene_summary": scene_summary,
            "objects": objects,
            "left_path": left_path,
            "center_path": center_path,
            "right_path": right_path,
            "overall_risk": overall_risk,
            "confidence": round(confidence, 2),
        }

        validated = validate_perception_dict(perception)
        if not validated:
            perception["debug"] = {
                "provider": "google_vision",
                "label_count": len(labels),
                "object_count": len(objects),
                "model_used": "google_vision_labels+object_localization",
            }
            return perception

        return safe_fallback(
            f"Vision output failed validation{benchmark_note}: {validated}"
        )

    except Exception as exc:
        return safe_fallback(f"Vision analysis error{benchmark_note}: {exc}")


def _get_position_from_poly(
    poly: dict
) -> str:
    """Determine left/center/right from bounding polygon vertices."""
    vertices = poly.get("normalizedVertices", [])
    if not vertices:
        return "center"

    try:
        cx = sum(v.get("x", 0.5) for v in vertices) / len(vertices)
        if cx < 0.33:
            return "left"
        elif cx > 0.66:
            return "right"
        return "center"
    except (TypeError, ZeroDivisionError):
        return "center"


def _get_center_y(poly: dict) -> float:
    """Get the average y coordinate from bounding polygon."""
    vertices = poly.get("normalizedVertices", [])
    if not vertices:
        return 0.5
    try:
        return sum(v.get("y", 0.5) for v in vertices) / len(vertices)
    except (TypeError, ZeroDivisionError):
        return 0.5


# ---------------------------------------------------------------------------
# Gemini provider
# ───────────────────────────────────────────────────────────────────────────

def analyze_frame_gemini(
    image_base64: str,
    api_key: str,
    *,
    scenario: Optional[str] = None,
    timestamp_ms: Optional[int] = None,
) -> dict:
    """Analyze a frame using Google Gemini multimodal API.

    Gemini is multimodal from the ground up and can perform object detection
    with bounding boxes, scene understanding, and structured JSON output.

    Uses gemini-3.8-flash (current model as of 2026).

    Args:
        image_base64: Base64-encoded JPEG/PNG image data.
        api_key: Google Gemini API key (x-goog-api-key header).
        scenario: Optional scenario name for benchmark tagging.
        timestamp_ms: Optional frame timestamp.

    Returns:
        Validated perception dict. On failure: safe_fallback().

    Note:
        Gemini returns text/JSON — we prompt for our exact schema format.
        Bounding boxes from Gemini are scaled [0,1000] — we rescale to [0,1]
        and convert to left/center/right position.
    """
    benchmark_note = f" [benchmark: {scenario}]" if scenario else ""

    try:
        payload = {
            "model": GEMINI_MODEL,
            "input": [
                {"type": "text", "text": GEMINI_PERCEPTION_PROMPT},
                {
                    "type": "image",
                    "data": image_base64,
                    "mime_type": "image/jpeg",
                },
            ],
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
            },
        }

        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }

        req = _make_request(GEMINI_URL, headers, payload)
        if req is None:
            return safe_fallback(f"Gemini API request failed{benchmark_note}")

        response_data = req.json()
        candidates = response_data.get("candidates", [])
        if not candidates:
            return safe_fallback(f"Gemini returned no candidates{benchmark_note}")

        content_parts = candidates[0].get("content", {}).get("parts", [])
        if not content_parts:
            return safe_fallback(f"Gemini returned empty content{benchmark_note}")

        gemini_text = content_parts[0].get("text", "")
        if not gemini_text:
            return safe_fallback(f"Gemini returned empty text{benchmark_note}")

        # Parse JSON from Gemini response
        try:
            gemini_json = json.loads(gemini_text)
        except json.JSONDecodeError:
            import re as _re
            match = _re.search(r'\\{.*\\}', gemini_text, _re.DOTALL)
            if match:
                try:
                    gemini_json = json.loads(match.group(0))
                except json.JSONDecodeError:
                    return safe_fallback(
                        f"Gemini returned unparseable JSON{benchmark_note}"
                    )
            else:
                return safe_fallback(
                    f"Gemini returned non-JSON response{benchmark_note}"
                )

        # Normalize Gemini output to our perception schema
        perception = _normalize_gemini_output(gemini_json)
        if perception is None:
            return safe_fallback(
                f"Gemini output could not be normalized{benchmark_note}"
            )

        validated = validate_perception_dict(perception)
        if not validated:
            perception["debug"] = {
                "provider": "gemini",
                "model_used": GEMINI_MODEL,
            }
            return perception

        return safe_fallback(
            f"Gemini output failed schema validation{benchmark_note}: {validated}"
        )

    except Exception as exc:
        return safe_fallback(f"Gemini analysis error{benchmark_note}: {exc}")


def _normalize_gemini_output(
    gemini_json: dict,
) -> Optional[dict]:
    """Normalize Gemini JSON response to our perception schema.

    Converts Gemini's output (which may include bounding boxes scaled [0,1000])
    to our standard perception format.

    Args:
        gemini_json: Parsed JSON from Gemini.

    Returns:
        Perception dict or None if normalization fails.
    """
    if not isinstance(gemini_json, dict):
        return None

    raw_objects = gemini_json.get("objects", [])
    if not isinstance(raw_objects, list):
        raw_objects = []

    objects = []
    for obj in raw_objects:
        if not isinstance(obj, dict):
            continue

        obj_type = str(obj.get("type", "")).lower()
        type_mapping = {
            "pole": "pole", "person": "person", "people": "person",
            "car": "vehicle", "cars": "vehicle", "truck": "vehicle",
            "bus": "vehicle", "motorcycle": "motorcycle",
            "motorbike": "motorcycle", "bicycle": "bicycle",
            "bike": "bicycle", "tree": "tree", "building": "wall",
            "wall": "wall", "stairs": "stairs", "bench": "bench",
            "bin": "bin", "trash": "bin", "door": "door",
            "fence": "fence", "road": "road", "sidewalk": "sidewalk",
            "sign": "sign", "traffic light": "sign", "animal": "animal",
            "construction": "construction_barrier",
            "barrier": "construction_barrier", "cone": "construction_barrier",
            "curb": "curb", "pothole": "pothole",
        }
        mapped_type = type_mapping.get(obj_type, "unknown_obstacle")

        # Position from bbox or explicit field
        bbox = obj.get("bbox") or obj.get("box_2d") or obj.get("bounding_box")
        position = str(obj.get("position", "center")).lower()
        if position not in ("left", "center", "right"):
            position = "center"
        elif bbox:
            try:
                ymin = float(bbox[0]) / 1000.0
                xmin = float(bbox[1]) / 1000.0
                ymax = float(bbox[2]) / 1000.0
                xmax = float(bbox[3]) / 1000.0
                cx = (xmin + xmax) / 2.0
                if cx < 0.33:
                    position = "left"
                elif cx > 0.66:
                    position = "right"
                else:
                    position = "center"
            except (ValueError, IndexError, TypeError):
                position = "center"

        # Distance from bbox or explicit value
        estimated_distance = obj.get("estimated_distance_m")
        distance_confidence = float(obj.get("distance_confidence", 0.5))
        if estimated_distance is None and bbox and distance_confidence >= 0.3:
            try:
                if isinstance(bbox, list) and len(bbox) >= 3:
                    cy_val = (float(bbox[0]) + float(bbox[2])) / 2000.0
                    if cy_val >= 0.1:
                        rough_m = 20.0 * (1.0 - cy_val)
                        if rough_m <= 18.0:
                            estimated_distance = round(rough_m, 1)
            except (ValueError, TypeError):
                pass
        if distance_confidence < 0.3:
            estimated_distance = None

        blocks_path = bool(
            obj.get("blocks_path", mapped_type in _BLOCKING_TYPES)
        )
        risk = str(obj.get("risk", "LOW")).upper()
        if risk not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            risk = _infer_risk(
                mapped_type, estimated_distance, distance_confidence, blocks_path
            )

        objects.append({
            "type": mapped_type,
            "position": position,
            "estimated_distance_m": estimated_distance,
            "distance_confidence": distance_confidence,
            "blocks_path": blocks_path,
            "risk": risk,
        })

    objects = objects[:15]

    left_path = _analyze_path(objects, "left")
    center_path = _analyze_path(objects, "center")
    right_path = _analyze_path(objects, "right")

    risk_levels = [
        center_path["risk"], left_path["risk"], right_path["risk"]
    ]
    for obj in objects:
        risk_levels.append(obj["risk"])
    overall_risk = _highest_risk(risk_levels)

    confidence = min(0.90, 0.5 + 0.05 * len(objects))

    if objects:
        types = list(dict.fromkeys(o["type"] for o in objects))[:5]
        scene_summary = "Detected: " + ", ".join(types)
        if any(o["position"] == "center" and o["blocks_path"] for o in objects):
            scene_summary += ". Hazard ahead."
    else:
        scene_summary = "Scene analyzed. No prominent obstacles detected."

    return {
        "scene_summary": scene_summary,
        "objects": objects,
        "left_path": left_path,
        "center_path": center_path,
        "right_path": right_path,
        "overall_risk": overall_risk,
        "confidence": round(confidence, 2),
    }


# ---------------------------------------------------------------------------
# Mock provider — generates perception from scenario fixtures
# ───────────────────────────────────────────────────────────────────────────

MOCK_SCENARIOS: dict[str, dict] = {
    "clear": {
        "scene_summary": "Scene analyzed. No prominent obstacles detected.",
        "objects": [],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.90},
        "center_path": {"clear": True, "risk": "LOW", "confidence": 0.90},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.90},
        "overall_risk": "LOW",
        "confidence": 0.90,
    },
    "pole_center": {
        "scene_summary": "Detected: pole. Hazard ahead.",
        "objects": [
            {
                "type": "pole",
                "position": "center",
                "estimated_distance_m": 4.0,
                "distance_confidence": 0.55,
                "blocks_path": True,
                "risk": "HIGH",
            }
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "center_path": {"clear": False, "risk": "HIGH", "confidence": 0.85},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "overall_risk": "HIGH",
        "confidence": 0.85,
    },
    "person_center": {
        "scene_summary": "Detected: person. Hazard ahead.",
        "objects": [
            {
                "type": "person",
                "position": "center",
                "estimated_distance_m": 5.0,
                "distance_confidence": 0.55,
                "blocks_path": True,
                "risk": "HIGH",
            }
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "center_path": {"clear": False, "risk": "HIGH", "confidence": 0.85},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "overall_risk": "HIGH",
        "confidence": 0.85,
    },
    "vehicle_center": {
        "scene_summary": "Detected: vehicle. Critical hazard ahead.",
        "objects": [
            {
                "type": "vehicle",
                "position": "center",
                "estimated_distance_m": 6.0,
                "distance_confidence": 0.55,
                "blocks_path": True,
                "risk": "CRITICAL",
            }
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "center_path": {"clear": False, "risk": "CRITICAL", "confidence": 0.90},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "overall_risk": "CRITICAL",
        "confidence": 0.90,
    },
    "road_right": {
        "scene_summary": "Detected: road. Right side has traffic corridor.",
        "objects": [
            {
                "type": "road",
                "position": "right",
                "estimated_distance_m": 5.0,
                "distance_confidence": 0.50,
                "blocks_path": False,
                "risk": "LOW",
            }
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "center_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "right_path": {"clear": False, "risk": "MEDIUM", "confidence": 0.70},
        "overall_risk": "MEDIUM",
        "confidence": 0.80,
    },
    "sidewalk_left": {
        "scene_summary": "Detected: sidewalk. Left path has clear pedestrian corridor.",
        "objects": [
            {
                "type": "sidewalk",
                "position": "left",
                "estimated_distance_m": 3.0,
                "distance_confidence": 0.55,
                "blocks_path": False,
                "risk": "LOW",
            }
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.88},
        "center_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "overall_risk": "LOW",
        "confidence": 0.85,
    },
    "construction_barrier": {
        "scene_summary": "Detected: construction barrier. Path partially blocked.",
        "objects": [
            {
                "type": "construction_barrier",
                "position": "center",
                "estimated_distance_m": 6.0,
                "distance_confidence": 0.55,
                "blocks_path": True,
                "risk": "HIGH",
            }
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "center_path": {"clear": False, "risk": "HIGH", "confidence": 0.85},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "overall_risk": "HIGH",
        "confidence": 0.85,
    },
    "pole_left": {
        "scene_summary": "Detected: pole. Hazard on left side.",
        "objects": [
            {
                "type": "pole",
                "position": "center",
                "estimated_distance_m": 4.0,
                "distance_confidence": 0.55,
                "blocks_path": True,
                "risk": "HIGH",
            }
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "center_path": {"clear": False, "risk": "HIGH", "confidence": 0.85},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "overall_risk": "HIGH",
        "confidence": 0.85,
    },
    "vehicle_stop": {
        "scene_summary": "Detected: vehicle. Critical hazard ahead.",
        "objects": [
            {
                "type": "vehicle",
                "position": "center",
                "estimated_distance_m": 6.0,
                "distance_confidence": 0.55,
                "blocks_path": True,
                "risk": "CRITICAL",
            }
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "center_path": {"clear": False, "risk": "CRITICAL", "confidence": 0.90},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "overall_risk": "CRITICAL",
        "confidence": 0.90,
    },
    "all_blocked": {
        "scene_summary": "Detected: obstacles in all directions.",
        "objects": [
            {
                "type": "construction_barrier",
                "position": "left",
                "estimated_distance_m": 5.0,
                "distance_confidence": 0.55,
                "blocks_path": True,
                "risk": "HIGH",
            },
            {
                "type": "construction_barrier",
                "position": "center",
                "estimated_distance_m": 4.0,
                "distance_confidence": 0.55,
                "blocks_path": True,
                "risk": "HIGH",
            },
            {
                "type": "construction_barrier",
                "position": "right",
                "estimated_distance_m": 5.0,
                "distance_confidence": 0.55,
                "blocks_path": True,
                "risk": "HIGH",
            },
        ],
        "left_path": {"clear": False, "risk": "HIGH", "confidence": 0.80},
        "center_path": {"clear": False, "risk": "HIGH", "confidence": 0.85},
        "right_path": {"clear": False, "risk": "HIGH", "confidence": 0.80},
        "overall_risk": "CRITICAL",
        "confidence": 0.85,
    },
    "low_conf": {
        "scene_summary": "Low confidence scene analysis.",
        "objects": [
            {
                "type": "unknown_obstacle",
                "position": "center",
                "estimated_distance_m": None,
                "distance_confidence": 0.20,
                "blocks_path": True,
                "risk": "LOW",
            }
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.30},
        "center_path": {"clear": False, "risk": "LOW", "confidence": 0.30},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.30},
        "overall_risk": "LOW",
        "confidence": 0.30,
    },
    "unknown_object": {
        "scene_summary": "Detected: unknown object.",
        "objects": [
            {
                "type": "unknown_obstacle",
                "position": "center",
                "estimated_distance_m": None,
                "distance_confidence": 0.20,
                "blocks_path": True,
                "risk": "LOW",
            }
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "center_path": {"clear": False, "risk": "LOW", "confidence": 0.85},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "overall_risk": "LOW",
        "confidence": 0.85,
    },
    "multiple_obstacles": {
        "scene_summary": "Detected: pole, person, vehicle. Multiple hazards.",
        "objects": [
            {
                "type": "pole",
                "position": "left",
                "estimated_distance_m": 8.0,
                "distance_confidence": 0.50,
                "blocks_path": True,
                "risk": "MEDIUM",
            },
            {
                "type": "person",
                "position": "center",
                "estimated_distance_m": 7.0,
                "distance_confidence": 0.55,
                "blocks_path": True,
                "risk": "HIGH",
            },
            {
                "type": "vehicle",
                "position": "right",
                "estimated_distance_m": 7.0,
                "distance_confidence": 0.55,
                "blocks_path": True,
                "risk": "CRITICAL",
            },
        ],
        "left_path": {"clear": False, "risk": "MEDIUM", "confidence": 0.75},
        "center_path": {"clear": False, "risk": "HIGH", "confidence": 0.85},
        "right_path": {"clear": False, "risk": "CRITICAL", "confidence": 0.90},
        "overall_risk": "CRITICAL",
        "confidence": 0.85,
    },
}


def analyze_frame_mock(
    image_base64: str = "",
    scenario: str = "clear",
    frame_timestamp_ms: Optional[int] = None,
) -> dict:
    """Generate mock perception for testing without a real Vision API.

    Uses predefined scenario fixtures that produce structured perception
    matching perception.schema.json. Each scenario is designed to test
    a specific safety decision outcome.

    Args:
        image_base64: Ignored in mock mode (for interface compatibility).
        scenario: One of the MOCK_SCENARIOS keys (default: "clear").
        frame_timestamp_ms: Optional timestamp for the perception record.

    Returns:
        Validated perception dict matching perception.schema.json.
    """
    scenario_data = MOCK_SCENARIOS.get(scenario, MOCK_SCENARIOS["clear"])
    perception = dict(scenario_data)
    perception["debug"] = {
        "provider": "mock",
        "scenario": scenario,
        "mock": True,
    }
    if frame_timestamp_ms is not None:
        perception["frame_timestamp_ms"] = frame_timestamp_ms

    validated = validate_perception_dict(perception)
    if not validated:
        return perception

    return safe_fallback(
        f"Mock scenario '{scenario}' failed validation: {validated}"
    )


# ---------------------------------------------------------------------------
# Unified entry point
# ───────────────────────────────────────────────────────────────────────────

def analyze_frame(
    image_base64: str = "",
    provider: Optional[VisionProvider] = None,
    api_key: str = "",
    *,
    scenario: Optional[str] = None,
    frame_timestamp_ms: Optional[int] = None,
) -> dict:
    """Analyze a camera frame using the specified vision provider.

    This is the single entry point for all vision analysis. The rest of
    Netra AI calls this function — it does not need to know which provider
    is being used.

    If provider is None, defaults to VisionProvider.MOCK.

    Args:
        image_base64: Base64-encoded image data.
        provider: VisionProvider.MOCK, .GOOGLE_VISION, or .GEMINI.
            If None, defaults to MOCK.
        api_key: API key for the provider (empty for MOCK).
        scenario: Optional scenario name (used for MOCK and benchmarking).
        frame_timestamp_ms: Optional frame timestamp.

    Returns:
        Validated perception dict matching perception.schema.json.
        On any failure: safe_fallback() result.
    """
    if provider is None:
        provider = VisionProvider.MOCK
    """Analyze a camera frame using the specified vision provider.

    This is the single entry point for all vision analysis. The rest of
    Netra AI calls this function — it does not need to know which provider
    is being used.

    Args:
        image_base64: Base64-encoded image data.
        provider: VisionProvider.MOCK, .GOOGLE_VISION, or .GEMINI.
        api_key: API key for the provider (empty for MOCK).
        scenario: Optional scenario name (used for MOCK and benchmarking).
        frame_timestamp_ms: Optional frame timestamp.

    Returns:
        Validated perception dict matching perception.schema.json.
        On any failure: safe_fallback() result.
    """
    if not image_base64 and provider != VisionProvider.MOCK:
        return safe_fallback(
            "analyze_frame: no image data provided for non-mock provider"
        )

    provider_str = provider.value

    if provider == VisionProvider.MOCK:
        scenario_name = scenario or "clear"
        return analyze_frame_mock(
            image_base64="",
            scenario=scenario_name,
            frame_timestamp_ms=frame_timestamp_ms,
        )

    elif provider == VisionProvider.GOOGLE_VISION:
        if not api_key:
            return safe_fallback(
                "analyze_frame: Google Vision API key required"
            )
        return analyze_frame_google_vision(
            image_base64,
            api_key,
            scenario=scenario,
            timestamp_ms=frame_timestamp_ms,
        )

    elif provider == VisionProvider.GEMINI:
        if not api_key:
            return safe_fallback(
                "analyze_frame: Gemini API key required"
            )
        return analyze_frame_gemini(
            image_base64,
            api_key,
            scenario=scenario,
            timestamp_ms=frame_timestamp_ms,
        )

    else:
        return safe_fallback(
            f"analyze_frame: unknown provider '{provider_str}'"
        )


# ---------------------------------------------------------------------------
# Backward-compatibility aliases (for existing tests)
# ---------------------------------------------------------------------------

def google_vision_label_to_object_type(label: str) -> Optional[str]:
    """Map a Google Vision label string to our object type enum.

    Args:
        label: Vision API label description (case-insensitive).

    Returns:
        Mapped object type string, or None if label is empty/unknown.
    """
    if not label:
        return None
    return LABEL_TYPE_MAP.get(label.lower(), "unknown_obstacle")

# Old name: _position_from_center(cx, cy) — takes center x and y coords
def _position_from_center(cx: float, cy: float) -> str:
    """Determine position string from bounding box center coordinates.

    Args:
        cx: Center x in [0, 1] (0 = left, 1 = right).
        cy: Center y in [0, 1] (0 = top, 1 = bottom).

    Returns:
        "left", "center", "right", or with "_far" suffix if cy < 0.33.
    """
    if cx < 0.33:
        result = "left"
    elif cx > 0.66:
        result = "right"
    else:
        result = "center"

    if cy < 0.33:
        result += "_far"

    return result

# Old name: _estimate_distance_from_y → _estimate_distance
_estimate_distance_from_y = _estimate_distance

# Old name: VALID_RISKS → VALID_RISK_LEVELS
VALID_RISKS = VALID_RISK_LEVELS

# TYPE_DANGER: map of object type → base danger value (for tests)
TYPE_DANGER: dict[str, float] = {
    "vehicle": 0.95, "motorcycle": 0.90, "bicycle": 0.70,
    "person": 0.65, "construction_barrier": 0.60,
    "pole": 0.45, "wall": 0.50, "fence": 0.40,
    "stairs": 0.55, "curb": 0.30, "pothole": 0.35,
    "tree": 0.20, "bench": 0.15, "bin": 0.10,
    "sign": 0.12, "door": 0.18, "animal": 0.50,
    "sidewalk": 0.05, "road": 0.15, "unknown_obstacle": 0.40,
}

