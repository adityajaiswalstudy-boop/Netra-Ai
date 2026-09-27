# Testing Guide

## Running Tests

```bash
cd Netra-Ai
python tests/safety/test_decisions.py
python tests/safety/test_maps.py
```

Or run both:

```bash
cd Netra-Ai
python tests/safety/test_decisions.py && python tests/safety/test_maps.py
```

## Current Results

82 tests, 0 failures, 0 errors, 0 skipped — OK

Test categories:
- **Safety decision engine (17 tests)** — Tests all 10 competition scenarios
- **Deterministic rules (2 tests)** — Verifies only allowed actions are produced
- **Validation functions (5 tests)** — Tests perception and decision schema validation
- **Maps mapper (28 tests)** — Tests duration parsing, maneuver mapping, mock routes, response normalization
- **Vision perception (37 tests)** — Tests mock scenarios, validation, label mapping, position/distance estimation, safety engine integration, provider enum, entry point

## Test Fixtures

Fixtures are in `tests/fixtures/scenarios.json`. Each fixture includes:
- `id` — test identifier
- `name` — human-readable name
- `description` — what the test covers
- `perception` — perception JSON input
- `navigation` — optional navigation state (for tests 7-8)
- `expected_action` — expected action from engine
- `expected_voice` — expected voice instruction

## Maps Mapper Tests

The Maps mapper tests in `tests/safety/test_maps.py` do NOT require an API key. They test:
- **Duration parsing (9 tests)**: ISO 8601 format ("PT3M", "PT1H30M", "PT45S") and seconds format ("780s")
- **Maneuver mapping (7 tests)**: 40+ Routes API maneuvers mapped to 8 simplified turn types
- **Mock route generation (4 tests)**: Correct distance, duration, steps, last step = destination
- **Response normalization (6 tests)**: Full Routes API v2 response → WalkingRoute
- **API constants (2 tests)**: Correct endpoint URL and field mask
- **Travel mode verification (1 test)**: Uses WALK not walking, TRAFFIC_UNAWARE for walking

## Adding New Tests

1. For safety engine: add a fixture to `tests/fixtures/scenarios.json` and a test method to `tests/safety/test_decisions.py`
2. For maps mapper: add a test method to `tests/safety/test_maps.py`
3. Run tests to verify

## Local Dev Server Tests

The mock server provides testing endpoints:

```bash
python server/app.py
# In another terminal:
curl -X POST http://localhost:8080/api/v1/mock/perception \
  -H 'Content-Type: application/json' \
  -d '{"scenario": "pole_left"}'

curl -X POST http://localhost:8080/api/v1/mock/decision \
  -H 'Content-Type: application/json' \
  -d '{"scenario": "pole_left"}'
```

## End-to-End Testing

Full end-to-end testing requires:
1. n8n Cloud workflows imported and active
2. API credentials configured (Google Maps Routes API key, Vision API key, GCP TTS credentials)
3. Mobile phone with camera + GPS
4. Bluetooth earphones paired
5. See docs/PHONE_TEST.md for step-by-step phone testing

### Mock server for e2e without n8n
The local mock server can simulate the full pipeline without n8n:
- Point PWA CONFIG.n8nBaseUrl to http://localhost:8080/api/v1/mock
- The PWA hits mock endpoints instead of n8n
- Test the full UI flow without any credentials
