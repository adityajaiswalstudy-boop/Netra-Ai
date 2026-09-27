# Phone Testing Guide

How to test AI SafePath on an actual phone for the competition demo.

---

## Before You Start

### Requirements
- Android or iOS phone with working camera and GPS
- Bluetooth earphones paired to the phone
- Laptop running the local dev server (or n8n Cloud workflows active)
- Both devices on the same Wi-Fi network

### What You Need to Do First
1. Start the local dev server: `python server/app.py` (default port 8080)
2. OR ensure n8n Cloud workflows are imported and active
3. Update `mobile/src/app.js` CONFIG with the correct n8n webhook URL

---

## Step 1: Start the Local Server

On your laptop:

```bash
cd Netra-Ai
python server/app.py
```

Output should show:

```
SafePath server starting on :8080
  Health:  http://localhost:8080/health
  Mock perception: http://localhost:8080/api/v1/mock/perception
  Mock decision:   http://localhost:8080/api/v1/mock/decision
```

The server is now running. Keep it running.

---

## Step 2: Find Your Laptop's LAN Address

You need your laptop's IP address on the local network so the phone can reach it.

### Windows (your laptop)
```powershell
ipconfig
```

Look for 'Wireless LAN adapter Wi-Fi' → IPv4 Address (e.g. 192.168.1.100)

Or use Python:

```bash
python -c "import socket; print(socket.gethostbyname(socket.gethostname()))"
```

### Notes
- If the address starts with 127.x or 10.x, use the actual Wi-Fi IP
- The address is typically 192.168.1.X or 10.0.0.X
- Make a note of it — you will need it in Step 4

---

## Step 3: Connect Phone to Same Network

- Ensure your phone is connected to the SAME Wi-Fi network as your laptop
- If laptop uses Ethernet and phone uses Wi-Fi, they may be on different subnets
- You can test connectivity by trying to reach the server from the phone browser

---

## Step 4: Open the PWA on Your Phone

### Option A: Direct file access (limited)
- Transfer mobile/index.html to your phone and open it
- LIMITATION: Camera and GPS often require HTTPS or localhost — file:// may not work

### Option B: Serve over HTTP (recommended for testing)
1. Serve from the mobile/ directory:
   ```bash
   cd mobile
   python -m http.server 8080
   ```
2. On your phone, open: http://<LAPTOP_IP>:8080/index.html

### Option C: Deploy to GitHub Pages (best for HTTPS)
- The mobile/ directory is already in the repo
- Push to GitHub and enable GitHub Pages
- Open https://adityajaiswalstudy-boop.github.io/Netra-Ai/mobile/ on your phone
- GitHub Pages provides HTTPS automatically

---

## Step 5: Grant Camera Permission

When the page loads:

1. Browser prompts: 'Allow this site to access your camera?'
2. Tap Allow
3. Camera feed appears in the video area
4. If denied: browser settings → site permissions → camera → allow

TROUBLESHOOTING:
- Camera may require HTTPS (or localhost, which doesn't work on a phone)
- Try a different browser
- No other app should be using the camera
- Demo mode works without camera — use as fallback

---

## Step 6: Grant Location Permission

1. When app requests GPS, browser prompts for location access
2. Tap Allow
3. GPS position appears in debug panel
4. If denied: browser settings → site permissions → location → allow

NOTES:
- GPS works best outdoors with clear sky view
- Indoor GPS may be inaccurate
- GPS not required for demo — demo mode simulates everything

---

## Step 7: Start Demo Mode (Recommended for First Test)

Before testing with live APIs, verify the UI works with demo mode.

1. Tap the Demo Mode button on the phone
2. Try each scenario:
   - Pole → Left: Simulates pole ahead, decision = LEFT
   - Vehicle → Stop: Simulates vehicle approaching, decision = STOP
   - Clear → Straight: Simulates clear path, decision = STRAIGHT
3. Verify:
   - Camera view updates with detection overlay
   - Path cards show CLEAR/BLOCKED correctly
   - Decision card shows the action (LEFT/STRAIGHT/STOP)
   - Voice instruction text appears
   - Speak button plays audio through speaker or Bluetooth

Demo mode requires NO external APIs.

---

## Step 8: Test Live Camera (if APIs configured)

If n8n Cloud workflows are imported and API keys configured:

1. Tap Start Camera
2. Tap Start Navigation (after setting destination)
3. Capture loop begins — frame sent to n8n every N seconds
4. Watch perception panel update with detected objects
5. Watch decision update based on camera input

If using local mock server:
- Point CONFIG.n8nBaseUrl to http://<LAPTOP_IP>:8080/api/v1/mock
- PWA hits mock endpoints instead of n8n
- Test full UI flow without n8n credentials

---

## Step 9: Test GPS

1. Start navigation
2. Watch navigation info section update as you move
3. GPS accuracy shown in debug mode
4. If GPS unavailable: app shows warning, perception still works

---

## Step 10: Test Voice / TTS

### Browser SpeechSynthesis (always available)
1. After decision, voice instruction text appears
2. Tap Speak button
3. Instruction spoken through phone speaker or Bluetooth
4. Uses browser built-in TTS — no API key needed

### Cloud TTS (requires Google Cloud credentials)
1. When configured, n8n /voice workflow generates audio via Google Cloud TTS
2. Audio returned as base64 and played by PWA
3. Higher quality than browser TTS
4. If Cloud TTS fails, falls back to browser SpeechSynthesis

### Bluetooth Earphones
1. Pair earphones to phone before starting
2. Start navigation
3. Voice instructions should play through earphones
4. If audio plays through phone speaker instead:
   - Check media audio enabled for Bluetooth
   - Try unpairing and re-pairing

---

## Step 11: Test the Full Flow

Once everything works individually:

1. Set destination: Thamel, Kathmandu
2. Start camera
3. Start navigation
4. Enable demo mode to simulate hazards, OR place real objects in front of camera
5. Watch full loop: frame → perception → decision → voice
6. Verify decision makes sense for what camera sees

COMPETITION DEMO FLOW:
1. Enter destination → show route info
2. Start camera → show camera feed
3. Start navigation → show status = active
4. Trigger demo scenario Pole → Left
5. Show: perception detects pole, LEFT clear, CENTER blocked
6. Decision: LEFT — Pole ahead. Move left. (speaker plays)
7. Trigger demo scenario Vehicle → Stop
8. Show: vehicle detected, decision: STOP — Vehicle approaching. Stop.
9. Reset to Clear → Straight
10. Show: clear path, decision: STRAIGHT — Path clear. Continue straight.

---

## Security Context Requirements

| Feature | Requirement | Works on HTTP? |
|---------|------------|----------------|
| Camera (getUserMedia) | Secure context (HTTPS or localhost) | Sometimes on Android Chrome |
| GPS (geolocation) | Secure context (HTTPS or localhost) | Sometimes on Android Chrome |
| Bluetooth | N/A (phone-level pairing) | Yes |
| TTS (browser) | No special requirement | Yes |
| TTS (cloud) | No special requirement | Yes |
| Fetch to n8n | No special requirement (CORS handled by n8n) | Yes |

For the competition demo:
- If HTTPS is hard to set up, use DEMO MODE — works on HTTP, no camera/GPS needed
- Demo mode is a fully valid demonstration of the UI, decision logic, and voice output
- Judges see the same visual experience as live mode

---

## Quick Troubleshooting

| Problem | Fix |
|---------|-----|
| Camera not starting | Check HTTPS, check permissions, try different browser, use demo mode |
| GPS not showing | Check permissions, go outdoors, use demo mode |
| Audio not playing | Check volume, check Bluetooth, try speaker first |
| Page not loading on phone | Check laptop IP, check firewall, try ngrok or deploy to GitHub Pages |
| n8n not responding | Use demo mode or local mock server |
| Decision not updating | Check capture interval, wait for next cycle, check debug mode |
| Allow prompt not appearing | Reload page, check browser settings, clear site data |

---

## For the Judges

1. Have demo mode ready — it always works, no API dependencies
2. Have phone charged and Bluetooth paired before presentation
3. Test full flow once before judges arrive
4. Explain architecture — show camera → n8n → safety engine → voice is real flow
5. Be honest — if live APIs unavailable, say demo mode shows same decision logic
