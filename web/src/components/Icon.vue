<script setup>
// 统一图标系统：内联 Lucide 风格线性 path，替换原先混用的几何字符。
// 决策：不引图标库依赖，只挑用到的十几个 path 内联；stroke-width 统一 1.6，
// 视觉重量一致，跨系统渲染也不会像 ▧ ▦ 那样字形漂移。
defineProps({ name: { type: String, required: true }, size: { type: [Number, String], default: 16 } });
const P = {
  plus: "M12 5v14M5 12h14",
  "message-plus": "M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5zM12 8v6M9 11h6",
  sparkles: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3zM18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8L18 16z",
  files: "M15 2H8a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V6l-4-4zM15 2v4h4M5 7a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h9",
  library: "M4 3h4v18H4zM10 3h4v18h-4zM17.5 3.2l3.3 17.3-3.9.8L13.6 4z",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1.08-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1.08 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z",
  folder: "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z",
  "chevron-down": "M6 9l6 6 6-6",
  "chevron-right": "M9 18l6-6-6-6",
  "chevron-left": "M15 18l-6-6 6-6",
  "panel-left": "M3 3h18v18H3zM9 3v18",
  x: "M18 6L6 18M6 6l12 12",
  "arrow-up": "M12 19V5M5 12l7-7 7 7",
  "arrow-down": "M12 5v14M19 12l-7 7-7-7",
  "arrow-left": "M19 12H5M12 19l-7-7 7-7",
  "arrow-up-right": "M7 17L17 7M7 7h10v10",
  check: "M20 6L9 17l-5-5",
  square: "M5 12h14",
  alert: "M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.35-4.35",
  eye: "M2 12s3.64-7 10-7 10 7 10 7-3.64 7-10 7-10-7-10-7zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  pencil: "M17 3a2.83 2.83 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5z",
  trash: "M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  "file-plus": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M12 18v-6M9 15h6",
  refresh: "M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15",
  stop: "M6 6h12v12H6z",
  square_dot: "M12 12h.01",
  book: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z",
};
</script>

<template>
  <svg
    :width="size" :height="size" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"
    aria-hidden="true" focusable="false" class="icon"
  >
    <path :d="P[name] || P.square_dot" />
  </svg>
</template>

<style scoped>
.icon { flex-shrink: 0; display: block; }
</style>
