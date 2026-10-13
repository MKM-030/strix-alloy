#!/usr/bin/env node
import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';

const asset = new URL('./web/vendor/qr-code.js', import.meta.url);
function qrApi() {
  assert.ok(existsSync(asset), 'the local browser QR asset exists');
  // No DOM, fetch, storage, or network API is provided to the classic script.
  const context = vm.createContext({});
  vm.runInContext(readFileSync(asset, 'utf8'), context);
  assert.equal(context.qrcodegen, undefined, 'the encoder remains private');
  assert.equal(typeof context.VoiceStudioQr?.toSvgDataUrl, 'function');
  return context.VoiceStudioQr;
}

function imageData(dataUrl) {
  assert.ok(dataUrl.startsWith('data:image/svg+xml;charset=utf-8,'));
  const svg = decodeURIComponent(dataUrl.slice(dataUrl.indexOf(',') + 1));
  assert.match(svg, /^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" /);
  assert.match(svg, /<rect width="100%" height="100%" fill="#fff"\/>/);
  const viewBox = svg.match(/viewBox="0 0 (\d+) (\d+)"/);
  assert.ok(viewBox, 'the SVG has a numeric view box');
  assert.equal(viewBox[1], viewBox[2], 'the QR is square');
  const side = Number(viewBox[1]);
  assert.equal((side - 8 - 17) % 4, 0, 'the image contains a QR version and border');
  const paths = [...svg.matchAll(/M(\d+),(\d+)h1v1h-1z/g)].map((match) => [+match[1], +match[2]]);
  assert.ok(paths.length > 100, 'black modules are drawn');
  return {svg, side, paths};
}

test('the classic browser script generates a local SVG with a four-module quiet zone', () => {
  const api = qrApi();
  assert.equal(Object.isFrozen(api), true);
  const {side, paths} = imageData(api.toSvgDataUrl('https://example.invalid/voice-studio/#access=synthetic-test-value'));
  for (const [x, y] of paths) {
    assert.ok(x >= 4 && y >= 4 && x < side - 4 && y < side - 4, 'every module preserves the quiet zone');
  }
  assert.equal(Math.min(...paths.map(([x]) => x)), 4);
  assert.equal(Math.min(...paths.map(([, y]) => y)), 4);
});

test('payload text is encoded only into numeric QR modules', () => {
  const value = 'https://example.invalid/#access=<script>alert("synthetic")</script>&name=Äö漢字';
  const {svg} = imageData(qrApi().toSvgDataUrl(value));
  assert.ok(!svg.includes('synthetic'));
  assert.ok(!svg.includes('script'));
  assert.ok(!svg.includes('href='));
  assert.ok(!svg.includes('onload='));
});

test('invalid payloads fail without including their contents in errors', () => {
  const api = qrApi();
  for (const value of [null, undefined, {}, '', 42]) {
    assert.throws(() => api.toSvgDataUrl(value), {name: 'TypeError', message: 'QR text must be a non-empty string.'});
  }
  const oversized = 'synthetic-' + 'x'.repeat(5000);
  assert.throws(() => api.toSvgDataUrl(oversized), (error) => error.name === 'RangeError' && !error.message.includes('synthetic-'));
});

// The independent reader is vendored for reproducible, offline Node tests.
// It is used only by tests; the browser encoder never loads it or uses a service.
const readerPath = process.env.VOICE_STUDIO_QR_DECODER || fileURLToPath(new URL('./test-support/jsQR.cjs', import.meta.url));
function qrReader() {
  assert.ok(existsSync(readerPath), 'the local independent QR decoder exists');
  return createRequire(import.meta.url)(readerPath);
}
for (const [label, value] of [
  ['short URL', 'https://example.invalid/voice-studio/#access=synthetic-test-value'],
  ['long URL', 'https://example.invalid/voice-studio/#access=synthetic-' + 'abcdefghijklmnopqrstuvwxyz0123456789'.repeat(6)],
  ['Unicode URL', 'https://example.invalid/#access=synthetic-Äö漢字&value=<svg>'],
  ['production-shaped URL', 'https://strix-alloy.tail7f425a.ts.net/voice-studio/#access=VSP-0123456789abcdef-abcdefghijklmnopqrstuvwx'],
]) {
  test(`an independent reader recovers the exact synthetic payload (${label})`, () => {
    const {side, paths} = imageData(qrApi().toSvgDataUrl(value));
    const scale = 8;
    const width = side * scale;
    const pixels = new Uint8ClampedArray(width * width * 4).fill(255);
    for (const [x, y] of paths) {
      for (let dy = 0; dy < scale; dy++) {
        for (let dx = 0; dx < scale; dx++) {
          const offset = (((y * scale + dy) * width) + x * scale + dx) * 4;
          pixels[offset] = pixels[offset + 1] = pixels[offset + 2] = 0;
        }
      }
    }
    const decoded = qrReader()(pixels, width, width, {inversionAttempts: 'dontInvert'});
    assert.ok(decoded, 'the SVG modules decode as a QR symbol');
    assert.equal(decoded.data, value, 'the encoded payload round-trips exactly');
  });
}
