import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const projects = [{ id: 'p1', name: '研发知识库' }, { id: 'p2', name: '产品文档' }];
const threads = { p1: [{ id: 't1', title: '架构讨论', agent_id: 'a1' }, { id: 't2', title: '接口设计', agent_id: 'a1' }], p2: [{ id: 't3', title: '产品问答', agent_id: 'a2' }] };
let slowHistory = false, slowRequest = false, failRun = false, missingScore = false;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
await page.route('http://localhost:8000/**', async route => {
  const req = route.request(), url = new URL(req.url()), path = url.pathname;
  const json = body => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'access-control-allow-origin': '*', 'access-control-allow-methods': '*', 'access-control-allow-headers': '*' } });
  if (path === '/projects') return json(projects);
  if (path === '/config/llm') return json({ base_url: 'https://example.invalid/v1', model: 'test-model', key_set: true });
  const agentMatch = path.match(/^\/projects\/(p[12])\/agents$/);
  if (agentMatch) return json([{ id: agentMatch[1] === 'p1' ? 'a1' : 'a2', name: '知识库助手', use_rag: true }]);
  const threadMatch = path.match(/^\/projects\/(p[12])\/threads$/);
  if (threadMatch) {
    if (req.method() === 'POST') { const thread = { id: 't4', ...req.postDataJSON() }; threads[threadMatch[1]].push(thread); return json(thread); }
    return json(threads[threadMatch[1]]);
  }
  if (path.startsWith('/threads/') && req.method() === 'DELETE') {
    for (const list of Object.values(threads)) { const index = list.findIndex(t => t.id === path.split('/')[2]); if (index >= 0) list.splice(index, 1); }
    return route.fulfill({ status: 204 });
  }
  if (/\/threads\/.+\/messages/.test(path)) {
    if (slowHistory && path.includes('t2')) await sleep(350);
    return json([{ role: 'assistant', content: path.includes('t2') ? '接口会话历史' : path.includes('t3') ? '产品会话历史' : path.includes('t4') ? '新建会话历史' : '架构会话历史' }]);
  }
  if (path === '/documents') return json([]);
  if (path === '/requests') { if (slowRequest) await sleep(350); return json({ request_id: 'req1' }); }
  if (path.endsWith('/stream')) {
    const hit = { title: '系统架构.md', content: '这是检索命中的完整原文。'.repeat(20), ...(missingScore ? {} : { similarity: .873 }) };
    const events = [['step', { step: { key: 'retrieve', status: 'running' } }], ['sources', { sources: [hit] }], ['step', { step: { key: 'agent', status: 'running' } }], ['token', { token: '这是测试回答' }], ['done', failRun ? { status: 'error', error: '测试失败' } : { status: 'done' }]];
    return route.fulfill({ status: 200, contentType: 'text/event-stream', body: events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('') });
  }
  throw new Error('Unhandled mock API: ' + req.method() + ' ' + path);
});
try {
  await page.goto(process.env.TEST_URL || 'http://127.0.0.1:5173');
  await page.getByText('架构会话历史', { exact: true }).waitFor();
  assert.equal(await page.getByRole('tab').count(), 0);
  await page.getByRole('heading', { name: '执行过程' }).waitFor();
  await page.getByRole('heading', { name: '命中资料' }).waitFor();
  const top = await page.locator('.execution-card').boundingBox(), bottom = await page.locator('.sources-card').boundingBox();
  assert(bottom.y >= top.y + top.height);
  assert.equal(await page.getByRole('list', { name: '研发知识库 的会话' }).getByRole('button', { name: '接口设计', exact: true }).count(), 1);
  await page.getByRole('button', { name: '展开项目 产品文档' }).click();
  await page.getByRole('button', { name: '产品问答', exact: true }).click();
  await page.getByText('产品会话历史', { exact: true }).waitFor();
  await page.getByRole('button', { name: '接口设计', exact: true }).click();
  await page.getByText('接口会话历史', { exact: true }).waitFor();
  await page.getByRole('link', { name: '模型配置', exact: true }).click();
  await page.getByRole('link', { name: '← 返回对话', exact: true }).last().click();
  await page.getByText('接口会话历史', { exact: true }).waitFor();
  for (const label of ['调整左栏宽度', '调整右栏宽度']) {
    const handle = page.getByRole('separator', { name: label });
    const before = Number(await handle.getAttribute('aria-valuenow'));
    await handle.focus(); await page.keyboard.press(label.includes('左') ? 'ArrowRight' : 'ArrowLeft');
    assert.equal(Number(await handle.getAttribute('aria-valuenow')), before + 16);
    const box = await handle.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + 200); await page.mouse.down();
    await page.mouse.move(box.x + (label.includes('左') ? 38 : -30), box.y + 200); await page.mouse.up();
    assert(Number(await handle.getAttribute('aria-valuenow')) > before + 16);
  }
  const savedWidth = await page.getByRole('separator', { name: '调整左栏宽度' }).getAttribute('aria-valuenow');
  await page.reload(); await page.getByText('架构会话历史', { exact: true }).waitFor();
  assert.equal(await page.getByRole('separator', { name: '调整左栏宽度' }).getAttribute('aria-valuenow'), savedWidth);
  await page.getByRole('button', { name: '收起左栏' }).click();
  assert.equal(await page.locator('.sidebar').count(), 0);
  await page.getByRole('button', { name: '展开左栏' }).click();
  await page.getByRole('button', { name: '收起右栏' }).click();
  assert.equal(await page.locator('.right-rail').count(), 0);
  await page.getByRole('button', { name: '展开右栏' }).click();
  await page.getByRole('button', { name: '在 研发知识库 新建会话' }).click();
  await page.getByPlaceholder('新会话', { exact: true }).fill('新增测试会话');
  await page.getByRole('button', { name: '创建会话', exact: true }).click();
  await page.getByText('新建会话历史', { exact: true }).waitFor();
  await page.getByRole('button', { name: '架构讨论', exact: true }).click();
  await page.getByText('架构会话历史', { exact: true }).waitFor();
  await page.getByRole('textbox').fill('解释架构');
  const send = page.getByRole('button', { name: '发送', exact: true });
  await send.hover(); await sleep(180);
  const background = await send.evaluate(el => getComputedStyle(el).backgroundColor);
  assert.equal(background, 'rgb(6, 102, 79)');
  const quiet = page.getByRole('button', { name: '收起右栏' });
  await quiet.hover(); await sleep(180); assert.equal(await quiet.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(247, 247, 248)');
  await send.click();
  await page.getByText('这是测试回答', { exact: true }).waitFor();
  await page.getByText('匹配度 87.3%', { exact: true }).waitFor();
  await page.getByText('100%', { exact: true }).waitFor();
  await page.locator('.source-button').click();
  await page.getByRole('dialog', { name: '系统架构.md' }).waitFor();
  await page.keyboard.press('Escape'); assert.equal(await page.getByRole('dialog').count(), 0);
  await sleep(400);
  if (process.env.SCREENSHOT_PATH) await page.screenshot({ path: process.env.SCREENSHOT_PATH, fullPage: true });
  slowHistory = true;
  await page.getByRole('button', { name: '接口设计', exact: true }).click();
  await page.getByRole('button', { name: '架构讨论', exact: true }).click();
  await sleep(500); assert.equal(await page.getByText('接口会话历史', { exact: true }).count(), 0);
  slowHistory = false; slowRequest = true;
  await page.getByRole('textbox').fill('旧请求'); await send.click();
  await page.getByRole('button', { name: '接口设计', exact: true }).click();
  await page.getByText('接口会话历史', { exact: true }).waitFor(); await sleep(500);
  assert.equal(await page.getByText('这是测试回答', { exact: true }).count(), 0);
  assert.equal(await page.locator('.source-button').count(), 0);
  slowRequest = false; failRun = true; missingScore = true;
  await page.getByRole('textbox').fill('触发失败'); await send.click();
  await page.getByText('执行失败', { exact: true }).waitFor();
  await page.getByText('匹配度 暂未提供', { exact: true }).waitFor();
  assert.equal(await page.locator('.steps .spin').count(), 0);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: '删除会话 新增测试会话' }).click();
  await page.getByRole('button', { name: '新增测试会话', exact: true }).waitFor({ state: 'detached' });
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert(await page.locator('.chat-wrap').evaluate(el => el.scrollWidth <= el.clientWidth));
  await page.getByRole('button', { name: '收起左栏' }).click();
  await page.getByRole('heading', { name: '命中资料' }).scrollIntoViewIfNeeded();
  assert.deepEqual(errors, []);
  console.log('PASS: dual cards, project tree, create/delete sessions, navigation, resize/persistence, collapse, button colors, sources/dialog, race isolation, failure/missing score, mobile layout; no browser errors.');
} finally { await browser.close(); }
