<script setup>
const text = defineModel({ type: String, default: "" });
defineProps({ busy: Boolean, disabled: Boolean, projectName: String });
const emit = defineEmits(["send"]);
function onEnter(event) {
  if (!event.shiftKey && !event.isComposing) { event.preventDefault(); emit("send"); }
}
</script>
<template>
  <div class="composer-area">
    <form class="composer" @submit.prevent="$emit('send')">
      <textarea v-model="text" aria-label="输入问题" rows="2" :disabled="disabled" placeholder="向知识库提问，让每个答案都有依据…" @keydown.enter="onEnter" />
      <div class="composer-bottom">
        <RouterLink to="/documents" class="scope" title="管理当前项目资料">▧ {{ projectName || '项目资料' }}</RouterLink>
        <button class="send" type="submit" :disabled="busy || disabled || !text.trim()" :aria-label="busy ? '正在回答' : '发送问题'">{{ busy ? '···' : '↑' }}</button>
      </div>
    </form>
    <p class="hint">按 Enter 发送 · Shift + Enter 换行 · 回答请结合原文核对</p>
  </div>
</template>
<style scoped>
.composer-area { width: min(100%, 820px); margin: 0 auto; padding: 12px 0 0; }
.composer { background: #fff; border: 1px solid var(--border); border-radius: 18px; padding: 12px 14px; box-shadow: 0 4px 24px #162d2010; }
.composer:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
textarea { border: 0; background: transparent; padding: 7px 4px; resize: none; min-height: 64px; max-height: 25dvh; font-size: 14px; line-height: 1.7; }
textarea:focus { box-shadow: none; }
.composer-bottom { display: flex; justify-content: space-between; align-items: center; }
.scope { font-size: 12px; color: var(--muted); text-decoration: none; padding: 5px 9px; border-radius: 6px; background: var(--panel2); max-width: 80%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.send { width: 34px; height: 34px; border-radius: 10px; padding: 0; font-size: 23px; }
.hint { text-align: center; color: var(--faint); font-size: 11px; margin: 10px 0 2px; }
</style>
