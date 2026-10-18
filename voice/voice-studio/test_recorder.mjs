#!/usr/bin/env node
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

// Import the browser module independently of a parent project's package type.
// Its document guard leaves only the real audio utilities active under Node.
const appSource = readFileSync(new URL('./web/app.js', import.meta.url), 'utf8');
const {encodeWav, inspectSignal} = await import(`data:text/javascript;base64,${Buffer.from(appSource).toString('base64')}`);
const workletSource = readFileSync(new URL('./web/recorder-worklet.js', import.meta.url), 'utf8');

function createRecorder(maximumFrames) {
  let Registered;
  const messages = [];
  class Processor {
    constructor() {
      this.port = {postMessage: message => messages.push(message)};
    }
  }
  vm.runInNewContext(workletSource, {
    AudioWorkletProcessor: Processor,
    Float32Array,
    registerProcessor: (name, constructor) => {
      assert.equal(name, 'voice-studio-recorder');
      Registered = constructor;
    }
  });
  return {instance: new Registered({processorOptions: {maximumFrames}}), messages};
}

test('WAV encoder writes a standard mono 24 kHz PCM16 file', () => {
  const buffer = encodeWav(new Float32Array(24000 * 3), 24000);
  const view = new DataView(buffer);
  const text = (offset, length) => String.fromCharCode(...new Uint8Array(buffer, offset, length));
  assert.equal(text(0, 4), 'RIFF');
  assert.equal(text(8, 4), 'WAVE');
  assert.equal(text(12, 4), 'fmt ');
  assert.equal(text(36, 4), 'data');
  assert.equal(view.getUint16(20, true), 1);
  assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(24, true), 24000);
  assert.equal(view.getUint32(28, true), 48000);
  assert.equal(view.getUint16(32, true), 2);
  assert.equal(view.getUint16(34, true), 16);
  assert.equal(view.getUint32(40, true), 144000);
  assert.equal(view.getUint32(4, true), buffer.byteLength - 8);
});

test('WAV encoding clamps signed samples and resamples 48 kHz capture to 24 kHz', () => {
  const view = new DataView(encodeWav(new Float32Array([-2, -1, 0, 1, 2]), 24000));
  assert.deepEqual(
    Array.from({length: 5}, (_, index) => view.getInt16(44 + index * 2, true)),
    [-32768, -32768, 0, 32767, 32767]
  );
  const resampled = encodeWav(new Float32Array(48000 * 3).fill(0.5), 48000);
  assert.equal((resampled.byteLength - 44) / 2, 72000);
  assert.equal(new DataView(resampled).getInt16(44, true), 16384);
});

test('signal diagnostics distinguish silence, usable volume and clipped peaks', () => {
  assert.equal(inspectSignal(new Float32Array(2048)).hasInput, false);
  const usable = inspectSignal(new Float32Array(2048).fill(0.06));
  assert.equal(usable.hasInput, true);
  assert.equal(usable.clipped, false);
  const loud = inspectSignal(new Float32Array(2048).fill(0.999));
  assert.equal(loud.clipped, true);
  assert.ok(loud.peak > 0.98);
});

test('capture mixes stereo to mono, enforces the exact maximum and emits silent output', () => {
  const {instance, messages} = createRecorder(6);
  const output = new Float32Array(10).fill(0.9);
  instance.process(
    [[new Float32Array(10).fill(0.6), new Float32Array(10).fill(0.2)]],
    [[output]]
  );
  assert.equal(messages[0].samples.length, 6);
  assert.ok(Math.abs(messages[0].samples[0] - 0.4) < 0.00001);
  assert.equal(messages[1].type, 'finished');
  assert.deepEqual(Array.from(output), Array(10).fill(0));
  instance.process([[new Float32Array(10).fill(0.6)]], [[output]]);
  assert.equal(messages.length, 2);
});

test('manual finish flushes the final partial capture once and discards later input', () => {
  const {instance, messages} = createRecorder(25000);
  instance.process([[new Float32Array(2401).fill(0.3)]], [[new Float32Array(2401)]]);
  instance.port.onmessage({data: 'finish'});
  instance.port.onmessage({data: 'finish'});
  assert.deepEqual(messages.filter(message => message.type === 'samples').map(message => message.samples.length), [2048, 353]);
  assert.equal(messages.filter(message => message.type === 'finished').length, 1);
  instance.process([[new Float32Array(128).fill(0.8)]], [[new Float32Array(128)]]);
  assert.equal(messages.filter(message => message.type === 'samples').length, 2);
});
