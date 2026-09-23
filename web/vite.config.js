import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 决策：前端一律走同源 /api，由 dev server 代理到后端。
// 面试理由：源码里不出现任何环境相关的绝对地址，构建产物可直接部署到任意域名；
// 需要指向别的后端时只改 VITE_PROXY_TARGET，不动代码。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
