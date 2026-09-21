<script setup>
// 资料管理页：按当前项目列出资料，支持新增与删除（CRUD 的增删查）。
// 资料归属项目，同项目多 Agent 共享，所以这里以 store.currentProject 为上下文。
import { ref, computed, watch } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";

const docs = ref([]);
const title = ref("");
const content = ref("");
const busy = ref(false);
const msg = ref("");
const msgType = ref("");

const projectId = computed(() => store.currentProjectId);

function flash(type, text) { msgType.value = type; msg.value = text; }

async function load() {
  if (!projectId.value) { docs.value = []; return; }
  docs.value = await api.listDocuments(projectId.value);
}

watch(projectId, load, { immediate: true });

async function add() {
  if (!title.value.trim() || !content.value.trim() || busy.value || !projectId.value) return;
  busy.value = true; msg.value = "";
  try {
    const r = await api.ingestDocument(projectId.value, title.value.trim(), content.value.trim());
    flash("ok", "入库成功，切成 " + r.chunk_count + " 块。");
    title.value = ""; content.value = "";
    await load();
  } catch (e) {
    flash("err", "入库失败: " + e.message);
  } finally {
    busy.value = false;
  }
}

async function remove(id, t) {
  if (!confirm('删除资料「' + t + '」？')) return;
  await api.deleteDocument(id);
  await load();
}
</script>

<template>
  <div class="page">
    <div v-if="!projectId" class="placeholder">先在左侧选择一个项目，再管理它的资料。</div>
    <template v-else>
      <h2>资料管理 · {{ store.currentProject?.name }}</h2>
      <p class="hint">资料归属当前项目，项目内所有开启检索的 Agent 共享这份资料。</p>

      <div class="card">
        <label>标题</label>
        <input v-model="title" placeholder="例如：请假制度" />
        <label>正文</label>
        <textarea v-model="content" rows="8" placeholder="粘贴文档正文，会自动切块向量化..." />
        <div class="actions">
          <button :disabled="busy || !title.trim() || !content.trim()" @click="add">
            {{ busy ? "入库中" : "入库" }}
          </button>
        </div>
        <div v-if="msg" :class="msgType">{{ msg }}</div>
      </div>

      <h3>已有资料（{{ docs.length }}）</h3>
      <ul class="docs">
        <li v-for="d in docs" :key="d.id">
          <div class="meta">
            <span class="dt">{{ d.title }}</span>
            <span class="dc">{{ d.chunk_count }} 块</span>
          </div>
          <button class="del" @click="remove(d.id, d.title)">删除</button>
        </li>
        <li v-if="docs.length === 0" class="empty">还没有资料，先在上面添加。</li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 760px; margin: 0 auto; padding: 28px; }
.placeholder { color: var(--muted); margin-top: 40px; text-align: center; }
h2 { margin: 0 0 4px; }
h3 { margin: 28px 0 10px; font-size: 15px; }
.hint { color: var(--muted); margin: 0 0 20px; font-size: 14px; }
.card { background: #fff; border: 1px solid var(--border); border-radius: 12px; box-shadow: var(--shadow-sm); padding: 22px; }
label { display: block; margin: 12px 0 6px; font-size: 14px; font-weight: 500; }
.actions { margin-top: 16px; }
.docs { list-style: none; margin: 0; padding: 0; }
.docs li { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border: 1px solid var(--border); border-radius: 12px; margin-bottom: 8px; background: var(--panel2); }
.meta { display: flex; align-items: center; gap: 10px; }
.dt { font-weight: 500; }
.dc { font-size: 12px; color: var(--muted); background: rgba(120,120,140,0.14); padding: 1px 8px; border-radius: 999px; }
.del { background: #fef2f2; color: #b91c1c; }
.del:hover { background: #fee2e2; }
.empty { justify-content: center; color: var(--muted); }
.ok { margin-top: 14px; padding: 10px 12px; background: var(--accent-soft); border: 1px solid rgba(16,163,127,0.35); border-radius: 10px; color: var(--accent-d); font-size: 14px; }
.err { margin-top: 14px; padding: 10px 12px; background: rgba(224,92,92,0.12); border: 1px solid rgba(224,92,92,0.35); border-radius: 10px; color: #c0392b; font-size: 14px; }
</style>
