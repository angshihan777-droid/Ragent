<script setup>
// 模型配置页：回显当前配置 -> 填地址/密钥拉模型下拉 -> 选模型 -> 保存。
import { ref, onMounted } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";

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
  <div class="card">
    <h2>模型配置</h2>
    <p class="hint">支持任意 OpenAI 兼容地址（如 DeepSeek）。填好地址密钥可自动拉取模型列表。</p>

    <label>接口地址 (base_url)</label>
    <input v-model="baseUrl" placeholder="https://api.deepseek.com/v1" />

    <label>API 密钥</label>
    <input
      v-model="apiKey"
      type="password"
      :placeholder="keySet ? '已设置（留空则不修改）' : '请输入密钥'"
    />

    <div class="actions">
      <button class="ghost" :disabled="fetching || !baseUrl.trim()" @click="fetchModels">
        {{ fetching ? "拉取中" : "拉取模型" }}
      </button>
    </div>

    <label>模型</label>
    <select v-model="model" :disabled="models.length === 0">
      <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
    </select>

    <div class="actions">
      <button :disabled="saving || !baseUrl.trim() || !model" @click="save">
        {{ saving ? "保存中" : "保存配置" }}
      </button>
    </div>

    <div v-if="msg" :class="msgType">{{ msg }}</div>
  </div>
</template>

<style scoped>
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
}
h2 { margin: 0 0 4px; }
.hint { color: var(--muted); margin: 0 0 20px; font-size: 14px; }
label { display: block; margin: 14px 0 6px; font-size: 14px; font-weight: 500; }
.actions { margin-top: 16px; }
.ghost { background: var(--panel2); color: var(--text); border: 1px solid var(--border); }
.ghost:hover:not(:disabled) { background: var(--line); }
.ok { margin-top: 16px; padding: 12px 14px; background: var(--accent-soft); border: 1px solid rgba(16,163,127,0.35); border-radius: 10px; color: var(--accent-d); font-size: 14px; }
.err { margin-top: 16px; padding: 12px 14px; background: rgba(224,92,92,0.12); border: 1px solid rgba(224,92,92,0.35); border-radius: 10px; color: #c0392b; font-size: 14px; }
</style>
