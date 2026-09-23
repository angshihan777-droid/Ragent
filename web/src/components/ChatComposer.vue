<script setup>
import Icon from "./Icon.vue";
const text = defineModel({ type: String, default: "" });
defineProps({ busy: Boolean, disabled: Boolean, projectName: String });
const emit = defineEmits(["send", "stop"]);
function onEnter(event) {
  if (!event.shiftKey && !event.isComposing) { event.preventDefault(); emit("send"); }
}
</script>
<template>
  <div class="composer-area">
    <form class="composer" @submit.prevent="$emit('send')">
      <textarea v-model="text" aria-label="输入问题" rows="2" :disabled="disabled" placeholder="向知识库提问，让每个答案都有依据…" @keydown.enter="onEnter" />
      <div class="composer-bottom">
        <RouterLink to="/documents" class="scope" title="管理当前项目资料">
          <Icon name="files" :size="14" /><span class="truncate">{{ projectName || '项目资料' }}</span>
        </RouterLink>
        <button v-if="busy" class="send stop" type="button" aria-label="停止生成" @click="$emit('stop')">
          <Icon name="stop" :size="13" />
        </button>
        <button v-else class="send btn-brand" type="submit" :disabled="disabled || !text.trim()" aria-label="发送问题">
          <Icon name="arrow-up" :size="17" />
        </button>
      </div>
    </form>
    <p class="hint">按 Enter 发送 · Shift + Enter 换行 · 回答请结合原文核对</p>
  </div>
</template>
<style scoped>
.composer-area { width: min(100%, 780px); margin: 0 auto; padding: var(--s-3) 0 0; }
.composer { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-xl); padding: var(--s-3); box-shadow: var(--shadow-sm); transition: border-color var(--ease), box-shadow var(--ease); }
.composer:focus-within { border-color: var(--brand); box-shadow: var(--ring); }
textarea { border: 0; background: transparent; padding: var(--s-1) var(--s-2); resize: none; min-height: 56px; max-height: 25dvh; font-size: var(--fs-body); line-height: 1.7; }
textarea:focus { box-shadow: none; }
.composer-bottom { display: flex; justify-content: space-between; align-items: center; gap: var(--s-3); margin-top: var(--s-1); }
.scope { display: inline-flex; align-items: center; gap: var(--s-2); font-size: var(--fs-xs); color: var(--muted); text-decoration: none; padding: 5px var(--s-2); border-radius: var(--r-sm); background: var(--surface-2); min-width: 0; max-width: 70%; transition: color var(--ease), background var(--ease); }
.scope:hover { color: var(--ink); background: var(--surface-3); }
.send { width: 32px; height: 32px; border-radius: var(--r-md); padding: 0; flex-shrink: 0; }
.stop { background: var(--n-700); }
.stop:hover:not(:disabled) { background: var(--n-800); }
.hint { text-align: center; color: var(--faint); font-size: var(--fs-xs); margin: var(--s-2) 0 0; }
</style>
