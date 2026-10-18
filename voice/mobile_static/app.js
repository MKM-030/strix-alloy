export function resolveBasePath(configured, pathname) {
  if (typeof configured === 'string' && /^\/[A-Za-z0-9_-]+$/.test(configured)) return configured;
  return pathname === '/scc-demo' || pathname.startsWith('/scc-demo/') ? '/scc-demo' : '';
}

// The bridge accepts RIFF/WAVE mono PCM16, regardless of the browser's recorder format.
export function encodeWav(audio) {
  const output = new ArrayBuffer(44 + audio.length * 2);
  const view = new DataView(output);
  const write = (offset, text) => [...text].forEach((letter, i) => view.setUint8(offset + i, letter.charCodeAt(0)));
  write(0, 'RIFF');
  view.setUint32(4, 36 + audio.length * 2, true);
  write(8, 'WAVE');
  write(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, audio.sampleRate, true);
  view.setUint32(28, audio.sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, 'data');
  view.setUint32(40, audio.length * 2, true);
  const channels = Array.from({ length: audio.numberOfChannels }, (_, i) => audio.getChannelData(i));
  for (let i = 0; i < audio.length; i++) {
    let sample = 0;
    for (const channel of channels) sample += channel[i];
    sample = Math.max(-1, Math.min(1, sample / channels.length));
    view.setInt16(44 + i * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
  }
  return output;
}

if (typeof document !== 'undefined') initialize();

function initialize() {
  const $ = id => document.getElementById(id);
  const basePath = resolveBasePath(document.documentElement.dataset.basePath, location.pathname);
  const ui = Object.fromEntries(['loginPanel', 'loginForm', 'loginButton', 'loginStatus', 'password',
    'chatPanel', 'connectionStatus', 'messages', 'emptyState', 'choices', 'status', 'error',
    'messageForm', 'messageInput', 'inputLabel', 'startButton', 'sendButton', 'recordButton',
    'recordLabel', 'recordHint', 'speechEnabled', 'confirmSend', 'resetButton', 'logoutButton',
    'speechPlayer'].map(id => [id, $(id)]));
  const state = {
    authenticated: false, csrf: '', started: false, busy: false, ended: false, failed: false,
    operation: '', connected: false, cursor: 0, generation: 0, pollController: null,
    seen: new Set(), choices: [], recorder: null, stream: null, recording: false,
    recordingDiscarded: false, recordingTimer: null, recordingStarted: 0, audioContext: null,
    audioUrl: '', speechController: null, speechGeneration: 0, audioPrimed: false,
    speechQueue: [], speechRunning: false, speechPreparing: false,
  };
  const supportsRecording = !!(window.isSecureContext && navigator.mediaDevices?.getUserMedia && window.MediaRecorder && (window.AudioContext || window.webkitAudioContext));

  function explain(error) {
    if (error?.name === 'AbortError') return '';
    if (error?.name === 'NotAllowedError' || error?.name === 'PermissionDeniedError') return 'Bitte erlauben Sie den Mikrofonzugriff in den Browser-Einstellungen. Sie können auch eine Nachricht schreiben.';
    if (error?.name === 'NotFoundError') return 'Kein Mikrofon gefunden. Sie können Ihre Nachricht auch schreiben.';
    if (error instanceof TypeError) return 'Die Verbindung ist gerade nicht erreichbar. Bitte versuchen Sie es erneut.';
    return error?.message || 'Das hat leider nicht geklappt. Bitte versuchen Sie es erneut.';
  }

  function showError(error) {
    const text = typeof error === 'string' ? error : explain(error);
    if (!text) return;
    ui.error.textContent = text;
    ui.error.hidden = false;
  }

  function clearError() {
    ui.error.hidden = true;
    ui.error.textContent = '';
  }

  function canSend() {
    return state.authenticated && state.started && state.connected && !state.operation && !state.busy && !state.recording && !state.speechPreparing && !state.ended && !state.failed;
  }

  function renderControls() {
    const ready = canSend();
    ui.loginButton.disabled = !!state.operation;
    ui.password.disabled = !!state.operation;
    ui.sendButton.disabled = !ready || !ui.messageInput.value.trim();
    ui.messageInput.disabled = !state.authenticated || !state.started || !!state.operation || state.recording || state.ended || state.failed;
    ui.recordButton.disabled = !state.recording && (!ready || !supportsRecording);
    ui.recordButton.setAttribute('aria-pressed', String(state.recording));
    ui.recordLabel.textContent = state.recording ? 'Aufnahme stoppen' : 'Sprechen';
    ui.startButton.hidden = state.started || !state.authenticated;
    ui.startButton.disabled = !!state.operation;
    ui.resetButton.disabled = !!state.operation || state.recording || state.busy;
    ui.logoutButton.disabled = !!state.operation;
    ui.choices.querySelectorAll('button').forEach(button => { button.disabled = !ready; });
    ui.messages.querySelectorAll('.replay').forEach(button => { button.disabled = !state.authenticated || !!state.operation || state.recording || state.speechPreparing; });
    ui.status.classList.toggle('recording', state.recording);
    ui.connectionStatus.classList.toggle('connected', state.authenticated && state.connected);
    ui.connectionStatus.textContent = !state.authenticated ? 'Geschützte Demo' : state.connected ? 'Verbunden' : 'Verbindung prüfen …';
    if (state.recording) {
      const elapsed = Math.min(30, Math.floor((Date.now() - state.recordingStarted) / 1000));
      ui.status.textContent = `Aufnahme läuft · ${elapsed} / 30 Sek. · Zum Beenden auf „Aufnahme stoppen“ tippen.`;
    } else if (state.operation) {
      ui.status.textContent = ({ session: 'Sitzung wird geladen …', start: 'Gespräch wird gestartet …', send: 'Nachricht wird gesendet …', reset: 'Gespräch wird neu gestartet …', transcribe: 'Ihre Aufnahme wird in Text umgewandelt …', microphone: 'Mikrofon wird vorbereitet …', logout: 'Sie werden abgemeldet …' })[state.operation] || 'Einen Moment …';
    } else if (state.speechPreparing) {
      ui.status.textContent = 'Sprachausgabe wird vorbereitet …';
    } else if (!state.connected && state.authenticated) {
      ui.status.textContent = 'Verbindung unterbrochen. Es wird erneut versucht …';
    } else if (state.failed) {
      ui.status.textContent = 'Das Gespräch konnte nicht fortgesetzt werden. Bitte starten Sie neu.';
    } else if (state.ended) {
      ui.status.textContent = 'Gespräch beendet. Für ein neues Anliegen wählen Sie „Neu starten“.';
    } else if (state.busy) {
      ui.status.textContent = 'Der Assistent antwortet …';
    } else if (!state.started) {
      ui.status.textContent = 'Starten Sie Ihr Gespräch.';
    } else {
      ui.status.textContent = 'Bereit für Ihre Antwort.';
    }
    if (!supportsRecording) ui.recordHint.textContent = 'Mikrofon in diesem Browser nicht verfügbar. Bitte verwenden Sie das Textfeld.';
  }

  async function request(path, { method = 'GET', body, signal, asBlob = false } = {}) {
    if (path.startsWith('/api/') && !state.authenticated) throw new Error('Bitte melden Sie sich zuerst an.');
    const headers = { Accept: asBlob ? 'audio/wav, application/json' : 'application/json' };
    if (method !== 'GET' && state.csrf) headers['X-CSRF-Token'] = state.csrf;
    if (body && !(body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }
    const response = await fetch(`${basePath}${path}`, { method, headers, body, credentials: 'same-origin', cache: 'no-store', signal });
    if (response.status === 401 && path !== '/auth/login') {
      showLogin('Ihre Anmeldung ist abgelaufen. Bitte melden Sie sich erneut an.');
      throw new Error('Ihre Anmeldung ist abgelaufen.');
    }
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const fallback = response.status === 429 ? 'Zu viele Versuche. Bitte warten Sie kurz und versuchen Sie es erneut.' : response.status === 403 ? 'Die Anfrage wurde abgewiesen. Bitte laden Sie die Seite neu und melden Sie sich erneut an.' : 'Die Anfrage konnte nicht ausgeführt werden. Bitte versuchen Sie es erneut.';
      throw new Error(typeof data.error === 'string' ? data.error : fallback);
    }
    if (asBlob) return response.blob();
    return response.status === 204 ? {} : response.json();
  }

  function stopSpeech() {
    state.speechGeneration++;
    state.speechQueue = [];
    // A cancelled fetch does not cancel server synthesis or release its audio lock.
    // Invalidate its result now, but wait for it to settle before allowing new input.
    if (!state.speechPreparing) {
      state.speechController?.abort();
      state.speechController = null;
    }
    ui.speechPlayer.pause();
    ui.speechPlayer.onended = null;
    ui.speechPlayer.onerror = null;
    if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
    state.audioUrl = '';
  }

  // Keep one media element and activate it during the user's gesture for mobile Safari.
  function primeAudio() {
    if (!state.audioPrimed) {
      const silent = encodeWav({ length: 400, numberOfChannels: 1, sampleRate: 8000, getChannelData: () => new Float32Array(400) });
      if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
      state.audioUrl = URL.createObjectURL(new Blob([silent], { type: 'audio/wav' }));
      ui.speechPlayer.src = state.audioUrl;
      const playback = ui.speechPlayer.play();
      playback?.then(() => { state.audioPrimed = true; }).catch(() => { state.audioPrimed = false; });
    }
    const Context = window.AudioContext || window.webkitAudioContext;
    if (Context && !state.audioContext) state.audioContext = new Context();
    if (state.audioContext?.state === 'suspended') state.audioContext.resume().catch(() => {});
  }

  async function playSpeech(eventId, manual = false) {
    if (!state.authenticated || state.recording || state.speechPreparing || (!manual && !ui.speechEnabled.checked)) return;
    const generation = state.speechGeneration;
    const controller = new AbortController();
    state.speechController = controller;
    state.speechPreparing = true;
    renderControls();
    try {
      let blob;
      try {
        blob = await request('/api/speak', { method: 'POST', body: { eventId }, signal: controller.signal, asBlob: true });
      } finally {
        state.speechPreparing = false;
        renderControls();
      }
      if (generation !== state.speechGeneration || state.recording) return;
      if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
      state.audioUrl = URL.createObjectURL(blob);
      ui.speechPlayer.src = state.audioUrl;
      await ui.speechPlayer.play();
      if (controller.signal.aborted || generation !== state.speechGeneration) return;
      await new Promise(resolve => {
        const finish = () => { controller.signal.removeEventListener('abort', finish); resolve(); };
        ui.speechPlayer.onended = finish;
        ui.speechPlayer.onerror = finish;
        controller.signal.addEventListener('abort', finish, { once: true });
      });
    } catch (error) {
      if (error.name !== 'AbortError' && state.authenticated && generation === state.speechGeneration) {
        showError(error.name === 'NotAllowedError' ? 'Tippen Sie unter der Antwort auf „Erneut anhören“, um die Sprachausgabe zu aktivieren.' : `Sprachausgabe: ${explain(error)}`);
      }
    } finally {
      if (state.speechController === controller) state.speechController = null;
    }
  }

  async function drainSpeechQueue() {
    if (state.speechRunning) return;
    state.speechRunning = true;
    try {
      while (state.speechQueue.length && state.authenticated && !state.recording) {
        const next = state.speechQueue.shift();
        if (next.manual || ui.speechEnabled.checked) await playSpeech(next.eventId, next.manual);
      }
    } finally {
      state.speechRunning = false;
    }
  }

  function clearConversation() {
    state.cursor = 0;
    state.seen.clear();
    state.choices = [];
    ui.messages.querySelectorAll('.message').forEach(element => element.remove());
    ui.emptyState.hidden = false;
    ui.choices.replaceChildren();
    ui.messageInput.value = '';
    ui.inputLabel.textContent = 'Ihre Nachricht';
    clearError();
  }

  function showLogin(message = '') {
    state.generation++;
    state.pollController?.abort();
    stopRecording(true);
    stopSpeech();
    state.authenticated = false;
    state.csrf = '';
    state.started = false;
    state.busy = false;
    state.connected = false;
    state.operation = '';
    state.ended = false;
    state.failed = false;
    clearConversation();
    ui.password.value = '';
    ui.loginPanel.hidden = false;
    ui.chatPanel.hidden = true;
    ui.loginStatus.textContent = message;
    renderControls();
  }

  function renderEvent(event, speak) {
    if (event.id == null || state.seen.has(event.id)) return;
    state.seen.add(event.id);
    if (typeof event.text !== 'string' || !event.text.trim()) return;
    const kind = event.kind === 'bot' ? 'bot' : event.kind === 'user' ? 'user' : 'system';
    const wrapper = document.createElement('article');
    wrapper.className = `message ${kind}`;
    const author = document.createElement('div');
    author.className = 'message-author';
    author.textContent = kind === 'bot' ? 'ServiceNow-Assistent' : kind === 'user' ? 'Sie' : 'Hinweis';
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    // All conversation content is treated as text, including remote HTML-like output.
    bubble.textContent = event.text;
    wrapper.append(author, bubble);
    if (kind === 'bot' && event.text.length <= 1500) {
      const replay = document.createElement('button');
      replay.type = 'button';
      replay.className = 'replay';
      replay.textContent = '▷ Erneut anhören';
      replay.addEventListener('click', () => {
        if (!state.authenticated || state.operation || state.recording || state.speechPreparing) return;
        stopSpeech();
        primeAudio();
        state.speechQueue.push({ eventId: event.id, manual: true });
        void drainSpeechQueue();
      });
      wrapper.append(replay);
      if (speak && ui.speechEnabled.checked) state.speechQueue.push({ eventId: event.id, manual: false });
    }
    ui.emptyState.hidden = true;
    ui.messages.append(wrapper);
    ui.messages.scrollTop = ui.messages.scrollHeight;
  }

  function renderChoices(choices) {
    if (!Array.isArray(choices)) choices = [];
    if (JSON.stringify(choices) === JSON.stringify(state.choices)) return;
    state.choices = choices;
    ui.choices.replaceChildren();
    for (const choice of choices) {
      if (!choice || typeof choice.label !== 'string' || choice.value == null) continue;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'choice';
      button.textContent = choice.label;
      button.addEventListener('click', () => {
        primeAudio();
        void sendMessage({ choice: choice.value });
      });
      ui.choices.append(button);
    }
  }

  function applySession(data) {
    if (typeof data.csrf === 'string') state.csrf = data.csrf;
    for (const key of ['started', 'busy', 'ended', 'failed']) {
      if (typeof data[key] === 'boolean') state[key] = data[key];
    }
  }

  async function poll(generation, initialHistory = false) {
    let history = initialHistory;
    while (state.authenticated && generation === state.generation) {
      const controller = new AbortController();
      state.pollController = controller;
      try {
        const data = await request(`/api/events?after=${encodeURIComponent(state.cursor)}&wait=20`, { signal: controller.signal });
        if (generation !== state.generation) return;
        state.connected = true;
        applySession(data);
        for (const event of Array.isArray(data.events) ? data.events : []) renderEvent(event, !history);
        if (Number.isSafeInteger(data.cursor) && data.cursor >= state.cursor) state.cursor = data.cursor;
        renderChoices(data.choices);
        ui.inputLabel.textContent = typeof data.inputLabel === 'string' && data.inputLabel.trim() ? data.inputLabel : 'Ihre Nachricht';
        history = false;
        renderControls();
        void drainSpeechQueue();
        // Some bridges answer immediately before a session starts or after it ends.
        if (!state.started || state.ended || state.failed) await new Promise(resolve => setTimeout(resolve, 1000));
      } catch (error) {
        if (error.name === 'AbortError' || generation !== state.generation || !state.authenticated) return;
        state.connected = false;
        renderControls();
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
    }
  }

  function startPolling(initialHistory = false) {
    state.generation++;
    state.pollController?.abort();
    void poll(state.generation, initialHistory);
  }

  async function openSession(autoStart) {
    state.operation = 'session';
    ui.loginPanel.hidden = true;
    ui.chatPanel.hidden = false;
    renderControls();
    try {
      const data = await request('/api/session');
      applySession(data);
      state.connected = true;
      state.operation = '';
      if (autoStart && !state.started) await startConversation();
      else startPolling(true);
    } catch (error) {
      showError(error);
    } finally {
      state.operation = '';
      renderControls();
    }
  }

  async function startConversation() {
    if (!state.authenticated || state.operation) return;
    state.operation = 'start';
    clearError();
    renderControls();
    try {
      await request('/api/start', { method: 'POST', body: {} });
      state.started = true;
      state.busy = true;
      state.connected = true;
      startPolling();
    } catch (error) {
      showError(error);
    } finally {
      state.operation = '';
      renderControls();
    }
  }

  async function sendMessage(payload) {
    if (!canSend()) return;
    if ('text' in payload) {
      payload.text = payload.text.trim();
      if (!payload.text) return;
    }
    state.operation = 'send';
    state.generation++;
    state.pollController?.abort();
    const previousChoices = state.choices;
    state.busy = true;
    renderChoices([]);
    stopSpeech();
    clearError();
    renderControls();
    try {
      await request('/api/message', { method: 'POST', body: payload });
      if ('text' in payload) ui.messageInput.value = '';
    } catch (error) {
      state.busy = false;
      if (state.authenticated) renderChoices(previousChoices);
      showError(error);
    } finally {
      state.operation = '';
      renderControls();
      if (state.authenticated) startPolling();
    }
  }

  function releaseMicrophone() {
    clearInterval(state.recordingTimer);
    state.recordingTimer = null;
    state.stream?.getTracks().forEach(track => track.stop());
    state.stream = null;
  }

  function stopRecording(discard = false) {
    state.recordingDiscarded = discard;
    if (state.recorder && state.recorder.state !== 'inactive') {
      if (!discard) state.operation = 'transcribe';
      state.recorder.stop();
    }
    state.recording = false;
    releaseMicrophone();
    renderControls();
  }

  async function transcribe(chunks, mime, generation) {
    if (state.recordingDiscarded || !state.authenticated || generation !== state.generation) return;
    state.operation = 'transcribe';
    renderControls();
    let sendImmediately = false;
    try {
      const recording = new Blob(chunks, { type: mime });
      if (!recording.size) throw new Error('Die Aufnahme war leer. Bitte versuchen Sie es erneut.');
      const decoded = await state.audioContext.decodeAudioData(await recording.arrayBuffer());
      const form = new FormData();
      form.append('file', new Blob([encodeWav(decoded)], { type: 'audio/wav' }), 'aufnahme.wav');
      const result = await request('/api/transcribe', { method: 'POST', body: form });
      if (!state.authenticated || generation !== state.generation) return;
      if (typeof result.text !== 'string' || !result.text.trim()) throw new Error('Es wurde keine Sprache erkannt. Bitte versuchen Sie es erneut oder schreiben Sie Ihre Nachricht.');
      ui.messageInput.value = result.text.trim();
      sendImmediately = !ui.confirmSend.checked;
    } catch (error) {
      showError(error);
    } finally {
      state.operation = '';
      renderControls();
    }
    if (!sendImmediately && ui.messageInput.value) ui.messageInput.focus();
    if (sendImmediately) await sendMessage({ text: ui.messageInput.value });
  }

  async function startRecording() {
    if (!canSend() || !supportsRecording) return;
    stopSpeech();
    primeAudio();
    state.operation = 'microphone';
    state.recordingDiscarded = false;
    clearError();
    renderControls();
    const generation = state.generation;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }, video: false });
      if (!state.authenticated || generation !== state.generation) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      state.stream = stream;
      const mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find(type => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      state.recorder = recorder;
      const chunks = [];
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      recorder.onerror = () => {
        stopRecording(true);
        showError('Die Aufnahme ist fehlgeschlagen. Bitte versuchen Sie es erneut.');
      };
      recorder.onstop = () => {
        if (state.recorder !== recorder) return;
        state.recorder = null;
        state.recording = false;
        releaseMicrophone();
        void transcribe(chunks, recorder.mimeType || mime || 'audio/webm', generation);
        renderControls();
      };
      recorder.start();
      state.recording = true;
      state.recordingStarted = Date.now();
      state.recordingTimer = setInterval(() => {
        if (Date.now() - state.recordingStarted >= 30000) stopRecording();
        else renderControls();
      }, 250);
    } catch (error) {
      releaseMicrophone();
      showError(error);
    } finally {
      state.operation = '';
      renderControls();
    }
  }

  ui.loginForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (state.operation) return;
    primeAudio();
    const password = ui.password.value;
    if (!password) return;
    state.operation = 'login';
    ui.loginStatus.textContent = 'Anmeldung läuft …';
    renderControls();
    try {
      const result = await request('/auth/login', { method: 'POST', body: { password } });
      ui.password.value = '';
      if (!result.authenticated || typeof result.csrf !== 'string') throw new Error('Die Anmeldung konnte nicht bestätigt werden.');
      state.authenticated = true;
      state.csrf = result.csrf;
      state.operation = '';
      await openSession(true);
    } catch (error) {
      ui.password.value = '';
      ui.loginStatus.textContent = explain(error);
    } finally {
      state.operation = '';
      renderControls();
    }
  });

  ui.messageForm.addEventListener('submit', event => {
    event.preventDefault();
    primeAudio();
    void sendMessage({ text: ui.messageInput.value });
  });
  ui.messageInput.addEventListener('input', renderControls);
  ui.messageInput.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault();
      primeAudio();
      void sendMessage({ text: ui.messageInput.value });
    }
  });
  ui.startButton.addEventListener('click', () => { primeAudio(); void startConversation(); });
  ui.recordButton.addEventListener('click', () => state.recording ? stopRecording() : void startRecording());
  ui.speechEnabled.addEventListener('change', () => {
    if (ui.speechEnabled.checked) primeAudio();
    else stopSpeech();
  });
  ui.resetButton.addEventListener('click', async () => {
    if (state.operation || state.recording || state.busy) return;
    primeAudio();
    state.operation = 'reset';
    state.generation++;
    state.pollController?.abort();
    stopSpeech();
    clearError();
    renderControls();
    try {
      const data = await request('/api/reset', { method: 'POST', body: {} });
      clearConversation();
      state.started = false;
      state.busy = false;
      state.ended = false;
      state.failed = false;
      applySession(data);
      state.operation = '';
      await startConversation();
    } catch (error) {
      showError(error);
      if (state.authenticated) startPolling(true);
    } finally {
      state.operation = '';
      renderControls();
    }
  });
  ui.logoutButton.addEventListener('click', async () => {
    if (state.operation) return;
    stopRecording(true);
    stopSpeech();
    state.operation = 'logout';
    renderControls();
    try {
      await request('/auth/logout', { method: 'POST', body: {} });
      showLogin('Sie sind abgemeldet.');
    } catch (error) {
      showError(error);
    } finally {
      state.operation = '';
      renderControls();
    }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && state.recording) stopRecording(true);
  });
  window.addEventListener('pagehide', () => {
    stopRecording(true);
    stopSpeech();
    state.pollController?.abort();
  });
  window.addEventListener('pageshow', () => {
    if (state.authenticated) startPolling(true);
  });

  renderControls();
  request('/auth/session').then(async session => {
    if (session.authenticated && typeof session.csrf === 'string') {
      state.authenticated = true;
      state.csrf = session.csrf;
      await openSession(false);
    } else showLogin();
  }).catch(error => showLogin(explain(error)));
}
