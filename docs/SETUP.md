# Setup Guide

## Prerequisites

- **Web browser** on phone (Chrome/Safari) for PWA
- **Python 3.8+** for local server/tests (optional)
- **n8n Cloud account** — for workflow hosting (REQUIRES USER ACTION)
- **Google Cloud project** — for Maps, Vision, TTS (REQUIRES USER ACTION)

## 1. Clone / Initialize

```bash
git clone https://github.com/adityajaiswalstudy-boop/Netra-Ai.git
cd Netra-Ai
```

## 2. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```env
GOOGLE_MAPS_API_KEY=your_maps_api_key
GOOGLE_TTS_PROJECT_ID=your_gcp_project_id
VISION_PROVIDER=google_vision
VISION_API_KEY=your_vision_api_key
N8N_WEBHOOK_SECRET=your_secret
```

**IMPORTANT**: Never commit `.env` with real values. It's in `.gitignore`.

## 3. n8n Cloud Setup (REQUIRES USER ACTION)

See [N8N_SETUP.md](N8N_SETUP.md) for step-by-step instructions.

Briefly:
1. Log in to n8n Cloud
2. Import the 5 workflow JSONs from `n8n/` directory
3. Configure credentials (Google Maps API, Vision API, TTS credentials)
4. Note the webhook URLs
5. Update `mobile/src/app.js` with your webhook base URL

## 4. Local Dev Server (OPTIONAL)

```bash
pip install flask requests
python server/app.py
```

The server provides:
- `GET /health` — health check
- `POST /api/v1/mock/perception` — mock perception for testing
- `POST /api/v1/mock/decision` — mock decision for testing
- `POST /api/v1/session` — session CRUD
- `POST /api/v1/n8n/<endpoint>` — proxy to n8n (if N8N_WEBHOOK_BASE set)

## 5. Running Tests

```bash
python tests/safety/test_decisions.py
```

Expected: 17 tests, 0 failures.

## 6. Phone Setup (REQUIRED FOR DEMO)

1. Open `mobile/index.html` in Chrome on your phone
2. Allow camera permission when prompted
3. Allow GPS permission when prompted
4. Pair Bluetooth earphones
5. Set destination and start navigation

### Serving the PWA

For best results, serve over HTTPS (required for camera/GPS on many browsers):

```bash
# Python simple server with HTTPS (dev only)
# In production, use a proper HTTPS server
python -m http.server 8080
# Then visit https://your-domain/mobile/
```

For local testing without HTTPS, use `localhost` — browsers allow camera/GPS on localhost without HTTPS.

## 7. PWA Installation

The `mobile/manifest.json` enables PWA installation. For production:
1. Host on HTTPS
2. Add service worker (not yet implemented)
3. Add icon files to `mobile/assets/`
4. User can "Add to Home Screen"

---

## Quick Checklist

- [ ] n8n Cloud account access
- [ ] Import 5 workflows to n8n
- [ ] Create Google Maps API key with Directions API enabled
- [ ] Create Vision API key (or decide on LLM provider)
- [ ] Create Google Cloud TTS credentials
- [ ] Copy `.env.example` to `.env` and fill values
- [ ] Update `mobile/src/app.js` with n8n webhook URLs
- [ ] Test on phone with camera + GPS
- [ ] Pair Bluetooth earphones
- [ ] Run demo mode for presentation backup
