const TARGET_SAMPLE_RATE = 24000;

export function encodeWav(samples, inputSampleRate) {
  if (!(samples instanceof Float32Array) || !Number.isFinite(inputSampleRate) || inputSampleRate <= 0) {
    throw new TypeError('Ungültige Audiodaten.');
  }
  const length = Math.round(samples.length * TARGET_SAMPLE_RATE / inputSampleRate);
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const writeText = (offset, value) => {
    for (let index = 0; index < value.length; index++) view.setUint8(offset + index, value.charCodeAt(index));
  };
  writeText(0, 'RIFF');
  view.setUint32(4, 36 + length * 2, true);
  writeText(8, 'WAVE');
  writeText(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, TARGET_SAMPLE_RATE, true);
  view.setUint32(28, TARGET_SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, 'data');
  view.setUint32(40, length * 2, true);
  for (let index = 0; index < length; index++) {
    const sourcePosition = index * inputSampleRate / TARGET_SAMPLE_RATE;
    const left = Math.floor(sourcePosition);
    const fraction = sourcePosition - left;
    const sample = (samples[left] || 0) * (1 - fraction) + (samples[Math.min(left + 1, samples.length - 1)] || 0) * fraction;
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(44 + index * 2, Math.round(clamped * (clamped < 0 ? 32768 : 32767)), true);
  }
  return buffer;
}

export function inspectSignal(samples) {
  let sum = 0;
  let peak = 0;
  let clippedSamples = 0;
  for (const value of samples) {
    const absolute = Math.abs(value);
    sum += value * value;
    peak = Math.max(peak, absolute);
    if (absolute >= 0.995) clippedSamples++;
  }
  const rms = samples.length ? Math.sqrt(sum / samples.length) : 0;
  return { rms, peak, clipped: samples.length > 0 && clippedSamples / samples.length > 0.001, hasInput: rms > 0.001 && peak > 0.005 };
}

if (typeof document !== 'undefined') initializeStudio();

function initializeStudio() {
  const elements = Object.fromEntries([...document.querySelectorAll('[id]')].map(element => [element.id, element]));
  const get = id => elements[id];
  const apiBase = new URL('./api/', import.meta.url);
  const state = {csrf:'', authenticated:false, profiles:[], selectedProfileId:null, maxSeconds:25, referenceText:'', recorder:null, starting:false, recording:null, operation:false, requestToken:0, previewUrl:null};
  const formatSeconds = seconds => `00:${String(Math.floor(seconds)).padStart(2, '0')}`;
  const apiUrl = path => new URL(path, apiBase).href;

  function message(element, text = '', kind = '') {
    element.textContent = text;
    element.classList.remove('is-error', 'is-warning', 'is-success', 'is-info');
    if (kind) element.classList.add(`is-${kind}`);
    element.hidden = !text;
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
    if (options.method && options.method !== 'GET' && state.csrf) headers.set('X-CSRF-Token', state.csrf);
    let response;
    try { response = await fetch(apiUrl(path), {...options, headers, credentials:'same-origin', cache:'no-store'}); }
    catch { throw new Error('Der Sprachdienst ist nicht erreichbar. Prüfen Sie Ihre Verbindung und versuchen Sie es erneut.'); }
    if (!response.ok) {
      let detail = {};
      try { detail = await response.json(); } catch { /* A proxy error can return HTML. */ }
      if (response.status === 401 && path !== 'login') showLogin();
      const error = new Error(detail.error || (response.status === 401 ? 'Der Zugangscode ist ungültig oder die Sitzung ist abgelaufen.' : 'Die Anfrage konnte nicht abgeschlossen werden. Bitte versuchen Sie es erneut.'));
      error.status = response.status;
      error.code = detail.code;
      throw error;
    }
    if (response.status === 204) return {};
    return response.json();
  }

  function updateControls() {
    const capturing = Boolean(state.recorder || state.starting);
    const ready = get('profile-name').value.trim().length > 0 && get('voice-consent').checked;
    get('record-button').disabled = !state.authenticated || !state.referenceText || !ready || capturing || state.operation;
    get('record-button').hidden = capturing;
    get('stop-button').hidden = !state.recorder || state.starting || state.recorder.stopping;
    get('stop-button').disabled = Boolean(state.recorder?.stopping);
    get('profile-name').disabled = capturing || state.operation;
    get('voice-consent').disabled = capturing || state.operation;
    get('save-button').disabled = !state.recording?.valid || !ready || capturing || state.operation;
    get('discard-button').disabled = capturing || state.operation;
    get('refresh-button').disabled = state.operation;
    get('logout-button').disabled = state.operation;
    get('active-preview-button').disabled = !state.selectedProfileId || state.operation || capturing;
    for (const button of document.querySelectorAll('[data-profile-action]')) button.disabled = state.operation || capturing || button.dataset.selected === 'true';
    for (const audio of document.querySelectorAll('audio')) {
      if (capturing) {
        if (!audio.hidden) { audio.dataset.restoreAfterCapture = 'true'; audio.hidden = true; }
        audio.pause();
      } else if (audio.dataset.restoreAfterCapture) {
        audio.hidden = false;
        delete audio.dataset.restoreAfterCapture;
      }
    }
    get('record-help').textContent = state.starting ? 'Mikrofonzugriff wird angefragt …' : state.recorder ? 'Lesen Sie den Text vollständig vor.' : ready ? `Ihr Browser fragt beim Start nach Mikrofonzugriff. Maximal ${state.maxSeconds} Sekunden.` : 'Name eingeben und Zustimmung bestätigen.';
  }

  function resetRecording() {
    get('recording-audio').pause();
    get('recording-audio').hidden = false;
    delete get('recording-audio').dataset.restoreAfterCapture;
    get('recording-audio').removeAttribute('src');
    get('recording-audio').load();
    if (state.recording?.url) URL.revokeObjectURL(state.recording.url);
    state.recording = null;
    get('recording-preview').hidden = true;
    get('record-state').textContent = 'Bereit zur Aufnahme';
    get('record-time').textContent = `${formatSeconds(0)} / ${formatSeconds(state.maxSeconds)}`;
    setMeter(0);
    updateControls();
  }

  function resetVoicePreview() {
    const audio = get('active-preview-audio');
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    audio.hidden = true;
    delete audio.dataset.restoreAfterCapture;
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = null;
  }

  function showLogin() {
    state.authenticated = false;
    state.csrf = '';
    state.requestToken++;
    if (state.recorder) void finishRecording(true);
    state.starting = false;
    resetRecording();
    resetVoicePreview();
    for (const audio of document.querySelectorAll('.profile-audio')) { audio.pause(); audio.removeAttribute('src'); }
    get('profile-list').replaceChildren();
    state.profiles = [];
    state.selectedProfileId = null;
    get('studio-view').hidden = true;
    get('login-view').hidden = false;
    get('logout-button').hidden = true;
    get('login-button').disabled = false;
    updateControls();
  }

  function showStudio(session) {
    state.authenticated = true;
    state.csrf = session.csrf || state.csrf;
    state.referenceText = session.reference_text || state.referenceText;
    state.maxSeconds = Math.min(25, Math.max(3, Number(session.max_recording_seconds) || 25));
    get('reference-text').textContent = state.referenceText;
    get('max-duration-label').textContent = state.maxSeconds;
    get('record-time').textContent = `${formatSeconds(0)} / ${formatSeconds(state.maxSeconds)}`;
    get('studio-view').hidden = false;
    get('login-view').hidden = true;
    get('logout-button').hidden = false;
    updateControls();
  }

  const create = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };

  function renderProfiles(data) {
    state.profiles = data.profiles || [];
    state.selectedProfileId = data.selected_profile_id || null;
    const active = state.profiles.find(profile => profile.id === state.selectedProfileId);
    get('active-name').textContent = active?.name || (state.selectedProfileId ? 'Ausgewählte Stimme' : 'Standardstimme');
    get('active-detail').textContent = state.selectedProfileId ? 'Ihre Auswahl gilt für den nächsten ServiceNow-Anruf.' : 'Noch kein eigenes Stimmprofil ausgewählt.';
    get('active-badge').textContent = state.selectedProfileId ? 'Ausgewählt' : 'Standard';
    const list = get('profile-list');
    for (const audio of list.querySelectorAll('audio')) audio.pause();
    list.replaceChildren();
    if (!state.profiles.length) {
      const empty = create('div', 'empty-state');
      const mark = create('span', 'empty-mark', '≋');
      mark.setAttribute('aria-hidden', 'true');
      empty.append(mark, create('h3', '', 'Ihre erste Stimme wartet auf Sie.'), create('p', '', 'Nehmen Sie den Text auf und speichern Sie Ihr erstes Stimmprofil.'));
      list.append(empty);
    }
    for (const profile of state.profiles) {
      const selected = profile.id === state.selectedProfileId;
      const item = create('article', `profile-item${selected ? ' is-selected' : ''}`);
      const top = create('div', 'profile-item-top');
      const avatar = create('span', 'profile-avatar', (profile.name || 'S').trim().slice(0, 2).toLocaleUpperCase('de-DE'));
      avatar.setAttribute('aria-hidden', 'true');
      const group = create('div', 'profile-title-group');
      group.append(create('h3', 'profile-title', profile.name || 'Stimmprofil'));
      const date = new Date(profile.created_at_utc);
      const dateText = Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('de-DE', {day:'2-digit', month:'2-digit', year:'numeric'}).format(date);
      const duration = Number(profile.duration_seconds);
      group.append(create('p', 'profile-meta', [Number.isFinite(duration) && duration > 0 ? `${duration.toFixed(1).replace('.', ',')} Sek.` : '', dateText].filter(Boolean).join(' · ')));
      top.append(avatar, group);
      if (selected) top.append(create('span', 'badge badge-active', 'Ausgewählt'));
      const actions = create('div', 'profile-actions');
      const originalLabel = profile.id === 'synthetic-scc-demo' ? 'Referenz' : 'Original';
      const listen = create('button', 'button button-secondary', `▷ ${originalLabel} anhören`);
      listen.type = 'button';
      listen.dataset.profileAction = 'listen';
      const audio = create('audio', 'profile-audio');
      audio.controls = true;
      audio.preload = 'none';
      audio.hidden = true;
      audio.setAttribute('aria-label', `${originalLabel}aufnahme: ${profile.name}`);
      audio.addEventListener('play', () => guardPlayback(audio));
      listen.addEventListener('click', async () => {
        pauseOtherAudio(audio);
        if (!audio.src) audio.src = apiUrl(`profiles/${encodeURIComponent(profile.id)}/audio`);
        audio.hidden = false;
        try { await audio.play(); } catch { message(get('page-message'), 'Die Originalaufnahme kann gerade nicht abgespielt werden. Nutzen Sie die Wiedergabetaste oder aktualisieren Sie die Seite.', 'error'); }
      });
      audio.addEventListener('error', () => message(get('page-message'), 'Die gespeicherte Aufnahme konnte nicht geladen werden. Bitte aktualisieren Sie die Stimmprofile.', 'error'));
      const select = create('button', selected ? 'button button-secondary' : 'button button-primary', selected ? 'Für nächsten Anruf ausgewählt' : 'Für nächste ServiceNow-Anfrage verwenden');
      select.type = 'button';
      select.dataset.profileAction = 'select';
      select.dataset.selected = String(selected);
      select.disabled = selected;
      select.addEventListener('click', () => activateProfile(profile));
      actions.append(listen, select);
      item.append(top, actions, audio);
      list.append(item);
    }
    updateControls();
  }

  async function loadProfiles() {
    const data = await api('profiles');
    renderProfiles(data);
  }

  async function activateProfile(profile) {
    state.operation = true;
    updateControls();
    message(get('page-message'));
    try {
      await api(`profiles/${encodeURIComponent(profile.id)}/activate`, {method:'POST', body:'{}'});
      resetVoicePreview();
      await loadProfiles();
      message(get('page-message'), `„${profile.name}“ ist für den nächsten ServiceNow-Anruf ausgewählt.`, 'success');
    } catch (error) {
      message(get('page-message'), error.code === 'call_in_progress' ? 'Es läuft noch ein Gespräch. Warten Sie, bis es beendet ist, und wählen Sie die Stimme dann erneut aus.' : error.message, 'error');
    } finally { state.operation = false; updateControls(); }
  }

  function pauseOtherAudio(exception) {
    for (const audio of document.querySelectorAll('audio')) if (audio !== exception) audio.pause();
  }

  function guardPlayback(audio) {
    if (state.recorder || state.starting) { audio.pause(); return; }
    pauseOtherAudio(audio);
  }

  function setMeter(level, clipped = false) {
    const value = Math.max(0, Math.min(100, Math.round(level)));
    get('input-meter').setAttribute('aria-valuenow', String(value));
    get('input-meter').classList.toggle('is-clipping', clipped);
    get('input-meter-fill').style.width = `${value}%`;
  }

  function microphoneError(error) {
    if (['NotAllowedError', 'PermissionDeniedError', 'SecurityError'].includes(error.name)) return 'Mikrofonzugriff wurde nicht erlaubt. Erlauben Sie ihn in den Website-Einstellungen Ihres Browsers und starten Sie die Aufnahme erneut.';
    if (['NotFoundError', 'DevicesNotFoundError'].includes(error.name)) return 'Es wurde kein Mikrofon gefunden. Verbinden Sie ein Mikrofon und starten Sie die Aufnahme erneut.';
    if (['NotReadableError', 'TrackStartError'].includes(error.name)) return 'Das Mikrofon ist nicht verfügbar. Prüfen Sie, ob eine andere Anwendung es verwendet, und versuchen Sie es erneut.';
    return error.message || 'Die Aufnahme konnte nicht gestartet werden. Bitte versuchen Sie es erneut.';
  }

  async function releaseAudio(recorder) {
    clearInterval(recorder.interval);
    clearTimeout(recorder.timeout);
    recorder.source?.disconnect();
    recorder.node?.disconnect();
    recorder.gain?.disconnect();
    for (const track of recorder.stream?.getTracks() || []) track.stop();
    if (recorder.context && recorder.context.state !== 'closed') {
      try { await recorder.context.close(); } catch { /* Tracks are already released. */ }
    }
    get('record-indicator').classList.remove('is-recording');
    setMeter(0);
  }

  async function startRecording() {
    if (state.recorder || state.starting || state.operation) return;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      message(get('record-message'), 'Die Mikrofonaufnahme benötigt eine sichere HTTPS-Verbindung und einen aktuellen Browser.', 'error');
      return;
    }
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass || !window.AudioWorkletNode) {
      message(get('record-message'), 'Dieser Browser unterstützt die Aufnahme nicht. Öffnen Sie das Voice Studio bitte in einem aktuellen Chrome, Edge, Firefox oder Safari.', 'error');
      return;
    }
    pauseOtherAudio();
    resetRecording();
    message(get('record-message'));
    state.starting = true;
    const token = ++state.requestToken;
    updateControls();
    get('record-state').textContent = 'Mikrofon wird vorbereitet …';
    const recorder = {stream:null, context:null, source:null, node:null, gain:null, chunks:[], frames:0, stopping:false};
    try {
      recorder.stream = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:false,noiseSuppression:false,autoGainControl:false},video:false});
      if (token !== state.requestToken || !state.authenticated) { await releaseAudio(recorder); return; }
      try { recorder.context = new AudioContextClass({sampleRate:TARGET_SAMPLE_RATE}); }
      catch { recorder.context = new AudioContextClass(); }
      if (!recorder.context.audioWorklet) throw new Error('Die Mikrofonaufnahme wird von diesem Browser nicht unterstützt. Bitte verwenden Sie einen aktuellen Browser.');
      state.recorder = recorder;
      await recorder.context.audioWorklet.addModule(new URL('./recorder-worklet.js', import.meta.url));
      if (token !== state.requestToken || !state.authenticated) { await releaseAudio(recorder); return; }
      recorder.finished = new Promise(resolve => { recorder.resolveFinished = resolve; });
      recorder.node = new AudioWorkletNode(recorder.context, 'voice-studio-recorder', {numberOfInputs:1, numberOfOutputs:1, outputChannelCount:[1], processorOptions:{maximumFrames:Math.floor(recorder.context.sampleRate * state.maxSeconds)}});
      recorder.node.port.onmessage = event => {
        if (event.data.type === 'samples') {
          const samples = event.data.samples;
          recorder.chunks.push(samples);
          recorder.frames += samples.length;
          const signal = inspectSignal(samples);
          setMeter(Math.sqrt(signal.rms) * 200, signal.clipped);
          if (signal.clipped) message(get('record-message'), 'Das Signal ist sehr laut. Sprechen Sie etwas leiser oder halten Sie mehr Abstand.', 'warning');
          else if (recorder.frames / recorder.context.sampleRate > 2 && !signal.hasInput) message(get('record-message'), 'Der Mikrofonpegel ist sehr niedrig. Sprechen Sie den Text vor und prüfen Sie Ihr Mikrofon.', 'warning');
          else message(get('record-message'));
        } else if (event.data.type === 'finished') {
          recorder.resolveFinished();
          if (!recorder.stopping) void finishRecording(false, true);
        }
      };
      recorder.source = recorder.context.createMediaStreamSource(recorder.stream);
      recorder.gain = recorder.context.createGain();
      recorder.gain.gain.value = 0;
      recorder.source.connect(recorder.node);
      recorder.node.connect(recorder.gain);
      recorder.gain.connect(recorder.context.destination);
      await recorder.context.resume();
      if (token !== state.requestToken || !state.authenticated || state.recorder !== recorder || recorder.stopping) {
        await releaseAudio(recorder);
        return;
      }
      state.starting = false;
      recorder.startedAt = performance.now();
      get('record-state').textContent = 'Aufnahme läuft';
      get('record-indicator').classList.add('is-recording');
      recorder.interval = setInterval(() => {
        const elapsed = Math.min(state.maxSeconds, (performance.now() - recorder.startedAt) / 1000);
        get('record-time').textContent = `${formatSeconds(elapsed)} / ${formatSeconds(state.maxSeconds)}`;
      }, 200);
      recorder.timeout = setTimeout(() => void finishRecording(false, true), state.maxSeconds * 1000 + 300);
      recorder.stream.getAudioTracks()[0]?.addEventListener('ended', () => {
        if (state.recorder === recorder && !recorder.stopping) {
          void finishRecording(true);
          message(get('record-message'), 'Die Mikrofonverbindung wurde unterbrochen. Bitte starten Sie eine neue Aufnahme.', 'error');
        }
      });
    } catch (error) {
      await releaseAudio(recorder);
      if (token === state.requestToken) {
        state.recorder = null;
        get('record-state').textContent = 'Aufnahme nicht gestartet';
        message(get('record-message'), microphoneError(error), 'error');
      }
    } finally {
      if (token === state.requestToken) state.starting = false;
      if (state.recorder === recorder && (!recorder.node || token !== state.requestToken)) state.recorder = null;
      updateControls();
      if (state.recorder === recorder && !recorder.stopping && !state.starting) get('stop-button').focus();
    }
  }

  async function finishRecording(discard = false, automatic = false) {
    const recorder = state.recorder;
    if (!recorder || recorder.stopping) return;
    const restoreFocus = document.activeElement === get('stop-button');
    recorder.stopping = true;
    clearInterval(recorder.interval);
    clearTimeout(recorder.timeout);
    updateControls();
    if (recorder.node && recorder.finished) {
      recorder.node.port.postMessage('finish');
      await Promise.race([recorder.finished, new Promise(resolve => setTimeout(resolve, 700))]);
    }
    await releaseAudio(recorder);
    if (state.recorder === recorder) state.recorder = null;
    state.starting = false;
    if (discard || !state.authenticated) { resetRecording(); return; }
    const samples = new Float32Array(recorder.frames);
    let position = 0;
    for (const chunk of recorder.chunks) { samples.set(chunk, position); position += chunk.length; }
    const duration = samples.length / recorder.context.sampleRate;
    const signal = inspectSignal(samples);
    get('record-time').textContent = `${formatSeconds(duration)} / ${formatSeconds(state.maxSeconds)}`;
    get('record-state').textContent = 'Aufnahme beendet';
    if (duration < 3) message(get('record-message'), 'Die Aufnahme ist zu kurz. Lesen Sie den Text vollständig vor; mindestens 3 Sekunden sind erforderlich.', 'error');
    else if (!signal.hasInput) message(get('record-message'), 'Es wurde keine ausreichende Stimme aufgenommen. Prüfen Sie das Mikrofon und nehmen Sie den Text erneut auf.', 'error');
    else if (signal.clipped) message(get('record-message'), 'Die Aufnahme übersteuert. Halten Sie mehr Abstand zum Mikrofon und nehmen Sie den Text erneut auf.', 'warning');
    else message(get('record-message'), automatic ? `Die Aufnahme wurde nach ${state.maxSeconds} Sekunden automatisch beendet. Hören Sie sie an und speichern Sie sie anschließend.` : 'Ihre Aufnahme ist bereit. Hören Sie sie an und speichern Sie sie anschließend.', 'success');
    if (samples.length) {
      const wav = encodeWav(samples, recorder.context.sampleRate);
      const url = URL.createObjectURL(new Blob([wav], {type:'audio/wav'}));
      state.recording = {wav, url, duration, referenceText:state.referenceText, valid:duration >= 3 && signal.hasInput && !signal.clipped};
      get('recording-audio').src = url;
      get('recording-preview').hidden = false;
      get('preview-duration').textContent = `${duration.toFixed(1).replace('.', ',')} Sek.`;
    }
    updateControls();
    if (restoreFocus) (state.recording ? get('recording-audio') : get('record-button')).focus();
  }

  async function saveRecording() {
    if (!state.recording?.valid || state.operation) return;
    state.operation = true;
    updateControls();
    const button = get('save-button');
    button.textContent = 'Wird gespeichert …';
    message(get('record-message'));
    try {
      const bytes = new Uint8Array(state.recording.wav);
      let binary = '';
      for (let offset = 0; offset < bytes.length; offset += 32768) binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
      await api('profiles', {method:'POST', body:JSON.stringify({name:get('profile-name').value.trim(), reference_text:state.recording.referenceText, language:'German', source:'desktop_microphone', consent:{own_voice:true, scope:'local_synthetic_voice_and_servicenow_demo', confirmed_at_utc:new Date().toISOString()}, wav_b64:btoa(binary)})});
      resetRecording();
      get('profile-name').value = '';
      get('voice-consent').checked = false;
      message(get('record-message'), 'Das Stimmprofil wurde gespeichert. Wählen Sie es jetzt für den nächsten ServiceNow-Anruf aus.', 'success');
      try { await loadProfiles(); } catch (error) { message(get('page-message'), `Das Stimmprofil wurde gespeichert. Die Liste konnte nicht aktualisiert werden: ${error.message}`, 'error'); }
    } catch (error) { message(get('record-message'), error.message, 'error'); }
    finally { state.operation = false; button.innerHTML = 'Stimmprofil speichern <span aria-hidden="true">→</span>'; updateControls(); }
  }

  get('login-form').addEventListener('submit', async event => {
    event.preventDefault();
    const button = get('login-button');
    button.disabled = true;
    button.textContent = 'Wird geöffnet …';
    message(get('page-message'));
    try {
      const result = await api('login', {method:'POST', body:JSON.stringify({password:get('access-code').value})});
      state.csrf = result.csrf || '';
      get('access-code').value = '';
      const session = await api('session');
      if (!session.authenticated) throw new Error('Die Anmeldung konnte nicht bestätigt werden. Bitte versuchen Sie es erneut.');
      showStudio(session);
      await loadProfiles();
      get('profile-name').focus();
    } catch (error) { message(get('page-message'), error.message, 'error'); }
    finally { button.disabled = false; button.innerHTML = 'Öffnen <span aria-hidden="true">→</span>'; }
  });
  get('logout-button').addEventListener('click', async () => {
    state.operation = true;
    updateControls();
    try { await api('logout', {method:'POST', body:'{}'}); showLogin(); message(get('page-message'), 'Sie sind abgemeldet.', 'info'); get('access-code').focus(); }
    catch (error) { message(get('page-message'), error.message, 'error'); }
    finally { state.operation = false; updateControls(); }
  });
  get('profile-name').addEventListener('input', updateControls);
  get('voice-consent').addEventListener('change', updateControls);
  get('record-button').addEventListener('click', startRecording);
  get('stop-button').addEventListener('click', () => void finishRecording());
  get('save-button').addEventListener('click', saveRecording);
  get('discard-button').addEventListener('click', () => { resetRecording(); message(get('record-message')); get('record-button').focus(); });
  get('refresh-button').addEventListener('click', async () => {
    state.operation = true; updateControls(); message(get('page-message'));
    try { await loadProfiles(); } catch (error) { message(get('page-message'), error.message, 'error'); }
    finally { state.operation = false; updateControls(); }
  });
  get('active-preview-button').addEventListener('click', async () => {
    if (state.operation || !state.selectedProfileId) return;
    state.operation = true;
    updateControls();
    message(get('page-message'));
    try {
      const response = await fetch(apiUrl('preview'), {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf}, body:'{}'});
      if (!response.ok) {
        let detail = {}; try { detail = await response.json(); } catch { /* Proxy errors need a friendly fallback. */ }
        if (response.status === 401) showLogin();
        throw new Error(detail.error || 'Die Stimmvorschau ist gerade nicht verfügbar. Bitte versuchen Sie es erneut.');
      }
      resetVoicePreview();
      state.previewUrl = URL.createObjectURL(await response.blob());
      const audio = get('active-preview-audio');
      audio.src = state.previewUrl;
      audio.hidden = false;
      pauseOtherAudio(audio);
      try { await audio.play(); } catch { message(get('page-message'), 'Die Vorschau ist bereit. Drücken Sie die Wiedergabetaste.', 'info'); }
    } catch (error) { message(get('page-message'), error instanceof TypeError ? 'Der Sprachdienst ist nicht erreichbar. Bitte prüfen Sie Ihre Verbindung und versuchen Sie es erneut.' : error.message || 'Die Stimmvorschau konnte nicht geladen werden.', 'error'); }
    finally { state.operation = false; updateControls(); }
  });
  for (const audio of document.querySelectorAll('audio')) audio.addEventListener('play', () => guardPlayback(audio));
  window.addEventListener('pagehide', () => {
    state.requestToken++;
    state.starting = false;
    if (state.recorder) {
      const recorder = state.recorder;
      state.recorder = null;
      void releaseAudio(recorder);
    }
    resetRecording();
    resetVoicePreview();
  });
  window.addEventListener('pageshow', event => { if (event.persisted) void bootstrap(); });
  async function bootstrap() {
    message(get('page-message'), 'Verbindung wird hergestellt …', 'info');
    try {
      const session = await api('session');
      if (session.authenticated) { showStudio(session); await loadProfiles(); }
      else showLogin();
      message(get('page-message'));
    } catch (error) { showLogin(); message(get('page-message'), error.message, 'error'); }
  }
  void bootstrap();
}
