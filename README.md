# Netra-Ai

**AI SafePath — AI-powered safety navigation assistant**

A mobile-first PWA that combines real-time camera perception with Google Maps navigation to provide walking safety guidance. Built for the AI competition platform.

![Status](docs/status.svg)

---

## Architecture

```
PHONE                          n8n CLOUD                     EXTERNAL APIs
┌─────────────────┐                                  ┌───────────────────────┐
│  Camera / GPS   │────►  mobile/index.html (PWA) ──►│  01_navigation_start  │──► Google Directions API
│  Destination    │       capture + decision loop     │  02_perception        │──► Google Vision API / LLM
│  UI + TTS       │       send frames, get decisions │  03_safety_decision   │──► Deterministic rules
└─────────────────┘                                  │  04_voice             │──► Google Cloud TTS
                                                       │  05_session_management│
                                                       └───────────────────────┘
```

**Key components:**
- **Mobile PWA** (`mobile/`) — Camera, GPS, destination input, periodic frame capture, TTS
- **Safety Decision Engine** (`server/safety_engine.py`) — Deterministic LEFT/RIGHT/STRAIGHT/STOP/WAIT logic with 17 passing tests
- **n8n Workflows** (`n8n/`) — 5 modular importable workflow JSONs
- **JSON Schemas** (`schemas/`) — Perception, decision, and navigation state schemas
- **Test Suite** (`tests/`) — 17 tests covering all 10 competition scenarios

---

## Quick Start

### 1. Set up n8n Cloud (REQUIRES USER ACTION)
See [N8N_SETUP.md](docs/N8N_SETUP.md) — import the 5 workflow JSONs and configure credentials.

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your API keys (never commit .env)
```

### 3. Start local dev server (OPTIONAL)
```bash
pip install flask requests
python server/app.py
# http://localhost:8080
```

### 4. Open the PWA
Open `mobile/index.html` in a browser on your phone. Allow camera and GPS permissions.

### 5. Import n8n workflows
After importing workflows to n8n Cloud, update `CONFIG.n8nBaseUrl` in `mobile/src/app.js` with your webhook URLs.

---

## Demo Mode

The PWA includes a built-in demo mode (click "Demo Mode" button) with 3 scenarios:
- **Pole → Left** — pole ahead, safe path left
- **Vehicle → Stop** — vehicle approaching, must stop
- **Clear → Straight** — open path, continue forward

Demo mode works without any external APIs — useful for judging presentations.

---

## Test Results

```
17 tests, 0 failures, 0 errors, 0 skipped — OK
```

See [TESTING.md](docs/TESTING.md) for details.

---

## Project Structure

```
Netra-Ai/
├── mobile/
│   ├── index.html          # PWA entry point (self-contained)
│   ├── styles/main.css     # Dark theme, mobile-optimized
│   ├── src/app.js          # Camera, GPS, capture loop, TTS
│   ├── manifest.json       # PWA manifest
│   └── assets/             # Icons (placeholder)
├── n8n/
│   ├── 01_navigation_start.json
│   ├── 02_perception.json
│   ├── 03_safety_decision.json
│   ├── 04_voice.json
│   └── 05_session_management.json
├── schemas/
│   ├── perception.schema.json
│   ├── decision.schema.json
│   └── navigation.schema.json
├── server/
│   ├── __init__.py
│   └── app.py              # Local dev server (Flask)
├── tests/
│   ├── fixtures/scenarios.json   # 10 test fixtures
│   └── safety/test_decisions.py  # 17 tests (all passing)
├── docs/
│   ├── N8N_SETUP.md
│   ├── API_SETUP.md
│   ├── TESTING.md
│   ├── DEMO_GUIDE.md
│   ├── TROUBLESHOOTING.md
│   ├── COST_NOTES.md
│   └── DECISIONS.md
├── README.md
├── .env.example
└── .gitignore
```

---

## Competition Demo Scenario

**Route:** Kathmandu Durbar Square → Thamel

1. User enters destination "Thamel, Kathmandu"
2. Starts navigation and camera
3. **Scenario A:** Camera sees a pole ~4m ahead in center
   - LEFT path: sidewalk (safe)
   - CENTER: blocked by pole
   - RIGHT: road (dangerous)
   - **Decision: LEFT** — "Pole ahead. Move left."
4. **Scenario B:** Vehicle approaches from front
   - **Decision: STOP** — "Vehicle approaching. Stop."
5. Resume navigation after hazard clears

---

## Status

| Component | Status |
|-----------|--------|
| Safety decision engine | ✅ BUILT, ✅ TESTED (17/17 pass) |
| n8n workflow JSONs | ✅ BUILT (5 files, import-ready) |
| Mobile PWA frontend | ✅ BUILT |
| JSON schemas | ✅ BUILT (3 schemas) |
| Local dev server | ✅ BUILT |
| Google Maps integration | 🔶 N8N workflow ready, REQUIRES API KEY |
| Google Vision integration | 🔶 N8N workflow ready, REQUIRES API KEY |
| Google Cloud TTS | 🔶 N8N workflow ready, REQUIRES CREDENTIALS |
| Full end-to-end test | 🔴 REQUIRES n8n Cloud credentials + API keys |
| PWA manifest icons | 🔴 PLACEHOLDER (add icon-192.png, icon-512.png) |

**BUILT** = implemented and verified locally
**REQUIRES USER ACTION** = needs credentials/account access only the user can provide
**BLOCKED** = waiting on external dependency

---

## Documentation

- [SETUP.md](docs/SETUP.md) — Environment setup
- [N8N_SETUP.md](docs/N8N_SETUP.md) — n8n Cloud workflow import guide
- [API_SETUP.md](docs/API_SETUP.md) — Google Maps, Vision, TTS credential setup
- [TESTING.md](docs/TESTING.md) — Running tests
- [DEMO_GUIDE.md](docs/DEMO_GUIDE.md) — Competition demo walkthrough
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — Common issues
- [COST_NOTES.md](docs/COST_NOTES.md) — API costs and free tiers
- [DECISIONS.md](docs/DECISIONS.md) — Architectural decisions

---

## License

Competition project. All rights reserved.
