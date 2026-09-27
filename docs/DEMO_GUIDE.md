# Demo Guide — Competition Presentation

## Overview

This guide walks through the competition demo. The demo is designed to be run on a phone with the PWA, showing real-time AI perception and safety decisions.

## Pre-Demo Checklist

- [ ] Phone charged
- [ ] Bluetooth earphones paired and connected
- [ ] Camera and GPS permissions granted
- [ ] n8n Cloud workflows imported and active (OR demo mode ready)
- [ ] API credentials configured (if using live APIs)
- [ ] Demo mode tested as backup

## Demo Flow

### Step 1: Introduction (30 seconds)

"AI SafePath is a real-time AI safety navigation assistant for pedestrians. It combines camera perception with map navigation to warn you about obstacles and hazards while you walk."

Show the phone screen:
- Display the PWA (dark theme, camera view, destination input)
- Point out the camera view, status badge, decision display

### Step 2: Set Destination (30 seconds)

1. Enter "Thamel, Kathmandu" in the destination field
2. Tap "Set"
3. Show destination display appearing
4. "Our route is from Kathmandu Durbar Square to Thamel"

If n8n is connected: show the route info appearing (distance, next step)
If not: use demo mode

### Step 3: Start Camera (30 seconds)

1. Tap "Start Camera"
2. Show the camera feed with overlay
3. "The camera is now capturing frames every 2 seconds"
4. "GPS is tracking our position"

### Step 4: Scenario A — Pole Detection (60 seconds)

**Using live n8n:**
1. Walk toward a pole or stand a pole in front of the camera
2. Wait for the next capture cycle (~2 seconds)
3. Show perception updating:
   - Objects list showing "pole" at ~4m
   - Path cards: CENTER = BLOCKED (HIGH risk), LEFT = CLEAR (LOW risk), RIGHT = BLOCKED (HIGH risk)
   - Overall risk: HIGH
4. Show decision: **LEFT**
5. Voice instruction: "Pole ahead. Move left." (heard through earphones)

**Using demo mode (backup):**
1. Tap "Demo Mode"
2. Tap "Pole → Left"
3. Same visual updates as above

**Key talking points:**
- "The AI detected a pole 4 meters ahead"
- "It analyzed three paths: left, center, right"
- "Center was blocked, left was safe (sidewalk), right was dangerous (road)"
- "The safety engine chose LEFT — the safest available path"
- "This decision was made deterministically using rules, not an LLM guessing"

### Step 5: Scenario B — Vehicle Stop (60 seconds)

**Using live n8n:**
1. Show a vehicle (or use demo mode)
2. Camera captures vehicle in center
3. Show perception: vehicle detected at ~6m
4. Decision: **STOP**
5. Voice: "Vehicle approaching. Stop."

**Using demo mode:**
1. Tap "Vehicle → Stop"
2. Same visual updates

**Key talking points:**
- "When a vehicle is detected in the center path under 8 meters, the system immediately stops"
- "This is a hard rule — safety beats everything"
- "The system doesn't try to route around — it stops for safety"

### Step 6: Scenario C — Clear Path (30 seconds)

**Using demo mode:**
1. Tap "Clear → Straight"
2. Show all paths clear, decision STRAIGHT
3. Voice: "Path clear. Continue straight."

**Key talking points:**
- "When the path is clear, the system tells you to continue"
- "It only alerts you when there's something to react to"

### Step 7: Wrap-up (30 seconds)

"AI SafePath demonstrates how AI perception and navigation can work together to improve pedestrian safety. The system is:

- **Real-time**: processes camera frames every 1-2 seconds
- **Deterministic**: uses clear safety rules, not black-box AI decisions
- **Modular**: built on n8n workflows that can be swapped and upgraded
- **Graceful**: falls back to WAIT/STOP when uncertain, never guesses

This is a competition prototype — it demonstrates the concept, not a production-ready device."

---

## Demo Mode

The PWA includes a built-in demo mode for presentations where n8n is not available.

To use:
1. Tap "Demo Mode" button (bottom of screen)
2. Choose a scenario
3. The UI updates with simulated perception and decision
4. Voice plays through browser SpeechSynthesis

Demo scenarios:
- **Pole → Left**: Pole detected, safe path left
- **Vehicle → Stop**: Vehicle approaching, must stop
- **Clear → Straight**: No obstacles, continue

---

## Troubleshooting During Demo

| Issue | Fix |
|-------|-----|
| Camera not starting | Check phone permissions, restart browser |
| GPS not showing | Ensure location services on, use demo mode |
| n8n not responding | Switch to demo mode (built into PWA) |
| No audio | Check Bluetooth, volume, try browser fallback |
| Decision not updating | Check capture interval, wait for next cycle |

---

## Backup Plan

Always have demo mode ready. If n8n Cloud or APIs are unavailable during the demo, demo mode provides the same visual experience without external dependencies.
