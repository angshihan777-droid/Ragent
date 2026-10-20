<script setup>
// 模型配置页：回显当前配置 -> 填地址/密钥拉模型下拉 -> 选模型 -> 保存。
import { ref, onMounted } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";
import Icon from "../components/Icon.vue";

const baseUrl = ref("");
const apiKey = ref(""); // 空=不改密钥；库里已存时占位提示「已设置」
const keySet = ref(false);
const model = ref("");
const models = ref([]); // 拉取到的可选模型 id 列表
// 推理强度：留空表示不改。推理模型默认 high 档「想很久」，简单问答也会拖到几十秒。
const effort = ref("low");
const costInput = ref(0);
const costOutput = ref(0);
const costHint = ref("");
const costSuggested = ref({ input: 0, output: 0 });
const EFFORT_OPTIONS = [
  { value: "low", label: "low（快，推荐日常提问）" },
  { value: "high", label: "high（慢，复杂推理）" },
  { value: "max", label: "max（最慢）" },
];

const loading = ref(false);
const fetching = ref(false);
const saving = ref(false);
const msg = ref(""); // 成功/错误提示
const msgType = ref(""); // "ok" | "err"

function flash(type, text) {
  msgType.value = type;
  msg.value = text;
}

// 回显配置：已保存的单价优先；两者都为 0 时，按后端给出的官方参考价预填。
function applyConfig(cfg) {
  baseUrl.value = cfg.base_url;
  model.value = cfg.model;
  keySet.value = cfg.key_set;
  effort.value = cfg.reasoning_effort || "low";
  costSuggested.value = {
    input: Number(cfg.cost_input_suggested || 0),
    output: Number(cfg.cost_output_suggested || 0),
  };
  const savedInput = Number(cfg.cost_input_per_1k || 0);
  const savedOutput = Number(cfg.cost_output_per_1k || 0);
  if (savedInput === 0 && savedOutput === 0 && costSuggested.value.input > 0) {
    costInput.value = costSuggested.value.input;
    costOutput.value = costSuggested.value.output;
    costHint.value = "已按 DeepSeek 官方参考价预填（高峰 + 缓存未命中），保存后生效。";
  } else {
    costInput.value = savedInput;
    costOutput.value = savedOutput;
    costHint.value = "";
  }
  models.value = cfg.model ? [cfg.model] : [];
}

function fillSuggested() {
  if (!costSuggested.value.input) return;
  costInput.value = costSuggested.value.input;
  costOutput.value = costSuggested.value.output;
  costHint.value = "已按 DeepSeek 官方参考价填入，保存后生效。";
}

// ---- 身份（§3.7 身份可迁移）----
const ownerId = ref("");
const targetId = ref(""); // 要切换到的 id，用户从另一台机器复制过来
const switching = ref(false);
const copied = ref(false);
const idMsg = ref("");
const idMsgType = ref("");

async function copyOwnerId() {
  // navigator.clipboard 在非 https 且非 localhost 下不可用，失败就提示用户手动选中，
  // 不引任何复制库——为一个按钮加依赖不划算
  try {
    await navigator.clipboard.writeText(ownerId.value);
    copied.value = true;
    setTimeout(() => (copied.value = false), 1600);
  } catch (_) {
    idMsgType.value = "err";
    idMsg.value = "当前环境不允许自动复制，请手动选中上面的 id 复制。";
  }
}

async function doSwitchIdentity() {
  const next = targetId.value.trim();
  if (!next || switching.value || next === ownerId.value) return;
  switching.value = true;
  idMsg.value = "";
  try {
    await store.switchIdentity(next);
    ownerId.value = store.ownerId;
    targetId.value = "";
    // 配置也跟着身份变了，重新回显一遍，否则页面上还是上一个身份的地址和模型
    const cfg = await api.getLLMConfig();
    applyConfig(cfg);
    idMsgType.value = "ok";
    idMsg.value = "已切换到 " + store.ownerId + "，数据已重新加载。";
  } catch (e) {
    idMsgType.value = "err";
    idMsg.value = "切换失败: " + e.message;
  } finally {
    switching.value = false;
  }
}

onMounted(async () => {
  loading.value = true;
  try {
    // 身份读失败不该拖垮整页配置回显，单独 try
    try {
      await store.loadIdentity();
      ownerId.value = store.ownerId;
    } catch (_) {
      ownerId.value = "";
    }
    const cfg = await api.getLLMConfig();
    // applyConfig 同时把当前已保存的模型放进下拉，未拉取列表时也能看到并保存
    applyConfig(cfg);
  } catch (e) {
    flash("err", "读取配置失败: " + e.message);
  } finally {
    loading.value = false;
  }
});

async function fetchModels() {
  if (!baseUrl.value.trim() || fetching.value) return;
  fetching.value = true;
  msg.value = "";
  try {
    // 密钥留空时后端用库里已存的密钥去拉，所以已设置过就不必重填
    const { models: list } = await api.listModels(baseUrl.value.trim(), apiKey.value);
    models.value = list;
    if (list.length === 0) {
      flash("err", "未拉取到任何模型，请检查地址/密钥。");
    } else {
      // 原选中的模型若不在新列表里，默认选第一个，避免保存一个不存在的模型
      if (!list.includes(model.value)) model.value = list[0];
      flash("ok", "拉取到 " + list.length + " 个模型。");
    }
  } catch (e) {
    flash("err", "拉取模型失败: " + e.message);
  } finally {
    fetching.value = false;
  }
}

async function save() {
  if (!baseUrl.value.trim() || !model.value || saving.value) return;
  saving.value = true;
  msg.value = "";
  try {
    const view = await api.saveLLMConfig(
      baseUrl.value.trim(), model.value, apiKey.value, effort.value,
      Number(costInput.value || 0), Number(costOutput.value || 0),
    );
    keySet.value = view.key_set;
    store.llm = view;
    store.models = [...new Set([view.model, ...store.models])];
    apiKey.value = ""; // 保存后清空输入框，密钥不回显
    costHint.value = "";
    flash("ok", "已保存。");
  } catch (e) {
    flash("err", "保存失败: " + e.message);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="config">
    <header class="heading">
      <h1>模型配置</h1>
      <p>支持任意 OpenAI 兼容地址（如 DeepSeek）。填好地址和密钥即可自动拉取可用模型。</p>
    </header>

    <div class="card">
      <div class="field">
        <label for="cfg-base">接口地址</label>
        <input id="cfg-base" v-model="baseUrl" placeholder="https://api.deepseek.com/v1" :disabled="loading" />
        <small>OpenAI 兼容的 base_url，通常以 /v1 结尾。</small>
      </div>

      <div class="field">
        <label for="cfg-key">API 密钥</label>
        <input
          id="cfg-key"
          v-model="apiKey"
          type="password"
          :disabled="loading"
          :placeholder="keySet ? '已设置（留空则不修改）' : '请输入密钥'"
        />
        <small>
          <span v-if="keySet" class="badge badge-brand"><Icon name="check" :size="12" />已保存密钥</span>
          <span v-else class="badge badge-danger">尚未配置</span>
          密钥只保存在本地后端，不会回显。
        </small>
      </div>

      <div class="field">
        <div class="field-head">
          <label for="cfg-model">模型</label>
          <button class="quiet" :disabled="fetching || !baseUrl.trim()" @click="fetchModels">
            <Icon name="refresh" :size="14" />{{ fetching ? "拉取中…" : "拉取模型" }}
          </button>
        </div>
        <select id="cfg-model" v-model="model" :disabled="models.length === 0">
          <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
        </select>
        <small>{{ models.length ? `共 ${models.length} 个可选模型。` : "填好地址后点击“拉取模型”获取列表。" }}</small>
      </div>

      <div class="field">
        <label for="cfg-effort">推理强度</label>
        <select id="cfg-effort" v-model="effort" :disabled="loading">
          <option v-for="o in EFFORT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <small>推理模型（如 DeepSeek V4）默认按 high 档思考，一句问候也要几十秒；改成 low 可把单次调用从 ~40 秒压到 ~1 秒。一次问答要调 2~3 次模型，差别会成倍放大。</small>
      </div>

      <div class="field">
        <div class="field-head">
          <label>成本估算单价</label>
          <button class="quiet" type="button" :disabled="!costSuggested.input" @click="fillSuggested">
            <Icon name="refresh" :size="14" />填入官方参考价
          </button>
        </div>
        <div class="cost-row">
          <label class="cost-item" for="cfg-cost-input">
            <span>输入（元 / 1K tokens）</span>
            <input id="cfg-cost-input" v-model.number="costInput" type="number" min="0" step="0.0001" :disabled="loading" />
          </label>
          <label class="cost-item" for="cfg-cost-output">
            <span>输出（元 / 1K tokens）</span>
            <input id="cfg-cost-output" v-model.number="costOutput" type="number" min="0" step="0.0001" :disabled="loading" />
          </label>
        </div>
        <small v-if="costHint" class="cost-hint">{{ costHint }}</small>
        <small>只用于「使用统计」页估算成本，不影响模型调用；留 0 表示不估算。</small>
      </div>

      <div v-if="msg" :class="msgType === 'ok' ? 'notice' : 'error-box'" role="status">
        <Icon :name="msgType === 'ok' ? 'check' : 'alert'" :size="15" />{{ msg }}
      </div>

      <footer class="actions">
        <button class="btn-brand" :disabled="saving || !baseUrl.trim() || !model" @click="save">
          {{ saving ? "保存中…" : "保存配置" }}
        </button>
      </footer>
    </div>

    <!-- 身份区放在页面最下方：它是「换机器时才用一次」的功能，不该和日常配置抢注意力 -->
    <div class="card identity">
      <div class="field">
        <label>当前身份 id</label>
        <div class="id-row">
          <code class="id-value">{{ ownerId || "读取中…" }}</code>
          <button class="quiet" :disabled="!ownerId" @click="copyOwnerId">
            <Icon :name="copied ? 'check' : 'files'" :size="14" />{{ copied ? "已复制" : "复制" }}
          </button>
        </div>
        <small>
          <span class="badge badge-danger"><Icon name="alert" :size="12" />等同于密码</span>
          你的项目、资料和对话都绑定在这个 id 上。任何人拿到它就能访问你的全部数据，不要外发。
        </small>
      </div>

      <div class="field">
        <label for="cfg-identity">切换身份</label>
        <div class="id-row">
          <input
            id="cfg-identity"
            v-model="targetId"
            placeholder="粘贴另一台机器上的身份 id"
            :disabled="switching"
            @keyup.enter="doSwitchIdentity"
          />
          <button
            class="btn-brand"
            :disabled="switching || !targetId.trim() || targetId.trim() === ownerId"
            @click="doSwitchIdentity"
          >
            {{ switching ? "切换中…" : "切换" }}
          </button>
        </div>
        <small>换浏览器或换机器时，把上面的 id 粘到这里即可接回原有数据；也用于认领迁移前的存量项目。</small>
      </div>

      <div v-if="idMsg" :class="idMsgType === 'ok' ? 'notice' : 'error-box'" role="status">
        <Icon :name="idMsgType === 'ok' ? 'check' : 'alert'" :size="15" />{{ idMsg }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.config { width: 100%; max-width: 620px; margin: 0 auto; padding: var(--s-7) var(--s-6); box-sizing: border-box; }
.heading h1 { margin: 0; font-size: var(--fs-display); letter-spacing: -.02em; }
.heading p { margin: var(--s-2) 0 var(--s-6); color: var(--muted); font-size: var(--fs-sm); line-height: 1.7; }
.card { padding: var(--s-5); }
.field + .field { margin-top: var(--s-5); padding-top: var(--s-5); border-top: 1px solid var(--border-soft); }
.field-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); margin-bottom: var(--s-2); }
.field-head label { margin: 0; }
.field-head button { padding: var(--s-2) var(--s-3); font-size: var(--fs-xs); }
.cost-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-3); }
.cost-item { display: flex; flex-direction: column; gap: var(--s-2); margin: 0; font-weight: 400; }
.cost-item span { font-size: var(--fs-xs); color: var(--muted); font-weight: 400; }
.cost-hint { color: var(--brand-ink); }
label { display: block; margin: 0 0 var(--s-2); font-size: var(--fs-sm); font-weight: 500; color: var(--text); }
small { display: flex; align-items: center; flex-wrap: wrap; gap: var(--s-2); margin-top: var(--s-2); color: var(--faint); font-size: var(--fs-xs); line-height: 1.6; }
.notice, .error-box { margin-top: var(--s-5); }
.identity { margin-top: var(--s-5); }
.id-row { display: flex; align-items: center; gap: var(--s-2); }
.id-row input { flex: 1; min-width: 0; }
.id-row button { flex: none; white-space: nowrap; }
/* 身份 id 是随机 uuid，窄屏下必须允许换行，否则会把卡片撑出横向滚动条 */
.id-value { flex: 1; min-width: 0; padding: var(--s-2) var(--s-3); border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface-2); font-size: var(--fs-xs); word-break: break-all; user-select: all; }
.actions { display: flex; justify-content: flex-end; margin-top: var(--s-5); padding-top: var(--s-5); border-top: 1px solid var(--border-soft); }
@media (max-width: 600px) { .config { padding: var(--s-5) var(--s-4); } .cost-row { grid-template-columns: 1fr; } }
</style>
