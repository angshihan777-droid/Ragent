<script setup>
import { onMounted, ref } from "vue";
import { RouterView, useRoute } from "vue-router";
import Sidebar from "./components/Sidebar.vue";
import ResizeHandle from "./components/ResizeHandle.vue";
import { usePreference } from "./composables/usePreference.js";
import Icon from "./components/Icon.vue";
import { store } from "./store.js";
const route = useRoute();
const sidebarWidth = usePreference("ragent.sidebarWidth", 264);
sidebarWidth.value = Math.min(360, Math.max(220, sidebarWidth.value));
const sidebarCollapsed = usePreference("ragent.sidebarCollapsed", false);
const loadError = ref("");
onMounted(async () => {
  const results = await Promise.allSettled([store.loadProjects(), store.loadLLM()]);
  loadError.value = results.filter(r => r.status === "rejected").map(r => r.reason.message).join("；");
});
</script>

<template>
  <div class="layout">
    <Sidebar v-if="!sidebarCollapsed" :style="{ width: sidebarWidth + 'px' }" @collapse="sidebarCollapsed = true" />
    <ResizeHandle v-if="!sidebarCollapsed" v-model="sidebarWidth" :min="220" :max="360" label="调整左栏宽度" />
    <main class="main">
      <div v-if="sidebarCollapsed || route.path !== '/chat'" class="shell-toolbar">
        <button v-if="sidebarCollapsed" class="quiet" @click="sidebarCollapsed = false"><Icon name="panel-left" :size="15" /> 项目与会话</button>
        <RouterLink v-if="route.path !== '/chat'" class="back-link" to="/chat"><Icon name="arrow-left" :size="15" /> 返回对话</RouterLink>
      </div>
      <p v-if="loadError" class="load-error" role="alert">加载失败：{{ loadError }}。请检查后端连接后刷新。</p>
      <div class="route-content"><RouterView /></div>
    </main>
  </div>
</template>

<style scoped>
.layout { display: flex; height: 100dvh; overflow: hidden; }
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }
.route-content { flex: 1; min-height: 0; overflow: auto; }
.shell-toolbar { display: flex; gap: var(--s-4); align-items: center; padding: var(--s-2) var(--s-4); border-bottom: 1px solid var(--border); background: var(--surface); }
.back-link { display: inline-flex; align-items: center; gap: var(--s-2); color: var(--muted); text-decoration: none; font-size: var(--fs-sm); padding: var(--s-1) var(--s-2); border-radius: var(--r-sm); transition: color var(--ease), background var(--ease); }
.back-link:hover { color: var(--ink); background: var(--surface-3); }
.load-error { color: var(--danger-ink); background: var(--danger-soft); border-bottom: 1px solid var(--danger-line); padding: var(--s-3) var(--s-4); margin: 0; font-size: var(--fs-sm); }
@media (max-width: 760px) { .layout { flex-direction: column; } .layout > :deep(.sidebar) { width: 100% !important; max-height: 36dvh; flex-shrink: 0; } }
</style>
