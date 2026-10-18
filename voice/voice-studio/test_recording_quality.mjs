import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = readFileSync(new URL('./web/app.js', import.meta.url), 'utf8');
const {inspectSignal} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const tone = (peak, seconds = 4, rate = 24000) => Float32Array.from({length: seconds * rate}, (_, i) => peak * Math.sin(i / 17));

test('recording with audible but backend-rejected low peak cannot be marked saveable', () => {
  const signal = inspectSignal(tone(0.009));
  assert.equal(signal.hasInput, false);
});

test('a brief sound followed by silence does not count as a full speech reference', () => {
  const samples = new Float32Array(24000 * 4);
  samples.set(tone(0.1, 0.2));
  assert.equal(inspectSignal(samples).hasInput, false);
});

test('normal speech remains admissible and limited isolated clipping matches backend allowance', () => {
  const samples = tone(0.1);
  for (let index = 0; index < 200; index++) samples[index] = 1;
  const signal = inspectSignal(samples);
  assert.equal(signal.hasInput, true);
  assert.equal(signal.clipped, false);
});
