// 四个独立功能页：对话、资料、图书馆与模型配置。
// 对话页是首屏，直接静态引入；其余三页懒加载，减小首屏包体。
import { createRouter, createWebHashHistory } from "vue-router";
import ChatPage from "./pages/ChatPage.vue";

const routes = [
  { path: "/", redirect: "/chat" },
  { path: "/chat", component: ChatPage },
  { path: "/documents", component: () => import("./pages/DocumentPage.vue") },
  { path: "/library", component: () => import("./pages/LibraryPage.vue") },
  { path: "/config", component: () => import("./pages/ConfigPage.vue") },
];

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
});
