<script setup>
import { computed } from "vue";
import { formatSimilarity, validSimilarity } from "../similarity.js";
const props = defineProps({
  steps: { type: Array, default: () => [] },
  sources: { type: Array, default: () => [] },
  runState: { type: String, default: "idle" },
  thread: Object,
  projectName: String,
  agentName: String,
  useRag: Boolean,
});
defineEmits(["trace"]);
const progress = computed(() => {
  const total = props.steps.length;
  const done = props.steps.filter(s => s.status === "done").length;
  return { total, done, pct: total ? Math.round(done / total * 100) : 0 };
});
</script>
<template>
  <div class="process">
    <!-- 执行计划：任务进度 + 计划清单(当前步转圈/已完成打勾) + 底部进度 -->
    <section class="panel execution-card" aria-labelledby="execution-title">
      <div class="prog-head">
        <h2 id="execution-title">执行过程</h2>
        <span class="badge" :class="runState">
          <span v-if="runState === 'running'" class="badge-dot"></span>
          {{ runState === 'running' ? '运行中' : runState === 'done' ? '已完成' : runState === 'error' ? '执行失败' : '待发送' }}
        </span>
      </div>

      <div v-if="steps.length" class="plan-title">
        <span class="pt-ico">🗂️</span>
        <div class="pt-txt">
          <div class="pt-name">{{ thread.title }}</div>
          <div class="pt-sub">{{ projectName }} · {{ agentName }}</div>
        </div>
      </div>

      <ul v-if="steps.length" class="steps">
        <li v-for="s in steps" :key="s.key" :class="s.status">
          <span class="ico">
            <span v-if="s.status === 'running'" class="spin"></span>
            <span v-else-if="s.status === 'done'" class="check">✓</span>
            <span v-else-if="s.status === 'error'">!</span>
            <span v-else class="dot"></span>
          </span>
          <span class="s-emoji">{{ s.icon }}</span>
          <span class="lbl">{{ s.label }}</span>
        </li>
      </ul>
      <p v-else class="p-empty">发送问题后，这里会铺开本轮的执行计划，并实时点亮每一步进度。</p>

      <div v-if="steps.length" class="prog-foot">
        <span>{{ progress.done }} / {{ progress.total }} 步</span>
        <div class="bar" role="progressbar" aria-label="执行进度" :aria-valuenow="progress.pct" :aria-valuemin="0" :aria-valuemax="100"><div class="bar-in" :style="{ width: progress.pct + '%' }"></div></div>
        <span>{{ progress.pct }}%</span>
      </div>
    </section>

    <!-- 命中资料：检索到的资料卡片，点击溯源看原文 -->
    <section class="panel sources-card" aria-labelledby="sources-title">
      <div class="prog-head"><h2 id="sources-title">命中资料</h2><span class="badge">{{ sources.length }} 条</span></div>
      <p class="score-hint">匹配度为向量余弦相似度，不代表回答正确率；资料按重排结果排序。</p>
      <ul v-if="sources.length" class="srcs">
        <li v-for="(s, i) in sources" :key="s.chunk_id || i">
          <button class="source-button" @click="$emit('trace', s)">
            <span class="src-t">{{ s.title || '未知来源' }}</span>
            <span class="match">匹配度 {{ formatSimilarity(s.similarity) }}</span>
            <meter v-if="validSimilarity(s.similarity)" min="-1" max="1" :value="s.similarity" :aria-label="(s.title || '资料') + ' 匹配度'"></meter>
            <span class="src-p">{{ (s.content || '').slice(0, 100) }}{{ s.content?.length > 100 ? '…' : '' }}</span>
            <span class="source-link">查看原文 ↗</span>
          </button>
        </li>
      </ul>
      <p v-else class="p-empty">{{ !useRag ? '当前会话未启用知识库检索。' : runState === 'running' ? '正在等待本轮检索结果…' : runState === 'done' ? '本轮未命中资料。' : runState === 'error' ? '本轮执行失败，未收到命中资料。' : '发送问题后，检索命中的资料与匹配度会显示在这里。' }}</p>
    </section>
  </div>
</template>
<style scoped>
.prog-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.badge { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; padding: 3px 11px; border-radius: 999px; background: rgba(0,0,0,0.05); color: var(--muted); }
.badge.running { background: var(--accent-soft); color: var(--accent); }
.badge.done { background: var(--ok-soft, rgba(16,163,127,.1)); color: var(--accent-d); }
.badge.error { background: rgba(224,92,92,0.12); color: #c0392b; }
.badge-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 0%,100% { opacity: 0.35; } 50% { opacity: 1; } }
.plan-title { display: flex; align-items: flex-start; gap: 10px; padding: 4px 0 14px; }
.pt-ico { font-size: 18px; line-height: 1.3; }
.pt-name { font-size: 14px; font-weight: 700; color: var(--ink); }
.pt-sub { font-size: 12px; color: var(--muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.steps { list-style: none; margin: 0; padding: 6px 0; border-top: 1px solid var(--line); }
.steps li { display: flex; align-items: center; gap: 9px; padding: 9px 8px; border-radius: 9px; font-size: 13.5px; color: var(--faint); }
.steps li.done { color: var(--text); }
.steps li.running { color: var(--accent); font-weight: 600; background: var(--accent-soft); }
.steps .ico { width: 16px; height: 16px; flex-shrink: 0; display: grid; place-items: center; }
.steps .check { color: var(--accent); font-size: 13px; }
.steps .dot { width: 8px; height: 8px; border: 1.5px solid var(--border); border-radius: 50%; }
.steps .spin { width: 13px; height: 13px; border: 2px solid var(--accent-soft); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.steps .s-emoji { font-size: 14px; }
.steps .lbl { flex: 1; }
.prog-foot { display: flex; align-items: center; gap: 10px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line); font-size: 12px; color: var(--muted); }
.prog-foot .bar { flex: 1; height: 6px; background: var(--line); border-radius: 999px; overflow: hidden; }
.prog-foot .bar-in { height: 100%; background: var(--accent); border-radius: 999px; transition: width 0.35s ease; }
.p-empty { font-size: 13px; color: var(--muted); line-height: 1.6; margin: 8px 2px; }
.srcs { list-style: none; margin: 0; padding: 0; }
.srcs li { padding: 0; border: 1px solid var(--border); border-radius: 10px; margin-bottom: 8px; background: #fff; transition: 0.12s; }
.source-button:hover { border-color: var(--accent); box-shadow: var(--shadow-sm); }
.src-t { max-width: 100%; font-size: 13px; font-weight: 600; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.src-p { overflow-wrap: anywhere; font-size: 12px; color: var(--muted); margin-top: 4px; line-height: 1.5; }


h2 { margin: 0; font-size: 14px; color: var(--ink); }
.process { height: 100%; min-height: 0; display: flex; flex-direction: column; gap: 14px; padding: 16px 12px; background: var(--panel2); overflow-y: auto; }
.panel { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 16px; min-width: 0; }
.execution-card { flex: 0 0 auto; }
.sources-card { flex: 1 0 auto; }
.pt-txt { min-width: 0; }
.score-hint { font-size: 11px; line-height: 1.6; color: var(--muted); }
.source-button { display: flex; flex-direction: column; width: 100%; text-align: left; padding: 12px; gap: 6px; background: transparent; color: var(--text); }
.source-button:hover:not(:disabled) { background: var(--accent-soft); }
.match, .source-link { font-size: 12px; color: var(--accent-d); }
meter { width: 100%; height: 6px; accent-color: var(--accent); }
.steps li.error { color: #a83232; }
@media (max-width: 760px) { .process { height: auto; } }

</style>
