<script setup>
defineProps({ projectName: String, available: Boolean, busy: Boolean, error: String });
defineEmits(["start"]);
</script>
<template>
  <section class="welcome">
    <div class="mark" aria-hidden="true">R<span>✦</span></div>
    <p class="eyebrow">你的项目知识工作台</p>
    <h1>从资料出发，找到答案</h1>
    <p class="description">围绕项目提问、梳理信息、追溯依据。<br>知识库助手会按需检索，资料与会话始终归属于你的项目。</p>
    <div class="start-card">
      <div class="project-line"><span class="project-icon">▧</span><div><strong>{{ projectName || '还没有项目' }}</strong><small>{{ available ? '当前项目 · 独立资料空间' : '从左侧创建项目，可同时上传资料' }}</small></div></div>
      <button :disabled="!available || busy" @click="$emit('start')">{{ busy ? '创建中…' : '开始新对话' }} <span aria-hidden="true">↗</span></button>
    </div>
    <div class="welcome-links" v-if="available">
      <RouterLink to="/documents"><span>▤</span><strong>管理项目资料</strong><small>PDF · Markdown · Word</small></RouterLink>
      <RouterLink to="/library"><span>▦</span><strong>浏览知识库</strong><small>查阅、编辑与删除资料</small></RouterLink>
    </div>
    <p class="history-note">新对话从空白开始，历史会话仅在左侧手动打开。</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </section>
</template>
<style scoped>
.welcome { width: min(650px, 100%); margin: auto; padding: 40px 28px; text-align: center; }
.mark { margin: 0 auto 22px; width: 62px; height: 62px; background: var(--accent-soft); color: var(--accent-d); border-radius: 19px; font-size: 36px; font-weight: 650; display: grid; place-content: center; position: relative; }
.mark span { position: absolute; right: -8px; top: -9px; font-size: 26px; }
.eyebrow { color: var(--accent-d); font-size: 12px; letter-spacing: 2px; }
h1 { font-size: clamp(25px, 3vw, 34px); font-weight: 600; letter-spacing: -1px; color: var(--ink); margin: 12px 0; }
.description { font-size: 14px; line-height: 1.9; color: var(--muted); margin-bottom: 30px; }
.start-card { border: 1px solid var(--border); border-radius: 16px; padding: 20px; background: white; text-align: left; box-shadow: var(--shadow-sm); }
.project-line { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }.project-icon { background: var(--panel2); padding: 9px 13px; border-radius: 9px; color: var(--accent); font-size: 22px; }
strong { font-size: 15px; font-weight: 650; overflow-wrap: anywhere; }small { display: block; color: var(--muted); font-size: 12px; margin-top: 5px; }button { width: 100%; font-size: 14px; }button span { float: right; }
.welcome-links { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 14px; text-align: left; }.welcome-links a { color: var(--text); text-decoration: none; border: 1px solid var(--line); padding: 16px; border-radius: 12px; }.welcome-links a:hover { border-color: var(--accent); background: var(--accent-soft); }.welcome-links span { float: right; color: var(--accent); }
.history-note { color: var(--faint); font-size: 11px; margin-top: 24px; }.error { color: #a33d32; }
@media (max-width: 500px) { .welcome { padding: 24px 16px; }.welcome-links { grid-template-columns: 1fr; } }
</style>
