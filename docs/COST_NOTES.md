# Cost Notes

## API Costs

### Google Maps Platform — Routes API v2

| Item | Details |
|------|---------|
| Purpose | Walking route from origin to destination |
| Free tier | 1000 requests/day (with billing account) |
| Demo usage | ~1 request per navigation session |
| Production cost | $5 per 1000 requests after free tier |
| Billing required | Yes (credit card on Google Cloud) |
| Credential | API key with Routes API enabled |

**Demo cost estimate**: One demo session = 1 Routes API call = $0.00 (within free tier)

### Google Cloud Vision API

| Item | Details |
|------|---------|
| Purpose | Object detection, scene analysis from camera frames |
| Free tier | 1000 units/month (OCR units, label detection = 1 unit/image) |
| Demo usage | ~10-20 frames per demo session = ~10-20 units |
| Production cost | $1.50 per 1000 units after free tier |
| Billing required | Yes |
| Credential | API key or service account |

**Demo cost estimate**: 20 Vision API calls = $0.00 (within free tier)

**Note**: The current n8n workflow uses Vision API labels as a fallback. In production, you'd use a proper vision model. Alternatives:

| Alternative | Cost |
|-------------|------|
| GPT-4V (OpenAI) | ~$0.02-$0.06 per image (gpt-4o) |
| Claude (Anthropic) | ~$0.003 per image (Haiku) to $0.01 (Opus) |
| Google Gemini | ~$0.00025 per image (Flash) to $0.0015 (Pro) |

Vision model choice can significantly affect cost for high-frequency capture.

### Google Cloud Text-to-Speech

| Item | Details |
|------|---------|
| Purpose | Convert text instructions to speech audio |
| Free tier | 1 million characters/month |
| Demo usage | ~100 chars per instruction × 10 instructions = ~1000 chars |
| Production cost | $4.00 per 1M characters after free tier |
| Billing required | Yes (GCP project with billing) |
| Credential | Service account JSON with TTS role |

**Demo cost estimate**: ~$0.00 (way under free tier)

### Browser SpeechSynthesis (Fallback)

| Item | Details |
|------|---------|
| Cost | Free |
| Limitations | Robotic voice, limited language support, inconsistent across browsers |
| Best for | Demo fallback, low-budget deployments |

---

## Total Demo Cost Estimate

| API | Demo Calls | Cost |
|-----|-----------|------|
| Routes API v2 | 1 | $0.00 |
| Vision API | 20 | $0.00 |
| Cloud TTS | 1000 chars | $0.00 |
| **Total** | | **$0.00** |

All within free tiers. Demo can be run without any API cost.

---

## Production Cost Estimate (Per User, Per Day)

Assumptions: 10 navigation sessions per day, 20 camera frames per session, 5 voice instructions per session.

| API | Daily Calls | Monthly Cost |
|-----|------------|--------------|
| Routes API v2 | 10 | $0.00 (within free tier) |
| Vision API (Vision API) | 200 | $0.00 (within free tier) |
| Cloud TTS | 5000 chars | $0.00 (within free tier) |
| **Total** | | **$0.00** |

Even at moderate usage, all APIs stay within free tiers.

At scale (1000 users, 10 sessions/day each):
- Routes API v2: 10,000 calls/day = $50/day after free tier
- Vision API: 200,000 calls/day = $300/day
- TTS: 5M chars/day = $20/day
- Total: ~$370/day

Cost optimization: Use cheaper vision models (Gemini Flash, Claude Haiku) and reduce capture frequency.

---

## n8n Cloud Pricing

n8n Cloud pricing (check current rates at n8n.io):
- Free tier: limited executions
- Paid tiers: more executions, more workflows

For demo purposes, the free tier may be sufficient. For production, check n8n Cloud pricing.

---

## Cost Optimization Strategies

1. **Reduce capture frequency** — 2s intervals are reasonable; 5s would reduce Vision API calls
2. **Use cheaper vision models** — Gemini Flash or Claude Haiku for production
3. **Cache routes** — Routes API calls are rare (once per session), not a cost driver
4. **Browser TTS fallback** — avoid Cloud TTS for simple instructions
5. **Local processing** — on-device object detection eliminates Vision API costs entirely

---

## Billing Setup Required

To use Google Maps, Vision, or TTS APIs, you need:
1. Google Cloud account
2. Billing account (credit card)
3. Project with APIs enabled
4. API credentials (keys or service accounts)

These are **user-only actions** — the developer cannot set them up.

See [API_SETUP.md](API_SETUP.md) for step-by-step instructions.
