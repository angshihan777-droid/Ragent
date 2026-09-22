import assert from 'node:assert/strict';
import { test } from 'node:test';
import { formatSimilarity } from '../src/similarity.js';
import { store } from '../src/store.js';
import { api } from '../src/api.js';
import { readStream } from '../src/sse.js';

test('similarity uses actual cosine values and never invents missing scores', () => {
  assert.equal(formatSimilarity(0.873), '87.3%');
  assert.equal(formatSimilarity(0), '0.0%');
  assert.equal(formatSimilarity(-0.2), '-20.0%');
  for (const invalid of [undefined, null, NaN, Infinity, '0.9', 1.2]) assert.equal(formatSimilarity(invalid), '暂未提供');
});

test('project switching ignores late responses and remembers each selected session', async () => {
  const originalAgents = api.listAgents, originalThreads = api.listThreads;
  let release;
  try {
    Object.assign(store, { currentProjectId: null, currentThreadId: null, selectedThreads: {}, threadsByProject: {} });
    api.listAgents = async id => [{ id: 'agent-' + id }];
    api.listThreads = id => id === 'slow' ? new Promise(resolve => { release = resolve; }) : Promise.resolve([{ id: id + '-1' }, { id: id + '-2' }]);
    const slow = store.selectProject('slow');
    await store.selectProject('fast');
    await store.selectThread('fast-2');
    release([{ id: 'slow-1' }]);
    await slow;
    assert.equal(store.currentProjectId, 'fast');
    assert.equal(store.currentThreadId, 'fast-2');
    assert.equal(store.agents[0].id, 'agent-fast');
    await store.selectProject('other');
    await store.selectProject('fast');
    assert.equal(store.currentThreadId, 'fast-2');
    await store.selectThread('foreign-thread');
    assert.equal(store.currentThreadId, 'fast-2');
  } finally { api.listAgents = originalAgents; api.listThreads = originalThreads; }
});

test('SSE passes real sources and steps through, supports abort signal', async () => {
  const originalFetch = globalThis.fetch;
  const controller = new AbortController();
  const source = { title: '资料', content: '原文', similarity: .8 };
  const events = [['step', { step: { key: 'retrieve', status: 'done' } }], ['sources', { sources: [source] }], ['token', { token: '回答' }], ['done', { status: 'done' }]];
  const stream = events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('');
  try {
    globalThis.fetch = async (_, options) => {
      assert.equal(options.signal, controller.signal);
      return new Response(stream);
    };
    let tokens = '', sources, step;
    const result = await readStream('/test', token => tokens += token, hits => sources = hits, value => step = value, controller.signal);
    assert.equal(tokens, '回答'); assert.deepEqual(sources, [source]); assert.equal(step.key, 'retrieve'); assert.equal(result.status, 'done');
  } finally { globalThis.fetch = originalFetch; }
});
