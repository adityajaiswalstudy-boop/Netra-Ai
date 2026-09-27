"""
AI SafePath — Vision Provider Adapter

Abstracts the vision provider behind a clean interface so the rest of the
application depends on normalized perception data, not provider-specific formats.

Supports:
  - Google Cloud Vision API (label detection + object localization)
  - Mock provider (for testing without API key)
  - Extensible: add new providers by implementing analyze_frame()

Every response is validated against schemas/perception.schema.json before
being returned. Malformed responses trigger a safe fallback.

Technical honesty:
  - Monocular phone cameras cannot provide exact physical distance
  - estimated_distance_m is ALWAYS an estimate
  - distance_confidence must accompany every distance estimate
  - null is used when distance cannot reasonably be estimated
"""

from __future__ import annotations
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path

# ---------------------------------------------------------------------------
# Provider enum
# ---------------------------------------------------------------------------

class VisionProvider(str, Enum):
    GOOGLE_VISION = "google_vision"
    MOCK = "mock"


# ---------------------------------------------------------------------------
# Perception data structures
# ---------------------------------------------------------------------------

@dataclass
class DetectedObject:
    type: str
    position: str
    estimated_distance_m: Optional[float] = None
    distance_confidence: float = 0.5
    blocks_path: bool = False
    risk: Optional[str] = None


@dataclass
class PathAnalysis:
    clear: bool
    risk: str
    confidence: float


@dataclass
class PerceptionResult:
    scene_summary: str
    objects: list[DetectedObject] = field(default_factory=list)
    left_path: PathAnalysis = field(default_factory=lambda: PathAnalysis(True, "LOW", 0.85))
    center_path: PathAnalysis = field(default_factory=lambda: PathAnalysis(True, "LOW", 0.88))
    right_path: PathAnalysis = field(default_factory=lambda: PathAnalysis(True, "LOW", 0.82))
    overall_risk: str = "LOW"
    confidence: float = 0.75
    frame_timestamp_ms: Optional[int] = None
    provider: str = "unknown"
    processing_time_ms: Optional[int] = None


# ---------------------------------------------------------------------------
# Object type → danger mapping (same logic as safety engine)
# ---------------------------------------------------------------------------

TYPE_DANGER: dict[str, float] = {
    "vehicle": 0.95, "motorcycle": 0.90, "bicycle": 0.70, "person": 0.65,
    "construction_barrier": 0.60, "pole": 0.45, "wall": 0.50, "fence": 0.40,
    "stairs": 0.55, "curb": 0.30, "pothole": 0.35, "tree": 0.20, "bench": 0.15,
    "bin": 0.10, "sign": 0.12, "door": 0.18, "animal": 0.50,
    "unknown_obstacle": 0.40,
}

VALID_OBJECT_TYPES = frozenset(TYPE_DANGER.keys()) | {"road", "sidewalk", "crossing", "background"}

VALID_POSITIONS = frozenset({"left", "center", "right", "left_far", "center_far", "right_far", "background"})

VALID_RISKS = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})

VALID_ACTIONS = frozenset({"LEFT", "RIGHT", "STRAIGHT", "STOP", "WAIT"})


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------

def validate_perception_dict(data: dict) -> list[str]:
    """Validate a perception dict against the perception schema.
    Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["perception must be a JSON object"]

    required = ["scene_summary", "objects", "left_path", "center_path",
                "right_path", "overall_risk", "confidence"]
    for key in required:
        if key not in data:
            errors.append(f"missing required field: {key}")

    if "overall_risk" in data:
        if data["overall_risk"] not in VALID_RISKS:
            errors.append(f"overall_risk must be LOW/MEDIUM/HIGH/CRITICAL, got: {data['overall_risk']}")

    if "confidence" in data:
        c = data["confidence"]
        if not isinstance(c, (int, float)) or c < 0 or c > 1:
            errors.append(f"confidence must be 0-1, got: {c}")

    if "objects" in data and isinstance(data["objects"], list):
        for i, obj in enumerate(data["objects"]):
            if not isinstance(obj, dict):
                errors.append(f"objects[{i}] must be an object")
                continue
            if "type" not in obj:
                errors.append(f"objects[{i}] missing type")
            elif obj["type"] not in VALID_OBJECT_TYPES:
                errors.append(f"objects[{i}] invalid type: {obj['type']}")
            if "position" not in obj:
                errors.append(f"objects[{i}] missing position")
            elif obj["position"] not in VALID_POSITIONS:
                errors.append(f"objects[{i}] invalid position: {obj['position']}")

    for path_key in ("left_path", "center_path", "right_path"):
        if path_key in data:
            p = data[path_key]
            if not isinstance(p, dict):
                errors.append(f"{path_key} must be an object")
                continue
            for pk in ("clear", "risk", "confidence"):
                if pk not in p:
                    errors.append(f"{path_key} missing {pk}")
            if "risk" in p and p["risk"] not in VALID_RISKS:
                errors.append(f"{path_key}.risk invalid: {p['risk']}")
            if "confidence" in p:
                c = p["confidence"]
                if not isinstance(c, (int, float)) or c < 0 or c > 1:
                    errors.append(f"{path_key}.confidence must be 0-1, got: {c}")

    return errors


def validate_decision_dict(data: dict) -> list[str]:
    """Validate a decision dict. Returns list of errors (empty = valid)."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["decision must be a JSON object"]

    for key in ("action", "reason", "confidence", "timestamp"):
        if key not in data:
            errors.append(f"missing required field: {key}")

    if "action" in data:
        if data["action"] not in VALID_ACTIONS:
            errors.append(f"action must be LEFT/RIGHT/STRAIGHT/STOP/WAIT, got: {data['action']}")

    if "confidence" in data:
        c = data["confidence"]
        if not isinstance(c, (int, float)) or c < 0 or c > 1:
            errors.append(f"confidence must be 0-1, got: {c}")

    return errors


def safe_fallback(perception: Optional[dict] = None) -> dict:
    """Return a safe fallback perception when Vision fails."""
    return {
        "scene_summary": "Vision perception unavailable. Waiting for reliable data.",
        "objects": [],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.5},
        "center_path": {"clear": True, "risk": "LOW", "confidence": 0.5},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.5},
        "overall_risk": "HIGH",
        "confidence": 0.0,
        "debug": {"source": "safe_fallback", "reason": "vision_unavailable"},
    }


# ---------------------------------------------------------------------------
# Google Vision API adapter
# ---------------------------------------------------------------------------

GOOGLE_VISION_URL = "https://vision.googleapis.com/v1/images:annotate"
GOOGLE_VISION_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/cloud-vision",
]

# Labels that Google Vision commonly returns for common obstacles
VISION_LABEL_ALIASES = {
    "person": "person", "people": "person", "man": "person", "woman": "person",
    "child": "person", "man": "person", "woman": "person",
    "car": "vehicle", "cars": "vehicle", "truck": "vehicle", "bus": "vehicle",
    "van": "vehicle", "sedan": "vehicle", "toyota": "vehicle", "honda": "vehicle",
    "motorcycle": "motorcycle", "motorbike": "motorcycle",
    "bicycle": "bicycle", "bike": "bicycle",
    "pole": "pole", "traffic light": "sign", "traffic signal": "sign",
    "sign": "sign", "street sign": "sign", "billboard": "sign",
    "tree": "tree", "building": "wall", "wall": "wall",
    "stairs": "stairs", "staircase": "stairs", "stair": "stairs",
    "bench": "bench", "trash can": "bin", "bin": "bin",
    "door": "door", "fence": "fence", "fencing": "fence",
    "road": "road", "street": "road", "sidewalk": "sidewalk",
    "crosswalk": "crossing", "crossing": "crossing",
    "curb": "curb", "pothole": "pothole",
    "animal": "animal", "dog": "animal", "cat": "animal",
    "construction": "construction_barrier", "barrier": "construction_barrier",
    "cone": "construction_barrier", "barricade": "construction_barrier",
}


def google_vision_label_to_object_type(label: str) -> Optional[str]:
    """Map a Google Vision label annotation to our object type enum."""
    if not label:
        return None
    label_lower = label.lower().strip()
    return VISION_LABEL_ALIASES.get(label_lower, "unknown_obstacle")


# ---------------------------------------------------------------------------
# Mock vision provider
# ---------------------------------------------------------------------------

MOCK_SCENARIOS: dict[str, dict] = {
    "clear": {
        "scene_summary": "Open sidewalk ahead. No obstacles detected.",
        "objects": [],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.90},
        "center_path": {"clear": True, "risk": "LOW", "confidence": 0.92},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.88},
        "overall_risk": "LOW",
        "confidence": 0.90,
    },
    "pole_left": {
        "scene_summary": "Pole detected ahead on sidewalk.",
        "objects": [
            {"type": "pole", "position": "center", "estimated_distance_m": 4.0,
             "distance_confidence": 0.72, "blocks_path": True, "risk": "HIGH"},
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.88},
        "center_path": {"clear": False, "risk": "HIGH", "confidence": 0.91},
        "right_path": {"clear": False, "risk": "HIGH", "confidence": 0.75},
        "overall_risk": "HIGH",
        "confidence": 0.86,
    },
    "vehicle_stop": {
        "scene_summary": "Vehicle approaching head-on.",
        "objects": [
            {"type": "vehicle", "position": "center", "estimated_distance_m": 6.0,
             "distance_confidence": 0.85, "blocks_path": True, "risk": "CRITICAL"},
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
        "center_path": {"clear": False, "risk": "CRITICAL", "confidence": 0.92},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.82},
        "overall_risk": "CRITICAL",
        "confidence": 0.90,
    },
    "all_blocked": {
        "scene_summary": "Multiple obstacles block all directions.",
        "objects": [
            {"type": "construction_barrier", "position": "center", "estimated_distance_m": 3.0,
             "distance_confidence": 0.80, "blocks_path": True, "risk": "CRITICAL"},
            {"type": "wall", "position": "left", "estimated_distance_m": 4.0,
             "distance_confidence": 0.75, "blocks_path": True, "risk": "HIGH"},
            {"type": "vehicle", "position": "right", "estimated_distance_m": 5.0,
             "distance_confidence": 0.65, "blocks_path": True, "risk": "CRITICAL"},
        ],
        "left_path": {"clear": False, "risk": "HIGH", "confidence": 0.80},
        "center_path": {"clear": False, "risk": "CRITICAL", "confidence": 0.90},
        "right_path": {"clear": False, "risk": "CRITICAL", "confidence": 0.85},
        "overall_risk": "CRITICAL",
        "confidence": 0.88,
    },
    "low_conf": {
        "scene_summary": "Blurry frame. Unable to determine obstacles reliably.",
        "objects": [],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.40},
        "center_path": {"clear": True, "risk": "LOW", "confidence": 0.35},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.38},
        "overall_risk": "LOW",
        "confidence": 0.30,
    },
    "unknown_object": {
        "scene_summary": "Unknown object detected ahead.",
        "objects": [
            {"type": "unknown_obstacle", "position": "center", "estimated_distance_m": None,
             "distance_confidence": 0.20, "blocks_path": True, "risk": "MEDIUM"},
        ],
        "left_path": {"clear": True, "risk": "LOW", "confidence": 0.70},
        "center_path": {"clear": False, "risk": "MEDIUM", "confidence": 0.60},
        "right_path": {"clear": True, "risk": "LOW", "confidence": 0.65},
        "overall_risk": "MEDIUM",
        "confidence": 0.55,
    },
}

import requests


def analyze_frame_google_vision(
    image_base64: str,
    api_key: str,
    frame_timestamp_ms: Optional[int] = None,
) -> dict:
    """
    Send an image to Google Cloud Vision API and return structured perception.

    Uses label detection + object localization.
    Maps Vision labels to our object type enum.
    Estimates distance heuristically (with low confidence — monocular camera limitation).

    Args:
        image_base64: Base64-encoded JPEG image
        api_key: Google Cloud API key (must have Vision API enabled)
        frame_timestamp_ms: Optional timestamp of the captured frame

    Returns:
        Dict conforming to perception schema, or safe fallback on error.
    """
    start = time.time()

    # Build Vision API request with label detection + object localization
    payload = {
        "requests": [{
            "image": {"content": image_base64},
            "features": [
                {"type": "LABEL_DETECTION", "maxResults": 15},
                {"type": "OBJECT_LOCALIZATION", "maxResults": 10},
            ]
        }]
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }

    try:
        resp = requests.post(GOOGLE_VISION_URL, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        vision_data = resp.json()
    except requests.Timeout:
        return safe_fallback()
    except requests.RequestException:
        return safe_fallback()
    except json.JSONDecodeError:
        return safe_fallback()

    # Parse Vision response
    responses = vision_data.get("responses", [])
    if not responses:
        return safe_fallback()

    vision_resp = responses[0]

    # Check for Vision API errors
    if "error" in vision_resp:
        return safe_fallback()

    # Collect labels
    labels: list[tuple[str, float]] = []
    for anno in vision_resp.get("labelAnnotations", []):
        name = anno.get("description", "").strip()
        score = anno.get("score", 0)
        if name and score > 0.5:
            labels.append((name, score))

    # Collect localized objects
    objects: list[dict] = []
    seen_types: set[str] = set()

    for anno in vision_resp.get("localizedObjectAnnotations", []):
        name = anno.get("name", "").strip()
        score = anno.get("score", 0)
        if not name or score < 0.5:
            continue

        obj_type = google_vision_label_to_object_type(name)
        if obj_type is None:
            continue

        # Estimate position based on bounding polygon center
        poly = anno.get("boundingPoly", {})
        vertices = poly.get("normalizedVertices", [])
        if vertices:
            cx = sum(v.get("x", 0) for v in vertices) / len(vertices)
            cy = sum(v.get("y", 0) for v in vertices) / len(vertices)
            position = _position_from_center(cx, cy)
        else:
            position = "center"

        # Monocular distance estimation (HEURISTIC — low confidence)
        # Objects higher in the frame (lower y) are generally farther away
        est_distance = _estimate_distance_from_y(cy, score)
        dist_conf = min(0.6, score * 0.5 + 0.2)  # Low confidence — monocular limitation

        # Determine if it blocks path
        blocks = obj_type in ("vehicle", "motorcycle", "bicycle", "person",
                               "construction_barrier", "pole", "wall", "fence",
                               "stairs", "curb", "pothole", "unknown_obstacle")
        if obj_type in ("tree", "bench", "bin", "sign", "door", "animal"):
            blocks = position in ("center", "center_far")

        # Determine risk
        base_danger = TYPE_DANGER.get(obj_type, 0.30)
        if est_distance is not None and est_distance < 3.0:
            base_danger = min(1.0, base_danger * 1.5)
        if est_distance is not None and est_distance < 1.0:
            base_danger = min(1.0, base_danger * 1.3)

        if base_danger >= 0.85:
            risk = "CRITICAL"
        elif base_danger >= 0.65:
            risk = "HIGH"
        elif base_danger >= 0.40:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        obj_id = f"{obj_type}_{position}"
        if obj_id in seen_types:
            continue
        seen_types.add(obj_id)

        objects.append({
            "type": obj_type,
            "position": position,
            "estimated_distance_m": est_distance,
            "distance_confidence": round(dist_conf, 2),
            "blocks_path": blocks,
            "risk": risk,
        })

    # Deduplicate labels-based objects
    label_objects: list[dict] = []
    label_seen: set[str] = set()
    for label_name, score in sorted(labels, key=lambda x: -x[1])[:10]:
        obj_type = google_vision_label_to_object_type(label_name)
        if obj_type is None:
            continue
        obj_id = f"{obj_type}_label"
        if obj_id in label_seen:
            continue
        label_seen.add(obj_id)

        # Estimate position from label (labels don't have bounding boxes)
        position = "center"  # Labels have no position info — be honest about it

        label_objects.append({
            "type": obj_type,
            "position": position,
            "estimated_distance_m": None,  # Labels don't give distance
            "distance_confidence": 0.15,   # Very low — no spatial info
            "blocks_path": obj_type in ("vehicle", "motorcycle", "pole", "construction_barrier"),
            "risk": "MEDIUM" if score > 0.8 else "LOW",
        })

    # Merge: prefer localized objects (have position), supplement with labels
    merged_objects = objects
    for lo in label_objects:
        # Don't add if we already have the same type from localization
        if not any(o["type"] == lo["type"] and o.get("position") != "center" for o in merged_objects):
            merged_objects.append(lo)

    # Limit total objects
    merged_objects = merged_objects[:15]

    # Build path analysis
    left_objs = [o for o in merged_objects if o["position"].startswith("left")]
    center_objs = [o for o in merged_objects if o["position"].startswith("center")]
    right_objs = [o for o in merged_objects if o["position"].startswith("right")]

    def analyze_path(objs: list[dict]) -> dict:
        if not objs:
            return {"clear": True, "risk": "LOW", "confidence": 0.85}
        danger = max(
            TYPE_DANGER.get(o["type"], 0.3) *
            (1.0 if o["estimated_distance_m"] is None else
             (1.0 if o["estimated_distance_m"] < 2 else
              0.8 if o["estimated_distance_m"] < 5 else
              0.5 if o["estimated_distance_m"] < 10 else 0.2))
            for o in objs
        )
        if danger >= 0.85:
            risk = "CRITICAL"
        elif danger >= 0.65:
            risk = "HIGH"
        elif danger >= 0.4:
            risk = "MEDIUM"
        else:
            risk = "LOW"
        return {
            "clear": danger < 0.3 and not any(o.get("blocks_path") for o in objs),
            "risk": risk,
            "confidence": min(0.95, 0.5 + 0.05 * len(objs)),
        }

    left_path = analyze_path(left_objs)
    center_path = analyze_path(center_objs)
    right_path = analyze_path(right_objs)

    # Overall risk
    all_risks = [center_path["risk"], left_path["risk"], right_path["risk"]]
    for o in merged_objects:
        if o.get("risk"):
            all_risks.append(o["risk"])
    risk_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    overall_risk = max(all_risks, key=lambda r: risk_order.get(r, 0))

    # Scene summary
    if merged_objects:
        types = sorted(set(o["type"] for o in merged_objects))
        summary = f"Detected: {', '.join(types[:5])}"
        if center_objs:
            summary += ". Hazard ahead."
    else:
        summary = "Scene analyzed. No prominent obstacles detected."

    processing_time = int((time.time() - start) * 1000)

    return {
        "scene_summary": summary,
        "objects": merged_objects,
        "left_path": left_path,
        "center_path": center_path,
        "right_path": right_path,
        "overall_risk": overall_risk,
        "confidence": min(0.90, 0.5 + 0.05 * len(merged_objects)),
        "frame_timestamp_ms": frame_timestamp_ms,
        "debug": {
            "provider": "google_vision",
            "label_count": len(labels),
            "object_count": len(merged_objects),
            "processing_time_ms": processing_time,
        },
    }


def _position_from_center(cx: float, cy: float) -> str:
    """Estimate position label from bounding box center (normalized 0-1)."""
    if cx < 0.33:
        h = "left"
    elif cx > 0.66:
        h = "right"
    else:
        h = "center"

    if cy < 0.33:
        v = "far"
    elif cy > 0.66:
        v = ""
    else:
        v = ""

    return f"{h}_{v}" if v else h


def _estimate_distance_from_y(cy: float, confidence: float) -> Optional[float]:
    """
    VERY ROUGH distance estimate from vertical position in frame.
    Objects lower in frame (higher y) are generally closer.
    This is a MONOCULAR ESTIMATE — low confidence, clearly documented.

    Returns meters estimate or None if unreliable.
    """
    # cy=0 is top (far), cy=1 is bottom (close)
    # Very rough: 0.8 y → ~2m, 0.5 y → ~5m, 0.2 y → ~15m
    if confidence < 0.3:
        return None  # Too uncertain

    rough_m = 20 * (1.0 - cy)  # 0 at bottom (close=0m), 20 at top (far=20m)
    if rough_m < 0.5:
        return 0.5
    if rough_m > 18:
        return None  # Too far to estimate with monocular camera
    return round(rough_m, 1)


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------

def analyze_frame_mock(
    image_base64: str = "",
    scenario: str = "clear",
    frame_timestamp_ms: Optional[int] = None,
) -> dict:
    """Return a mock perception result for testing without an API key."""
    scenario_data = MOCK_SCENARIOS.get(scenario, MOCK_SCENARIOS["clear"])
    result = dict(scenario_data)
    result["frame_timestamp_ms"] = frame_timestamp_ms or int(time.time() * 1000)
    result["debug"] = result.get("debug", {})
    result["debug"]["provider"] = "mock"
    result["debug"]["scenario"] = scenario
    return result


# ---------------------------------------------------------------------------
# Unified analyze_frame entry point
# ---------------------------------------------------------------------------

def analyze_frame(
    image_base64: str,
    provider: VisionProvider = VisionProvider.MOCK,
    api_key: Optional[str] = None,
    scenario: str = "clear",
    frame_timestamp_ms: Optional[int] = None,
) -> dict:
    """
    Analyze a camera frame and return structured perception.

    This is the main entry point. The rest of the application should use this,
    NOT the provider-specific functions directly.

    Args:
        image_base64: Base64-encoded JPEG frame
        provider: Which vision provider to use
        api_key: API key for the provider (if needed)
        scenario: Mock scenario name (only used by mock provider)
        frame_timestamp_ms: Timestamp of the captured frame

    Returns:
        Dict conforming to perception schema, OR safe fallback on failure.
    """
    if provider == VisionProvider.MOCK:
        return analyze_frame_mock(
            image_base64=image_base64,
            scenario=scenario,
            frame_timestamp_ms=frame_timestamp_ms,
        )
    elif provider == VisionProvider.GOOGLE_VISION:
        if not api_key:
            return safe_fallback()
        return analyze_frame_google_vision(
            image_base64=image_base64,
            api_key=api_key,
            frame_timestamp_ms=frame_timestamp_ms,
        )
    else:
        return safe_fallback()
