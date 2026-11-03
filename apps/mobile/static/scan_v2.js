(function () {
  const $ = id => document.getElementById(id);
  const video = $('liveVideo'), statusEl = $('scanStatus'), list = $('candidateList'), photo = $('scanPhoto');
  const canvas = $('scanCanvas');
  let stream = null, detector = null, timer = null, locked = false, searchSeq = 0, searchTimer = null, frameBusy = false;

  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const say = (msg, bad) => { statusEl.textContent = msg; statusEl.className = bad ? 'alert danger' : 'muted'; };

  function showCandidates(rows, intro) {
    list.innerHTML = (intro ? '<div class="muted">' + esc(intro) + '</div>' : '') + rows.map(r =>
      '<a class="mobile-row" href="/mobile/confirm/' + encodeURIComponent(r.tracking_id) + '"><div><b>' + esc(r.title || r.tracking_id) +
      '</b><small>' + esc(r.part || r.description || '—') + ' · ' + esc(r.customer || (r.kind === 'TEMP' ? 'Unidentified' : '—')) +
      '</small></div><div class="mobile-row-right"><strong>' + (r.qty != null ? Math.round(r.qty) : '') + '</strong><small>' + esc(r.kind) + '</small></div></a>').join('');
  }

  function handle(d) {
    if (!d) { locked = false; say('No response from the server.', true); return; }
    if (d.ambiguous) { showCandidates(d.candidates || [], (d.candidates || []).length + ' matches. Choose the correct one.'); say('Several matches found.'); return; }
    const id = d.tracking_id || d.wo_id || (d.candidates && d.candidates[0] && d.candidates[0].tracking_id);
    if (d.ok && id) { location = '/mobile/confirm/' + encodeURIComponent(id); return; }
    locked = false;
    say(d.error || 'No matching work order. Type the code or record an unidentified part.', true);
    if ($('unidLink')) $('unidLink').hidden = false;
  }

  async function resolve(value, method) {
    say('Looking up…');
    try {
      const r = await fetch('/api/v2/resolve?method=' + method + '&value=' + encodeURIComponent(value));
      if (r.status === 401) { location = '/login?next=/mobile/scan'; return; }
      handle(await r.json());
    } catch (e) { locked = false; say('Server not reachable. Try a photo or type the work order.', true); }
  }

  function stop() {
    if (timer) clearTimeout(timer);
    timer = null;
    if (stream) stream.getTracks().forEach(t => t.stop());
    stream = null;
    detector = null;
    frameBusy = false;
    if (video) { video.srcObject = null; video.hidden = true; }
    if ($('stopScan')) $('stopScan').hidden = true;
    if ($('startScan')) $('startScan').hidden = false;
  }

  async function sendFrame() {
    if (!video || !canvas || video.readyState < 2) return null;
    const w = video.videoWidth, h = video.videoHeight;
    if (!w || !h) return null;
    canvas.width = w; canvas.height = h;
    canvas.getContext('2d').drawImage(video, 0, 0, w, h);
    const blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg', 0.82));
    if (!blob) return null;
    const fd = new FormData();
    fd.append('photo', blob, 'live-frame.jpg');
    const r = await fetch('/api/decode-qr-photo', { method: 'POST', body: fd });
    if (r.status === 401) { location = '/login?next=/mobile/scan'; return null; }
    return r.json();
  }

  async function loop() {
    if (!stream || locked) return;
    try {
      if (detector) {
        const hits = await detector.detect(video);
        if (hits.length) {
          locked = true;
          const value = hits[0].rawValue;
          stop();
          await resolve(value, 'LIVE_CAMERA');
          return;
        }
      } else if (!frameBusy) {
        frameBusy = true;
        try {
          const d = await sendFrame();
          if (d && (d.ok || d.ambiguous) && (d.wo_id || d.tracking_id || d.ambiguous)) {
            locked = true;
            stop();
            handle(d);
            return;
          }
        } catch (e) { /* keep scanning */ }
        frameBusy = false;
      }
    } catch (e) { /* frame not ready */ }
    timer = setTimeout(loop, detector ? 160 : 700);
  }

  const CAMERA_ERRORS = {
    NotAllowedError: 'Camera permission was denied. Allow camera in the browser settings, or use Photo of QR.',
    NotFoundError: 'No camera on this device. Use Photo of QR or type the work order.',
    NotReadableError: 'The camera is in use by another app. Close it, or use Photo of QR.',
    OverconstrainedError: 'The rear camera could not be selected. Use Photo of QR.',
    SecurityError: 'This browser blocked the camera. Use Photo of QR or type the work order.'
  };

  if ($('startScan')) $('startScan').onclick = async () => {
    locked = false;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      say('This browser has no live camera. Use Photo of QR or type the work order.', true);
      if (photo) photo.focus();
      return;
    }
    try {
      if (window.BarcodeDetector) {
        try { detector = new BarcodeDetector({ formats: ['qr_code'] }); } catch (e) { detector = null; }
      }
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
      video.srcObject = stream;
      video.hidden = false;
      $('stopScan').hidden = false;
      $('startScan').hidden = true;
      say(detector ? 'Camera on. Hold the QR steady.' : 'Camera on. Frames are read by the server — hold the QR steady.');
      await video.play();
      loop();
    } catch (e) {
      stop();
      say(CAMERA_ERRORS[e.name] || ('Camera could not start. Use Photo of QR or type the work order. (' + (e.name || 'error') + ')'), true);
    }
  };
  if ($('stopScan')) $('stopScan').onclick = () => { stop(); say('Camera stopped.'); };
  window.addEventListener('pagehide', stop);
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });

  if (photo) photo.onchange = async () => {
    const file = photo.files[0];
    if (!file) return;
    say('Reading photo…');
    try {
      const fd = new FormData();
      fd.append('photo', file);
      const r = await fetch('/api/decode-qr-photo', { method: 'POST', body: fd });
      if (r.status === 401) { location = '/login?next=/mobile/scan'; return; }
      handle(await r.json());
    } catch (e) { say('Photo could not be sent. Check the connection and try again.', true); }
  };

  const input = $('woSearch');
  async function search() {
    const q = input.value.trim(), n = ++searchSeq;
    if (q.length < 1) { list.innerHTML = ''; return; }
    try {
      const d = await (await fetch('/api/v2/search?q=' + encodeURIComponent(q))).json();
      if (n !== searchSeq) return;
      if (d.rows && d.rows.length) showCandidates(d.rows, d.rows.length > 1 ? 'Choose the correct work order.' : '');
      else { list.innerHTML = '<div class="muted">No match. Check the code, or record an unidentified part.</div>'; if ($('unidLink')) $('unidLink').hidden = false; }
    } catch (e) { if (n === searchSeq) list.innerHTML = '<div class="muted">Search unavailable. Check the connection.</div>'; }
  }
  if (input) input.oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(search, 180); };
})();
