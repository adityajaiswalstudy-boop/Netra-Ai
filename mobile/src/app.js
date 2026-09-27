/**
 * AI SafePath — Mobile PWA
 *
 * Architecture:
 *   Camera → periodic frame capture → base64 → POST to n8n /perception
 *   → structured perception JSON → POST to n8n /safety-decision
 *   → LEFT/RIGHT/STRAIGHT/STOP/WAIT + voice_instruction
 *   → Browser SpeechSynthesis (fallback) or POST to /voice for cloud TTS
 */

(function () {
  'use strict';

  // ── Configuration ──
  const CONFIG = {
    // Change these to your n8n Cloud webhook URLs after importing workflows
    n8nBaseUrl: 'https://YOUR_N8N_SUBDOMAIN.app.n8n.cloud/webhook',  // ← Replace with your n8n Cloud webhook URL after importing workflows
    endpoints: {
      navigationStart: 'navigation-start',
      perception: 'perception',
      safetyDecision: 'safety-decision',
      voice: 'voice',
      session: 'session',
    },
    captureIntervalMs: 2000,
    ttsLanguage: 'en-US',
    debug: false,
    maxImageSize: 1200000, // 1.2MB max base64
  };

  // ── State ──
  const state = {
    camera: { stream: null, active: false },
    session: {
      id: null,
      origin: null,
      destination: null,
      route: null,
      status: 'idle',
    },
    perception: null,
    decision: null,
    navigation: null,
    captureTimer: null,
    isNavigating: false,
  };

  // ── DOM refs ──
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const dom = {
    statusBadge: $('#status-badge'),
    statusText: $('.status-text'),
    destinationInput: $('#destination-input'),
    btnSetDestination: $('#btn-set-destination'),
    destinationDisplay: $('#destination-display'),
    destName: $('#dest-name'),
    btnClearDestination: $('#btn-clear-destination'),
    btnStartCamera: $('#btn-start-camera'),
    btnStopCamera: $('#btn-stop-camera'),
    cameraStream: $('#camera-stream'),
    cameraStatus: $('#camera-status'),
    btnStartNav: $('#btn-start-navigation'),
    btnStopNav: $('#btn-stop-navigation'),
    decisionAction: $('#decision-action'),
    voiceText: $('#voice-text'),
    btnSpeak: $('#btn-speak'),
    navRouteInfo: $('#nav-route-info'),
    navNextStep: $('#nav-next-step'),
    navRemaining: $('#nav-remaining'),
    navInfoSection: $('#nav-info-section'),
    perceptionSection: $('#perception-section'),
    perceptionObjects: $('#perception-objects'),
    pathLeftStatus: $('#path-left-status'),
    pathCenterStatus: $('#path-center-status'),
    pathRightStatus: $('#path-right-status'),
    pathLeftRisk: $('#path-left-risk'),
    pathCenterRisk: $('#path-center-risk'),
    pathRightRisk: $('#path-right-risk'),
    overallRisk: $('#overall-risk'),
    perceptionConfidence: $('#perception-confidence'),
    sessionInfo: $('#session-info'),
    sessionIdDisplay: $('#session-id-display'),
    latencyDisplay: $('#latency-display'),
    latencyValue: $('#latency-value'),
    captureInterval: $('#capture-interval'),
    ttsLanguage: $('#tts-language'),
    debugMode: $('#debug-mode'),
    demoOverlay: $('#demo-overlay'),
    btnExitDemo: $('#btn-exit-demo'),
  };

  // ── Utility ──
  function setStatus(level, text) {
    dom.statusBadge.className = 'status-badge status-' + level;
    dom.statusText.textContent = text;
  }

  function show(el) { el.classList.remove('hidden'); }
  function hide(el) { el.classList.add('hidden'); }
  function toggle(el, show) { show ? show(el) : hide(el); }

  function formatDistance(m) {
    if (m < 1000) return m + 'm';
    return (m / 1000).toFixed(1) + 'km';
  }

  function genId() {
    return 'sp_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 6);
  }

  // ── Camera ──
  async function startCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
      dom.cameraStream.srcObject = stream;
      state.camera.stream = stream;
      state.camera.active = true;
      dom.cameraStatus.textContent = 'Camera active';
      dom.cameraStatus.style.color = '#2ed573';
      hide(dom.btnStartCamera);
      show(dom.btnStopCamera);
      setStatus('active', 'Camera on');
      return true;
    } catch (err) {
      dom.cameraStatus.textContent = 'Camera denied: ' + err.message;
      dom.cameraStatus.style.color = '#ff4757';
      setStatus('danger', 'Camera failed');
      return false;
    }
  }

  function stopCamera() {
    if (state.camera.stream) {
      state.camera.stream.getTracks().forEach(t => t.stop());
      state.camera.stream = null;
    }
    state.camera.active = false;
    dom.cameraStream.srcObject = null;
    dom.cameraStatus.textContent = 'Camera stopped';
    dom.cameraStatus.style.color = '';
    show(dom.btnStartCamera);
    hide(dom.btnStopCamera);
    setStatus('idle', 'Ready');
  }

  // ── Frame capture ──
  function captureFrame() {
    if (!state.camera.active) return null;
    const video = dom.cameraStream;
    if (!video.videoWidth || !videoHeight) return null;

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.7);
    const base64 = dataUrl.split(',')[1];

    if (base64.length > CONFIG.maxImageSize * 1.33) {
      // Too large, re-encode at lower quality
      const lowQuality = canvas.toDataURL('image/jpeg', 0.4);
      return lowQuality.split(',')[1];
    }
    return base64;
  }

  // ── HTTP helper ──
  async function postToN8n(endpoint, payload) {
    const url = CONFIG.n8nBaseUrl + '/' + endpoint;
    const start = performance.now();
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const latency = Math.round(performance.now() - start);
      if (!res.ok) {
        const text = await res.text();
        throw new Error('HTTP ' + res.status + ': ' + text.slice(0, 200));
      }
      const json = await res.json();
      if (CONFIG.debug) {
        console.log('[SafePath] ' + endpoint + ' OK (' + latency + 'ms):', json);
      }
      show(dom.latencyDisplay);
      dom.latencyValue.textContent = latency;
      return json;
    } catch (err) {
      hide(dom.latencyDisplay);
      console.error('[SafePath] ' + endpoint + ' failed:', err.message);
      if (CONFIG.debug) {
        alert('API call failed: ' + err.message);
      }
      return null;
    }
  }

  // ── Perception pipeline ──
  async function runPerceptionCycle() {
    if (!state.camera.active || !state.session.id) return;

    setStatus('warning', 'Analyzing...');
    const base64 = captureFrame();
    if (!base64) {
      console.warn('Frame capture failed');
      return;
    }

    // Step 1: Send frame to perception
    const perceptionPayload = {
      image_base64: base64,
      frame_timestamp_ms: Date.now(),
      session_id: state.session.id,
      device_id: 'mobile_pwa',
      // GPS coordinates (from device geolocation)
      latitude: state.gps?.latitude ?? null,
      longitude: state.gps?.longitude ?? null,
      // Heading in degrees (0-360, true north), null if not available
      heading: state.gps?.heading ?? null,
      // GPS accuracy in meters
      gps_accuracy_m: state.gps?.accuracy ?? null,
    };

    const perResult = await postToN8n(CONFIG.endpoints.perception, perceptionPayload);
    if (!perResult || perResult.error) {
      console.warn('Perception failed, skipping cycle');
      setStatus('warning', 'Perception error');
      return;
    }

    state.perception = perResult;
    updatePerceptionUI(perResult);

    // Step 2: Send perception to safety decision
    const decisionPayload = {
      perception: perResult,
      navigation: state.navigation,
      session_id: state.session.id,
    };

    const decResult = await postToN8n(CONFIG.endpoints.safetyDecision, decisionPayload);
    if (!decResult || decResult.error) {
      console.warn('Decision failed:', decResult);
      return;
    }

    state.decision = decResult;
    updateDecisionUI(decResult);

    // Step 3: TTS (browser fallback)
    speakInstruction(decResult.voice_instruction);
  }

  // ── UI updates ──
  function updatePerceptionUI(per) {
    // Objects list
    const objects = per.objects || [];
    if (objects.length === 0) {
      dom.perceptionObjects.innerHTML = '<p class="no-data">No obstacles detected.</p>';
    } else {
      dom.perceptionObjects.innerHTML = objects
        .slice(0, 8)
        .map(o => {
          const dist = o.estimated_distance_m != null
            ? '~=' + o.estimated_distance_m.toFixed(1) + 'm'
            : 'distance unknown';
          return '<div>• ' + o.type + ' (' + o.position + ', ' + dist + ')</div>';
        })
        .join('');
    }

    // Path cards
    for (const dir of ['left', 'center', 'right']) {
      const path = per[dir + '_path'];
      const card = $('#path-' + dir);
      const statusEl = dom['path' + dir.charAt(0).toUpperCase() + dir.slice(1) + 'Status'];
      const riskEl = dom['path' + dir.charAt(0).toUpperCase() + dir.slice(1) + 'Risk'];
      if (!path) continue;

      card.className = 'path-card ' + (path.clear ? 'clear' : (path.risk === 'HIGH' || path.risk === 'CRITICAL' ? 'blocked' : 'partial'));
      statusEl.textContent = path.clear ? 'CLEAR' : 'BLOCKED';
      riskEl.textContent = 'Risk: ' + path.risk + ' (conf: ' + path.confidence.toFixed(2) + ')';
    }

    // Overall risk
    const risk = per.overall_risk || 'LOW';
    dom.overallRisk.textContent = risk;
    dom.overallRisk.className = 'risk-value ' + risk.toLowerCase();
    dom.perceptionConfidence.textContent = (per.confidence || 0).toFixed(2);
  }

  function updateDecisionUI(dec) {
    const action = dec.action || 'WAIT';
    dom.decisionAction.textContent = action;
    dom.decisionAction.className = 'decision-action ' + action.toLowerCase();

    dom.voiceText.textContent = dec.voice_instruction || 'No instruction';
    dom.btnSpeak.disabled = false;

    // Navigation context
    if (dec.navigation_context) {
      const nc = dec.navigation_context;
      if (nc.current_step_instruction) {
        dom.navInfoSection.classList.remove('hidden');
        dom.navRouteInfo.textContent = (state.navigation?.route?.total_distance_m ? formatDistance(state.navigation.route.total_distance_m) : '—') +
          ' to go';
        dom.navNextStep.textContent = nc.current_step_instruction;
        dom.navRemaining.textContent = nc.remaining_steps + ' steps';
      }
    }

    // Status based on action
    if (action === 'STOP') setStatus('danger', 'STOP');
    else if (action === 'WAIT') setStatus('warning', 'Wait');
    else if (state.isNavigating) setStatus('active', 'Navigating');
  }

  // ── TTS ──
  function speakInstruction(text) {
    if (!text || text.trim().length === 0) return;
    // Browser SpeechSynthesis fallback
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = CONFIG.ttsLanguage;
      utter.rate = 1.0;
      utter.pitch = 1.0;
      window.speechSynthesis.speak(utter);
    }
  }

  // ── Navigation ──
  async function startNavigation() {
    if (!state.session.destination) {
      alert('Set a destination first.');
      return;
    }

    setStatus('warning', 'Starting...');
    dom.btnStartNav.disabled = true;

    // Create session on n8n
    const sessionPayload = {
      action: 'create',
      session_id: genId(),
      origin: state.session.origin || { lat: 0, lng: 0 },
      destination: state.session.destination,
    };

    const sessionResult = await postToN8n(CONFIG.endpoints.session, sessionPayload);
    if (!sessionResult) {
      alert('Failed to create session');
      dom.btnStartNav.disabled = false;
      return;
    }

    state.session.id = sessionResult.session_id || sessionResult.id || genId();
    dom.sessionIdDisplay.textContent = state.session.id;
    show(dom.sessionInfo);
    state.isNavigating = true;
    hide(dom.btnStartNav);
    show(dom.btnStopNav);
    setStatus('active', 'Navigating');

    // Start periodic capture
    runCaptureLoop();
  }

  function stopNavigation() {
    state.isNavigating = false;
    stopCaptureLoop();
    hide(dom.btnStopNav);
    show(dom.btnStartNav);
    dom.btnStartNav.disabled = false;
    setStatus('idle', 'Paused');
  }

  function runCaptureLoop() {
    stopCaptureLoop();
    state.captureTimer = setInterval(() => {
      if (state.isNavigating && state.camera.active) {
        runPerceptionCycle();
      }
    }, CONFIG.captureIntervalMs);
  }

  function stopCaptureLoop() {
    if (state.captureTimer) {
      clearInterval(state.captureTimer);
      state.captureTimer = null;
    }
  }

  // ── GPS ──
  function startGPS() {
    if (!('geolocation' in navigator)) {
      console.warn('Geolocation not available');
      return;
    }
    navigator.geolocation.watchPosition(
      (pos) => {
        state.session.origin = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy_m: pos.coords.accuracy,
        };
        state.session.current_location = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy_m: pos.coords.accuracy,
          timestamp: Date.now(),
        };
        if (CONFIG.debug) {
          console.log('[SafePath] GPS:', state.session.current_location);
        }
      },
      (err) => {
        console.warn('[SafePath] GPS error:', err.message);
        setStatus('warning', 'GPS unavailable');
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 5000 }
    );
  }

  // ── Destination ──
  function setDestination(address) {
    state.session.destination = {
      address: address,
      name: address,
    };
    dom.destName.textContent = address;
    show(dom.destinationDisplay);
    hide(dom.destinationInput.parentElement);
    dom.btnStartNav.disabled = false;
    setStatus('idle', 'Destination set');
  }

  function clearDestination() {
    state.session.destination = null;
    hide(dom.destinationDisplay);
    show(dom.destinationInput.parentElement);
    dom.btnStartNav.disabled = true;
    dom.destinationInput.value = '';
    dom.destinationInput.focus();
  }

  // ── Demo mode ──
  const DEMO_SCENARIOS = {
    pole_left: {
      perception: {
        scene_summary: 'Pole detected ahead on sidewalk.',
        objects: [
          { type: 'pole', position: 'center', estimated_distance_m: 4.0, distance_confidence: 0.72, blocks_path: true, risk: 'HIGH' },
        ],
        left_path: { clear: true, risk: 'LOW', confidence: 0.88 },
        center_path: { clear: false, risk: 'HIGH', confidence: 0.91 },
        right_path: { clear: false, risk: 'HIGH', confidence: 0.75 },
        overall_risk: 'HIGH',
        confidence: 0.86,
      },
      expectedAction: 'LEFT',
      voice: 'Pole ahead. Move left.',
    },
    vehicle_stop: {
      perception: {
        scene_summary: 'Vehicle approaching head-on.',
        objects: [
          { type: 'vehicle', position: 'center', estimated_distance_m: 6.0, distance_confidence: 0.85, blocks_path: true, risk: 'CRITICAL' },
        ],
        left_path: { clear: true, risk: 'LOW', confidence: 0.85 },
        center_path: { clear: false, risk: 'CRITICAL', confidence: 0.92 },
        right_path: { clear: true, risk: 'LOW', confidence: 0.82 },
        overall_risk: 'CRITICAL',
        confidence: 0.90,
      },
      expectedAction: 'STOP',
      voice: 'Vehicle approaching. Stop.',
    },
    clear: {
      perception: {
        scene_summary: 'Open sidewalk ahead. No obstacles.',
        objects: [],
        left_path: { clear: true, risk: 'LOW', confidence: 0.90 },
        center_path: { clear: true, risk: 'LOW', confidence: 0.92 },
        right_path: { clear: true, risk: 'LOW', confidence: 0.88 },
        overall_risk: 'LOW',
        confidence: 0.90,
      },
      expectedAction: 'STRAIGHT',
      voice: 'Path clear. Continue straight.',
    },
  };

  function runDemo(scenarioId) {
    const demo = DEMO_SCENARIOS[scenarioId];
    if (!demo) return;

    state.perception = demo.perception;
    updatePerceptionUI(demo.perception);

    const decResult = {
      action: demo.expectedAction,
      reason: 'Demo scenario: ' + scenarioId,
      confidence: demo.perception.confidence,
      timestamp: Date.now(),
      voice_instruction: demo.voice,
      perception_summary: { overall_risk: demo.perception.overall_risk, primary_threat: 'demo', threat_count: demo.perception.objects.length },
    };

    state.decision = decResult;
    updateDecisionUI(decResult);
    speakInstruction(demo.voice);
  }

  // ── Event listeners ──
  dom.btnSetDestination.addEventListener('click', () => {
    const val = dom.destinationInput.value.trim();
    if (val) setDestination(val);
  });

  dom.destinationInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const val = dom.destinationInput.value.trim();
      if (val) setDestination(val);
    }
  });

  dom.btnClearDestination.addEventListener('click', clearDestination);

  dom.btnStartCamera.addEventListener('click', startCamera);
  dom.btnStopCamera.addEventListener('click', stopCamera);

  dom.btnStartNav.addEventListener('click', startNavigation);
  dom.btnStopNav.addEventListener('click', stopNavigation);

  dom.btnSpeak.addEventListener('click', () => {
    if (state.decision?.voice_instruction) {
      speakInstruction(state.decision.voice_instruction);
    }
  });

  dom.captureInterval.addEventListener('change', (e) => {
    CONFIG.captureIntervalMs = parseInt(e.target.value, 10);
    if (state.isNavigating) {
      runCaptureLoop(); // restart with new interval
    }
  });

  dom.ttsLanguage.addEventListener('change', (e) => {
    CONFIG.ttsLanguage = e.target.value;
  });

  dom.debugMode.addEventListener('change', (e) => {
    CONFIG.debug = e.target.checked;
  });

  dom.btnExitDemo.addEventListener('click', () => {
    hide(dom.demoOverlay);
  });

  $$('.demo-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const scenario = btn.dataset.scenario;
      runDemo(scenario);
    });
  });

  // ── Keyboard shortcuts ──
  document.addEventListener('keydown', (e) => {
    if (e.key === 'c' && !e.ctrlKey && !e.metaKey) {
      if (state.camera.active) stopCamera();
      else startCamera();
    }
    if (e.key === ' ' && state.isNavigating) {
      e.preventDefault();
      stopNavigation();
    }
  });

  // ── Init ──
  function init() {
    setStatus('idle', 'Ready');
    dom.destinationInput.focus();

    // Try to start GPS
    startGPS();

    // Check if PWA is installed
    if ('serviceWorker' in navigator) {
      // Service worker registration would go here
      console.log('[SafePath] PWA ready');
    }

    console.log('[SafePath] Initialized. Point camera and set destination.');
  }

  // ── Expose for debugging ──
  window.SafePath = {
    state,
    CONFIG,
    startCamera,
    stopCamera,
    runPerceptionCycle,
    startNavigation,
    stopNavigation,
    runDemo,
    setDestination,
    clearDestination,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
