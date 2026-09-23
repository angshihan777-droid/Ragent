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

const loading = ref(false);
const fetching = ref(false);
const saving = ref(false);
const msg = ref(""); // 成功/错误提示
const msgType = ref(""); // "ok" | "err"

function flash(type, text) {
  msgType.value = type;
  msg.value = text;
}

onMounted(async () => {
  loading.value = true;
  try {
    const cfg = await api.getLLMConfig();
    baseUrl.value = cfg.base_url;
    model.value = cfg.model;
    keySet.value = cfg.key_set;
    // 当前已保存的模型先放进下拉，未拉取列表时也能看到并保存
    if (cfg.model) models.value = [cfg.model];
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
    const view = await api.saveLLMConfig(baseUrl.value.trim(), model.value, apiKey.value);
    keySet.value = view.key_set;
    store.llm = view;
    store.models = [...new Set([view.model, ...store.models])];
    apiKey.value = ""; // 保存后清空输入框，密钥不回显
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

      <div v-if="msg" :class="msgType === 'ok' ? 'notice' : 'error-box'" role="status">
        <Icon :name="msgType === 'ok' ? 'check' : 'alert'" :size="15" />{{ msg }}
      </div>

      <footer class="actions">
        <button class="btn-brand" :disabled="saving || !baseUrl.trim() || !model" @click="save">
          {{ saving ? "保存中…" : "保存配置" }}
        </button>
      </footer>
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
label { display: block; margin: 0 0 var(--s-2); font-size: var(--fs-sm); font-weight: 500; color: var(--text); }
small { display: flex; align-items: center; flex-wrap: wrap; gap: var(--s-2); margin-top: var(--s-2); color: var(--faint); font-size: var(--fs-xs); line-height: 1.6; }
.notice, .error-box { margin-top: var(--s-5); }
.actions { display: flex; justify-content: flex-end; margin-top: var(--s-5); padding-top: var(--s-5); border-top: 1px solid var(--border-soft); }
@media (max-width: 600px) { .config { padding: var(--s-5) var(--s-4); } }
</style>
