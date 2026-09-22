// 五个独立功能页：介绍、对话、资料、图书馆与模型配置。
import { createRouter, createWebHashHistory } from "vue-router";
import ChatPage from "./pages/ChatPage.vue";
import IntroPage from "./pages/IntroPage.vue";
import DocumentPage from "./pages/DocumentPage.vue";
import ConfigPage from "./pages/ConfigPage.vue";
import LibraryPage from "./pages/LibraryPage.vue";

const routes = [
  { path: "/", redirect: "/chat" },
  { path: "/chat", component: ChatPage },
  { path: "/intro", component: IntroPage },
  { path: "/documents", component: DocumentPage },
  { path: "/library", component: LibraryPage },
  { path: "/config", component: ConfigPage },
];

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
});
