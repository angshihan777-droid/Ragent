<script setup>
// 使用统计页：只展示当前身份的 Token 与执行结果，数据来自 agent_runs.usage。
import { onMounted, ref } from "vue";
import { api } from "../api.js";
import Icon from "../components/Icon.vue";

const days = ref(7);
const data = ref(null);
const loading = ref(false);
const error = ref("");

async function load(nextDays = days.value) {
  days.value = nextDays;
  loading.value = true;
  error.value = "";
  try {
    data.value = await api.getMetrics(nextDays);
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

onMounted(() => load(7));

const fmt = (value) => Number(value || 0).toLocaleString("zh-CN");
const rate = (value) => (value === null || value === undefined ? "—" : (value * 100).toFixed(1) + "%");
const cost = (value) => (value === null || value === undefined ? "未配置" : "¥ " + value.toFixed(4));
</script>

<template>
  <div class="metrics">
    <header class="heading">
      <h1>使用统计</h1>
      <p>按当前身份统计最近的模型 Token 消耗与执行结果。</p>
    </header>

    <div class="toolbar">
      <div class="seg" role="group" aria-label="统计时间范围">
        <button :class="{ active: days === 7 }" @click="load(7)">近 7 天</button>
        <button :class="{ active: days === 30 }" @click="load(30)">近 30 天</button>
      </div>
      <button class="quiet refresh" :disabled="loading" @click="load()">
        <Icon name="refresh" :size="14" />{{ loading ? "刷新中…" : "刷新" }}
      </button>
    </div>

    <p v-if="error" class="error-box" role="alert">加载失败：{{ error }}</p>
    <p v-else-if="loading && !data" class="placeholder">加载中…</p>

    <template v-else-if="data">
      <div class="cards">
        <div class="stat">
          <span class="label">输入 Token</span>
          <strong>{{ fmt(data.input_tokens) }}</strong>
          <small>提示词与上下文</small>
        </div>
        <div class="stat">
          <span class="label">输出 Token</span>
          <strong>{{ fmt(data.output_tokens) }}</strong>
          <small>模型生成内容</small>
        </div>
        <div class="stat">
          <span class="label">模型调用</span>
          <strong>{{ fmt(data.llm_calls) }}</strong>
          <small>决策 / 证据检查 / 回答</small>
        </div>
        <div class="stat">
          <span class="label">执行成功率</span>
          <strong>{{ rate(data.success_rate) }}</strong>
          <small>完成 {{ fmt(data.done_runs) }} · 失败 {{ fmt(data.failed_runs) }}</small>
        </div>
      </div>

      <div class="cost card">
        <div class="cost-head">
          <span class="label">估算成本</span>
          <strong>{{ cost(data.estimated_cost) }}</strong>
        </div>
        <p v-if="data.estimated_cost === null">
          在 <RouterLink to="/config">模型配置</RouterLink> 里填写输入/输出单价后显示估算成本。
        </p>
        <p v-else>按配置的每 1K Token 单价估算，不代表服务商账单。</p>
      </div>
    </template>

    <p class="note">数据来源：agent_runs.usage。只统计当前浏览器身份，切换身份后会看到另一份数据。</p>
  </div>
</template>

<style scoped>
.metrics { width: 100%; max-width: 860px; margin: 0 auto; padding: var(--s-7) var(--s-6); box-sizing: border-box; }
.heading h1 { margin: 0; font-size: var(--fs-display); letter-spacing: -.02em; }
.heading p { margin: var(--s-2) 0 var(--s-5); color: var(--muted); font-size: var(--fs-sm); line-height: 1.7; }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); margin-bottom: var(--s-5); }
.seg { display: inline-flex; padding: 3px; border: 1px solid var(--border); border-radius: var(--r-full); background: var(--surface-2); }
.seg button { border: 0; background: transparent; color: var(--muted); padding: var(--s-2) var(--s-4); border-radius: var(--r-full); font-size: var(--fs-sm); cursor: pointer; }
.seg button.active { background: var(--surface); color: var(--ink); box-shadow: 0 1px 2px rgb(0 0 0 / 6%); }
.refresh { display: inline-flex; align-items: center; gap: var(--s-2); font-size: var(--fs-sm); padding: var(--s-2) var(--s-3); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: var(--s-4); }
.stat { display: flex; flex-direction: column; gap: var(--s-1); padding: var(--s-5); border: 1px solid var(--border); border-radius: var(--r-md); background: var(--surface); }
.label { color: var(--muted); font-size: var(--fs-sm); }
.stat strong { font-size: 30px; line-height: 1.2; font-variant-numeric: tabular-nums; }
.stat small { color: var(--faint); font-size: var(--fs-xs); }
.cost { margin-top: var(--s-4); padding: var(--s-5); }
.cost-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s-3); }
.cost-head strong { font-size: 24px; font-variant-numeric: tabular-nums; }
.cost p { margin: var(--s-2) 0 0; color: var(--muted); font-size: var(--fs-xs); line-height: 1.7; }
.cost code { padding: 1px 4px; border-radius: var(--r-sm); background: var(--surface-3); font-size: var(--fs-xs); }
.placeholder { color: var(--muted); font-size: var(--fs-sm); }
.note { margin-top: var(--s-5); color: var(--faint); font-size: var(--fs-xs); line-height: 1.7; }
@media (max-width: 600px) { .metrics { padding: var(--s-5) var(--s-4); } }
</style>
