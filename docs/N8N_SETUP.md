# n8n Cloud Setup Guide

## Overview

This project includes 5 n8n workflow JSON files in the `n8n/` directory. These are import-ready for n8n Cloud.

## Prerequisites

- n8n Cloud account (USER ACTION REQUIRED — only you can provide this)
- n8n Cloud workspace URL (e.g. https://aditya8728.app.n8n.cloud)

## Step 1: Import Workflows

1. Log in to your n8n Cloud workspace
2. Click Workflows in the left sidebar
3. Click New workflow (or Import)
4. For each of the 5 JSON files in `n8n/`:

   | File | Name it |
   |------|---------|
   | `01_navigation_start.json` | Navigation Start |
   | `02_perception.json` | Perception |
   | `03_safety_decision.json` | Safety Decision |
   | `04_voice.json` | Voice / TTS |
   | `05_session_management.json` | Session Management |

5. After importing, click Activate on each workflow (toggle in top-right)

## Step 2: Configure Credentials

### 01_navigation_start.json — Google Maps API (Routes API v2)

IMPORTANT: This workflow uses the Routes API v2 (not the deprecated Directions API).

1. In the workflow, click on the 'Google Routes API v2' HTTP request node
2. In the Credentials section, click Create New Credential
3. Choose HTTP Header Auth (or Generic Header Auth)
4. Add header: `X-Goog-Api-Key` with your Google Maps API key value
5. Label: `GOOGLE_MAPS_API`

REQUIRED: Enable Routes API in Google Cloud Console.
Documentation: https://developers.google.com/maps/documentation/routes
Endpoint: POST https://routes.googleapis.com/directions/v2:computeRoutes
The workflow sends:
- Header X-Goog-Api-Key: your API key
- Header X-Goog-FieldMask: routes.duration,routes.distanceMeters,routes.polyline,routes.legs,routes.warnings
- Body: origin, destination, travelMode=WALK, routingPreference=TRAFFIC_UNAWARE

### 02_perception.json — Vision API

1. Click on 'Google Vision API' node (or the vision provider node)
2. Create credential with your Vision API key
3. Label: GOOGLE_VISION_API

NOTE: The current implementation uses Vision API labels as a fallback. For production, replace with GPT-4V or Claude node for proper object detection with bounding boxes.

### 04_voice.json — Google Cloud TTS

1. Click on 'Google Cloud TTS' HTTP request node
2. Create credential using Google Auth (OAuth2) or HTTP Header Auth
3. If using Google Auth, select your GCP project and enable Cloud Text-to-Speech API
4. The workflow sends:
   - Header Authorization: Bearer <access_token>
   - Header X-Goog-User-Project: your GCP project ID
   - Body: input.text, voice.languageCode+name, audioConfig (MP3)
5. Label: GOOGLE_TTS

REQUIRED: Enable Cloud Text-to-Speech API in Google Cloud Console.
Documentation: https://cloud.google.com/text-to-speech/docs
Endpoint: POST https://text-to-speech.googleapis.com/v1/text:synthesize

## Step 3: Get Webhook URLs

Each workflow listens on a webhook. After activation:

1. Open each workflow in n8n
2. Click on the Webhook node
3. Copy the Production URL

Example URLs:
  https://aditya8728.app.n8n.cloud/webhook/navigation-start
  https://aditya8728.app.n8n.cloud/webhook/perception
  https://aditya8728.app.n8n.cloud/webhook/safety-decision
  https://aditya8728.app.n8n.cloud/webhook/voice
  https://aditya8728.app.n8n.cloud/webhook/session

## Step 4: Update Mobile App

In `mobile/src/app.js`, update:

```javascript
const CONFIG = {
  n8nBaseUrl: 'https://YOUR_WORKSPACE.app.n8n.cloud/webhook',
  endpoints: {
    navigationStart: 'navigation-start',
    perception: 'perception',
    safetyDecision: 'safety-decision',
    voice: 'voice',
    session: 'session',
  },
};
```

## Step 5: Test Webhooks

Use curl to test each endpoint from your laptop:

```bash
# Test navigation start (Routes API v2)
curl -X POST https://YOUR_WORKSPACE.app.n8n.cloud/webhook/navigation-start \
  -H 'Content-Type: application/json' \
  -d '{
    "origin": {"lat": 27.7169, "lng": 85.3230},
    "destination": {"lat": 27.7275, "lng": 85.3155, "address": "Thamel", "name": "Thamel"}
  }'

# Test safety decision
curl -X POST https://YOUR_WORKSPACE.app.n8n.cloud/webhook/safety-decision \
  -H 'Content-Type: application/json' \
  -d '{
    "perception": {
      "scene_summary": "test",
      "objects": [{"type": "pole", "position": "center", "estimated_distance_m": 4.0, "blocks_path": true, "risk": "HIGH"}],
      "left_path": {"clear": true, "risk": "LOW", "confidence": 0.88},
      "center_path": {"clear": false, "risk": "HIGH", "confidence": 0.91},
      "right_path": {"clear": false, "risk": "HIGH", "confidence": 0.75},
      "overall_risk": "HIGH",
      "confidence": 0.86
    }
  }'
```

## Troubleshooting

- Workflow not triggering: Check that workflow is activated (green toggle)
- Credential errors: Verify credential type matches node expectation
- 401/403: API key may be expired or restricted — check Google Cloud Console
- Directions API still being called: Make sure you imported the UPDATED workflow (01_navigation_start.json uses Routes API v2, not the old Directions API)
- CORS errors: n8n Cloud webhooks handle CORS — if issues, check n8n settings
