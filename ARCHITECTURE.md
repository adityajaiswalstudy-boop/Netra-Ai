# AI SafePath — Architecture

## System Overview

AI SafePath is a mobile-first AI safety assistant that combines two complementary information sources:

1. **Global navigation context** — Google Maps **Routes API v2** provides walking route, steps, turn instructions
2. **Local environmental perception** — Camera frames analyzed by vision AI to detect obstacles, vehicles, pedestrians

These are fused by a **deterministic safety decision engine** that produces exactly one of: LEFT, RIGHT, STRAIGHT, STOP, WAIT.

## Design Principles

### Safety First
- Safety beats route efficiency in every decision
- Vehicle hazards → immediate STOP regardless of navigation context
- Low perception confidence → WAIT (never guess)

### Modular n8n Workflows
- 5 separate workflows instead of one giant workflow
- Each workflow has a single responsibility
- Importable independently to n8n Cloud

### Deterministic Safety Rules
- The safety decision engine uses deterministic rules, not LLM reasoning
- Rules are transparent, testable, and predictable
- The engine is verified by 45 unit tests (17 safety + 28 maps)

### Graceful Degradation
- Maps API failure → local perception still works
- Vision API failure → WAIT/STOP
- TTS failure → browser SpeechSynthesis fallback
- GPS failure → clear indication to user

### Clean API Abstraction
- The Maps mapper (server/maps_mapper.py) normalizes the Routes API v2 response
- No other module depends on Google's raw response structure
- Easy to swap providers or add mock routes for testing

## Data Flow

```
[mobile]                        [n8n cloud]                      [external]
   │                               │                               │
   │  User enters destination     │                               │
   │──────────────────────────────►│                               │
   │                               │  01_navigation_start          │
   │                               │  ──► Google Routes API v2     │
   │                               │  ◄── walking route steps      │
   │                               │◄──────────────────────────────│
   │◄──────────────────────────────│                               │
   │                               │                               │
   │  Start camera + GPS          │                               │
   │  Periodic frame capture ─────► 02_perception                │
   │  (base64 JPEG)               │  ──► Vision AI / LLM          │
   │                               │  ◄── structured perception    │
   │◄──────────────────────────────│                               │
   │                               │                               │
   │  perception + navigation ────► 03_safety_decision           │
   │                               │  ──► deterministic rules      │
   │                               │  ◄── LEFT/RIGHT/STRAIGHT/     │
   │                               │        STOP/WAIT              │
   │◄──────────────────────────────│                               │
   │                               │                               │
   │  voice_instruction ──────────► 04_voice (optional)          │
   │                               │  ──► Google Cloud TTS         │
   │◄──────────────────────────────│  ◄── audio (mp3)              │
   │                               │                               │
   │  Browser SpeechSynthesis ───── fallback when TTS unavailable│
   │  Audio to Bluetooth earphones ◄── phone audio out          │
```

## Component Responsibilities

### Mobile PWA (mobile/)
- **Camera**: Periodic frame capture via getUserMedia, JPEG encoding, base64
- **GPS**: Geolocation API for current position and heading
- **Destination input**: Text input for destination address/name
- **Perception loop**: Capture → POST to /perception → receive structured JSON
- **Decision loop**: Send perception + navigation → POST to /safety-decision → receive action
- **TTS**: Browser SpeechSynthesis fallback + optional cloud TTS via /voice
- **Live/Demo mode**: Clear visual indicator showing which mode is active
- **Demo mode**: Built-in simulated scenarios for presentation

### Safety Decision Engine (server/safety_engine.py)
- **Input**: Validated perception JSON + optional navigation state
- **Output**: Exactly one of LEFT/RIGHT/STRAIGHT/STOP/WAIT
- **Rules**:
  1. If perception confidence < 0.45 → WAIT
  2. If vehicle/motorcycle in center < 8m → STOP
  3. If vehicle in center with unknown distance → STOP (conservative)
  4. If all paths blocked at HIGH/CRITICAL risk → STOP
  5. If center blocked at HIGH/CRITICAL risk → best side path (LEFT/RIGHT)
  6. If center clear and LOW risk → STRAIGHT
  7. If center MEDIUM risk → STRAIGHT with caution
  8. Fallback → WAIT

### Google Maps Routes API Mapper (server/maps_mapper.py)
- **Input**: Origin lat/lng, destination lat/lng, API key
- **Output**: Normalized WalkingRoute (route_id, distance_m, duration_s, steps[], polyline, warnings)
- **API**: POST https://routes.googleapis.com/directions/v2:computeRoutes
- **Auth**: X-Goog-Api-Key header
- **Field mask**: X-Goog-FieldMask header (routes.duration,routes.distanceMeters,routes.polyline,routes.legs,routes.warnings)
- **Duration parsing**: Handles ISO 8601 ("PT3M") and seconds format ("780s")
- **Maneuver mapping**: 40+ Routes API maneuvers → 8 simplified turn types
- **Mock generator**: make_mock_walking_route() for testing without API key

### n8n Workflows (n8n/*.json)

| Workflow | Purpose | Key Nodes |
|----------|---------|-----------|
| 01_navigation_start | Start navigation, get walking route | Webhook → Code (validate) → HTTP Request (Routes API v2) → Code (parse) → Respond |
| 02_perception | Analyze camera frame | Webhook → Code (validate) → Vision API → Code (schema conversion) → Respond |
| 03_safety_decision | Deterministic safety rules | Webhook → Code (validate) → Code (apply rules) → Respond |
| 04_voice | TTS audio generation | Webhook → Code (validate) → HTTP Request (Google Cloud TTS, OAuth2) → Code (parse) → Respond |
| 05_session_management | Session CRUD | Webhook → Code (handler) → Respond |

## JSON Schemas

### Perception Schema (schemas/perception.schema.json)
Defines the structured output from vision analysis: scene summary, detected objects with type/position/distance/risk, per-path analysis (left/center/right), overall risk and confidence.

### Decision Schema (schemas/decision.schema.json)
Defines the final output: action (enum), reason, confidence, timestamp, perception summary, navigation context, voice instruction, debug info.

### Navigation Schema (schemas/navigation.schema.json)
Defines session state: session ID, origin, destination, current location, heading, route steps, status, last perception/decision.

## External APIs

| API | Purpose | Where configured |
|-----|---------|-----------------|
| Google Routes API v2 | Walking route, steps | 01_navigation_start workflow + server/maps_mapper.py |
| Google Vision API (or LLM) | Object detection, scene analysis | 02_perception workflow |
| Google Cloud TTS | Voice instructions audio | 04_voice workflow |

## Testing

### Safety Decision Engine (17 tests)
Tests all 10 competition scenarios + validation functions + deterministic rules.

### Maps Mapper (28 tests)
Tests duration parsing, maneuver mapping, mock route generation, response normalization, API constants. No API key required.

### Running all tests
```bash
cd Netra-Ai
python tests/safety/test_decisions.py
python tests/safety/test_maps.py
```

## Limitations

- **Monocular distance estimation is not exact** — distances are estimates with confidence values
- **This is a prototype** — not a replacement for human judgment or professional navigation aids
- **Walking routes may miss sidewalks** — Google Maps Routes API provides global context only; local perception provides safety
- **Vision pipeline** — the n8n workflow uses Vision API labels as a fallback. Replace with GPT-4V or Claude for proper object detection
- **Session persistence** — n8n workflow 05 stores sessions in-memory. Add a database for production

## Future Improvements

- Replace Vision API label fallback with GPT-4V or Claude for proper object detection
- Add Redis for session persistence
- Add haptic feedback for STOP decisions
- Offline mode with on-device object detection
- Alternative TTS providers (Azure, Amazon Polly)
- PWA service worker for installability
