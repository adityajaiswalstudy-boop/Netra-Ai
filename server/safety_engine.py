
"""
AI SafePath — Deterministic Safety Decision Engine

Combines:
  - Structured perception (from vision AI)
  - Navigation context (from Google Maps)
  - Deterministic safety rules

Produces ONLY: LEFT | RIGHT | STRAIGHT | STOP | WAIT

Safety beats route efficiency. Always.
"""

from __future__ import annotations
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Action(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    STRAIGHT = "STRAIGHT"
    STOP = "STOP"
    WAIT = "WAIT"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Decision result
# ---------------------------------------------------------------------------

@dataclass
class SafetyDecision:
    action: Action
    reason: str
    confidence: float
    timestamp: float = field(default_factory=time.time)
    perception_summary: dict = field(default_factory=dict)
    navigation_context: dict = field(default_factory=dict)
    voice_instruction: str = ""
    debug: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "confidence": round(self.confidence, 3),
            "timestamp": self.timestamp,
            "perception_summary": self.perception_summary,
            "navigation_context": self.navigation_context,
            "voice_instruction": self.voice_instruction,
            "debug": self.debug,
        }


# ---------------------------------------------------------------------------
# Risk mapping helpers
# ---------------------------------------------------------------------------

RISK_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}


def worst_risk(*risks: Optional[RiskLevel]) -> RiskLevel:
    """Return the worst (highest) risk from a sequence."""
    levels = [RISK_ORDER[r] for r in risks if r is not None]
    if not levels:
        return RiskLevel.LOW
    return RiskLevel(max(levels))


def risk_from_score(score: float) -> RiskLevel:
    """Map a 0-1 danger score to a risk level."""
    if score >= 0.85:
        return RiskLevel.CRITICAL
    if score >= 0.65:
        return RiskLevel.HIGH
    if score >= 0.40:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


# ---------------------------------------------------------------------------
# Path analysis
# ---------------------------------------------------------------------------

@dataclass
class PathAnalysis:
    clear: bool
    risk: RiskLevel
    confidence: float
    blocking_objects: list = field(default_factory=list)


def analyze_path(objects: list[dict], direction: str) -> PathAnalysis:
    """
    Analyze a single path direction (left/center/right) given detected objects.

    Objects should be dicts with: type, position, risk, blocks_path,
    estimated_distance_m, distance_confidence.
    """
    blocking: list[dict] = []
    danger_score = 0.0
    object_count = 0

    # Direction prefix: "left", "center", "right"
    dir_prefix = direction.lower()

    for obj in objects:
        obj_type = obj.get("type", "")
        position = obj.get("position", "")
        blocks = obj.get("blocks_path", False)
        obj_risk = obj.get("risk")
        dist = obj.get("estimated_distance_m")
        dist_conf = obj.get("distance_confidence", 0)

        # Determine if this object affects this path
        if not (position.startswith(dir_prefix) or position == direction):
            continue

        object_count += 1

        # Base danger from object type
        type_danger: dict[str, float] = {
            "vehicle": 0.95,
            "motorcycle": 0.90,
            "bicycle": 0.70,
            "person": 0.65,
            "construction_barrier": 0.60,
            "pole": 0.45,
            "wall": 0.50,
            "fence": 0.40,
            "stairs": 0.55,
            "curb": 0.30,
            "pothole": 0.35,
            "tree": 0.20,
            "bench": 0.15,
            "bin": 0.10,
            "sign": 0.12,
            "door": 0.18,
            "animal": 0.50,
            "unknown_obstacle": 0.40,
        }
        base = type_danger.get(obj_type, 0.30)

        # Distance modifier: closer = more dangerous
        if dist is not None and dist > 0:
            if dist < 2.0:
                dist_mod = 1.0
            elif dist < 5.0:
                dist_mod = 0.8
            elif dist < 10.0:
                dist_mod = 0.5
            else:
                dist_mod = 0.2
        else:
            dist_mod = 0.5  # unknown distance, mid-range

        # Distance confidence penalty
        if dist_conf < 0.5:
            dist_mod *= 0.6

        # If it blocks path, bump danger
        if blocks:
            base += 0.25

        obj_danger = min(base * dist_mod, 1.0)
        danger_score = max(danger_score, obj_danger)

        if blocks or obj_danger >= 0.4:
            blocking.append(obj)

    clear = danger_score < 0.30 and len(blocking) == 0
    risk = risk_from_score(danger_score)

    confidence = min(1.0, 0.5 + 0.1 * object_count)
    if object_count == 0:
        confidence = 0.85  # no objects seen across all paths = high confidence

    return PathAnalysis(clear=clear, risk=risk, confidence=confidence, blocking_objects=blocking)


# ---------------------------------------------------------------------------
# Safety Decision Engine
# ---------------------------------------------------------------------------

class SafetyDecisionEngine:
    """
    Deterministic safety decision engine.

    Priority order (highest first):
      1. Immediate physical safety
      2. Path clearance
      3. Avoid vehicles / dangerous road situations
      4. Current navigation instruction
      5. Destination progress
      6. Route efficiency
    """

    # Vehicle types that trigger STOP regardless of distance when close
    VEHICLE_TYPES = {"vehicle", "motorcycle"}

    # Object types that definitively block a path
    HARD_BLOCKERS = {"wall", "construction_barrier", "fence"}

    def __init__(self, confidence_threshold: float = 0.45):
        """
        Args:
            confidence_threshold: Below this overall perception confidence,
                the engine returns WAIT instead of a directional action.
        """
        self.confidence_threshold = confidence_threshold

    def decide(
        self,
        perception: dict,
        navigation: Optional[dict] = None,
    ) -> SafetyDecision:
        """
        Args:
            perception: Validated perception dict (matches perception schema).
            navigation: Optional navigation state dict.

        Returns:
            SafetyDecision with exactly one of LEFT/RIGHT/STRAIGHT/STOP/WAIT.
        """
        now = time.time()

        # --- Validate perception confidence ---
        perception_conf = perception.get("confidence", 0)
        if perception_conf < self.confidence_threshold:
            return SafetyDecision(
                action=Action.WAIT,
                reason=(
                    f"Perception confidence ({perception_conf:.2f}) below threshold "
                    f"({self.confidence_threshold:.2f}). Waiting for better data."
                ),
                confidence=perception_conf,
                timestamp=now,
                perception_summary={
                    "overall_risk": perception.get("overall_risk", "LOW"),
                    "primary_threat": "low_confidence",
                    "threat_count": 0,
                },
                voice_instruction="Wait. Reassessing.",
                debug={
                    "rules_triggered": ["low_confidence"],
                    "safety_score": perception_conf,
                },
            )

        objects = perception.get("objects", [])
        overall_risk = RiskLevel(perception.get("overall_risk", "LOW"))

        # --- Analyze each path ---
        left_analysis = analyze_path(objects, "left")
        center_analysis = analyze_path(objects, "center")
        right_analysis = analyze_path(objects, "right")

        # --- Check for immediate vehicle hazards ---
        vehicle_threats = [
            o for o in objects
            if o.get("type") in self.VEHICLE_TYPES
            and o.get("position", "").startswith("center")
        ]

        immediate_stop = False
        stop_reason_parts: list[str] = []

        for v in vehicle_threats:
            dist = v.get("estimated_distance_m")
            if dist is not None and dist < 8.0:
                immediate_stop = True
                stop_reason_parts.append(
                    f"{v['type']} approaching at ~{dist:.1f}m"
                )
            elif dist is None:
                # Unknown distance vehicle in center = conservative STOP
                immediate_stop = True
                stop_reason_parts.append("vehicle in path (distance unknown)")

        if immediate_stop:
            return SafetyDecision(
                action=Action.STOP,
                reason="; ".join(stop_reason_parts) + ". Stopping for safety.",
                confidence=min(0.95, 0.7 + 0.1 * len(vehicle_threats)),
                timestamp=now,
                perception_summary={
                    "overall_risk": RiskLevel.CRITICAL,
                    "primary_threat": "vehicle",
                    "threat_count": len(vehicle_threats),
                },
                navigation_context=_nav_context(navigation),
                voice_instruction="Vehicle approaching. Stop.",
                debug={
                    "rules_triggered": ["vehicle_immediate_stop"],
                    "safety_score": 0.95,
                },
            )

        # --- Center path check ---
        if not center_analysis.clear and center_analysis.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            # Center is blocked at high/critical risk -> must go around
            pass  # handled by path selection below
        elif not center_analysis.clear:
            # Center blocked but low/medium risk
            pass

        # --- Path selection: prefer the safest available path ---
        paths = {
            "LEFT": (left_analysis, "left"),
            "RIGHT": (right_analysis, "right"),
            "STRAIGHT": (center_analysis, "center"),
        }

        # Score each path: clear + low risk = best
        def path_score(analysis: PathAnalysis) -> tuple[int, int]:
            # First criterion: is it clear?
            clear_pref = 0 if analysis.clear else 1
            # Second criterion: risk level (lower is better)
            risk_pref = RISK_ORDER[analysis.risk]
            return (clear_pref, risk_pref)

        scored = [(path_name, path_score(analysis), analysis)
                  for path_name, (analysis, _) in paths.items()]
        scored.sort(key=lambda x: x[1])

        best_action, best_score, best_analysis = scored[0]
        second_best = scored[1] if len(scored) > 1 else None

        # --- Decision logic ---

        rules_triggered: list[str] = []

        # Case 1: All paths blocked -> STOP
        all_blocked = all(not analysis.clear for analysis, _ in paths.values())
        if all_blocked and overall_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return SafetyDecision(
                action=Action.STOP,
                reason="All paths blocked. Stopping.",
                confidence=0.85,
                timestamp=now,
                perception_summary={
                    "overall_risk": overall_risk.value,
                    "primary_threat": _primary_threat(objects),
                    "threat_count": len(objects),
                },
                navigation_context=_nav_context(navigation),
                voice_instruction="Path blocked. Stop.",
                debug={
                    "rules_triggered": ["all_paths_blocked"],
                    "safety_score": RISK_ORDER[overall_risk],
                },
            )

        # Case 2: Center blocked, choose best side
        if not center_analysis.clear and center_analysis.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            rules_triggered.append("center_blocked")
            if best_action in ("LEFT", "RIGHT"):
                side = "left" if best_action == Action.LEFT else "right"
                blockage = _describe_blockage(center_analysis.blocking_objects)
                return SafetyDecision(
                    action=Action(best_action),
                    reason=f"Center path blocked: {blockage}. Go {side}.",
                    confidence=best_analysis.confidence,
                    timestamp=now,
                    perception_summary={
                        "overall_risk": overall_risk.value,
                        "primary_threat": _primary_threat(objects),
                        "threat_count": len(objects),
                    },
                    navigation_context=_nav_context(navigation),
                    voice_instruction=f"{blockage}. Move {side}.",
                    debug={
                        "rules_triggered": rules_triggered,
                        "safety_score": RISK_ORDER[overall_risk],
                        "alternative_considered": second_best[0] if second_best else None,
                    },
                )

        # Case 3: Straight is clear -> STRAIGHT
        if center_analysis.clear and center_analysis.risk == RiskLevel.LOW:
            rules_triggered.append("path_clear")
            return SafetyDecision(
                action=Action.STRAIGHT,
                reason="Path ahead clear. Continue forward.",
                confidence=center_analysis.confidence,
                timestamp=now,
                perception_summary={
                    "overall_risk": overall_risk.value,
                    "primary_threat": _primary_threat(objects) or "none",
                    "threat_count": len(objects),
                },
                navigation_context=_nav_context(navigation),
                voice_instruction="Path clear. Continue straight.",
                debug={
                    "rules_triggered": rules_triggered,
                    "safety_score": RISK_ORDER[overall_risk],
                },
            )

        # Case 4: Best available is a side path
        if best_action in ("LEFT", "RIGHT"):
            side = best_action.lower()
            blockage = _describe_blockage(center_analysis.blocking_objects) if not center_analysis.clear else "hazard ahead"
            return SafetyDecision(
                action=Action(best_action),
                reason=f"{blockage}. Safest path is {side}.",
                confidence=best_analysis.confidence,
                timestamp=now,
                perception_summary={
                    "overall_risk": overall_risk.value,
                    "primary_threat": _primary_threat(objects),
                    "threat_count": len(objects),
                },
                navigation_context=_nav_context(navigation),
                voice_instruction=f"{blockage}. Move {side}." if blockage else f"Move {side}.",
                debug={
                    "rules_triggered": rules_triggered,
                    "safety_score": RISK_ORDER[overall_risk],
                    "alternative_considered": second_best[0] if second_best else None,
                },
            )

        # Fallback: if center is blocked but at LOW/MEDIUM risk, we can still go straight
        # with caution (only if confidence is decent)
        if center_analysis.risk in (RiskLevel.LOW, RiskLevel.MEDIUM):
            return SafetyDecision(
                action=Action.STRAIGHT,
                reason=f"Center path has {center_analysis.risk.lower()} risk. Proceed with caution.",
                confidence=center_analysis.confidence,
                timestamp=now,
                perception_summary={
                    "overall_risk": overall_risk.value,
                    "primary_threat": _primary_threat(objects) or "low_risk_obstacle",
                    "threat_count": len(objects),
                },
                navigation_context=_nav_context(navigation),
                voice_instruction="Path ahead. Continue with caution.",
                debug={
                    "rules_triggered": ["cautious_straight"],
                    "safety_score": RISK_ORDER[center_analysis.risk],
                },
            )

        # Absolute fallback: WAIT
        return SafetyDecision(
            action=Action.WAIT,
            reason="Unable to determine safe path. Waiting.",
            confidence=perception_conf,
            timestamp=now,
            perception_summary={
                "overall_risk": overall_risk.value,
                "primary_threat": _primary_threat(objects),
                "threat_count": len(objects),
            },
            voice_instruction="Wait. Reassessing.",
            debug={
                "rules_triggered": ["fallback_wait"],
                "safety_score": RISK_ORDER[overall_risk],
            },
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nav_context(navigation: Optional[dict]) -> dict:
    if not navigation:
        return {}
    route = navigation.get("route", {})
    steps = route.get("steps", [])
    current_idx = route.get("current_step_index", 0)
    current_step = steps[current_idx] if steps and current_idx < len(steps) else {}
    next_turn = current_step.get("turn")
    return {
        "current_step_instruction": current_step.get("instruction", ""),
        "remaining_steps": max(0, len(steps) - current_idx),
        "next_turn": next_turn,
    }


def _primary_threat(objects: list[dict]) -> Optional[str]:
    if not objects:
        return None
    # Return the type of the closest high-risk object
    threats = [o for o in objects if o.get("risk") in ("HIGH", "CRITICAL") or o.get("blocks_path")]
    if not threats:
        return None
    threats.sort(key=lambda o: o.get("estimated_distance_m") or 999)
    return threats[0].get("type", "unknown")


def _describe_blockage(blockers: list[dict]) -> str:
    if not blockers:
        return "path blocked"
    types = sorted(set(o.get("type", "obstacle") for o in blockers))
    if len(types) == 1:
        return f"{types[0]} ahead"
    return " and ".join(types) + " ahead"


# ---------------------------------------------------------------------------
# JSON validation
# ---------------------------------------------------------------------------

def validate_perception(data: dict) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["perception must be a JSON object"]

    required = ["scene_summary", "objects", "left_path", "center_path",
                "right_path", "overall_risk", "confidence"]
    for key in required:
        if key not in data:
            errors.append(f"missing required field: {key}")

    if "overall_risk" in data:
        if data["overall_risk"] not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            errors.append(f"overall_risk must be LOW/MEDIUM/HIGH/CRITICAL, got: {data['overall_risk']}")

    if "confidence" in data:
        c = data["confidence"]
        if not isinstance(c, (int, float)) or c < 0 or c > 1:
            errors.append(f"confidence must be 0-1, got: {c}")

    if "objects" in data and isinstance(data["objects"], list):
        valid_types = {
            "person", "vehicle", "motorcycle", "bicycle", "pole", "tree",
            "wall", "stairs", "pothole", "construction_barrier", "bench",
            "bin", "sign", "door", "fence", "road", "sidewalk", "crossing",
            "curb", "unknown_obstacle", "animal",
        }
        valid_positions = {"left", "center", "right", "left_far", "center_far",
                           "right_far", "background"}
        for i, obj in enumerate(data["objects"]):
            if not isinstance(obj, dict):
                errors.append(f"objects[{i}] must be an object")
                continue
            if "type" not in obj:
                errors.append(f"objects[{i}] missing type")
            elif obj["type"] not in valid_types:
                errors.append(f"objects[{i}] invalid type: {obj['type']}")
            if "position" not in obj:
                errors.append(f"objects[{i}] missing position")
            elif obj["position"] not in valid_positions:
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
            if "risk" in p and p["risk"] not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
                errors.append(f"{path_key}.risk invalid: {p['risk']}")
            if "confidence" in p:
                c = p["confidence"]
                if not isinstance(c, (int, float)) or c < 0 or c > 1:
                    errors.append(f"{path_key}.confidence must be 0-1, got: {c}")

    return errors


def validate_decision(data: dict) -> list[str]:
    """Return list of validation errors for a decision (empty = valid)."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["decision must be a JSON object"]

    for key in ("action", "reason", "confidence", "timestamp"):
        if key not in data:
            errors.append(f"missing required field: {key}")

    if "action" in data:
        if data["action"] not in ("LEFT", "RIGHT", "STRAIGHT", "STOP", "WAIT"):
            errors.append(f"action must be LEFT/RIGHT/STRAIGHT/STOP/WAIT, got: {data['action']}")

    if "confidence" in data:
        c = data["confidence"]
        if not isinstance(c, (int, float)) or c < 0 or c > 1:
            errors.append(f"confidence must be 0-1, got: {c}")

    return errors
