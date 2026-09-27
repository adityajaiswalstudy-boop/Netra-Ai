# Architectural Decisions

## Decision Log

### D1: PWA over Native App

**Decision**: Build as a Progressive Web App (PWA) rather than a native iOS/Android app.

**Why**:
- Faster development — single codebase for iOS and Android
- No app store approval needed for competition demo
- Camera and GPS work in modern mobile browsers
- Easier to share with judges (just open a URL)
- Can be added to home screen for app-like experience

**Alternatives considered**:
- **React Native / Flutter**: More native capabilities but slower to build, needs app store for distribution
- **Native Android (Kotlin)**: Most capable but requires Android device for demo, longer dev time

**Rejected**: Native approaches add complexity without clear benefit for a competition prototype.

---

### D2: Periodic Frame Capture over Continuous Video

**Decision**: Capture JPEG frames every 1-2 seconds rather than streaming continuous video.

**Why**:
- Dramatically lower bandwidth — JPEGs are small vs video streams
- Avoids API rate limits and cost (Vision API charges per image)
- Simpler architecture — no WebRTC or video streaming needed
- Each frame is processed independently, easier to debug
- 1-2 second interval is fast enough for walking speed hazards

**Alternatives considered**:
- **WebRTC streaming**: Real-time but complex, high bandwidth, expensive for cloud vision APIs
- **Continuous upload**: Would quickly hit API quotas and bandwidth limits

**Rejected**: Continuous approaches are overkill for walking-speed hazards and expensive.

---

### D3: Deterministic Safety Rules over LLM Decision-Making

**Decision**: Use a deterministic rule engine (Python) for final safety decisions, not an LLM.

**Why**:
- **Predictable**: Same input always produces same output — explainable to judges
- **Testable**: 17 unit tests verify exact behavior across 10 scenarios
- **Safe**: Hard rules for vehicles (STOP under 8m) can't be overridden by an LLM
- **Fast**: Rule evaluation is instant, no LLM latency for the final decision
- **Cheap**: No LLM tokens spent on the decision step

**How it works**:
- Perception (vision AI) → structured JSON
- Deterministic rules evaluate the JSON → LEFT/RIGHT/STRAIGHT/STOP/WAIT
- The same rules run in both Python (server/safety_engine.py) and JavaScript (n8n workflow 03)

**Alternatives considered**:
- **LLM as decision maker**: Could reason about complex situations but unpredictable, expensive, hard to test
- **Hybrid**: LLM for perception, rules for decision — this is what we chose

**Rejected**: Pure LLM decision-making is too unpredictable for safety-critical decisions.

---

### D4: n8n as Workflow Orchestrator

**Decision**: Use n8n Cloud for workflow orchestration rather than a custom backend.

**Why**:
- Visual workflow builder — easy to modify and debug during competition prep
- Pre-built nodes for Google Maps, Vision, TTS APIs
- Webhook triggers from the mobile PWA
- Modular — 5 separate workflows each with clear responsibility
- Importable JSON files — reproducible setup on any n8n instance

**Alternatives considered**:
- **Custom FastAPI/Flask backend**: More control but more code to write and maintain
- **Serverless functions (AWS Lambda, Cloudflare Workers)**: Good but need API gateway setup
- **Direct from PWA to APIs**: Simpler but no orchestration, retry logic, or transformation layer

**Rejected**: Custom backend adds development time without clear benefit for the competition scope.

---

### D5: Google Maps + Camera Fusion

**Decision**: Combine Google Maps navigation context with camera perception for safety decisions.

**Why**:
- **Global + local**: Maps provides the macro route, camera provides micro environmental awareness
- **Context-aware**: A pole on the route is different from a pole off-route
- **Practical**: Navigation systems already tell you where to go; this adds safety awareness
- **Demonstrable**: Judges can see both the route and the local perception

**How it works**:
- Maps → route steps, current instruction, next turn
- Camera → obstacles, vehicles, pedestrians in immediate vicinity
- Safety engine → considers both, safety beats route

**Alternatives considered**:
- **Camera-only**: Would detect obstacles but no navigation context
- **Maps-only**: Great for navigation, no safety awareness of immediate hazards

**Rejected**: Either alone is incomplete — together they provide a more useful system.

---

### D6: Browser SpeechSynthesis as TTS Fallback

**Decision**: Use browser SpeechSynthesis as fallback when cloud TTS is unavailable.

**Why**:
- **Zero cost**: No API calls needed
- **Zero setup**: Works out of the box in browsers
- **Offline-capable**: Works without internet (basic voices)
- **Good enough for demo**: Clear enough for short instructions

**Tradeoffs**:
- Voice quality is robotic compared to Google TTS
- Language support varies by browser/OS
- Not all browsers support it equally

**Rejected**: Relying solely on cloud TTS would add a point of failure. The fallback ensures the demo works even without TTS credentials.

---

### D7: JSON Schema Validation

**Decision**: Validate all AI outputs against JSON schemas before processing.

**Why**:
- **Safety**: Malformed AI output can't cause undefined behavior
- **Clear contracts**: Schemas define exactly what each component expects
- **Early failure**: Bad data is caught before it reaches the decision engine
- **Documentation**: Schemas serve as living documentation of data contracts

**Implementation**:
- `schemas/perception.schema.json` — validates vision output
- `schemas/decision.schema.json` — validates decision output
- `schemas/navigation.schema.json` — validates session state
- Validation functions in `server/safety_engine.py`
- Input validation in n8n workflow 03

---

### D8: Modular n8n Workflows (5 Separate Files)

**Decision**: Split into 5 separate n8n workflows rather than one monolithic workflow.

**Why**:
- **Maintainable**: Each workflow has one job
- **Independently testable**: Can test each workflow's webhook separately
- **Reusability**: Workflows can be rearranged or replaced
- **Import-friendly**: Smaller files, easier to review
- **Parallel development**: Different workflows can be worked on independently

**Workflows**:
1. `01_navigation_start.json` — route planning
2. `02_perception.json` — vision analysis
3. `03_safety_decision.json` — deterministic rules (mirrors Python engine)
4. `04_voice.json` — TTS audio generation
5. `05_session_management.json` — session CRUD

---

### D9: LEFT/RIGHT/STRAIGHT/STOP/WAIT Action Set

**Decision**: Restrict final actions to exactly 5 discrete commands.

**Why**:
- **Simple to communicate**: Short, clear voice instructions
- **Easy to test**: Finite state space — all cases coverable
- **Unambiguous**: No confusion about what "move a little left" means
- **Machine-readable**: Easy for other systems to consume
- **Competition-friendly**: Clear pass/fail evaluation

**Mapping**: The decision engine only produces these 5 values. Any LLM or perception output is normalized through the rules before reaching the final action.

---

### D10: Conservative Default (WAIT/STOP on Uncertainty)

**Decision**: When perception confidence is low or data is incomplete, default to WAIT or STOP.

**Why**:
- **Safety**: Better to wait than to give wrong direction
- **Honest**: Doesn't pretend to know when it doesn't
- **Expected behavior**: Judges will see the system handle uncertainty properly
- **Aligned with spec**: Section 8 of the AI SafePath directive

**Implementation**:
- Perception confidence < 0.45 → WAIT
- Missing required fields → WAIT
- Vehicle with unknown distance → STOP (conservative)

---

### D11: Monocular Distance Estimation with Confidence

**Decision**: Provide estimated distances with explicit confidence values rather than claiming exact measurements.

**Why**:
- **Honest**: Monocular camera can't measure exact distance
- **Useful**: Even rough distance estimates help the decision engine
- **Transparent**: Confidence values communicate uncertainty
- **Safe**: Low-confidence distances are penalized in the risk calculation

**Implementation**:
- `estimated_distance_m` with `distance_confidence` in perception schema
- Distance confidence below 0.5 penalizes the danger score
- Unknown distances default to mid-range danger

---

### D12: Demo Mode Built Into PWA

**Decision**: Include a built-in demo mode in the mobile PWA with simulated scenarios.

**Why**:
- **Competition-ready**: Demo works without n8n Cloud or API credentials
- **Reliable**: No dependency on external services during presentation
- **Backup plan**: If live APIs fail during demo, demo mode saves the presentation
- **Easy to use**: One tap to switch scenarios

**Implementation**:
- 3 built-in scenarios: Pole→Left, Vehicle→Stop, Clear→Straight
- Demo overlay in the PWA UI
- Simulates perception JSON and decision — same UI updates as live mode

---


### D13: Google Maps Routes API v2 over Directions API

**Decision**: Use the Google Maps Routes API v2 (GA since 2023) instead of the legacy Directions API.

**Why**:
- **Current**: Routes API v2 is the current, recommended API for new projects
- **Better data**: Returns structured legs with navigationInstruction (maneuver enum + instructions text)
- **Field masks**: Only request the fields you need — reduces response size
- **Auth model**: X-Goog-Api-Key header is cleaner than query parameter for API key
- **Duration format**: ISO 8601 duration strings are unambiguous
- **WALK travel mode**: Explicit walking mode with appropriate routing

**Migration details**:
- Old endpoint: `GET https://maps.googleapis.com/maps/api/directions/json?origin=...&destination=...&mode=walking`
- New endpoint: `POST https://routes.googleapis.com/directions/v2:computeRoutes`
- Auth: `X-Goog-Api-Key: <key>` header + `X-Goog-FieldMask: <fields>` header
- Travel mode: `travelMode: "WALK"` (not `mode: "walking"`)
- Duration: ISO 8601 string ("780s") parsed to integer seconds by the mapper
- Steps: `navigationInstruction.maneuver` (enum) + `navigationInstruction.instructions` (text)
- Origin/destination: `{location: {latLng: {latitude, longitude}}}` (not `lat,lng` string)

**Implementation**:
- `server/maps_mapper.py` — Python adapter with duration parsing, maneuver mapping, mock generator
- `n8n/01_navigation_start.json` — Updated HTTP Request node to use Routes API v2
- `tests/safety/test_maps.py` — 28 tests covering the mapper

**Alternatives considered**:
- **Stay on Directions API**: Simpler but deprecated for new projects, less structured response
- **Mapbox Directions API**: Different provider, would need different integration
- **OpenStreetMap routing**: Free but less reliable for pedestrian routing

**Rejected**: Staying on the Directions API would mean using a deprecated API with a less structured response format.

## Future Decision Points

These are not yet decided and may need to be addressed:

- **Vision model selection**: Google Vision vs GPT-4V vs Claude vs Gemini — depends on cost/quality tradeoff
- **Session storage**: In-memory (demo) vs Redis vs database (production)
- **PWA service worker**: For offline caching and installability
- **Alternative TTS providers**: Azure, Amazon Polly as alternatives to Google TTS
- **Haptic feedback**: Vibration on STOP decisions for accessibility
