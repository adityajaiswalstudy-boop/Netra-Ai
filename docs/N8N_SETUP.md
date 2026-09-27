# n8n Cloud Setup Guide

## Overview

This project includes 5 n8n workflow JSON files in the `n8n/` directory. These are **import-ready** for n8n Cloud.

## Prerequisites

- n8n Cloud account (REQUIRES USER ACTION — only you can provide this)
- n8n Cloud workspace URL (e.g. `https://aditya8728.app.n8n.cloud`)

## Step 1: Import Workflows

1. Log in to your n8n Cloud workspace
2. Click **Workflows** in the left sidebar
3. Click **New workflow** (or Import)
4. For each of the 5 JSON files in `n8n/`:

   | File | Name it |
   |------|---------|
   | `01_navigation_start.json` | Navigation Start |
   | `02_perception.json` | Perception |
   | `03_safety_decision.json` | Safety Decision |
   | `04_voice.json` | Voice / TTS |
   | `05_session_management.json` | Session Management |

5. After importing, click **Activate** on each workflow (toggle in top-right)

## Step 2: Configure Credentials

Each workflow requires credentials. Configure these in n8n Cloud:

### 01_navigation_start.json — Google Maps API
1. In the workflow, click on the "Google Directions API" node
2. Click **Create New Credential**
3. Choose **Google API** (or HTTP Header auth if using API key in URL)
4. Enter your Google Maps API key
5. Label: `GOOGLE_MAPS_API`

**Required API**: Directions API (enable in Google Cloud Console)

### 02_perception.json — Vision API
1. Click on "Google Vision API" node
2. Create credential with your Vision API key
3. Label: `GOOGLE_VISION_API`

**Note**: The current implementation uses Vision API labels as a fallback. For production, replace with GPT-4V or Claude node for proper object detection.

### 04_voice.json — Google Cloud TTS
1. Click on "Google Cloud TTS" node
2. Create credential with your GCP service account JSON or API key
3. Label: `GOOGLE_TTS_CREDENTIALS`

**Required API**: Cloud Text-to-Speech API

## Step 3: Get Webhook URLs

Each workflow listens on a webhook. After activation:

1. Open each workflow in n8n
2. Click on the Webhook node
3. Copy the **Test URL** or **Production URL**

Example:
```
https://aditya8728.app.n8n.cloud/webhook/navigation-start
https://aditya8728.app.n8n.cloud/webhook/perception
https://adityajaisp8.app.n8n.cloud/webhook/safety-decision
https://adityajaisp8.app.n8n.cloud/webhook/voice
https://adityajaisp8.app.n8n.cloud/webhook/session
```

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
  // ...
};
```

Alternatively, if n8n Cloud is on a different domain, set the full URLs.

## Step 5: Test Webhooks

Use curl to test each endpoint:

```bash
# Test navigation start
curl -X POST https://YOUR_WORKSPACE.app.n8n.cloud/webhook/navigation-start \
  -H "Content-Type: application/json" \
  -d '{
    "origin": {"lat": 27.7169, "lng": 85.3230},
    "destination": {"lat": 27.7275, "lng": 85.3155, "address": "Thamel", "name": "Thamel"}
  }'

# Test perception (with a small base64 image)
curl -X POST https://YOUR_WORKSPACE.app.n8n.cloud/webhook/perception \
  -H "Content-Type: application/json" \
  -d '{"image_base64": "placeholder", "frame_timestamp_ms": 12345}'

# Test safety decision
curl -X POST https://YOUR_WORKSPACE.app.n8n.cloud/webhook/safety-decision \
  -H "Content-Type: application/json" \
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

- **Webhook not triggering**: Check that the workflow is activated (green toggle)
- **Credential errors**: Verify the credential type matches what the node expects
- **401/403 errors**: Check API key is valid and has the required scopes
- **CORS errors**: n8n Cloud webhooks should handle CORS. If issues, check n8n settings.

---

## Magic Host Names

When you import a workflow, n8n assigns a webhook path. The workflow names above use:

- `navigation-start`
- `perception`
- `safety-decision`
- `voice`
- `session`

If you rename workflows, update the webhook paths accordingly.
