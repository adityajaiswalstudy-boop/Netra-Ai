# Troubleshooting Guide

## Camera Issues

### Camera not starting
- Check that you've granted camera permission in the browser prompt
- On iOS Safari, camera requires HTTPS (or localhost)
- On Android Chrome, camera works on HTTPS or localhost
- Try refreshing the page and clicking "Start Camera" again
- Check if another app is using the camera

### Camera shows black screen
- Some browsers require `playsinline` attribute (included in the HTML)
- Try a different browser
- Check if camera is being used by another app

### Camera stream is sideways
- The PWA requests `facingMode: 'environment'` which should use the back camera
- On some devices, orientation is handled by the OS

## GPS Issues

### GPS not available
- Check that location services are enabled on the phone
- Browser may require location permission
- In outdoor environments, GPS works better
- For demo purposes, GPS is not required — demo mode works without it

### GPS position is inaccurate
- Wait a minute for GPS to lock
- Move to an area with clearer sky view
- GPS accuracy is shown in the debug panel (when enabled)

## n8n Cloud Issues

### Webhook not triggering
1. Check that the workflow is **activated** (green toggle switch in n8n)
2. Check the webhook URL is correct in `mobile/src/app.js`
3. Check n8n execution log for errors
4. Test with curl from terminal:
   ```bash
   curl -X POST https://YOUR_WORKSPACE.app.n8n.cloud/webhook/perception \
     -H "Content-Type: application/json" \
     -d '{"image_base64": "test", "frame_timestamp_ms": 123}'
   ```

### Credential errors
- Verify the credential type matches the node
- Google API node needs Google API credential with API key
- Google Auth node needs service account JSON
- Re-create credentials if unsure

### 401/403 errors
- API key may be expired or restricted
- Check API key restrictions in Google Cloud Console
- Verify the API is enabled in Google Cloud Console

### Workflow execution timeout
- Vision API may be slow on large images
- Try reducing image quality in capture (lower JPEG quality)
- Increase n8n timeout settings if needed

## API Issues

### Directions API returns ZERO_RESULTS
- Check origin and destination are valid coordinates
- Check the API key has Directions API enabled
- Try a different destination

### Vision API returns empty labels
- Image may be too dark or blurry
- Try a clearer photo
- Consider switching to GPT-4V or Claude for better detection

### TTS returns empty audio
- Check text is valid and not too long (max ~5000 chars)
- Check voice name is valid for the language
- Try a different voice name

## Mobile PWA Issues

### PWA not installing
- PWA requires HTTPS (except localhost)
- Icon files are placeholders — add `icon-192.png` and `icon-512.png` to `mobile/assets/`
- Service worker not yet implemented

### App looks broken
- Check browser is up to date
- Try Chrome on Android or Safari on iOS
- Clear browser cache

### Audio not playing through Bluetooth
- Ensure Bluetooth earphones are connected before starting
- Try unpairing and re-pairing
- Some phones require media audio to be enabled for Bluetooth

## Test Failures

### Tests fail after code changes
```bash
cd Netra-Ai
python tests/safety/test_decisions.py
```
Check the error output. Common issues:
- Changed the safety engine logic — update tests to match
- Added/removed fields in schemas — update validation tests

### Import errors
- Ensure you're running from the `Netra-Ai` directory
- Check Python version (3.8+ required)
- Check the `sys.path` in `test_decisions.py` points to the server directory

## Performance Issues

### Slow perception cycle
- Image upload is the main bottleneck
- Reduce image resolution or JPEG quality
- Use a faster network connection
- Consider using a local vision model

### High latency
- Check network speed
- Google Cloud APIs can have variable latency
- For demo, use the local mock server

## Getting Help

1. Check this troubleshooting guide
2. Check n8n execution logs in the n8n UI
3. Check browser console (F12 → Console) for JavaScript errors
4. Check Python test output for detailed failures
5. For API issues, check Google Cloud Console for quota/billing issues
