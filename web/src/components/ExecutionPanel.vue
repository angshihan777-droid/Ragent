<script setup>
import { computed } from "vue";
import { formatSimilarity, validSimilarity, meterValue } from "../similarity.js";
import Icon from "./Icon.vue";
const props = defineProps({
  steps: { type: Array, default: () => [] },
  sources: { type: Array, default: () => [] },
  runState: { type: String, default: "idle" },
  thread: Object,
  projectName: String,
});
defineEmits(["trace"]);
const retrieved = computed(() => props.steps.some(s => s.node === "retrieve"));
const completed = computed(() => props.steps.filter(s => s.status === "done").length);
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
        <span class="pt-ico"><Icon name="files" :size="15" /></span>
        <div class="pt-txt">
          <div class="pt-name truncate">{{ thread?.title }}</div>
          <div class="pt-sub truncate">{{ projectName }} · 知识库助手</div>
        </div>
      </div>

      <ul v-if="steps.length" class="steps">
        <li v-for="s in steps" :key="s.key" :class="s.status">
          <span class="ico">
            <span v-if="s.status === 'running'" class="spin"></span>
            <Icon v-else-if="s.status === 'done'" name="check" :size="14" class="check" />
            <Icon v-else-if="s.status === 'error'" name="alert" :size="14" />
            <span v-else class="dot"></span>
          </span>
          <span class="s-num">{{ s.icon }}</span>
          <span class="lbl">{{ s.label }}</span>
        </li>
      </ul>
      <p v-else class="p-empty">发送问题后，这里会记录本轮实际执行的步骤。</p>

      <div v-if="steps.length" class="prog-foot">已完成 {{ completed }} 个实际步骤 · {{ runState === 'running' ? '处理中' : '本轮记录' }}</div>
    </section>

    <!-- 命中资料：检索到的资料卡片，点击溯源看原文 -->
    <section class="panel sources-card" aria-labelledby="sources-title">
      <div class="prog-head"><h2 id="sources-title">命中资料</h2><span class="badge">{{ sources.length }} 条</span></div>
      <p class="score-hint">匹配度为向量余弦相似度，不代表回答正确率；资料按重排结果排序。</p>
      <ul v-if="sources.length" class="srcs">
        <li v-for="(s, i) in sources" :key="s.chunk_id || i">
          <button class="source-button" @click="$emit('trace', s)">
            <span class="src-t">{{ s.citation_id ? '[' + s.citation_id + '] ' : '' }}{{ s.title || '未知来源' }}</span>
            <span v-if="s.metadata?.page_start" class="src-p">第 {{ s.metadata.page_start }} 页</span>
            <span v-if="s.metadata?.heading_path?.length" class="src-p">{{ s.metadata.heading_path.join(" / ") }}</span>
            <span class="match">匹配度 {{ formatSimilarity(s.similarity) }}</span>

            <meter v-if="validSimilarity(s.similarity)" min="0" max="1" low="0.5" high="0.75" optimum="1" :value="meterValue(s.similarity)" :aria-label="(s.title || '资料') + ' 匹配度'"></meter>
            <span class="src-p">{{ (s.content || '').slice(0, 100) }}{{ s.content?.length > 100 ? '…' : '' }}</span>
            <span class="source-link">查看原文 <Icon name="arrow-up-right" :size="12" /></span>
          </button>
        </li>
      </ul>
      <p v-else class="p-empty">{{ runState === 'running' ? '助手正在处理；需要资料时会自动检索。' : runState === 'done' ? (retrieved ? '本轮未获得可用资料，请结合回答查看原因。' : '本轮未检索资料。') : runState === 'error' ? '本轮执行失败，未收到命中资料。' : '发送问题后，检索命中的资料与匹配度会显示在这里。' }}</p>
    </section>
  </div>
</template>
<style scoped>
.process { height: 100%; min-height: 0; display: flex; flex-direction: column; gap: var(--s-3); padding: var(--s-3); background: var(--surface-2); overflow-y: auto; border-left: 1px solid var(--border); }
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: var(--s-4); min-width: 0; }
.execution-card { flex: 0 0 auto; }
.sources-card { flex: 1 0 auto; }
h2 { margin: 0; font-size: var(--fs-sm); color: var(--ink); }

.prog-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); margin-bottom: var(--s-3); }
.badge.running { background: var(--brand-soft); color: var(--brand-ink); }
.badge.done { background: var(--brand-soft); color: var(--brand-ink); }
.badge.error { background: var(--danger-soft); color: var(--danger-ink); }
.badge-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 0.35; } 50% { opacity: 1; } }

.plan-title { display: flex; align-items: flex-start; gap: var(--s-2); padding-bottom: var(--s-3); }
.pt-ico { display: grid; place-items: center; width: 26px; height: 26px; border-radius: var(--r-sm); background: var(--surface-3); color: var(--muted); flex-shrink: 0; }
.pt-txt { min-width: 0; }
.pt-name { font-size: var(--fs-sm); font-weight: 500; color: var(--ink); }
.pt-sub { font-size: var(--fs-xs); color: var(--muted); margin-top: 1px; }

.steps { list-style: none; margin: 0; padding: var(--s-1) 0; border-top: 1px solid var(--line); }
.steps li { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-2); border-radius: var(--r-sm); font-size: var(--fs-sm); color: var(--faint); }
.steps li.done { color: var(--text); }
.steps li.running { color: var(--brand-ink); font-weight: 500; background: var(--brand-soft); }
.steps li.error { color: var(--danger-ink); }
.steps .ico { width: 16px; height: 16px; flex-shrink: 0; display: grid; place-items: center; }
.steps .check { color: var(--brand); }
.steps .dot { width: 7px; height: 7px; border: 1.5px solid var(--n-300); border-radius: 50%; }
.steps .spin { width: 13px; height: 13px; border: 2px solid var(--brand-line); border-top-color: var(--brand); border-radius: 50%; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.steps .s-num { font-size: var(--fs-xs); color: var(--faint); font-variant-numeric: tabular-nums; }
.steps .lbl { flex: 1; min-width: 0; }

.prog-foot { margin-top: var(--s-3); padding-top: var(--s-3); border-top: 1px solid var(--line); font-size: var(--fs-xs); color: var(--muted); }
.p-empty { font-size: var(--fs-sm); color: var(--muted); line-height: 1.7; margin: var(--s-2) 0 0; }
.score-hint { font-size: var(--fs-xs); line-height: 1.6; color: var(--muted); margin: 0 0 var(--s-3); }

.srcs { list-style: none; margin: 0; padding: 0; }
.srcs li { padding: 0; border: 1px solid var(--border); border-radius: var(--r-md); margin-bottom: var(--s-2); background: var(--surface); overflow: hidden; transition: border-color var(--ease); }
.srcs li:hover { border-color: var(--brand-line); }
.source-button { display: flex; flex-direction: column; align-items: stretch; width: 100%; text-align: left; padding: var(--s-3); gap: var(--s-1); background: transparent; color: var(--text); font-weight: 400; border: 0; border-radius: 0; }
.source-button:hover:not(:disabled) { background: var(--brand-soft); }
.src-t { max-width: 100%; font-size: var(--fs-sm); font-weight: 500; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.src-p { overflow-wrap: anywhere; font-size: var(--fs-xs); color: var(--muted); line-height: 1.55; }
.match { font-size: var(--fs-xs); color: var(--brand-ink); font-weight: 500; }
.source-link { display: inline-flex; align-items: center; gap: var(--s-1); font-size: var(--fs-xs); color: var(--brand-ink); margin-top: var(--s-1); }
meter { width: 100%; height: 4px; margin-bottom: var(--s-1); }
meter::-webkit-meter-bar { background: var(--surface-3); border: 0; border-radius: var(--r-full); height: 4px; }
meter::-webkit-meter-optimum-value { background: var(--brand); border-radius: var(--r-full); }
meter::-webkit-meter-suboptimum-value { background: var(--warn); border-radius: var(--r-full); }
meter::-moz-meter-bar { background: var(--brand); border-radius: var(--r-full); }
@media (max-width: 760px) { .process { height: auto; border-left: 0; border-top: 1px solid var(--border); } }

</style>
