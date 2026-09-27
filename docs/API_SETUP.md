# API Setup Guide

External APIs required for AI SafePath.

---

## Google Maps Platform — Routes API (v2)

### What it is used for
- Compute walking routes between origin and destination
- Turn-by-turn navigation steps
- Route distance and duration

### Setup
1. Go to https://console.cloud.google.com/google/maps-apis
2. Create or select a project
3. Enable Routes API (NOT the old Directions API)
4. Create API key (Credentials → Create credentials → API key)
5. Restrict key to Routes API only
6. Copy key to .env as GOOGLE_MAPS_API_KEY

### API Details
- Endpoint: POST https://routes.googleapis.com/directions/v2:computeRoutes
- Auth: X-Goog-Api-Key header (NOT query parameter)
- Field mask: X-Goog-FieldMask header (required — specifies which fields to return)
- Travel mode: WALK (for walking routes)
- Routing preference: TRAFFIC_UNAWARE (traffic not relevant for walking)

### Request body example
```json
{
  "origin": {"location": {"latLng": {"latitude": 27.7169, "longitude": 85.3230}}},
  "destination": {"location": {"latLng": {"latitude": 27.7275, "longitude": 85.3155}}},
  "travelMode": "WALK",
  "routingPreference": "TRAFFIC_UNAWARE"
}
```

### Response includes
- routes[0].distanceMeters: total distance in meters
- routes[0].duration: ISO 8601 duration string (e.g. "780s")
- routes[0].polyline.encodedPolyline: encoded route polyline
- routes[0].legs[0].steps: array of steps with navigationInstruction
- routes[0].warnings: array of warning strings

### Important notes
- Walking routes may sometimes miss clear sidewalks or pedestrian paths
- Google Maps route = GLOBAL NAVIGATION CONTEXT only
- Camera perception = LOCAL ENVIRONMENT SAFETY
- The local safety layer must override navigation when there is an immediate hazard
- Duration is returned as a string ("780s"), not an integer — the mapper parses it

### Quota and pricing
- Routes API: 1000 requests/day free tier (with billing account)
- Demo usage: ~1 request per navigation session
- Production: pay-as-you-go after free tier
- Billing account required (credit card on Google Cloud)

### Place it
n8n workflow: 01_navigation_start.json → Google Routes API v2 node
Credential label: GOOGLE_MAPS_API
Python mapper: server/maps_mapper.py → get_walking_route()

---

## Google Cloud Vision API

### What it is used for
- Object detection from camera frames
- Scene understanding (labels, localized objects)

### Setup
1. Go to https://console.cloud.google.com/vision
2. Enable Cloud Vision API
3. Create API key or use service account
4. Copy key to .env as VISION_API_KEY

### Alternative: LLM-based Vision
Instead of Google Vision, you can use:
- GPT-4V (OpenAI): multimodal, excellent at object detection with spatial awareness
- Claude (Anthropic): multimodal, good at structured output
- Google Gemini: multimodal, good Vision integration

To switch providers, modify 02_perception.json to use the appropriate n8n node.

### Quota and pricing
- Vision API: 1000 units/month free tier
- GPT-4V: paid per image (~$0.02-$0.06/image)
- Claude: paid per image

### Place it
n8n workflow: 02_perception.json → Vision API node
Credential label: GOOGLE_VISION_API

---

## Google Cloud Text-to-Speech

### What it is used for
- Convert text instructions to speech audio for phone playback
- Support for multiple languages and voices

### Setup
1. Go to https://console.cloud.google.com/text-to-speech
2. Enable Cloud Text-to-Speech API
3. Create service account with Cloud Text-to-Speech API User role
4. Download JSON key or use OAuth2
5. In n8n, create Google Auth credential with the service account
6. Label: GOOGLE_TTS

### API Details
- Endpoint: POST https://text-to-speech.googleapis.com/v1/text:synthesize
- Auth: OAuth2 Bearer token (service account) with scope https://www.googleapis.com/auth/cloud-platform
- Request body: input.text, voice.languageCode+name, audioConfig.audioEncoding=MP3
- Response: audioContent (base64-encoded MP3)

### Voice options
- en-US-Standard-A (female)
- en-US-Standard-B (male)
- Plus Wavenet voices for higher quality

### Quota and pricing
- 1 million characters/month free tier
- Demo usage: ~100 characters per instruction = negligible
- Production: $4 per 1M characters after free tier

### Place it
n8n workflow: 04_voice.json → Google Cloud TTS node
Credential label: GOOGLE_TTS

---

## Browser SpeechSynthesis (Fallback — No API Key Needed)

The mobile PWA uses browser SpeechSynthesis as a fallback:

```javascript
const utter = new SpeechSynthesisUtterance(text);
utter.lang = 'en-US';
window.speechSynthesis.speak(utter);
```

Pros: No API key, no cost, works offline (basic voices)
Cons: Robotic voice quality, limited language support, inconsistent across browsers

---

## Summary

| API | Purpose | Free Tier | Demo Cost | Requires |
|-----|---------|-----------|-----------|----------|
| Google Routes API v2 | Walking route | 1000 req/day | ~1 req | API key |
| Google Vision API | Object detection | 1000 units/mo | ~10 units | API key |
| GPT-4V (alternative) | Object detection | Paid only | ~$0.20 | OpenAI key |
| Google Cloud TTS | Voice audio | 1M chars/mo | ~500 chars | GCP service account |
| Browser SpeechSynthesis | Voice fallback | Unlimited | Free | None |

See COST_NOTES.md for detailed cost estimates.
