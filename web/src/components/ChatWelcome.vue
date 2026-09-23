<script setup>
import Icon from "./Icon.vue";
defineProps({ projectName: String, available: Boolean, busy: Boolean, error: String });
defineEmits(["start"]);
</script>
<template>
  <section class="welcome">
    <div class="mark" aria-hidden="true">R</div>
    <h1>从资料出发，找到答案</h1>
    <p class="description">围绕项目提问、梳理信息、追溯依据。助手会按需检索，并把依据一并给出。</p>
    <div class="start-card">
      <div class="project-line">
        <span class="project-icon"><Icon name="folder" :size="17" /></span>
        <div class="pl-txt">
          <strong>{{ projectName || '还没有项目' }}</strong>
          <small>{{ available ? '当前项目 · 独立资料空间' : '从左侧创建项目，可同时上传资料' }}</small>
        </div>
      </div>
      <button class="btn-brand start-btn" :disabled="!available || busy" @click="$emit('start')">
        {{ busy ? '创建中…' : '开始新对话' }}<Icon name="arrow-up-right" :size="15" />
      </button>
    </div>
    <div class="welcome-links" v-if="available">
      <RouterLink to="/documents">
        <Icon name="files" :size="17" /><strong>管理项目资料</strong><small>PDF · Markdown · Word</small>
      </RouterLink>
      <RouterLink to="/library">
        <Icon name="library" :size="17" /><strong>浏览知识库</strong><small>查阅、编辑与删除资料</small>
      </RouterLink>
    </div>
    <p class="history-note">新对话从空白开始，历史会话仅在左侧手动打开。</p>
    <p v-if="error" class="error-box" role="alert">{{ error }}</p>
  </section>
</template>
<style scoped>
.welcome { width: min(560px, 100%); margin: auto; padding: var(--s-6) var(--s-5); text-align: center; }
.mark { margin: 0 auto var(--s-4); width: 48px; height: 48px; background: var(--brand); color: #fff; border-radius: var(--r-lg); font-size: 22px; font-weight: 600; display: grid; place-content: center; }
h1 { font-size: var(--fs-display); margin-bottom: var(--s-3); }
.description { font-size: var(--fs-sm); line-height: 1.8; color: var(--muted); margin: 0 auto var(--s-5); max-width: 42ch; }

.start-card { border: 1px solid var(--border); border-radius: var(--r-lg); padding: var(--s-4); background: var(--surface); text-align: left; }
.project-line { display: flex; align-items: center; gap: var(--s-3); margin-bottom: var(--s-4); }
.project-icon { display: grid; place-items: center; width: 38px; height: 38px; background: var(--surface-2); border-radius: var(--r-md); color: var(--brand); flex-shrink: 0; }
.pl-txt { min-width: 0; }
strong { display: block; font-size: var(--fs-body); font-weight: 500; color: var(--ink); overflow-wrap: anywhere; }
small { display: block; color: var(--muted); font-size: var(--fs-xs); margin-top: 2px; }
.start-btn { width: 100%; font-size: var(--fs-sm); }

.welcome-links { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-2); margin-top: var(--s-2); text-align: left; }
.welcome-links a { display: block; color: var(--text); text-decoration: none; border: 1px solid var(--border); padding: var(--s-3); border-radius: var(--r-md); background: var(--surface); transition: border-color var(--ease), background var(--ease); }
.welcome-links a:hover { border-color: var(--brand-line); background: var(--brand-soft); }
.welcome-links a > svg { color: var(--brand); margin-bottom: var(--s-2); }
.welcome-links strong { font-size: var(--fs-sm); }

.history-note { color: var(--faint); font-size: var(--fs-xs); margin-top: var(--s-5); }
.error-box { margin-top: var(--s-3); text-align: left; }
@media (max-width: 500px) { .welcome { padding: var(--s-5) var(--s-3); } .welcome-links { grid-template-columns: 1fr; } }
</style>
