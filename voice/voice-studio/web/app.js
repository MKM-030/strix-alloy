const TARGET_SAMPLE_RATE = 24000;
const DEFAULT_PREVIEW_TEXT = 'Herzlich willkommen bei Sopra Steria auf der Smart Country Convention. Gemeinsam mit ServiceNow machen wir digitale Services einfach. Ich helfe Ihnen gern, einen neuen Laptop für Ihren Mitarbeiter zu bestellen.';
const MAX_PREVIEW_CHARACTERS = 300;

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

export function inspectSignal(samples, inputSampleRate = TARGET_SAMPLE_RATE) {
  let sum = 0;
  let peak = 0;
  let clippedSamples = 0;
  let blockSum = 0;
  let blockLength = 0;
  let speechBlocks = 0;
  let blocks = 0;
  const length = Math.round(samples.length * TARGET_SAMPLE_RATE / inputSampleRate);
  const finishBlock = () => {
    if (!blockLength) return;
    if (Math.sqrt(blockSum / blockLength) >= 0.003) speechBlocks++;
    blocks++;
    blockSum = 0;
    blockLength = 0;
  };
  // Inspect the same 24 kHz PCM16 samples that encodeWav sends to the server.
  for (let index = 0; index < length; index++) {
    const position = index * inputSampleRate / TARGET_SAMPLE_RATE;
    const left = Math.floor(position);
    const fraction = position - left;
    const sample = (samples[left] || 0) * (1 - fraction) + (samples[Math.min(left + 1, samples.length - 1)] || 0) * fraction;
    const clamped = Math.max(-1, Math.min(1, sample));
    const pcm = Math.round(clamped * (clamped < 0 ? 32768 : 32767));
    const value = pcm / 32768;
    const absolute = Math.abs(value);
    sum += value * value;
    blockSum += value * value;
    blockLength++;
    peak = Math.max(peak, absolute);
    if (Math.abs(pcm) >= 32700) clippedSamples++;
    if (blockLength === TARGET_SAMPLE_RATE / 50) finishBlock();
  }
  finishBlock();
  const rms = length ? Math.sqrt(sum / length) : 0;
  const speechFraction = blocks ? speechBlocks / blocks : 0;
  return {rms, peak, speechFraction, clipped:length > 0 && clippedSamples / length > 0.005,
    hasInput:rms >= 0.004 && peak >= 0.02 && speechFraction >= 0.15};
}

export function deletionAvailability(profile, selectedProfileId) {
  if (!profile || profile.can_delete !== true || profile.id === 'synthetic-scc-demo') return 'hidden';
  return profile.id === selectedProfileId ? 'selected' : 'allowed';
}

const PERSONAL_CODE_PATTERN = /^VSP-[a-f0-9]{16}-[A-Za-z0-9_-]{24}$/;

export function personalLoginUrl(baseUrl, code) {
  if (typeof code !== 'string' || !PERSONAL_CODE_PATTERN.test(code)) throw new TypeError('Bitte einen persönlichen Zugangscode verwenden.');
  const url = new URL(baseUrl);
  url.search = '';
  url.hash = `access=${encodeURIComponent(code)}`;
  return url.href;
}

function takePersonalLoginFragment() {
  if (!window.location?.href || !/^#access(?:=|$)/.test(window.location.hash)) return '';
  const url = new URL(window.location.href);
  const fragment = url.hash;
  url.hash = '';
  // Remove the bearer token before parsing it or making the first API request.
  window.history.replaceState(window.history.state, '', url.pathname + url.search);
  const match = /^#access=([^&]*)$/.exec(fragment);
  if (!match) return '';
  try {
    const code = decodeURIComponent(match[1]);
    return PERSONAL_CODE_PATTERN.test(code) ? code : '';
  } catch { return ''; }
}

if (typeof document !== 'undefined') initializeStudio();

function initializeStudio() {
  let initialPersonalCode = takePersonalLoginFragment();
  const elements = Object.fromEntries([...document.querySelectorAll('[id]')].map(element => [element.id, element]));
  const get = id => elements[id];
  const apiBase = new URL('./api/', import.meta.url);
  const state = {csrf:'', authenticated:false, isAdmin:false, principalId:'', recordingAllowed:true, postfairMode:false, profiles:[], selectedProfileId:null, maxSeconds:25, referenceText:'', recorder:null, starting:false, recording:null, operation:false, requestToken:0, previewUrl:null, previewText:DEFAULT_PREVIEW_TEXT, previewRequest:null, previewToken:0, previewProfile:null, profilePreviewUrl:null, previewReturnFocus:null, pendingDeletion:null, deletionReturnFocus:null};
  const formatSeconds = seconds => `00:${String(Math.floor(seconds)).padStart(2, '0')}`;
  const apiUrl = path => new URL(path, apiBase).href;

  function message(element, text = '', kind = '') {
    element.textContent = text;
    element.classList.remove('is-error', 'is-warning', 'is-success', 'is-info');
    if (kind) element.classList.add(`is-${kind}`);
    element.hidden = !text;
  }

  async function api(path, options = {}, responseType = 'json') {
    const headers = new Headers(options.headers || {});
    if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
    if (options.method && options.method !== 'GET' && state.csrf) headers.set('X-CSRF-Token', state.csrf);
    let response;
    try { response = await fetch(apiUrl(path), {...options, headers, credentials:'same-origin', cache:'no-store'}); }
    catch { throw new Error('Der Sprachdienst ist nicht erreichbar. Prüfen Sie Ihre Verbindung und versuchen Sie es erneut.'); }
    if (!response.ok) {
      let detail = {};
      try { detail = await response.json(); } catch { /* A proxy error can return HTML. */ }
      if (response.status === 401 && path !== 'login' && responseType !== 'blob') showLogin();
      const error = new Error(detail.error || (response.status === 401 ? 'Der Zugangscode ist ungültig oder die Sitzung ist abgelaufen.' : 'Die Anfrage konnte nicht abgeschlossen werden. Bitte versuchen Sie es erneut.'));
      error.status = response.status;
      error.code = detail.code;
      throw error;
    }
    if (response.status === 204) return {};
    return responseType === 'blob' ? response.blob() : response.json();
  }

  function updateControls() {
    const capturing = Boolean(state.recorder || state.starting);
    const previewing = Boolean(state.previewRequest || state.previewProfile);
    const busy = state.operation || previewing;
    const ready = get('profile-name').value.trim().length > 0 && get('voice-consent').checked && (!state.postfairMode || get('retention-consent').checked);
    get('record-button').disabled = !state.authenticated || !state.recordingAllowed || !state.referenceText || !ready || capturing || busy;
    get('record-button').hidden = capturing;
    get('stop-button').hidden = !state.recorder || state.starting || state.recorder.stopping;
    get('stop-button').disabled = Boolean(state.recorder?.stopping);
    get('profile-name').disabled = capturing || busy;
    get('voice-consent').disabled = capturing || busy;
    get('retention-consent').disabled = capturing || busy;
    get('save-button').disabled = !state.recordingAllowed || !state.recording?.valid || !ready || capturing || busy;
    get('discard-button').disabled = capturing || busy;
    get('refresh-button').disabled = busy;
    get('logout-button').disabled = state.operation;
    get('admin-menu-button').disabled = state.operation;
    get('admin-close-button').disabled = state.operation;
    get('active-preview-button').disabled = !state.selectedProfileId || busy || capturing;
    get('create-code-button').disabled = !state.isAdmin || busy || capturing;
    get('personal-code-label').disabled = busy || capturing;
    get('copy-code-button').disabled = busy || capturing;
    get('copy-link-button').disabled = busy || capturing;
    get('dismiss-code-button').disabled = busy || capturing;
    get('preview-read-button').disabled = !state.authenticated || !state.previewProfile || state.operation || Boolean(state.previewRequest) || capturing;
    get('preview-text').disabled = state.operation || Boolean(state.previewRequest) || capturing;
    get('delete-confirm-button').disabled = state.operation;
    get('delete-cancel-button').disabled = state.operation;
    get('delete-access-code').disabled = state.operation;
    for (const button of document.querySelectorAll('[data-profile-action]')) button.disabled = busy || capturing || button.dataset.selected === 'true' || button.dataset.expired === 'true';
    for (const audio of document.querySelectorAll('audio')) {
      if (capturing) {
        if (!audio.hidden) { audio.dataset.restoreAfterCapture = 'true'; audio.hidden = true; }
        audio.pause();
      } else if (audio.dataset.restoreAfterCapture) {
        audio.hidden = false;
        delete audio.dataset.restoreAfterCapture;
      }
    }
    get('record-help').textContent = !state.recordingAllowed ? 'Die Aufnahmezeit der Messe-Demo ist beendet.' : state.starting ? 'Mikrofonzugriff wird angefragt …' : state.recorder ? 'Lesen Sie den Text vollständig vor.' : ready ? `Ihr Browser fragt beim Start nach Mikrofonzugriff. Maximal ${state.maxSeconds} Sekunden.` : 'Name eingeben und Zustimmung bestätigen.';
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

  function resetProfilePreview() {
    const audio = get('preview-audio');
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    audio.hidden = true;
    delete audio.dataset.restoreAfterCapture;
    if (state.profilePreviewUrl) URL.revokeObjectURL(state.profilePreviewUrl);
    state.profilePreviewUrl = null;
  }

  function restorePreviewFocus() {
    const target = state.previewReturnFocus;
    if (!state.authenticated) { state.previewReturnFocus = null; return; }
    if (!get('preview-dialog').open && !state.previewRequest && !state.operation) {
      state.previewReturnFocus = null;
      if (target?.isConnected && !target.disabled) target.focus();
    }
  }

  function clearPreviewDialog() {
    state.previewToken++;
    state.previewProfile = null;
    resetProfilePreview();
    get('preview-text').value = '';
    get('preview-profile-name').textContent = '';
    message(get('preview-message'));
    updateControls();
  }

  function closePreviewDialog() {
    clearPreviewDialog();
    if (get('preview-dialog').open) get('preview-dialog').close();
    restorePreviewFocus();
  }

  function openPreviewDialog(profile, returnFocus) {
    if (!state.authenticated || state.operation || state.previewRequest || state.recorder || state.starting) return;
    closePreviewDialog();
    pauseOtherAudio();
    state.previewProfile = {id:profile.id, name:profile.name};
    state.previewReturnFocus = returnFocus;
    get('preview-profile-name').textContent = profile.name || 'Stimmprofil';
    get('preview-audio').setAttribute('aria-label', `Beispieltext mit der Stimme: ${profile.name || 'Stimmprofil'}`);
    get('preview-text').value = state.previewText;
    get('preview-dialog').showModal();
    updateControls();
    get('preview-text').focus();
  }

  function currentPreview(request) {
    return state.previewRequest === request && request.token === state.previewToken && request.sessionToken === state.requestToken && state.authenticated &&
      (request.dialog ? get('preview-dialog').open && state.previewProfile?.id === request.profileId : state.selectedProfileId === request.profileId);
  }

  async function generatePreview(profileId, text, dialog = false) {
    if (!state.authenticated || state.operation || state.previewRequest || state.recorder || state.starting || (dialog && !state.previewProfile)) return;
    text = text.trim();
    const status = dialog ? get('preview-message') : get('page-message');
    const length = [...text].length;
    if (length < 3 || length > MAX_PREVIEW_CHARACTERS) {
      message(status, `Bitte geben Sie einen Beispieltext mit 3 bis ${MAX_PREVIEW_CHARACTERS} Zeichen ein.`, 'error');
      if (dialog) get('preview-text').focus();
      return;
    }
    const request = {profileId, dialog, token:++state.previewToken, sessionToken:state.requestToken};
    state.previewRequest = request;
    pauseOtherAudio();
    if (dialog) resetProfilePreview(); else resetVoicePreview();
    message(status, 'Die Stimmvorschau wird erstellt …', 'info');
    updateControls();
    try {
      // Let shared synthesis finish even if the dialog closes; only current results reach the UI.
      const blob = await api(`profiles/${encodeURIComponent(profileId)}/preview`, {method:'POST', body:JSON.stringify({text})}, 'blob');
      if (!currentPreview(request)) return;
      const url = URL.createObjectURL(blob);
      if (dialog) state.profilePreviewUrl = url; else state.previewUrl = url;
      const audio = get(dialog ? 'preview-audio' : 'active-preview-audio');
      audio.src = url;
      audio.hidden = false;
      message(status);
      pauseOtherAudio(audio);
      try { await audio.play(); }
      catch { if (currentPreview(request)) message(status, 'Die Vorschau ist bereit. Drücken Sie die Wiedergabetaste.', 'info'); }
    } catch (error) {
      if (currentPreview(request)) {
        if (error.status === 401) {
          showLogin();
          message(get('page-message'), error.message, 'error');
        } else message(status, error instanceof TypeError ? 'Der Sprachdienst ist nicht erreichbar. Prüfen Sie Ihre Verbindung und versuchen Sie es erneut.' : error.message || 'Die Stimmvorschau konnte nicht geladen werden.', 'error');
      }
    } finally {
      if (state.previewRequest === request) {
        state.previewRequest = null;
        updateControls();
        restorePreviewFocus();
      }
    }
  }

  function showLogin() {
    state.authenticated = false;
    state.isAdmin = false;
    state.principalId = '';
    state.csrf = '';
    state.requestToken++;
    state.previewRequest = null;
    state.previewReturnFocus = null;
    closePreviewDialog();
    if (state.recorder) void finishRecording(true);
    state.starting = false;
    resetRecording();
    resetVoicePreview();
    for (const audio of document.querySelectorAll('.profile-audio')) { audio.pause(); audio.removeAttribute('src'); }
    get('profile-list').replaceChildren();
    state.profiles = [];
    state.selectedProfileId = null;
    closeAdminPanel();
    closeDeletionDialog();
    get('admin-menu-button').hidden = true;
    get('existing-access-codes').open = false;
    get('personal-access-list').replaceChildren();
    get('personal-code-label').value = '';
    message(get('admin-message'));
    get('session-label').hidden = true;
    get('retention-consent').checked = false;
    get('voice-consent').checked = false;
    state.postfairMode = false;
    get('studio-view').hidden = true;
    get('login-view').hidden = false;
    get('logout-button').hidden = true;
    get('login-button').disabled = false;
    updateControls();
  }

  function showStudio(session) {
    state.authenticated = true;
    state.isAdmin = session.is_admin === true;
    state.principalId = session.principal_id || '';
    state.recordingAllowed = session.recording_allowed !== false;
    state.postfairMode = session.postfair_mode === true;
    get('retention-consent-label').hidden = !state.postfairMode;
    get('retention-consent').checked = false;
    get('retention-notice').textContent = state.postfairMode ? 'Die Messeaufnahmen wurden gelöscht. Neue Aufnahmen bleiben gespeichert, bis Sie oder ein Administrator sie löschen.' : 'Die Aufnahmen der Messe-Demo werden nach der Messe automatisch gelöscht. Sie können Ihre Stimme jederzeit löschen.';
    message(get('retention-message'), state.recordingAllowed ? '' : 'Die Aufnahmezeit für diese Messe-Demo ist beendet. Sie können vorhandene Profile weiterhin anhören und löschen sowie die Standardstimme auswählen.', 'info');
    closeAdminPanel();
    get('admin-menu-button').hidden = !state.isAdmin;
    if (!state.isAdmin) get('personal-access-list').replaceChildren();
    get('session-label').textContent = state.isAdmin ? 'Administrator' : session.label || 'Persönlicher Zugang';
    get('session-label').hidden = state.isAdmin;
    state.csrf = session.csrf || state.csrf;
    state.referenceText = session.reference_text || state.referenceText;
    const previewText = typeof session.preview_text === 'string' ? session.preview_text.trim() : '';
    state.previewText = [...previewText].length >= 3 && [...previewText].length <= MAX_PREVIEW_CHARACTERS ? previewText : DEFAULT_PREVIEW_TEXT;
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
      const ownershipText = profile.id === 'synthetic-scc-demo' ? 'Standardstimme' : profile.owner_is_self === true ? 'Ihr Profil' : profile.owner_is_self === false ? 'Geteiltes Profil' : '';
      group.append(create('p', 'profile-meta', [Number.isFinite(duration) && duration > 0 ? `${duration.toFixed(1).replace('.', ',')} Sek.` : '', dateText, ownershipText].filter(Boolean).join(' · ')));
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
      const preview = create('button', 'button button-secondary', 'Beispieltext anhören');
      preview.type = 'button';
      preview.dataset.profileAction = 'preview';
      preview.addEventListener('click', () => openPreviewDialog(profile, preview));
      const select = create('button', selected ? 'button button-secondary' : 'button button-primary', selected ? 'Für nächsten Anruf ausgewählt' : 'Für nächste ServiceNow-Anfrage verwenden');
      select.type = 'button';
      select.dataset.profileAction = 'select';
      select.dataset.selected = String(selected);
      select.dataset.expired = String(profile.can_activate === false || (!state.recordingAllowed && profile.id !== 'synthetic-scc-demo'));
      if (select.dataset.expired === 'true') select.setAttribute('title', 'Dieses Messeprofil ist abgelaufen. Bitte nehmen Sie Ihre Stimme mit neuer Zustimmung auf.');
      select.disabled = selected;
      select.addEventListener('click', () => activateProfile(profile));
      actions.append(listen, preview, select);
      item.append(top, actions, audio);
      const deletion = deletionAvailability(profile, state.selectedProfileId);
      if (deletion !== 'hidden') {
        const remove = create('button', 'icon-button profile-delete');
        remove.type = 'button';
        remove.innerHTML = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7M14 10v7"/></svg>';
        remove.dataset.profileAction = 'delete';
        remove.dataset.selected = String(deletion === 'selected');
        remove.setAttribute('aria-label', `Stimmprofil „${profile.name}“ löschen`);
        remove.setAttribute('title', deletion === 'selected' ? 'Zuerst eine andere Stimme auswählen' : `„${profile.name}“ dauerhaft löschen`);
        remove.addEventListener('click', () => openDeletionDialog(profile, remove));
        top.append(remove);
        if (deletion === 'selected') {
          const help = create('p', 'deletion-help', 'Zuerst eine andere Stimme auswählen.');
          const helpId = `delete-help-${list.children.length}`;
          help.id = helpId;
          remove.setAttribute('aria-describedby', helpId);
          item.append(help);
        }
      }
      list.append(item);
    }
    updateControls();
  }

  async function loadProfiles() {
    const data = await api('profiles');
    renderProfiles(data);
  }

  async function activateProfile(profile) {
    if (!state.authenticated || state.operation || state.previewRequest || state.previewProfile || state.recorder || state.starting) return;
    if (profile.can_activate === false || (!state.recordingAllowed && profile.id !== 'synthetic-scc-demo')) {
      message(get('page-message'), 'Dieses Messeprofil ist abgelaufen. Bitte nehmen Sie Ihre Stimme mit neuer Zustimmung auf.', 'error');
      return;
    }
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

  function clearCodeDisplay() {
    get('generated-access-code').value = '';
    get('generated-login-link').value = '';
    get('generated-code-label').textContent = '';
    get('generated-qr').removeAttribute('src');
    get('generated-qr').removeAttribute('alt');
    get('generated-qr').hidden = true;
    get('generated-code-panel').hidden = true;
    message(get('code-copy-message'));
  }

  function closeAdminPanel(restoreFocus = false) {
    get('admin-panel').hidden = true;
    get('admin-menu-button').setAttribute('aria-expanded', 'false');
    clearCodeDisplay();
    get('existing-access-codes').open = false;
    message(get('admin-message'));
    if (restoreFocus && state.authenticated && state.isAdmin) get('admin-menu-button').focus();
  }

  function toggleAdminPanel() {
    if (!state.authenticated || !state.isAdmin || state.operation) return;
    if (!get('admin-panel').hidden) { closeAdminPanel(true); return; }
    get('admin-panel').hidden = false;
    get('admin-menu-button').setAttribute('aria-expanded', 'true');
    get('personal-code-label').focus();
  }

  async function loadAccessCodes() {
    if (!state.isAdmin) return;
    const token = state.requestToken;
    try {
      const result = await api('access-codes');
      if (token !== state.requestToken || !state.authenticated || !state.isAdmin) return;
      const entries = Array.isArray(result.access_codes) ? result.access_codes : [];
      const list = get('personal-access-list');
      list.replaceChildren();
      get('existing-access-summary').textContent = `Bereits angelegte Zugänge (${entries.length})`;
      for (const entry of entries) {
        const date = new Date(entry.created_at_utc);
        const dateText = Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('de-DE', {day:'2-digit', month:'2-digit', year:'numeric'}).format(date);
        list.append(create('li', '', [entry.label || 'Persönlicher Zugang', dateText].filter(Boolean).join(' · ')));
      }
      if (!entries.length) list.append(create('li', '', 'Noch keine persönlichen Zugänge angelegt.'));
    } catch (error) {
      if (token === state.requestToken && state.isAdmin) message(get('admin-message'), `Die vorhandenen Zugänge konnten nicht geladen werden: ${error.message}`, 'error');
    }
  }

  function closeDeletionDialog() {
    get('delete-access-code').value = '';
    state.pendingDeletion = null;
    message(get('delete-message'));
    if (get('delete-dialog').open) get('delete-dialog').close();
  }

  function openDeletionDialog(profile, returnFocus) {
    if (!state.authenticated || state.operation || state.previewRequest || state.previewProfile || state.recorder || state.starting || deletionAvailability(profile, state.selectedProfileId) !== 'allowed') return;
    pauseOtherAudio();
    state.pendingDeletion = {id:profile.id, name:profile.name};
    state.deletionReturnFocus = returnFocus;
    get('delete-profile-name').textContent = profile.name;
    get('delete-access-code').value = '';
    get('delete-confirm-button').textContent = 'Dauerhaft löschen';
    message(get('delete-message'));
    get('delete-dialog').showModal();
    get('delete-access-code').focus();
  }

  async function deleteProfile(event) {
    event.preventDefault();
    if (state.operation || !state.pendingDeletion) return;
    const profile = {...state.pendingDeletion};
    const input = get('delete-access-code');
    const password = input.value;
    input.value = '';
    if (!password.trim()) {
      message(get('delete-message'), 'Bitte geben Sie Ihren Zugangscode ein.', 'error');
      input.focus();
      return;
    }
    state.operation = true;
    get('delete-confirm-button').textContent = 'Wird gelöscht …';
    message(get('delete-message'));
    updateControls();
    let deleted = false;
    let returnToList = false;
    try {
      await api(`profiles/${encodeURIComponent(profile.id)}`, {method:'DELETE', body:JSON.stringify({password})});
      deleted = true;
      closeDeletionDialog();
      renderProfiles({profiles:state.profiles.filter(candidate => candidate.id !== profile.id), selected_profile_id:state.selectedProfileId});
      try {
        await loadProfiles();
        message(get('page-message'), `„${profile.name}“ wurde dauerhaft gelöscht.`, 'success');
      } catch (error) {
        message(get('page-message'), `„${profile.name}“ wurde dauerhaft gelöscht. Die Liste konnte nicht aktualisiert werden: ${error.message}`, 'error');
      }
    } catch (error) {
      if (['delete_purge_failed', 'delete_finalize_failed'].includes(error.code) && state.authenticated) {
        returnToList = true;
        closeDeletionDialog();
        renderProfiles({profiles:state.profiles.filter(candidate => candidate.id !== profile.id), selected_profile_id:state.selectedProfileId});
        let detail = error.message;
        try { await loadProfiles(); }
        catch (refreshError) { detail += ` Die Liste konnte nicht aktualisiert werden: ${refreshError.message}`; }
        message(get('page-message'), detail, 'error');
      } else message(state.authenticated ? get('delete-message') : get('page-message'), error.message, 'error');
    } finally {
      state.operation = false;
      get('delete-confirm-button').textContent = 'Dauerhaft löschen';
      input.value = '';
      updateControls();
      if ((deleted || returnToList) && state.authenticated) get('refresh-button').focus();
      else if (get('delete-dialog').open) input.focus();
    }
  }

  async function createPersonalCode(event) {
    event.preventDefault();
    if (!state.authenticated || !state.isAdmin || get('admin-panel').hidden || state.operation || state.recorder || state.starting) return;
    const label = get('personal-code-label').value.trim();
    if (!label) { message(get('admin-message'), 'Bitte geben Sie eine Bezeichnung für den persönlichen Zugang ein.', 'error'); get('personal-code-label').focus(); return; }
    clearCodeDisplay();
    state.operation = true;
    const token = state.requestToken;
    get('create-code-button').textContent = 'Wird erstellt …';
    message(get('admin-message'));
    updateControls();
    try {
      const result = await api('access-codes', {method:'POST', body:JSON.stringify({label})});
      if (token !== state.requestToken || !state.authenticated || !state.isAdmin) return;
      if (typeof result.code !== 'string' || !result.code) throw new Error('Der Zugang wurde erstellt, aber sein Code konnte nicht angezeigt werden. Bitte erstellen Sie einen neuen Zugang.');
      get('generated-code-label').textContent = result.access_code?.label || label;
      get('generated-access-code').value = result.code;
      const link = personalLoginUrl(new URL('../', apiBase).href, result.code);
      get('generated-login-link').value = link;
      try {
        get('generated-qr').src = globalThis.VoiceStudioQr.toSvgDataUrl(link);
        get('generated-qr').setAttribute('alt', `QR-Code zur Anmeldung für ${result.access_code?.label || label}`);
        get('generated-qr').hidden = false;
      } catch { message(get('code-copy-message'), 'Der QR-Code konnte nicht angezeigt werden. Kopieren Sie den Anmeldelink oder Zugangscode.', 'info'); }
      get('generated-code-panel').hidden = false;
      get('personal-code-label').value = '';
      message(get('admin-message'), 'Der persönliche Zugang wurde erstellt.', 'success');
      await loadAccessCodes();
      get('generated-access-code').focus();
    } catch (error) { message(state.authenticated ? get('admin-message') : get('page-message'), error.message, 'error'); }
    finally { state.operation = false; get('create-code-button').textContent = 'Zugang mit QR-Code erstellen'; updateControls(); }
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
    if (!get('voice-consent').checked || (state.postfairMode && !get('retention-consent').checked)) return;
    if (!state.recordingAllowed || state.recorder || state.starting || state.operation || state.previewRequest || state.previewProfile) return;
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
          const signal = inspectSignal(samples, recorder.context.sampleRate);
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
    const signal = inspectSignal(samples, recorder.context.sampleRate);
    get('record-time').textContent = `${formatSeconds(duration)} / ${formatSeconds(state.maxSeconds)}`;
    get('record-state').textContent = 'Aufnahme beendet';
    if (duration < 3) message(get('record-message'), 'Die Aufnahme ist zu kurz. Lesen Sie den Text vollständig vor; mindestens 3 Sekunden sind erforderlich.', 'error');
    else if (!signal.hasInput) message(get('record-message'), 'Die Aufnahme ist zu leise oder enthält zu wenig Sprache. Sprechen Sie näher am Mikrofon und lesen Sie den Text vollständig vor. Nehmen Sie danach erneut auf.', 'error');
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
    if (!get('voice-consent').checked || (state.postfairMode && !get('retention-consent').checked)) return;
    if (!state.recordingAllowed || !state.recording?.valid || state.operation || state.previewRequest || state.previewProfile) return;
    state.operation = true;
    updateControls();
    const button = get('save-button');
    button.textContent = 'Wird gespeichert …';
    message(get('record-message'));
    try {
      const bytes = new Uint8Array(state.recording.wav);
      let binary = '';
      for (let offset = 0; offset < bytes.length; offset += 32768) binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
      await api('profiles', {method:'POST', body:JSON.stringify({name:get('profile-name').value.trim(), reference_text:state.recording.referenceText, language:'German', source:'desktop_microphone', consent:{own_voice:true, scope:'local_synthetic_voice_and_servicenow_demo', confirmed_at_utc:new Date().toISOString(), ...(state.postfairMode ? {retention:'until_deleted', retention_notice:'Neue Aufnahmen bleiben gespeichert, bis Sie oder ein Administrator sie löschen.'} : {})}, wav_b64:btoa(binary)})});
      resetRecording();
      get('profile-name').value = '';
      get('voice-consent').checked = false;
      get('retention-consent').checked = false;
      message(get('record-message'), 'Das Stimmprofil wurde gespeichert. Wählen Sie es jetzt für den nächsten ServiceNow-Anruf aus.', 'success');
      try { await loadProfiles(); } catch (error) { message(get('page-message'), `Das Stimmprofil wurde gespeichert. Die Liste konnte nicht aktualisiert werden: ${error.message}`, 'error'); }
    } catch (error) { message(get('record-message'), error.message, 'error'); }
    finally { state.operation = false; button.innerHTML = 'Stimmprofil speichern <span aria-hidden="true">→</span>'; updateControls(); }
  }

  async function signIn(password) {
    const button = get('login-button');
    button.disabled = true;
    button.textContent = 'Wird geöffnet …';
    message(get('page-message'));
    get('access-code').value = '';
    try {
      const result = await api('login', {method:'POST', body:JSON.stringify({password})});
      state.csrf = result.csrf || '';
      get('access-code').value = '';
      const session = await api('session');
      if (!session.authenticated) throw new Error('Die Anmeldung konnte nicht bestätigt werden. Bitte versuchen Sie es erneut.');
      showStudio(session);
      await loadProfiles();
      await loadAccessCodes();
      get('profile-name').focus();
    } catch (error) {
      if (!state.authenticated) showLogin();
      message(get('page-message'), error.message, 'error');
      (state.authenticated ? get('refresh-button') : get('access-code')).focus();
    }
    finally { button.disabled = false; button.innerHTML = 'Öffnen <span aria-hidden="true">→</span>'; }
  }
  get('login-form').addEventListener('submit', async event => {
    event.preventDefault();
    await signIn(get('access-code').value);
  });
  get('logout-button').addEventListener('click', async () => {
    state.operation = true;
    updateControls();
    try { await api('logout', {method:'POST', body:'{}'}); showLogin(); message(get('page-message'), 'Sie sind abgemeldet.', 'info'); get('access-code').focus(); }
    catch (error) { message(get('page-message'), error.message, 'error'); }
    finally { state.operation = false; updateControls(); }
  });
  get('profile-name').addEventListener('input', updateControls);
  get('preview-form').addEventListener('submit', event => {
    event.preventDefault();
    return state.previewProfile ? generatePreview(state.previewProfile.id, get('preview-text').value, true) : undefined;
  });
  get('preview-close-button').addEventListener('click', closePreviewDialog);
  get('preview-dialog').addEventListener('cancel', event => { event.preventDefault(); closePreviewDialog(); });
  get('preview-dialog').addEventListener('close', () => {
    if (get('preview-dialog').open) return;
    clearPreviewDialog();
    restorePreviewFocus();
  });
  get('preview-audio').addEventListener('error', () => {
    if (get('preview-dialog').open && state.profilePreviewUrl) message(get('preview-message'), 'Die Stimmvorschau konnte nicht abgespielt werden. Bitte versuchen Sie es erneut.', 'error');
  });
  get('delete-form').addEventListener('submit', deleteProfile);
  get('delete-cancel-button').addEventListener('click', closeDeletionDialog);
  get('delete-dialog').addEventListener('cancel', event => {
    if (state.operation) event.preventDefault();
  });
  get('delete-dialog').addEventListener('close', () => {
    get('delete-access-code').value = '';
    state.pendingDeletion = null;
    message(get('delete-message'));
    const target = state.deletionReturnFocus;
    state.deletionReturnFocus = null;
    if (state.authenticated && !state.operation && target?.isConnected && !target.disabled) target.focus();
  });
  get('create-code-form').addEventListener('submit', createPersonalCode);
  get('admin-menu-button').addEventListener('click', toggleAdminPanel);
  get('admin-close-button').addEventListener('click', () => { if (!state.operation) closeAdminPanel(true); });
  get('admin-panel').addEventListener('keydown', event => {
    if (event.key === 'Escape' && !state.operation && !get('admin-panel').hidden) {
      event.preventDefault();
      closeAdminPanel(true);
    }
  });
  get('dismiss-code-button').addEventListener('click', () => { clearCodeDisplay(); get('personal-code-label').focus(); });
  get('copy-code-button').addEventListener('click', async () => {
    const input = get('generated-access-code');
    if (!input.value || state.operation || state.recorder || state.starting) return;
    try { await navigator.clipboard.writeText(input.value); message(get('code-copy-message'), 'Code kopiert. Bewahren Sie ihn sicher auf.', 'success'); }
    catch { input.focus(); input.select(); message(get('code-copy-message'), 'Bitte kopieren Sie den markierten Code.', 'info'); }
  });
  get('copy-link-button').addEventListener('click', async () => {
    const input = get('generated-login-link');
    if (!input.value || state.operation || state.recorder || state.starting) return;
    try { await navigator.clipboard.writeText(input.value); message(get('code-copy-message'), 'Anmeldelink kopiert. Nur an die benannte Person weitergeben.', 'success'); }
    catch { input.focus(); input.select(); message(get('code-copy-message'), 'Bitte kopieren Sie den markierten Anmeldelink.', 'info'); }
  });
  get('voice-consent').addEventListener('change', updateControls);
  get('retention-consent').addEventListener('change', updateControls);
  get('record-button').addEventListener('click', startRecording);
  get('stop-button').addEventListener('click', () => void finishRecording());
  get('save-button').addEventListener('click', saveRecording);
  get('discard-button').addEventListener('click', () => { resetRecording(); message(get('record-message')); get('record-button').focus(); });
  get('refresh-button').addEventListener('click', async () => {
    state.operation = true; updateControls(); message(get('page-message'));
    try { await loadProfiles(); } catch (error) { message(get('page-message'), error.message, 'error'); }
    finally { state.operation = false; updateControls(); }
  });
  get('active-preview-button').addEventListener('click', () => state.selectedProfileId && !state.previewProfile ? generatePreview(state.selectedProfileId, state.previewText) : undefined);
  for (const audio of document.querySelectorAll('audio')) audio.addEventListener('play', () => guardPlayback(audio));
  window.addEventListener('pagehide', () => {
    state.requestToken++;
    state.previewRequest = null;
    state.previewReturnFocus = null;
    closePreviewDialog();
    state.starting = false;
    closeAdminPanel();
    closeDeletionDialog();
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
    if (initialPersonalCode) {
      const code = initialPersonalCode;
      initialPersonalCode = '';
      await signIn(code);
      return;
    }
    message(get('page-message'), 'Verbindung wird hergestellt …', 'info');
    try {
      const session = await api('session');
      if (session.authenticated) { showStudio(session); await loadProfiles(); await loadAccessCodes(); }
      else showLogin();
      message(get('page-message'));
    } catch (error) { showLogin(); message(get('page-message'), error.message, 'error'); }
  }
  void bootstrap();
}
