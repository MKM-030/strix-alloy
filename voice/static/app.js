'use strict';
const $ = id => document.getElementById(id);
let csrf = '', cursor = 0, enabled = false, state = {}, recording = null, audioBusy = false;
let playbackUrl = '', stopped = false, speakQueue = Promise.resolve();
let generation = 0, resetting = false;
const pendingFetches = new Set();
async function scopedFetch(url, options = {}, epoch = generation) {
  if (epoch !== generation) throw new DOMException('Stale conversation', 'AbortError');
  const controller = new AbortController(); pendingFetches.add(controller);
  try {
    const response = await fetch(url, {...options, signal: controller.signal});
    if (epoch !== generation) throw new DOMException('Stale conversation', 'AbortError');
    return response;
  } finally { pendingFetches.delete(controller); }
}
function invalidateConversation() {
  if (recording) { const r = recording; recording = null; clearTimeout(r.timer); r.node.disconnect(); r.source.disconnect(); r.stream.getTracks().forEach(t => t.stop()); r.context.close(); $('record').textContent = 'Aufnahme starten'; }
  generation++; pendingFetches.forEach(c => c.abort()); pendingFetches.clear();
  $('player').pause(); $('player').removeAttribute('src'); $('player').load();
  if (playbackUrl) { URL.revokeObjectURL(playbackUrl); playbackUrl = ''; }
  speakQueue = Promise.resolve(); audioBusy = false;
}
function status(text, error = false) { $('status').textContent = text; $('status').className = error ? 'error' : ''; }
function controls() {
  const ready = !resetting && enabled && state.started && !state.busy && !state.ended && !state.failed;
  $('start').disabled = !enabled || state.started || resetting;
  $('send').disabled = !ready || !!recording;
  $('record').disabled = audioBusy;
  $('audioTest').disabled = audioBusy || !!recording;
  $('roundtrip').disabled = audioBusy || !!recording;
  $('reset').disabled = !enabled || resetting;
  document.querySelectorAll('#choices button').forEach(b => b.disabled = !ready);
}
async function api(path, data, form = false, epoch = generation) {
  const options = { method: 'POST', headers: {'X-CSRF-Token': csrf} };
  if (form) options.body = data;
  else { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(data); }
  const response = await scopedFetch(path, options, epoch);
  if (!response.ok) throw new Error((await response.text()).slice(0, 220));
  return response;
}
function bubble(text, kind, eventId) {
  const row = document.createElement('div'); row.className = 'bubble ' + kind;
  const label = document.createElement('span'); label.className = 'speaker';
  label.textContent = kind === 'user' ? 'Du' : kind === 'bot' ? 'ServiceNow' : 'Hinweis';
  row.append(label, document.createTextNode(text));
  if (eventId && kind === 'bot') {
    const replay = document.createElement('button'); replay.className = 'replay secondary'; replay.textContent = 'Vorlesen';
    replay.onclick = () => enqueueSpeech(eventId); row.append(document.createElement('br'), replay);
  }
  $('chat').append(row); $('chat').scrollTop = $('chat').scrollHeight;
}
async function play(blob) {
  if (playbackUrl) URL.revokeObjectURL(playbackUrl);
  playbackUrl = URL.createObjectURL(blob); $('player').src = playbackUrl;
  await $('player').play().catch(() => { status('Audio ist bereit. Zum Abspielen den Player starten.'); });
}
function enqueueSpeech(id) {
  const epoch = generation;
  speakQueue = speakQueue.then(async () => {
    if (epoch !== generation) return;
    audioBusy = true; controls();
    try { const response = await api('/api/speak', {eventId:id}, false, epoch);
      const blob = await response.blob(); if (epoch !== generation) return; await play(blob);
      if (!$('player').paused) await new Promise(resolve => {
        $('player').addEventListener('ended', resolve, {once:true});
        $('player').addEventListener('error', resolve, {once:true});
        $('player').addEventListener('pause', resolve, {once:true});
      });
    } catch(e) { if (epoch === generation && e.name !== 'AbortError') status('Vorlesen nicht verfügbar: ' + e.message, true); }
    finally { if (epoch === generation) { audioBusy = false; controls(); } }
  });
}
async function poll() {
  while (!stopped) {
    if (resetting) { await new Promise(resolve => setTimeout(resolve, 50)); continue; }
    const epoch = generation;
    try {
      const response = await scopedFetch('/api/events?after=' + cursor + '&wait=20', {}, epoch);
      if (!response.ok) throw new Error('Lokale Sitzung abgelaufen. Bitte Seite neu laden.');
      const result = await response.json(); if (epoch !== generation) continue;
      state = result; cursor = state.cursor;
      for (const event of state.events) { bubble(event.text, event.kind, event.id);
        if (event.kind === 'bot' && $('autoSpeak').checked) enqueueSpeech(event.id); }
      $('choices').replaceChildren();
      for (const choice of state.choices) {
        const button = document.createElement('button'); button.className = 'secondary'; button.textContent = choice.label || choice.value;
        button.onclick = () => send({choice:choice.value}, choice.label); $('choices').append(button);
      }
      $('inputLabel').textContent = state.inputLabel;
      if (!enabled) status('Audio ist lokal verfügbar. Die ServiceNow-Verbindung ist noch nicht eingerichtet.');
      else if (state.failed) status('Der Dialog benötigt einen Neustart. Die letzte Antwort bleibt sichtbar.', true);
      else if (state.ended) status('Dialog beendet. Du kannst einen neuen Dialog starten.');
      else if (state.busy) status('ServiceNow verarbeitet die Anfrage …');
      else status(state.started ? 'Bereit für deine Antwort.' : 'Bereit. Starte einen Dialog.');
      controls();
    } catch(e) { if (epoch !== generation || e.name === 'AbortError') continue;
      status(e.message, true); stopped = true; controls(); }
  }
}
async function send(data, label) {
  const epoch = generation;
  state.busy = true; controls();
  try { await api('/api/message', data, false, epoch); if (epoch !== generation) return; bubble(label || data.text, 'user'); $('transcript').value = ''; }
  catch(e) { if (epoch !== generation || e.name === 'AbortError') return; status(e.message, true); state.busy = false; controls(); }
}
$('send').onclick = () => send({text:$('transcript').value});
$('start').onclick = async () => { const epoch = generation; $('start').disabled = true;
  try { await api('/api/start', {}, false, epoch); if (epoch !== generation) return; state.started = true; state.busy = true; controls(); }
  catch(e) { if (epoch !== generation || e.name === 'AbortError') return; status(e.message, true); controls(); }
};
$('reset').onclick = async () => {
  if (resetting) return;
  resetting = true; invalidateConversation();
  try { const response = await api('/api/reset', {}); const session = await response.json();
    csrf = session.csrf; cursor = 0; state = {}; $('chat').replaceChildren(); $('choices').replaceChildren();
    if (stopped) { stopped = false; poll(); }
  } catch(e) { state.failed = true; status(e.message, true); }
  finally { resetting = false; controls(); }
};
function wav(samples, rate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buffer);
  const str = (at, value) => [...value].forEach((c,i) => view.setUint8(at+i,c.charCodeAt(0)));
  str(0,'RIFF'); view.setUint32(4,36+samples.length*2,true); str(8,'WAVE'); str(12,'fmt ');
  view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true);
  view.setUint32(24,rate,true); view.setUint32(28,rate*2,true); view.setUint16(32,2,true); view.setUint16(34,16,true);
  str(36,'data'); view.setUint32(40,samples.length*2,true);
  samples.forEach((v,i) => view.setInt16(44+i*2,Math.max(-1,Math.min(1,v))*(v<0?32768:32767),true));
  return new Blob([buffer], {type:'audio/wav'});
}
async function recognize(blob) {
  const data = new FormData(); data.append('file',blob,'utterance.wav');
  return (await (await api('/api/transcribe',data,true)).json()).text;
}
async function stopRecording() {
  const r = recording; if (!r) return; recording = null; clearTimeout(r.timer);
  r.node.disconnect(); r.source.disconnect(); r.stream.getTracks().forEach(t => t.stop());
  await r.context.close(); $('record').textContent = 'Aufnahme starten';
  const samples = new Float32Array(r.length); let offset = 0;
  r.chunks.forEach(chunk => { samples.set(chunk,offset); offset += chunk.length; });
  audioBusy = true; controls(); status('Sprache wird erkannt …');
  try { $('transcript').value = await recognize(wav(samples,r.rate)); status('Erkannten Text prüfen und senden.'); }
  catch(e) { status(e.message,true); } finally { audioBusy = false; controls(); }
}
$('record').onclick = async () => {
  if (recording) return stopRecording();
  $('player').pause();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
    const context = new AudioContext(); await context.resume(); const source = context.createMediaStreamSource(stream);
    // PCM samples avoid browser-dependent MediaRecorder codecs. One minute bounded recording.
    const node = context.createScriptProcessor(4096,1,1);
    recording = {stream,context,source,node,rate:context.sampleRate,chunks:[],length:0,timer:setTimeout(stopRecording,59000)};
    node.onaudioprocess = e => { if(recording) { const chunk = new Float32Array(e.inputBuffer.getChannelData(0)); recording.chunks.push(chunk); recording.length += chunk.length; } };
    source.connect(node); node.connect(context.destination); $('record').textContent = 'Aufnahme stoppen'; status('Aufnahme läuft …'); controls();
  } catch(e) { status('Mikrofon nicht verfügbar: '+e.message,true); }
};
async function testAudio(roundtrip) {
  audioBusy = true; controls(); const began = performance.now(); $('audioResult').textContent = 'Stimme wird erzeugt …';
  try {
    const blob = await (await api('/api/audio-test',{text:$('testText').value})).blob(); await play(blob);
    if (roundtrip) { const context = new AudioContext(); const decoded = await context.decodeAudioData(await blob.arrayBuffer());
      const mono = new Float32Array(decoded.length); for(let c=0;c<decoded.numberOfChannels;c++){ const samples=decoded.getChannelData(c); for(let i=0;i<mono.length;i++)mono[i]+=samples[i]/decoded.numberOfChannels; }
      const text = await recognize(wav(mono,decoded.sampleRate)); await context.close(); $('audioResult').textContent = 'Erkannt: '+text;
    } else $('audioResult').textContent = 'Audio ist bereit.';
    $('audioResult').textContent += ' Dauer: '+((performance.now()-began)/1000).toFixed(1)+' s.';
  } catch(e) { $('audioResult').textContent = e.message; } finally { audioBusy=false;controls(); }
}
$('audioTest').onclick = () => testAudio(false); $('roundtrip').onclick = () => testAudio(true);
window.addEventListener('pagehide', () => { stopped=true; if(recording) recording.stream.getTracks().forEach(t=>t.stop()); });
(async () => { try { const response=await fetch('/api/session'); if(!response.ok)throw new Error('Lokale Verbindung nicht verfügbar');
  const session=await response.json(); csrf=session.csrf; enabled=session.serviceNowEnabled; state.started=session.started; controls(); poll();
} catch(e){status(e.message,true);} })();
