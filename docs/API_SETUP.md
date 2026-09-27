# API Setup Guide

This document covers the external APIs required for AI SafePath and how to set them up.

---

## Google Maps Platform

### What it's used for
- **Directions API**: Walking route from origin to destination
- **Route steps**: Turn-by-turn walking instructions

### Setup
1. Go to https://console.cloud.google.com/google/maps-apis
2. Create a project (or use existing)
3. Enable **Directions API**
4. Create API key (Credentials → Create credentials → API key)
5. Restrict the key to Directions API only
6. Copy the key to `.env` as `GOOGLE_MAPS_API_KEY`

### Quota & Pricing
- Directions API: 1000 requests/day free tier
- Demo usage: ~1 request per navigation session
- Production: pay-as-you-go after free tier

### Place it
n8n workflow: `01_navigation_start.json` → Google Directions API node
Credential label: `GOOGLE_MAPS_API`

---

## Google Cloud Vision API

### What it's used for
- Object detection from camera frames
- Scene understanding (labels, objects)

### Setup
1. Go to https://console.cloud.google.com/vision
2. Enable **Cloud Vision API**
3. Create API key or use service account
4. Copy key to `.env` as `VISION_API_KEY`

### Alternative: LLM-based Vision
Instead of Google Vision, you can use:
- **GPT-4V** (OpenAI) — multimodal, excellent at object detection
- **Claude** (Anthropic) — multimodal, good at structured output
- **Google Gemini** — multimodal, good Vision integration

To switch providers, modify `02_perception.json` to use the appropriate n8n node.

### Quota & Pricing
- Vision API: 1000 units/month free tier
- GPT-4V: paid per image (~$0.02-$0.06/image depending on tier)
- Claude: paid per image

### Place it
n8n workflow: `02_perception.json` → Vision API node
Credential label: `GOOGLE_VISION_API`

---

## Google Cloud Text-to-Speech

### What it's used for
- Converting text instructions to audio for playback on phone
- Support for multiple languages and voices

### Setup
1. Go to https://console.cloud.google.com/text-to-speech
2. Enable **Cloud Text-to-Speech API**
3. Create service account with Text-to-Speech role
4. Download JSON key
5. In n8n, create Google Auth credential with the JSON key
6. Label: `GOOGLE_TTS_CREDENTIALS`

### Voice options
- en-US-Standard-A (female)
- en-US-Standard-B (male)
- Plus Wavenet voices for higher quality

### Quota & Pricing
- 1 million characters/month free tier
- Demo usage: ~100 characters per instruction, ~50 instructions per demo = negligible
- Production: $4 per 1M characters after free tier

### Place it
n8n workflow: `04_voice.json` → Google Cloud TTS node
Credential label: `GOOGLE_TTS_CREDENTIALS`

---

## Browser SpeechSynthesis (Fallback — No API Key Needed)

The mobile PWA uses browser SpeechSynthesis as a fallback when cloud TTS is unavailable:

```javascript
const utter = new SpeechSynthesisUtterance(text);
utter.lang = 'en-US';
window.speechSynthesis.speak(utter);
```

**Pros**: No API key, no cost, works offline (basic voices)
**Cons**: Robotic voice quality, limited language support, inconsistent across browsers

---

## Summary

| API | Purpose | Free Tier | Demo Cost | Requires |
|-----|---------|-----------|-----------|----------|
| Google Directions API | Walking route | 1000 req/day | ~1 req | API key |
| Google Vision API | Object detection | 1000 units/mo | ~10 units | API key |
| GPT-4V (alternative) | Object detection | Paid only | ~$0.20 | OpenAI key |
| Google Cloud TTS | Voice audio | 1M chars/mo | ~500 chars | GCP service account |
| Browser SpeechSynthesis | Voice fallback | Unlimited | Free | None |

---

## Cost Notes

See [COST_NOTES.md](COST_NOTES.md) for detailed cost estimates.
