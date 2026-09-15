import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 决策：不配后端代理，直连 http://localhost:8000（后端已开 CORS）。
// 面试理由：最小配置，少一层代理转发，联调更直观。
export default defineConfig({
  plugins: [vue()],
  server: { port: 5173 },
});
