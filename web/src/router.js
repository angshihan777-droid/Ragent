// 三页切换用 vue-router。
// 面试理由：三个独立功能页，路由比手写条件渲染清晰，也是前端通用做法。
import { createRouter, createWebHashHistory } from "vue-router";
import ChatPage from "./pages/ChatPage.vue";
import DocumentPage from "./pages/DocumentPage.vue";
import ConfigPage from "./pages/ConfigPage.vue";
import LibraryPage from "./pages/LibraryPage.vue";

const routes = [
  { path: "/", redirect: "/chat" },
  { path: "/chat", component: ChatPage },
  { path: "/documents", component: DocumentPage },
  { path: "/library", component: LibraryPage },
  { path: "/config", component: ConfigPage },
];

export const router = createRouter({
  // 用 hash 模式：纯静态托管也能刷新不 404，dev 阶段最省心
  history: createWebHashHistory(),
  routes,
});
