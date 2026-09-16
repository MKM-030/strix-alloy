#!/usr/bin/env node
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { performance } from 'node:perf_hooks';

const argv = process.argv.slice(2);
function flag(name, fallback) {
  const index = argv.indexOf(name);
  return index >= 0 && argv[index + 1] !== undefined ? argv[index + 1] : fallback;
}

const endpoint = String(flag('--endpoint', 'http://127.0.0.1:8826/v1')).replace(/\/+$/u, '');
const model = String(flag('--model', 'qwen3.8-flash-next'));
const outputDir = String(flag('--output-dir', 'C:/AI/local-ai/flashnext/benchmarks'));
const includeLongPrompts = argv.includes('--long-prompts');
const parsedEndpoint = new URL(endpoint);
if (parsedEndpoint.hostname !== '127.0.0.1' && parsedEndpoint.hostname !== 'localhost') {
  throw new Error('Flash-Next-Benchmark erlaubt ausschließlich Loopback-Endpunkte.');
}

const cases = [
  {
    id: 'json',
    messages: [
      { role: 'user', content: 'Antworte ausschließlich mit gültigem JSON: {"ok":true,"n":3}.' },
    ],
    maxTokens: 128,
    extras: { chat_template_kwargs: { enable_thinking: false } },
  },
  {
    id: 'german',
    messages: [
      {
        role: 'user',
        content:
          'Erkläre auf Deutsch in zwei kurzen Sätzen, warum ein lokaler Request-Slot nützlich ist.',
      },
    ],
    maxTokens: 192,
    extras: { chat_template_kwargs: { enable_thinking: false } },
  },
  {
    id: 'powershell',
    messages: [
      {
        role: 'user',
        content:
          'Gib genau eine sichere PowerShell-Zeile aus, die den freien TCP-Port 8826 prüft. Kein Markdown.',
      },
    ],
    maxTokens: 192,
    extras: { chat_template_kwargs: { enable_thinking: false } },
  },
  {
    id: 'javascript',
    messages: [
      {
        role: 'user',
        content:
          'Schreibe eine kleine JavaScript-Funktion add(a,b), die Zahlen addiert. Nur der Code.',
      },
    ],
    maxTokens: 128,
    extras: { chat_template_kwargs: { enable_thinking: false } },
  },
  {
    id: 'revn-coding',
    messages: [
      {
        role: 'user',
        content:
          'Synthetische REV:N-Aufgabe: Entwirf in höchstens sechs Stichpunkten einen Testplan für eine idempotente lokale Modell-Lane mit Healthcheck, Abbruch und Session-Isolation. Keine Produktaufrufe.',
      },
    ],
    maxTokens: 384,
    extras: { chat_template_kwargs: { enable_thinking: false } },
  },
  {
    id: 'reasoning-visible-answer',
    messages: [
      {
        role: 'user',
        content: 'Nenne auf Deutsch die Zahl 17 und begründe sie in einem kurzen Satz.',
      },
    ],
    maxTokens: 256,
    extras: { reasoning_effort: 'low' },
  },
];

function longPrompt(repetitions) {
  const body = 'alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu ';
  return `${body.repeat(repetitions)}\nCount the repeated sequence and answer with the final checksum word: omega.`;
}

if (includeLongPrompts) {
  cases.push(
    {
      id: 'prompt-8k',
      messages: [{ role: 'user', content: longPrompt(700) }],
      maxTokens: 96,
      extras: { chat_template_kwargs: { enable_thinking: false } },
    },
    {
      id: 'prompt-32k',
      messages: [{ role: 'user', content: longPrompt(2700) }],
      maxTokens: 96,
      extras: { chat_template_kwargs: { enable_thinking: false } },
    },
  );
}

async function getText(path) {
  const response = await fetch(`${endpoint.replace(/\/v1$/u, '')}${path}`, {
    signal: AbortSignal.timeout(10_000),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}: ${text.slice(0, 400)}`);
  return text;
}

function parseMetric(text, name) {
  const match = new RegExp(`^${name}(?:\\{[^\\n]*\\})?\\s+([0-9.eE+-]+)$`, 'mu').exec(text);
  return match ? Number(match[1]) : null;
}

function metricDelta(before, after, name) {
  const oldValue = parseMetric(before, name);
  const newValue = parseMetric(after, name);
  return oldValue === null || newValue === null ? null : newValue - oldValue;
}

async function postChat(messages, maxTokens, extras = {}, signal) {
  const started = performance.now();
  const controller = new AbortController();
  const response = await fetch(`${endpoint}/chat/completions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      model,
      messages,
      max_tokens: maxTokens,
      temperature: 0,
      top_p: 1,
      stream: true,
      stream_options: { include_usage: true },
      ...extras,
    }),
    signal: signal ?? controller.signal,
  });
  if (!response.ok)
    throw new Error(
      `chat/completions: HTTP ${response.status}: ${(await response.text()).slice(0, 500)}`,
    );
  if (!response.body) throw new Error('chat/completions: Antwort ohne Body.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let text = '';
  let reasoning = '';
  let usage = null;
  let firstEventMs = null;
  let firstContentMs = null;
  let finishReason = null;
  const toolCalls = new Map();
  const events = [];
  const consume = (chunk) => {
    buffer += decoder.decode(chunk, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data:')) continue;
      const payload = line.slice(5).trim();
      if (payload === '[DONE]') continue;
      let item;
      try {
        item = JSON.parse(payload);
      } catch {
        continue;
      }
      events.push(item);
      if (firstEventMs === null) firstEventMs = performance.now() - started;
      const choice = item.choices?.[0];
      const delta = choice?.delta;
      if (typeof delta?.content === 'string') {
        if (firstContentMs === null && delta.content.length > 0)
          firstContentMs = performance.now() - started;
        text += delta.content;
      }
      if (typeof delta?.reasoning_content === 'string') reasoning += delta.reasoning_content;
      if (Array.isArray(delta?.tool_calls)) {
        for (const incoming of delta.tool_calls) {
          const index = incoming.index ?? toolCalls.size;
          const current = toolCalls.get(index) ?? {
            index,
            function: { name: '', arguments: '' },
          };
          if (incoming.id) current.id = incoming.id;
          if (incoming.type) current.type = incoming.type;
          if (incoming.function?.name) current.function.name += incoming.function.name;
          if (typeof incoming.function?.arguments === 'string') {
            current.function.arguments += incoming.function.arguments;
          }
          toolCalls.set(index, current);
        }
      }
      if (choice?.finish_reason) finishReason = choice.finish_reason;
      if (item.usage) usage = item.usage;
    }
  };
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    consume(value);
  }
  await reader.cancel().catch(() => {});
  return {
    elapsedMs: performance.now() - started,
    ttftMs: firstContentMs ?? firstEventMs,
    text,
    reasoning,
    usage,
    finishReason,
    eventCount: events.length,
    toolCalls: [...toolCalls.values()],
  };
}

async function runCase(testCase) {
  // Warmup is retained in raw output and never used as a measurement.
  const warmup = await postChat(testCase.messages, testCase.maxTokens, testCase.extras);
  const runs = [];
  for (let index = 0; index < 3; index += 1) {
    runs.push(await postChat(testCase.messages, testCase.maxTokens, testCase.extras));
  }
  return { id: testCase.id, warmup, runs };
}

async function runMultiTurn() {
  const first = await postChat(
    [{ role: 'user', content: 'Merke dir die Zahl 17 für diesen Test.' }],
    64,
    { chat_template_kwargs: { enable_thinking: false } },
  );
  const second = await postChat(
    [
      { role: 'user', content: 'Merke dir die Zahl 17 für diesen Test.' },
      { role: 'assistant', content: first.text },
      { role: 'user', content: 'Welche Zahl solltest du dir merken? Antworte nur mit der Zahl.' },
    ],
    32,
    { chat_template_kwargs: { enable_thinking: false } },
  );
  return { first, second };
}

async function runToolMock() {
  const tools = [
    {
      type: 'function',
      function: {
        name: 'mock_weather',
        description: 'Returns a synthetic weather value; never call a real service.',
        parameters: {
          type: 'object',
          properties: { city: { type: 'string' } },
          required: ['city'],
        },
      },
    },
  ];
  const first = await postChat(
    [{ role: 'user', content: 'Nutze das Mock-Tool für Berlin.' }],
    256,
    { tools, tool_choice: 'required', chat_template_kwargs: { enable_thinking: false } },
  );
  const rawToolCall = first.toolCalls?.[0] ?? null;
  const toolCall = rawToolCall
    ? {
        ...rawToolCall,
        function: {
          ...rawToolCall.function,
          arguments: JSON.parse(rawToolCall.function.arguments),
        },
      }
    : null;
  const second = await postChat(
    [
      { role: 'user', content: 'Nutze das Mock-Tool für Berlin.' },
      { role: 'assistant', content: first.text, ...(toolCall ? { tool_calls: [toolCall] } : {}) },
      ...(toolCall
        ? [
            {
              role: 'tool',
              tool_call_id: toolCall.id,
              content: '{"city":"Berlin","temperatureC":21,"source":"synthetic"}',
            },
          ]
        : []),
    ],
    256,
    { chat_template_kwargs: { enable_thinking: false } },
  );
  return { first, toolCall, second };
}

async function main() {
  const health = JSON.parse(await getText('/health'));
  const models = JSON.parse(await getText('/v1/models'));
  const props = JSON.parse(await getText('/props'));
  const metricsBefore = await getText('/metrics').catch(() => '');
  const started = new Date().toISOString();
  const results = [];
  for (const testCase of cases) results.push(await runCase(testCase));
  const multiTurn = await runMultiTurn();
  let toolMock;
  try {
    toolMock = await runToolMock();
  } catch (error) {
    toolMock = { error: String(error) };
  }
  let abort;
  try {
    const controller = new AbortController();
    const request = postChat(
      [{ role: 'user', content: 'Erzeuge eine lange, aber harmlose Testantwort.' }],
      512,
      { chat_template_kwargs: { enable_thinking: false } },
      controller.signal,
    );
    setTimeout(() => controller.abort(), 100);
    const result = await Promise.race([
      request.catch((error) => ({ error: String(error) })),
      new Promise((resolve) => setTimeout(() => resolve({ bounded: true }), 500)),
    ]);
    abort = { bounded: true, clientAbortSent: controller.signal.aborted, result };
  } catch (error) {
    abort = { error: String(error) };
  }
  const metricsAfter = await getText('/metrics').catch(() => '');
  const output = {
    schemaVersion: 1,
    started,
    finished: new Date().toISOString(),
    endpoint,
    model,
    health,
    models,
    props,
    metricsBefore,
    metricsAfter,
    metricDeltas: {
      promptTokens: metricDelta(metricsBefore, metricsAfter, 'llamacpp:prompt_tokens_total'),
      predictedTokens: metricDelta(metricsBefore, metricsAfter, 'llamacpp:tokens_predicted_total'),
      speculativeAccepted: metricDelta(
        metricsBefore,
        metricsAfter,
        'llamacpp:spec_decode_num_accepted_tokens_total',
      ),
    },
    cases: results,
    multiTurn,
    toolMock,
    abort,
    notes: [
      'TTFT is measured from request start to first streamed content event.',
      'SSE event count is not token count; usage and server metrics remain authoritative.',
      'The abort probe is bounded and never treated as a successful generation.',
    ],
  };
  await mkdir(outputDir, { recursive: true });
  const path = join(outputDir, `benchmark-${started.replaceAll(/[:.]/gu, '-')}.json`);
  await writeFile(path, JSON.stringify(output, null, 2) + '\n', 'utf8');
  process.stdout.write(
    JSON.stringify({ output: path, model, endpoint, cases: results.length }) + '\n',
  );
}

await main();
