<script setup>
// 应用外壳：左侧持久化侧栏(项目/会话分区) + 右侧主面板(路由出口)。
// 决策：像 Codex 那样把「项目→会话」的导航常驻左侧，主面板只切内容，
// 用户在哪个项目/会话的上下文始终可见，不用来回跳页找。
import { onMounted } from "vue";
import { RouterView } from "vue-router";
import Sidebar from "./components/Sidebar.vue";
import { store } from "./store.js";

onMounted(async () => {
  await store.loadProjects();
  // 左栏要展示当前模型，进应用就读一次生效配置
  await store.loadLLM();
});
</script>

<template>
  <div class="layout">
    <Sidebar />
    <main class="main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}
.main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}
</style>
