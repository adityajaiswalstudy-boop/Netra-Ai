# Testing Guide

## Running Tests

```bash
cd Netra-Ai
python tests/safety/test_decisions.py
```

## Current Results

```
17 tests, 0 failures, 0 errors, 0 skipped — OK
```

Test categories:
- **Safety decision engine** (10 scenario tests) — Tests all 10 competition scenarios
- **Deterministic rules** (2 tests) — Verifies only allowed actions are produced
- **Validation functions** (5 tests) — Tests perception and decision schema validation

## Test Fixtures

Fixtures are in `tests/fixtures/scenarios.json`. Each fixture includes:
- `id` — test identifier
- `name` — human-readable name
- `description` — what the test covers
- `perception` — perception JSON input
- `navigation` — optional navigation state (for tests 7-8)
- `expected_action` — expected action from engine
- `expected_voice` — expected voice instruction

## Adding New Tests

1. Add a fixture to `tests/fixtures/scenarios.json`
2. Add a test method to `tests/safety/test_decisions.py`
3. Run tests to verify

## Test Scenarios Covered

| # | Scenario | Input | Expected |
|---|----------|-------|----------|
| 1 | Clear path | No obstacles, all paths clear | STRAIGHT |
| 2 | Pole center, left safe | Pole 4m ahead, left sidewalk | LEFT |
| 3 | Pole center, left blocked, right safe | Pole + construction left, right clear | RIGHT |
| 4 | All paths blocked | Barriers in all directions | STOP |
| 5 | Vehicle approaching | Vehicle 6m in center | STOP |
| 6 | Low confidence | Confidence 0.30 | WAIT |
| 7 | Maps route available | Valid navigation with route steps | STRAIGHT + nav context |
| 8 | Maps failure | Navigation null | STRAIGHT (graceful fallback) |
| 9 | Malformed vision | Missing required fields | WAIT (validation catch) |
| 10 | Vehicle unknown distance | Vehicle in center, no distance | STOP (conservative) |

## Local Dev Server Tests

The mock server provides testing endpoints:

```bash
python server/app.py
# In another terminal:
curl -X POST http://localhost:8080/api/v1/mock/perception \
  -H "Content-Type: application/json" \
  -d '{"scenario": "pole_left"}'

curl -X POST http://localhost:8080/api/v1/mock/decision \
  -H "Content-Type: application/json" \
  -d '{"scenario": "pole_left"}'
```

## End-to-End Testing

Full end-to-end testing requires:
1. n8n Cloud workflows imported and active
2. API credentials configured
3. Mobile phone with camera + GPS
4. Bluetooth earphones paired

See [DEMO_GUIDE.md](DEMO_GUIDE.md) for demo testing instructions.
