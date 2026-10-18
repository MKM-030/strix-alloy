"""Exercise the shipped browser handlers; no bridge or audio service is contacted."""
import shutil
import subprocess
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "mobile_static" / "app.js"
HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

class Element {
  constructor(tag = 'div') {
    this.tagName = tag;
    this.children = [];
    this.listeners = {};
    this.className = '';
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.hidden = false;
    this.textContent = '';
    this.classList = { toggle() {} };
    this.playCount = 0;
    this.pauseCount = 0;
  }
  append(...children) {
    for (const child of children) { child.parent = this; this.children.push(child); }
  }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  remove() { this.parent.children = this.parent.children.filter(child => child !== this); }
  querySelectorAll(selector) {
    return this.children.flatMap(child => [
      ...(selector === 'button' ? child.tagName === 'button' :
        child.className.split(' ').includes(selector.slice(1))) ? [child] : [],
      ...child.querySelectorAll(selector),
    ]);
  }
  addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
  async emit(name, properties = {}) {
    for (const handler of this.listeners[name] || []) {
      await handler({ preventDefault() {}, ...properties });
    }
  }
  setAttribute() {}
  focus() {}
  pause() { this.pauseCount++; }
  play() { this.playCount++; return Promise.resolve(); }
}

function response(data = {}, status = 200) {
  return {
    ok: status >= 200 && status < 300, status,
    json: async () => data,
    blob: async () => new Blob(['synthetic-test-wave'], { type: 'audio/wav' }),
  };
}

async function flush() {
  // Public handlers launch async work without returning their promises.
  for (let i = 0; i < 12; i++) await new Promise(resolve => setImmediate(resolve));
}

async function setup() {
  const elements = {};
  const el = id => elements[id] ||= new Element();
  el('speechEnabled').checked = true;
  el('messageInput').value = 'Eine Antwort';
  const speech = deferred();
  const calls = [];
  const audioUrls = [];
  let microphoneCalls = 0;
  let eventCalls = 0;
  let hasHistory = true;
  let speechSignal;
  const document = {
    documentElement: { dataset: { basePath: '/scc-demo' } },
    getElementById: el,
    createElement: tag => new Element(tag),
    addEventListener() {},
  };
  const mediaDevices = {
    getUserMedia: async () => {
      microphoneCalls++;
      return { getTracks: () => [{ stop() {} }] };
    },
  };
  class Recorder {
    static isTypeSupported() { return true; }
    constructor() { this.state = 'inactive'; }
    start() { this.state = 'recording'; }
    stop() { this.state = 'inactive'; }
  }
  class AudioContext { constructor() { this.state = 'running'; } }
  const context = vm.createContext({
    document, location: { pathname: '/scc-demo/' },
    window: { isSecureContext: true, MediaRecorder: Recorder, AudioContext, addEventListener() {} },
    navigator: { mediaDevices }, MediaRecorder: Recorder,
    AbortController, Blob, FormData, console,
    setTimeout, clearTimeout, setInterval, clearInterval,
    URL: {
      createObjectURL: () => { const url = 'blob:test-' + audioUrls.length; audioUrls.push(url); return url; },
      revokeObjectURL() {},
    },
    fetch: async (url, options) => {
      const path = url.replace('/scc-demo', '').split('?')[0];
      calls.push({ path, options });
      if (path === '/auth/session' || path === '/auth/login')
        return response({ authenticated: true, csrf: 'test-csrf' });
      if (path === '/api/session')
        return response({ csrf: 'test-csrf', started: true, busy: false, ended: false, failed: false });
      if (path === '/api/speak') {
        speechSignal = options.signal;
        if (options.signal) options.signal.addEventListener('abort', () => {
          const error = new Error('aborted'); error.name = 'AbortError'; speech.reject(error);
        }, { once: true });
        return speech.promise;
      }
      if (path === '/api/events') {
        // The first poll is history: it creates a replay button without auto speech.
        if (eventCalls++ === 0)
          return response({ started: true, busy: false, cursor: 1,
            events: hasHistory ? [{ id: 1, kind: 'bot', text: 'Wie heißt der Mitarbeiter?' }] : [],
            choices: hasHistory ? [{ value: 'yes', label: 'Ja' }] : [] });
        return new Promise((resolve, reject) => {
          options.signal?.addEventListener('abort', () => {
            const error = new Error('aborted'); error.name = 'AbortError'; reject(error);
          }, { once: true });
        });
      }
      if (path === '/api/reset') {
        eventCalls = 0;
        hasHistory = false;
        return response({ csrf: 'test-csrf', started: true, busy: false, ended: false, failed: false });
      }
      if (path === '/api/start') {
        eventCalls = 0;
        return response({});
      }
      return response({});
    },
  });
  const source = fs.readFileSync(process.argv[1], 'utf8').replace(/^export /gm, '');
  vm.runInContext(source, context, { filename: 'app.js' });
  await flush();
  const replay = () => el('messages').querySelectorAll('.replay')[0];
  assert.equal(el('recordButton').disabled, false, 'fixture must start ready');
  assert.ok(replay(), 'fixture must contain a real rendered bot replay button');
  await replay().emit('click');
  await flush();
  assert.equal(calls.filter(call => call.path === '/api/speak').length, 1);
  return {
    el, replay, speech, calls, audioUrls,
    signal: () => speechSignal,
    microphoneCalls: () => microphoneCalls,
    playCount: () => el('speechPlayer').playCount,
    async finish() { await el('logoutButton').emit('click'); await flush(); },
  };
}

async function run(scenario) {
  const app = await setup();
  const { el, speech, calls } = app;
  if (scenario === 'pending') {
    assert.equal(el('recordButton').disabled, true, 'mic must be locked while TTS is pending');
    assert.equal(el('sendButton').disabled, true, 'send must be locked while TTS is pending');
    assert.equal(el('choices').querySelectorAll('button')[0].disabled, true, 'choices must be locked');
    assert.equal(app.replay().disabled, true, 'replay must be locked');
    assert.match(el('status').textContent, /Sprachausgabe.*vorbereitet/, 'pending speech needs visible status');
    await el('messageForm').emit('submit');
    await el('messageInput').emit('keydown', { ctrlKey: true, key: 'Enter' });
    await el('recordButton').emit('click');
    await el('choices').querySelectorAll('button')[0].emit('click');
    await app.replay().emit('click');
    await flush();
    assert.equal(app.microphoneCalls(), 0, 'pending TTS must not acquire the mic');
    assert.equal(calls.filter(call => call.path === '/api/message').length, 0, 'pending TTS must not send');
    assert.equal(calls.filter(call => call.path === '/api/speak').length, 1, 'pending TTS must not start another synthesis');
    speech.reject(new Error('test ends pending synthesis'));
  } else if (scenario === 'invalidated') {
    const plays = app.playCount(), urls = app.audioUrls.length;
    el('speechEnabled').checked = false;
    await el('speechEnabled').emit('change');
    assert.equal(app.signal()?.aborted || false, false, 'stop must not abort unfinished server synthesis');
    assert.equal(el('recordButton').disabled, true, 'stop must keep mic locked until fetch settles');
    speech.resolve(response());
    await flush();
    assert.equal(app.playCount(), plays, 'invalidated audio must not play');
    assert.equal(app.audioUrls.length, urls, 'invalidated audio must not be installed');
    assert.equal(el('recordButton').disabled, false, 'settled invalidated speech must release mic');
  } else if (scenario === 'playback') {
    const plays = app.playCount();
    speech.resolve(response());
    await flush();
    assert.equal(app.playCount(), plays + 1, 'settled speech must play');
    assert.equal(el('recordButton').disabled, false, 'completed synthesis must release mic during playback');
    assert.equal(el('sendButton').disabled, false, 'completed synthesis must release send');
    const pauses = el('speechPlayer').pauseCount;
    await el('recordButton').emit('click');
    await flush();
    assert.equal(app.signal().aborted, true, 'playback may be aborted after fetch settles');
    assert.equal(app.microphoneCalls(), 1, 'playback may be interrupted to record');
    assert.ok(el('speechPlayer').pauseCount > pauses, 'recording must stop playback');
  } else if (scenario === 'failure') {
    assert.equal(el('recordButton').disabled, true, 'fixture must be in synthesis');
    speech.reject(new Error('TTS unavailable'));
    await flush();
    assert.equal(el('recordButton').disabled, false, 'failed synthesis must release mic');
    assert.equal(el('sendButton').disabled, false, 'failed synthesis must release send');
    assert.equal(app.replay().disabled, false, 'failed synthesis must release replay');
    assert.match(el('error').textContent, /TTS unavailable/);
  } else if (scenario === 'reset' || scenario === 'logout') {
    const plays = app.playCount(), urls = app.audioUrls.length;
    if (scenario === 'reset') {
      await el('resetButton').emit('click');
    } else {
      await el('logoutButton').emit('click');
      el('password').value = 'test-only';
      await el('loginForm').emit('submit');
    }
    await flush();
    assert.equal(app.signal()?.aborted || false, false, scenario + ' must not abort pending synthesis');
    assert.equal(el('recordButton').disabled, true, scenario + ' must preserve the synthesis lock');
    speech.resolve(response());
    await flush();
    assert.equal(app.playCount(), plays, scenario + ' must invalidate late audio');
    assert.equal(app.audioUrls.length, urls, scenario + ' must not install late audio');
    assert.equal(el('recordButton').disabled, false, scenario + ' must release lock when fetch settles');
  } else {
    throw new Error('Unknown scenario: ' + scenario);
  }
  await flush();
  await app.finish();
}
run(process.argv[2]).then(() => process.exit(0)).catch(error => {
  console.error(error.stack); process.exit(1);
});
"""


class MobileFrontendTests(unittest.TestCase):
    def run_browser_case(self, scenario):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the browser behavior tests")
        result = subprocess.run(
            [node, "-e", HARNESS, str(APP), scenario],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pending_synthesis_blocks_microphone_message_choice_and_replay(self):
        self.run_browser_case("pending")

    def test_stopping_speech_waits_for_fetch_and_discards_late_audio(self):
        self.run_browser_case("invalidated")

    def test_completed_synthesis_allows_playback_interruption_for_recording(self):
        self.run_browser_case("playback")

    def test_failed_synthesis_unlocks_controls(self):
        self.run_browser_case("failure")

    def test_reset_keeps_lock_until_invalidated_synthesis_settles(self):
        self.run_browser_case("reset")

    def test_logout_and_login_keep_lock_until_old_synthesis_settles(self):
        self.run_browser_case("logout")
