<script setup>
// 知识库「图书馆」页：跨项目汇总所有资料，可按项目筛选，点条目查看归属与切块数。
// 决策：DocumentPage 只看当前项目；这里给全局视角，方便统一盘点所有已入库资料。
import { ref, computed, onMounted } from "vue";
import { store } from "../store.js";

const loading = ref(false);
const filter = ref("all");   // "all" 或某个 project_id

onMounted(async () => {
  loading.value = true;
  try {
    if (store.projects.length === 0) await store.loadProjects();
    await store.loadLibrary();
  } finally {
    loading.value = false;
  }
});

// 按项目筛选后的资料列表
const shown = computed(() =>
  filter.value === "all"
    ? store.library
    : store.library.filter((d) => d.project_id === filter.value)
);
// 顶部统计：资料总数 + 覆盖项目数
const stat = computed(() => {
  const projs = new Set(store.library.map((d) => d.project_id));
  return { docs: store.library.length, projects: projs.size };
});
</script>

<template>
  <div class="page">
    <h2>知识库图书馆</h2>
    <p class="hint">
      跨项目查看全部已入库资料，共 {{ stat.docs }} 份，覆盖 {{ stat.projects }} 个项目。
      单项目的增删改在左侧选中项目后到「知识库」页操作。
    </p>

    <div class="bar">
      <label>按项目筛选</label>
      <select v-model="filter">
        <option value="all">全部项目</option>
        <option v-for="p in store.projects" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <ul v-else class="docs">
      <li v-for="d in shown" :key="d.id">
        <div class="meta">
          <span class="dt">{{ d.title }}</span>
          <span class="proj">{{ d.project_name }}</span>
        </div>
        <span class="dc">{{ d.chunk_count }} 块</span>
      </li>
      <li v-if="shown.length === 0" class="empty">没有匹配的资料。</li>
    </ul>
  </div>
</template>

<style scoped>
.page { max-width: 820px; margin: 0 auto; padding: 28px; }
h2 { margin: 0 0 4px; }
.hint { color: var(--muted); margin: 0 0 20px; font-size: 14px; line-height: 1.6; }
.bar { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
.bar label { font-size: 13px; color: var(--muted); }
.bar select { padding: 7px 10px; border-radius: 8px; }
.docs { list-style: none; margin: 0; padding: 0; }
.docs li { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border: 1px solid var(--border); border-radius: 12px; margin-bottom: 8px; background: var(--panel2); }
.meta { display: flex; align-items: center; gap: 10px; min-width: 0; }
.dt { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.proj { font-size: 12px; color: var(--accent-d); background: var(--accent-soft); padding: 1px 9px; border-radius: 999px; white-space: nowrap; }
.dc { font-size: 12px; color: var(--muted); background: rgba(120,120,140,0.14); padding: 1px 8px; border-radius: 999px; white-space: nowrap; }
.empty { justify-content: center; color: var(--muted); text-align: center; padding: 30px; }
</style>
